"""
Agent Configuration
"""

from pydantic import BaseModel
from typing import List, Optional
import yaml


class SSHConfig(BaseModel):
    """SSH configuration"""
    timeout: int = 30
    retry: int = 3
    port: int = 22


class SNMPConfig(BaseModel):
    """SNMP configuration"""
    timeout: int = 5
    community: str = "public"
    version: str = "v2c"


class AgentConfig(BaseModel):
    """Agent configuration"""
    VERSION: str = "0.1.0"
    
    # API
    API_KEY: str = ""
    API_ENDPOINT: str = "http://localhost:8000"
    
    # Discovery
    DISCOVERY_METHODS: List[str] = ["ssh", "snmp"]
    SCAN_INTERVAL: str = "24h"
    
    # SSH
    SSH_TIMEOUT: int = 30
    SSH_RETRY: int = 3
    
    # SNMP
    SNMP_TIMEOUT: int = 5
    
    # Logging
    LOG_LEVEL: str = "info"
    
    # Target devices (loaded from config file)
    devices: List[dict] = []
    
    @classmethod
    def from_file(cls, path: str) -> "AgentConfig":
        """Load config from YAML file"""
        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
            return cls(**data)
        except FileNotFoundError:
            # Return defaults
            return cls()
    
    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Load config from environment variables"""
        import os
        return cls(
            API_KEY=os.getenv("API_KEY", ""),
            API_ENDPOINT=os.getenv("API_ENDPOINT", "http://localhost:8000"),
            DISCOVERY_METHODS=os.getenv("DISCOVERY_METHODS", "ssh,snmp").split(","),
            SCAN_INTERVAL=os.getenv("SCAN_INTERVAL", "24h"),
            SSH_TIMEOUT=int(os.getenv("SSH_TIMEOUT", "30")),
            SNMP_TIMEOUT=int(os.getenv("SNMP_TIMEOUT", "5")),
            LOG_LEVEL=os.getenv("LOG_LEVEL", "info"),
        )
