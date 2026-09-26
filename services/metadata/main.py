import os
import logging
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from vault.services.metadata.engine import MetadataEngine
from vault.services.metadata.repair import RepairLoop
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("METADATA_DB_PATH", "/tmp/vault_metadata.db")
engine = MetadataEngine(DB_PATH)
repair_loop = RepairLoop(engine, interval_seconds=10)

async def startup():
    await engine.init_db()
    
    # Pre-register local cluster nodes for the hackathon demo if they don't exist yet
    if os.getenv("IS_LEADER") == "true":
        await engine.register_node("storage-1", "http://storage-1:9000")
        await engine.register_node("storage-2", "http://storage-2:9000")
        await engine.register_node("storage-3", "http://storage-3:9000")
        
        # Start repair loop in background
        asyncio.create_task(repair_loop.start())

async def shutdown():
    repair_loop.stop()

async def get_placement(request):
    nodes = await engine.get_healthy_nodes()
    # Simple strategy: just return all healthy nodes (up to RF). 
    # For Phase 4, we assume we just return 3 healthy nodes.
    # A real placement engine would check rack/zone constraints.
    return JSONResponse({"nodes": nodes[:3]})

async def commit_object(request):
    data = await request.json()
    try:
        await engine.commit_object(
            data['object_key'], 
            data['object_id'], 
            data['version_id'], 
            data['checksum'], 
            data.get('size', 0)
        )
        
        for rep in data.get('replicas', []):
            await engine.commit_chunk_replica(
                data['object_id'],
                rep['chunk_id'],
                0, # Only 1 chunk in MVP
                rep['node_id'],
                data['checksum']
            )
            
        return JSONResponse({"status": "success"})
    except Exception as e:
        logger.error(f"Failed to commit object metadata: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_metadata(request):
    object_key = request.path_params['object_key']
    metadata = await engine.get_object_metadata(object_key)
    if not metadata:
        return JSONResponse({"error": "Object not found"}, status_code=404)
    return JSONResponse(metadata)

async def node_heartbeat(request):
    data = await request.json()
    await engine.register_node(data['node_id'], data['url'])
    return JSONResponse({"status": "ok"})

routes = [
    Route('/placement', get_placement, methods=['GET']),
    Route('/metadata/commit', commit_object, methods=['POST']),
    Route('/metadata/{object_key}', get_metadata, methods=['GET']),
    Route('/nodes/heartbeat', node_heartbeat, methods=['POST']),
]

app = Starlette(debug=True, routes=routes, on_startup=[startup], on_shutdown=[shutdown])

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
