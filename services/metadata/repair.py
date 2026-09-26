import asyncio
import logging
import httpx
from vault.services.metadata.engine import MetadataEngine

logger = logging.getLogger(__name__)

REPLICATION_FACTOR = 3

class RepairLoop:
    def __init__(self, engine: MetadataEngine, interval_seconds: int = 10):
        self.engine = engine
        self.interval_seconds = interval_seconds
        self._running = False

    async def start(self):
        self._running = True
        while self._running:
            try:
                await self._run_repair_cycle()
            except Exception as e:
                logger.error(f"Error in repair cycle: {e}")
            await asyncio.sleep(self.interval_seconds)

    def stop(self):
        self._running = False

    async def _run_repair_cycle(self):
        logger.info("Running background repair cycle...")
        # 1. Identify healthy nodes
        nodes = await self.engine.get_healthy_nodes()
        if len(nodes) < REPLICATION_FACTOR:
            logger.warning(f"Not enough healthy nodes for full repair. Have {len(nodes)}, need {REPLICATION_FACTOR}.")
            # We can still repair up to the number of available nodes.

        healthy_node_ids = {n['node_id'] for n in nodes}
        node_url_map = {n['node_id']: n['url'] for n in nodes}
        
        # 2. Find chunks that are under-replicated
        async with httpx.AsyncClient() as client:
            import aiosqlite
            async with aiosqlite.connect(self.engine.db_path) as db:
                # Find all chunk IDs
                async with db.execute("SELECT chunk_id, object_id, checksum FROM chunks") as cursor:
                    chunks = await cursor.fetchall()

                for chunk in chunks:
                    chunk_id, object_id, expected_checksum = chunk
                    
                    # Get current healthy replicas for this chunk
                    async with db.execute('''
                        SELECT node_id FROM chunk_replicas 
                        WHERE chunk_id=? AND status='healthy'
                    ''', (chunk_id,)) as rep_cursor:
                        replicas = [row[0] async for row in rep_cursor]

                    # Filter replicas to those that are actually on currently healthy nodes
                    active_replicas = [r for r in replicas if r in healthy_node_ids]
                    
                    if len(active_replicas) < min(REPLICATION_FACTOR, len(nodes)):
                        logger.info(f"Chunk {chunk_id} is under-replicated ({len(active_replicas)}/{REPLICATION_FACTOR}). Initiating repair.")
                        
                        if not active_replicas:
                            logger.error(f"Chunk {chunk_id} has NO healthy replicas. Data loss!")
                            continue
                            
                        # Find a target node that doesn't have this chunk
                        target_node_id = None
                        for n_id in healthy_node_ids:
                            if n_id not in active_replicas:
                                target_node_id = n_id
                                break
                                
                        if not target_node_id:
                            continue # No node available to take it
                            
                        source_node_id = active_replicas[0]
                        source_url = node_url_map[source_node_id]
                        target_url = node_url_map[target_node_id]
                        
                        # Initiate repair: read from source, write to target
                        logger.info(f"Repairing {chunk_id} from {source_node_id} to {target_node_id}")
                        try:
                            # 1. Read
                            read_url = f"{source_url}/chunks/{object_id}/{chunk_id}?expected_checksum={expected_checksum}"
                            res = await client.get(read_url, timeout=10.0)
                            res.raise_for_status()
                            data = res.content
                            
                            # 2. Write
                            write_url = f"{target_url}/chunks/{object_id}/{chunk_id}"
                            w_res = await client.post(write_url, content=data, timeout=10.0)
                            w_res.raise_for_status()
                            
                            # 3. Update metadata
                            await self.engine.commit_chunk_replica(object_id, chunk_id, 0, target_node_id, expected_checksum)
                            logger.info(f"Successfully repaired {chunk_id} on {target_node_id}")
                            
                        except Exception as e:
                            logger.error(f"Repair failed for {chunk_id}: {e}")
