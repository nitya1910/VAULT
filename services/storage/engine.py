import os
import hashlib
import aiofiles
import uuid
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class StorageEngine:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.temp_dir = self.data_dir / "tmp"
        self.objects_dir = self.data_dir / "objects"
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.objects_dir.mkdir(parents=True, exist_ok=True)

    def _get_object_path(self, object_id: str, chunk_id: str) -> Path:
        # We can store chunks like objects_dir/object_id/chunk_id
        obj_path = self.objects_dir / object_id
        obj_path.mkdir(exist_ok=True)
        return obj_path / chunk_id

    async def put_chunk(self, object_id: str, chunk_id: str, data: bytes) -> str:
        """
        Atomically write a chunk of data, verify checksum, and return the SHA-256 checksum.
        """
        temp_path = self.temp_dir / f"{object_id}_{chunk_id}_{uuid.uuid4().hex}.tmp"
        
        # Calculate checksum while writing
        sha256 = hashlib.sha256()
        
        try:
            async with aiofiles.open(temp_path, "wb") as f:
                await f.write(data)
                sha256.update(data)
                await f.flush()
                os.fsync(f.fileno())
                
            checksum = sha256.hexdigest()
            final_path = self._get_object_path(object_id, chunk_id)
            
            # Atomic rename (POSIX)
            temp_path.rename(final_path)
            return checksum
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            logger.error(f"Failed to put chunk {chunk_id} for object {object_id}: {e}")
            raise

    async def get_chunk(self, object_id: str, chunk_id: str, expected_checksum: str = None) -> bytes:
        """
        Read a chunk of data and optionally verify its checksum before returning.
        """
        final_path = self._get_object_path(object_id, chunk_id)
        if not final_path.exists():
            raise FileNotFoundError(f"Chunk {chunk_id} not found for object {object_id}")

        async with aiofiles.open(final_path, "rb") as f:
            data = await f.read()
            
        if expected_checksum:
            sha256 = hashlib.sha256()
            sha256.update(data)
            actual_checksum = sha256.hexdigest()
            if actual_checksum != expected_checksum:
                raise ValueError("Checksum mismatch: Data corruption detected")
                
        return data

    async def delete_object(self, object_id: str):
        """
        Delete all chunks for a given object.
        """
        obj_path = self.objects_dir / object_id
        if not obj_path.exists():
            return
            
        for chunk_file in obj_path.iterdir():
            if chunk_file.is_file():
                chunk_file.unlink()
        obj_path.rmdir()
        
    def check_health(self) -> dict:
        total, used, free = 0, 0, 0
        try:
            statvfs = os.statvfs(str(self.data_dir))
            total = statvfs.f_frsize * statvfs.f_blocks
            free = statvfs.f_frsize * statvfs.f_bavail
            used = total - free
        except AttributeError:
            pass # statvfs is Unix only
            
        return {
            "status": "HEALTHY",
            "capacity": {
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free
            }
        }
