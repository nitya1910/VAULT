import os
import uuid
import asyncio
import logging
import httpx
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

METADATA_URL = os.getenv("METADATA_URL", "http://metadata-1:8000")
WRITE_QUORUM = 2
READ_QUORUM = 2

async def replicate_chunk_to_node(client: httpx.AsyncClient, node_id: str, node_url: str, object_id: str, chunk_id: str, data: bytes):
    url = f"{node_url}/chunks/{object_id}/{chunk_id}"
    try:
        response = await client.post(url, content=data, timeout=5.0)
        response.raise_for_status()
        return {"node_id": node_id, "url": node_url, "chunk_id": chunk_id, "checksum": response.json().get("checksum")}
    except Exception as e:
        logger.error(f"Failed to replicate chunk to {node_id} ({node_url}): {e}")
        return None

async def upload_object(request):
    object_key = request.path_params['object_key']
    object_id = str(uuid.uuid4())
    data = await request.body()
    chunk_id = f"{object_id}-0"
    
    async with httpx.AsyncClient() as client:
        # 1. Ask metadata service for placement
        try:
            placement_res = await client.get(f"{METADATA_URL}/placement")
            placement_res.raise_for_status()
            nodes = placement_res.json()["nodes"]
        except Exception as e:
            return JSONResponse({"error": f"Failed to reach metadata service: {e}"}, status_code=500)
            
        if len(nodes) < WRITE_QUORUM:
            return JSONResponse({"error": "Not enough healthy storage nodes for quorum"}, status_code=503)
            
        # 2. Replicate concurrently
        tasks = []
        for node in nodes:
            tasks.append(replicate_chunk_to_node(client, node["node_id"], node["url"], object_id, chunk_id, data))
            
        results = await asyncio.gather(*tasks)
        
        success_replicas = [r for r in results if r is not None]
                    
        if len(success_replicas) < WRITE_QUORUM:
            return JSONResponse({"error": "Failed to achieve write quorum"}, status_code=503)
            
        chunk_checksum = success_replicas[0]["checksum"]
        version_id = str(uuid.uuid4())
        
        # 3. Commit to metadata
        try:
            commit_payload = {
                "object_key": object_key,
                "object_id": object_id,
                "version_id": version_id,
                "checksum": chunk_checksum,
                "size": len(data),
                "replicas": success_replicas
            }
            commit_res = await client.post(f"{METADATA_URL}/metadata/commit", json=commit_payload)
            commit_res.raise_for_status()
        except Exception as e:
            logger.error(f"Metadata commit failed: {e}")
            return JSONResponse({"error": "Failed to commit object metadata"}, status_code=500)
        
    return JSONResponse({
        "status": "success",
        "object_id": object_id,
        "object_key": object_key,
        "version_id": version_id,
        "checksum": chunk_checksum,
        "replicas_written": len(success_replicas)
    })

async def read_chunk_from_node(client: httpx.AsyncClient, node_url: str, object_id: str, chunk_id: str, expected_checksum: str):
    url = f"{node_url}/chunks/{object_id}/{chunk_id}?expected_checksum={expected_checksum}"
    try:
        response = await client.get(url, timeout=5.0)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        logger.error(f"Failed to read from {node_url}: {e}")
    return None

async def get_object(request):
    object_key = request.path_params['object_key']
    
    async with httpx.AsyncClient() as client:
        # 1. Fetch metadata
        try:
            meta_res = await client.get(f"{METADATA_URL}/metadata/{object_key}")
            if meta_res.status_code == 404:
                return JSONResponse({"error": "Object not found"}, status_code=404)
            meta_res.raise_for_status()
            metadata = meta_res.json()
        except Exception as e:
            return JSONResponse({"error": f"Failed to fetch metadata: {e}"}, status_code=500)
            
        object_id = metadata["object_id"]
        checksum = metadata["checksum"]
        replicas = metadata.get("replicas", [])
        
        if not replicas:
            return JSONResponse({"error": "No healthy replicas found for object"}, status_code=404)
            
        # 2. Try fetching from replicas until one succeeds
        for rep in replicas:
            data = await read_chunk_from_node(client, rep["url"], object_id, rep["chunk_id"], checksum)
            if data is not None:
                return Response(content=data, media_type="application/octet-stream")
                
    return JSONResponse({"error": "Failed to read from all replicas (Data unavailable or corrupted)"}, status_code=503)

routes = [
    Route('/objects/{object_key}', upload_object, methods=['PUT']),
    Route('/objects/{object_key}', get_object, methods=['GET']),
]

app = Starlette(debug=True, routes=routes)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
