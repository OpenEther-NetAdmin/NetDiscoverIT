"""
Agent Configuration
"""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel
from typing import Dict, List, Optional


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


class SanitizerConfig(BaseModel):
    """Sanitizer-specific configuration"""
    prefer_textfsm: bool = True
    fallback_to_regex: bool = True
    enable_llm: bool = False
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:7b"
    safety_check_enabled: bool = True
    block_on_failure: bool = True
    max_config_size_mb: int = 50
    timeout_seconds: int = 30
    custom_tokens: Optional[Dict[str, str]] = None


class AgentConfig(BaseModel):
    """Agent configuration"""
    VERSION: str = "0.1.0"
    
    # API
    API_KEY: str = ""
    API_ENDPOINT: str = "http://localhost:8000"
    ORG_ID: str = "default"
    
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

    # Database
    db_path: str = "/app/data/agent.db"
    db_retention_days: int = 90

    # Target devices (loaded from config file)
    devices: List[dict] = []
    
    # LLM Providers
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    GOOGLE_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:7b"
    
    # Sanitizer
    sanitizer: SanitizerConfig = SanitizerConfig()
    
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
        return cls(
            API_KEY=os.getenv("API_KEY", ""),
            API_ENDPOINT=os.getenv("API_ENDPOINT", "http://localhost:8000"),
            ORG_ID=os.getenv("ORG_ID", "default"),
            DISCOVERY_METHODS=os.getenv("DISCOVERY_METHODS", "ssh,snmp").split(","),
            SCAN_INTERVAL=os.getenv("SCAN_INTERVAL", "24h"),
            SSH_TIMEOUT=int(os.getenv("SSH_TIMEOUT", "30")),
            SNMP_TIMEOUT=int(os.getenv("SNMP_TIMEOUT", "5")),
            LOG_LEVEL=os.getenv("LOG_LEVEL", "info"),
            ANTHROPIC_API_KEY=os.getenv("ANTHROPIC_API_KEY", ""),
            ANTHROPIC_MODEL=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            GOOGLE_API_KEY=os.getenv("GOOGLE_API_KEY", ""),
            OLLAMA_BASE_URL=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            OLLAMA_MODEL=os.getenv("OLLAMA_MODEL", "llama3.2:7b"),
        )
