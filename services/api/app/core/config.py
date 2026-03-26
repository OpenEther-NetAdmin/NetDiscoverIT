"""
Application configuration
"""

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    model_config = ConfigDict(env_file=".env", case_sensitive=True)

    # App
    APP_NAME: str = "NetDiscoverIT"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    APP_URL: str = "http://localhost:3000"
    APP_API_URL: str = "http://localhost:8000"

    # Database — no defaults for secrets; app fails loudly at startup if unset
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "netdiscoverit"
    POSTGRES_USER: str = "netdiscoverit"
    POSTGRES_PASSWORD: str

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # JWT — no defaults for secrets
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Internal API — no default for secrets
    INTERNAL_API_KEY: str

    # Credential encryption — Fernet key (32 bytes, URL-safe base64-encoded, 44 chars)
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    CREDENTIAL_ENCRYPTION_KEY: str

    # LLM Providers
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "llama3.2:7b"

    # Vector DB
    VECTOR_DB_PROVIDER: str = "pgvector"
    VECTOR_DIMENSION: int = 768

    # Neo4j Graph Database — no default for password
    NEO4J_HOST: str = "neo4j"
    NEO4J_PORT: int = 7687
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str
    NEO4J_SCHEME: str = "bolt"  # Use "bolt+s" or "neo4j+s" for TLS

    @property
    def NEO4J_URI(self) -> str:
        return f"{self.NEO4J_SCHEME}://{self.NEO4J_HOST}:{self.NEO4J_PORT}"

    # Logging
    LOG_LEVEL: str = "info"
    LOG_FORMAT: str = "json"

    # CORS — comma-separated, no spaces
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080"

    # Rate limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_WRITE: str = "60/minute"
    RATE_LIMIT_READ: str = "200/minute"

    # NLI / RAG
    NLI_VECTOR_TOP_K: int = 5      # devices retrieved per domain; clamped to 20 at runtime
    NLI_RATE_LIMIT: str = "10/minute"


settings = Settings()
