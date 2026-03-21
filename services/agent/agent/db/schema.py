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