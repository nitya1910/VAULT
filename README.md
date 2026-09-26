# Vault: Fault-Tolerant Distributed Object Storage

Vault is a lightweight, self-healing, distributed object storage system designed for fault tolerance and high availability.

Built for a Hackathon, Vault demonstrates core distributed systems concepts:
* **Quorum Reads/Writes (N=3, W=2, R=2)**
* **Leader-Follower Metadata Consistency**
* **Background Self-Healing (Anti-entropy repair loop)**
* **Data Integrity Checks (SHA-256)**

## Architecture
The cluster consists of three main components:
1. **API Gateway** (`api-gateway:8080`): Accepts user requests, negotiates with the metadata service, and orchestrates quorum writes/reads to the storage nodes.
2. **Metadata Service** (`metadata-1:8000`): The control plane (Leader). Tracks object chunk locations and node health using SQLite. Runs a background repair loop.
3. **Storage Nodes** (`storage-1`, `storage-2`, `storage-3`): The data plane. Simple atomic file writers that verify SHA-256 checksums.

## Quick Start (Docker)
The easiest way to run the entire cluster is via Docker Compose:

```bash
docker compose up --build
```

## Hackathon Demo Steps
1. **Upload an Object:**
```bash
curl -X PUT http://localhost:8080/objects/my-file -d "Hello Vault Distributed Storage!"
```

2. **Retrieve the Object:**
```bash
curl http://localhost:8080/objects/my-file
```

3. **Demonstrate Fault Tolerance:**
Kill a storage node to simulate a hardware failure:
```bash
docker compose stop storage-1
```
Try retrieving the file again. It will still succeed because of the R=2 Quorum!

4. **Demonstrate Self-Healing:**
Upload a *new* file while `storage-1` is down. It writes to `storage-2` and `storage-3` (W=2 success).
Then, bring `storage-1` back online:
```bash
docker compose start storage-1
```
Watch the logs of `metadata-1`. Within 10 seconds, the background repair loop will detect that the file is under-replicated and automatically copy it to `storage-1`.

## Local Development (Python)
Requirements: Python 3.11+
```bash
pip install -r requirements.txt
pytest vault/tests/unit
```
