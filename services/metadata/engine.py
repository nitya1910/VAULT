import aiosqlite
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class MetadataEngine:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS objects (
                    object_key TEXT PRIMARY KEY,
                    object_id TEXT UNIQUE NOT NULL,
                    version_id TEXT NOT NULL,
                    size INTEGER DEFAULT 0,
                    checksum TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    object_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    size INTEGER DEFAULT 0,
                    checksum TEXT,
                    FOREIGN KEY(object_id) REFERENCES objects(object_id) ON DELETE CASCADE
                )
            ''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS chunk_replicas (
                    chunk_id TEXT,
                    node_id TEXT,
                    status TEXT DEFAULT 'healthy',
                    PRIMARY KEY (chunk_id, node_id),
                    FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    status TEXT DEFAULT 'healthy',
                    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await db.commit()

    async def register_node(self, node_id: str, url: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO nodes (node_id, url, status, last_heartbeat)
                VALUES (?, ?, 'healthy', CURRENT_TIMESTAMP)
                ON CONFLICT(node_id) DO UPDATE SET 
                    url=excluded.url,
                    status='healthy',
                    last_heartbeat=CURRENT_TIMESTAMP
            ''', (node_id, url))
            await db.commit()

    async def get_healthy_nodes(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT node_id, url FROM nodes WHERE status='healthy'") as cursor:
                return [{"node_id": row[0], "url": row[1]} async for row in cursor]

    async def commit_object(self, object_key: str, object_id: str, version_id: str, checksum: str, size: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO objects (object_key, object_id, version_id, checksum, size)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(object_key) DO UPDATE SET
                    object_id=excluded.object_id,
                    version_id=excluded.version_id,
                    checksum=excluded.checksum,
                    size=excluded.size
            ''', (object_key, object_id, version_id, checksum, size))
            await db.commit()

    async def commit_chunk_replica(self, object_id: str, chunk_id: str, chunk_index: int, node_id: str, checksum: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR IGNORE INTO chunks (chunk_id, object_id, chunk_index, checksum)
                VALUES (?, ?, ?, ?)
            ''', (chunk_id, object_id, chunk_index, checksum))
            
            await db.execute('''
                INSERT OR REPLACE INTO chunk_replicas (chunk_id, node_id, status)
                VALUES (?, ?, 'healthy')
            ''', (chunk_id, node_id))
            await db.commit()

    async def get_object_metadata(self, object_key: str):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT object_id, version_id, checksum FROM objects WHERE object_key=?", (object_key,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                
                object_id = row[0]
                
                # Fetch replicas
                async with db.execute('''
                    SELECT r.chunk_id, r.node_id, n.url 
                    FROM chunk_replicas r
                    JOIN nodes n ON r.node_id = n.node_id
                    WHERE r.chunk_id LIKE ? AND r.status='healthy' AND n.status='healthy'
                ''', (f"{object_id}-%",)) as rep_cursor:
                    replicas = [{"chunk_id": r[0], "node_id": r[1], "url": r[2]} async for r in rep_cursor]

                return {
                    "object_key": object_key,
                    "object_id": object_id,
                    "version_id": row[1],
                    "checksum": row[2],
                    "replicas": replicas
                }
