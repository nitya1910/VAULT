import os
import uuid
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from vault.services.storage.engine import StorageEngine

DATA_DIR = os.getenv("DATA_DIR", "/data")
engine = StorageEngine(DATA_DIR)

async def upload_chunk(request):
    object_id = request.path_params['object_id']
    chunk_id = request.path_params['chunk_id']
    
    data = await request.body()
    try:
        checksum = await engine.put_chunk(object_id, chunk_id, data)
        return JSONResponse({
            "object_id": object_id,
            "chunk_id": chunk_id,
            "checksum": checksum,
            "status": "success"
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_chunk(request):
    object_id = request.path_params['object_id']
    chunk_id = request.path_params['chunk_id']
    expected_checksum = request.query_params.get("expected_checksum")
    
    try:
        data = await engine.get_chunk(object_id, chunk_id, expected_checksum)
        return Response(content=data, media_type="application/octet-stream")
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def delete_object(request):
    object_id = request.path_params['object_id']
    try:
        await engine.delete_object(object_id)
        return JSONResponse({"status": "success", "object_id": object_id})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def health_check(request):
    return JSONResponse(engine.check_health())

routes = [
    Route('/chunks/{object_id}/{chunk_id}', upload_chunk, methods=['POST']),
    Route('/chunks/{object_id}/{chunk_id}', get_chunk, methods=['GET']),
    Route('/objects/{object_id}', delete_object, methods=['DELETE']),
    Route('/health', health_check, methods=['GET']),
]

app = Starlette(debug=True, routes=routes)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 9000))
    uvicorn.run(app, host="0.0.0.0", port=port)
