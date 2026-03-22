# Local Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete Local Agent infrastructure: SQLite schema for on-prem storage, agent data upload endpoint for device metadata batches, and Docker containerization for on-prem deployment.

**Architecture:** 
- SQLite schema mirrors PostgreSQL LocalAgent + Device + Credential + raw configs (90-day retention)
- Upload endpoint accepts device metadata batches, upserts into cloud PostgreSQL
- Docker image uses python:3.11-slim with network scanning tools (existing Dockerfile at docker/agent/Dockerfile)

**Tech Stack:** SQLite (aiosqlite), FastAPI, Docker, bcrypt, Pydantic

---

## Task 1: SQLite Schema for Local Agent

**Files:**
- Create: `services/agent/agent/db/schema.py` - SQLite schema definitions
- Create: `services/agent/agent/db/__init__.py` - DB module init
- Modify: `services/agent/agent/config.py` - Add SQLite config
- Test: `tests/agent/test_schema.py` - Schema tests

**Step 1: Create schema.py with SQLite tables**

```python
"""
Local Agent SQLite Schema
Mirrors cloud PostgreSQL minus ML vectors; holds raw configs for 90 days.
"""

import aiosqlite
from datetime import datetime, timedelta
from uuid import uuid4
import logging

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

CREATE_TABLES_SQL = """
-- Agents table (mirrors cloud LocalAgent)
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    site_id TEXT,
    name TEXT NOT NULL,
    api_key_hash TEXT NOT NULL,
    agent_version TEXT,
    last_seen TEXT,
    last_ip TEXT,
    is_active INTEGER DEFAULT 1,
    capabilities TEXT DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agents_org ON agents(organization_id);
CREATE INDEX IF NOT EXISTS idx_agents_site ON agents(site_id);
CREATE INDEX IF NOT EXISTS idx_agents_active ON agents(is_active);

-- Devices table (minimal device inventory)
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    hostname TEXT,
    ip_address TEXT,
    mac_address TEXT,
    device_type TEXT,
    vendor TEXT,
    model TEXT,
    os_version TEXT,
    site_id TEXT,
    discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT DEFAULT '{}',
    config_hash TEXT,
    raw_config TEXT,
    config_collected_at TEXT,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE INDEX IF NOT EXISTS idx_devices_agent ON devices(agent_id);
CREATE INDEX IF NOT EXISTS idx_devices_ip ON devices(ip_address);
CREATE INDEX IF NOT EXISTS idx_devices_hostname ON devices(hostname);
CREATE INDEX IF NOT EXISTS idx_devices_discovered ON devices(discovered_at);

-- Credentials table (encrypted; agent uses for device access)
CREATE TABLE IF NOT EXISTS credentials (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    name TEXT NOT NULL,
    credential_type TEXT NOT NULL,
    username_encrypted TEXT,
    password_encrypted TEXT,
    secret_encrypted TEXT,
    priority INTEGER DEFAULT 0,
    last_used TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE INDEX IF NOT EXISTS idx_credentials_agent ON credentials(agent_id);

-- Raw configs table (90-day retention)
CREATE TABLE IF NOT EXISTS raw_configs (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    config_text TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    collected_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (device_id) REFERENCES devices(id)
);

CREATE INDEX IF NOT EXISTS idx_raw_configs_device ON raw_configs(device_id);
CREATE INDEX IF NOT EXISTS idx_raw_configs_expires ON raw_configs(expires_at);

-- Discovery scans table
CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    scan_type TEXT NOT NULL,
    target_cidrs TEXT,
    status TEXT DEFAULT 'pending',
    started_at TEXT,
    completed_at TEXT,
    devices_found INTEGER DEFAULT 0,
    error_message TEXT,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE INDEX IF NOT EXISTS idx_scans_agent ON scans(agent_id);
CREATE INDEX IF NOT EXISTS idx_scans_status ON scans(status);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class LocalAgentDB:
    """SQLite database manager for local agent"""
    
    def __init__(self, db_path: str = "/app/data/agent.db"):
        self.db_path = db_path
    
    async def init_db(self) -> None:
        """Initialize database and create tables"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(CREATE_TABLES_SQL)
            await db.execute(
                "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,)
            )
            await db.commit()
        logger.info(f"Database initialized at {self.db_path}")
    
    async def get_agent(self, agent_id: str) -> dict | None:
        """Get agent by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM agents WHERE id = ?", (agent_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    async def upsert_device(self, device: dict) -> None:
        """Insert or update device"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO devices (id, agent_id, hostname, ip_address, mac_address, 
                    device_type, vendor, model, os_version, site_id, metadata, 
                    config_hash, raw_config, config_collected_at, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    hostname = excluded.hostname,
                    ip_address = excluded.ip_address,
                    mac_address = excluded.mac_address,
                    device_type = excluded.device_type,
                    vendor = excluded.vendor,
                    model = excluded.model,
                    os_version = excluded.os_version,
                    metadata = excluded.metadata,
                    config_hash = excluded.config_hash,
                    raw_config = excluded.raw_config,
                    config_collected_at = excluded.config_collected_at,
                    last_seen = CURRENT_TIMESTAMP
            """, (
                device.get('id', str(uuid4())),
                device['agent_id'],
                device.get('hostname'),
                device.get('ip_address'),
                device.get('mac_address'),
                device.get('device_type'),
                device.get('vendor'),
                device.get('model'),
                device.get('os_version'),
                device.get('site_id'),
                device.get('metadata', '{}'),
                device.get('config_hash'),
                device.get('raw_config'),
                device.get('config_collected_at'),
            ))
            await db.commit()
    
    async def cleanup_old_configs(self, retention_days: int = 90) -> int:
        """Delete raw configs older than retention period"""
        async with aiosqlite.connect(self.db_path) as db:
            cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()
            cursor = await db.execute(
                "DELETE FROM raw_configs WHERE expires_at < ?",
                (cutoff,)
            )
            await db.commit()
            return cursor.rowcount
    
    async def close(self) -> None:
        """Close database connection pool"""
        pass
```

**Step 2: Run test to verify schema module compiles**

Run: `python -c "from agent.db.schema import LocalAgentDB, CREATE_TABLES_SQL; print('OK')"`
Expected: OK (or import error if deps missing)

**Step 3: Create config update for SQLite path**

Modify: `services/agent/agent/config.py` - Add `db_path` field to `AgentConfig`

Add after existing fields:
```python
db_path: str = "/app/data/agent.db"  # SQLite database path
db_retention_days: int = 90  # Raw config retention
```

**Step 4: Commit**

```bash
git add services/agent/agent/db/ services/agent/agent/config.py
git commit -m "feat(agent): add SQLite schema for local agent storage"
```

---

## Task 2: Agent Data Upload Endpoint

**Files:**
- Modify: `services/api/app/api/routes.py` - Add POST /agents/{id}/upload
- Modify: `services/api/app/api/schemas.py` - Add upload schemas
- Test: `tests/api/test_agent_upload.py` - Upload endpoint tests

**Step 1: Add upload schemas**

Modify: `services/api/app/api/schemas.py` - Add after AgentResponse:

```python
class DeviceMetadataUpload(BaseModel):
    """Single device metadata for batch upload"""
    hostname: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    device_type: str | None = None
    vendor: str | None = None
    model: str | None = None
    os_version: str | None = None
    site_id: str | None = None
    metadata: dict[str, Any] = {}
    config_hash: str | None = None
    raw_config: str | None = None
    config_collected_at: datetime | None = None


class AgentUploadRequest(BaseModel):
    """Batch upload request from agent"""
    devices: list[DeviceMetadataUpload]
    scan_id: str | None = None


class AgentUploadResponse(BaseModel):
    """Upload response"""
    uploaded: int
    updated: int
    errors: list[str]
```

**Step 2: Add upload endpoint to routes.py**

Modify: `services/api/app/api/routes.py` - Add after heartbeat endpoint (~line 420):

```python
@router.post(
    "/agents/{agent_id}/upload",
    response_model=schemas.AgentUploadResponse,
    dependencies=[Depends(dependencies.get_agent_auth)],
)
async def upload_agent_data(
    agent_id: str,
    request: schemas.AgentUploadRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Upload device metadata batches from agent.
    
    Accepts device metadata collected by local agent.
    Creates/updates Device records in cloud PostgreSQL.
    """
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import Device
    
    try:
        agent_uuid = UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent_id format")
    
    uploaded = 0
    updated = 0
    errors = []
    
    for device_data in request.devices:
        try:
            # Check if device exists
            existing = None
            if device_data.ip_address:
                result = await db.execute(
                    select(Device).where(
                        Device.organization_id == UUID(request.state.agent_org_id),
                        Device.ip_address == device_data.ip_address
                    )
                )
                existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing device
                for field, value in {
                    "hostname": device_data.hostname,
                    "mac_address": device_data.mac_address,
                    "device_type": device_data.device_type,
                    "vendor": device_data.vendor,
                    "model": device_data.model,
                    "os_version": device_data.os_version,
                    "metadata": device_data.metadata,
                    "config_hash": device_data.config_hash,
                    "last_seen": func.now(),
                }.items():
                    if value is not None:
                        setattr(existing, field, value)
                updated += 1
            else:
                # Create new device
                new_device = Device(
                    id=uuid4(),
                    organization_id=UUID(request.state.agent_org_id),
                    site_id=UUID(device_data.site_id) if device_data.site_id else None,
                    hostname=device_data.hostname,
                    ip_address=device_data.ip_address,
                    mac_address=device_data.mac_address,
                    device_type=device_data.device_type,
                    vendor=device_data.vendor,
                    model=device_data.model,
                    os_version=device_data.os_version,
                    metadata=device_data.metadata,
                    config_hash=device_data.config_hash,
                    discovered_at=func.now(),
                    last_seen=func.now(),
                )
                db.add(new_device)
                uploaded += 1
            
        except Exception as e:
            errors.append(f"Device {device_data.hostname or device_data.ip_address}: {str(e)}")
    
    await db.commit()
    
    return schemas.AgentUploadResponse(
        uploaded=uploaded,
        updated=updated,
        errors=errors,
    )
```

**Note:** Need to add `request.state.agent_org_id` to agent_auth dependency. Check `app/api/dependencies.py` for current implementation and update to include org_id in request.state.

**Step 3: Run linter to verify**

Run: `flake8 services/api/app/api/routes.py --max-line-length=120 --ignore=E501,W503`
Expected: No errors

**Step 4: Commit**

```bash
git add services/api/app/api/routes.py services/api/app/api/schemas.py
git commit -m "feat(api): add agent data upload endpoint"
```

---

## Task 3: Agent Docker Containerization

**Files:**
- Modify: `docker/agent/Dockerfile` - Enhance with proper entrypoint
- Create: `docker/agent/requirements.txt` - Agent Python dependencies
- Create: `docker/agent/docker-compose.yml` - Local dev deployment
- Create: `configs/agent.yaml` - Default agent configuration

**Step 1: Create agent requirements.txt**

Create: `docker/agent/requirements.txt`

```
aiosqlite>=0.19.0
bcrypt>=4.0.0
pyyaml>=6.0
python-dotenv>=1.0.0
httpx>=0.25.0
netmiko>=4.1.0
paramiko>=3.0.0
textfsm>=1.1.3
nornir>=3.0.0
```

**Step 2: Enhance Dockerfile**

Modify: `docker/agent/Dockerfile` - Add proper entrypoint and healthcheck

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    snmp \
    libsnmp-dev \
    nmap \
    masscan \
    arp-scan \
    fprobe \
    nfdump \
    && rm -rf /var/lib/apt/lists/*

COPY docker/agent/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/agent /app/agent
COPY configs/agent.yaml /app/config/agent.yaml

RUN mkdir -p /app/data

ENV PYTHONPATH=/app
ENV AGENT_CONFIG_PATH=/app/config/agent.yaml

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["python", "-m", "agent.main"]
CMD ["--mode", "continuous"]
```

**Step 3: Create docker-compose.yml for agent**

Create: `docker/agent/docker-compose.yml`

```yaml
version: '3.8'

services:
  agent:
    build:
      context: ..
      dockerfile: docker/agent/Dockerfile
    container_name: netdiscover-agent
    environment:
      - AGENT_API_KEY=${AGENT_API_KEY}
      - AGENT_NAME=${AGENT_NAME:-Local Agent}
      - CLOUD_API_URL=${CLOUD_API_URL:-http://api:8000}
      - DB_PATH=/app/data/agent.db
      - LOG_LEVEL=INFO
    volumes:
      - agent_data:/app/data
      - ./configs/agent.yaml:/app/config/agent.yaml:ro
    restart: unless-stopped
    networks:
      - agent-network

volumes:
  agent_data:

networks:
  agent-network:
    driver: bridge
```

**Step 4: Create/update agent config.yaml**

Create: `configs/agent.yaml` (if not exists)

```yaml
agent:
  name: "Local Agent"
  mode: "continuous"  # continuous, scheduled, on-demand
  scan_interval_minutes: 60

discovery:
  methods:
    - arp_scan
    - nmap
    - snmp_walk
  target_cidrs: []
  exclude_cidrs: []
  ports:
    - 22
    - 23
    - 80
    - 443
    - 161

credentials:
  priority_order:
    - ssh_key
    - snmp
    - telnet
    - http_basic

sanitizer:
  enable_tier1: true
  enable_tier2: true
  enable_tier3: true

cloud:
  api_url: "http://api:8000"
  upload_batch_size: 100
  upload_interval_seconds: 300

database:
  path: "/app/data/agent.db"
  retention_days: 90

logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

**Step 5: Add health endpoint to agent main.py**

Modify: `services/agent/agent/main.py` - Add health check endpoint

Add after imports:
```python
from fastapi import FastAPI
import uvicorn
```

Add health endpoint class:
```python
def create_app() -> FastAPI:
    """Create FastAPI app for agent"""
    app = FastAPI(title="NetDiscoverIT Local Agent")
    
    @app.get("/health")
    async def health():
        return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
    
    @app.get("/ready")
    async def ready():
        # Check connectivity to cloud
        return {"status": "ready"}
    
    return app
```

**Step 6: Test Docker build**

Run: `docker build -f docker/agent/Dockerfile -t netdiscover-agent:latest .`
Expected: Build succeeds

**Step 7: Commit**

```bash
git add docker/agent/ docker/agent/requirements.txt configs/agent.yaml
git commit -m "feat(agent): add Docker containerization for local agent"
```

---

## Task 4: Integration - Agent DB + Upload Flow

**Files:**
- Modify: `services/agent/agent/main.py` - Integrate SQLite storage
- Modify: `services/agent/agent/uploader.py` - Use upload endpoint

**Step 1: Integrate DB into Agent main**

Modify: `services/agent/agent/main.py` - Initialize DB and store devices locally before upload

Add to imports:
```python
from agent.db.schema import LocalAgentDB
```

Update Agent.__init__:
```python
self.db = LocalAgentDB(config.db_path)
```

Add run method update to store discovered devices:
```python
async def run_discovery(self) -> dict:
    # ... discovery phases 1-4 ...
    
    # Store locally in SQLite
    logger.info("Storing devices in local DB")
    for device in devices:
        await self.db.upsert_device({
            'agent_id': self.config.agent_id,
            'hostname': device.get('hostname'),
            'ip_address': device.get('ip_address'),
            'mac_address': device.get('mac_address'),
            'device_type': device.get('device_type'),
            'vendor': device.get('vendor'),
            'model': device.get('model'),
            'os_version': device.get('os_version'),
            'metadata': sanitized.get(device['hostname'], {}),
        })
    
    # Upload to cloud
    await self.uploader.upload_vectors(vectors)
```

**Step 2: Commit**

```bash
git add services/agent/agent/main.py
git commit -m "feat(agent): integrate SQLite storage into discovery flow"
```

---

## Verification Commands

After completing all tasks:
```bash
# Run API tests
pytest tests/api/test_agent_upload.py -v

# Build agent container
docker build -f docker/agent/Dockerfile -t netdiscover-agent:latest .

# Test agent starts
docker run --rm netdiscover-agent:latest python -c "from agent.db.schema import LocalAgentDB; print('OK')"
```

---

**Plan complete and saved to `docs/plans/2026-03-21-local-agent.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
