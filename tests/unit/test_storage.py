import pytest
import os
import shutil
import hashlib
from vault.services.storage.engine import StorageEngine

@pytest.fixture
def storage_dir(tmp_path):
    data_dir = tmp_path / "data"
    yield str(data_dir)
    if data_dir.exists():
        shutil.rmtree(data_dir)

@pytest.mark.asyncio
async def test_put_and_get_chunk(storage_dir):
    engine = StorageEngine(storage_dir)
    
    obj_id = "test-obj-1"
    chunk_id = "chunk-1"
    data = b"Hello Vault!"
    
    # PUT
    checksum = await engine.put_chunk(obj_id, chunk_id, data)
    
    expected_checksum = hashlib.sha256(data).hexdigest()
    assert checksum == expected_checksum
    
    # GET
    retrieved_data = await engine.get_chunk(obj_id, chunk_id, expected_checksum=checksum)
    assert retrieved_data == data

@pytest.mark.asyncio
async def test_get_chunk_corrupted(storage_dir):
    engine = StorageEngine(storage_dir)
    
    obj_id = "test-obj-2"
    chunk_id = "chunk-1"
    data = b"Original data"
    
    checksum = await engine.put_chunk(obj_id, chunk_id, data)
    
    # Manually corrupt the file
    chunk_path = engine._get_object_path(obj_id, chunk_id)
    with open(chunk_path, "wb") as f:
        f.write(b"Corrupted data")
        
    # GET should fail checksum verification
    with pytest.raises(ValueError, match="Checksum mismatch"):
        await engine.get_chunk(obj_id, chunk_id, expected_checksum=checksum)

@pytest.mark.asyncio
async def test_delete_object(storage_dir):
    engine = StorageEngine(storage_dir)
    
    obj_id = "test-obj-3"
    await engine.put_chunk(obj_id, "chunk-1", b"Data 1")
    await engine.put_chunk(obj_id, "chunk-2", b"Data 2")
    
    obj_path = engine.objects_dir / obj_id
    assert obj_path.exists()
    
    await engine.delete_object(obj_id)
    assert not obj_path.exists()
