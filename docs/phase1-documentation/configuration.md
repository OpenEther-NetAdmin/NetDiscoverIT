# Configuration Guide

This guide covers configuration options for all NetDiscoverIT services. All configuration uses environment variables with sensible defaults for development.

## Environment Setup

Copy the example environment file to get started:

```bash
make setup
```

This creates a `.env` file from `.env.example` that you can customize.

## Required Secrets

These environment variables must be set in production. The application fails to start if they are unset:

- `POSTGRES_PASSWORD` - Password for the PostgreSQL database
- `JWT_SECRET_KEY` - Secret key for JWT token signing
- `INTERNAL_API_KEY` - Key for internal service communication
- `CREDENTIAL_ENCRYPTION_KEY` - Key for encrypting stored credentials ( Fernet format)

## API Service Configuration

**File:** `services/api/app/core/config.py`

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | localhost | PostgreSQL server hostname |
| `POSTGRES_PORT` | 5432 | PostgreSQL server port |
| `POSTGRES_DB` | netdiscoverit | Database name |
| `POSTGRES_USER` | netdiscoverit | Database user |
| `POSTGRES_PASSWORD` | (required) | Database password |
| `NEO4J_URI` | bolt://localhost:7687 | Neo4j connection URI |
| `NEO4J_USERNAME` | neo4j | Neo4j username |
| `NEO4J_PASSWORD` | neo4j | Neo4j password |
| `JWT_SECRET_KEY` | (required) | JWT signing secret |
| `JWT_ALGORITHM` | HS256 | JWT algorithm |
| `JWT_EXPIRATION_MINUTES` | 60 | Token expiration time |
| `CORS_ORIGINS` | http://localhost:3000 | Allowed CORS origins |
| `LOG_LEVEL` | info | Logging level |

## Agent Service Configuration

**File:** `services/agent/agent/config.py`

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | (empty) | Authentication key for API |
| `API_ENDPOINT` | http://localhost:8000 | API service URL |
| `DISCOVERY_METHODS` | ssh,snmp | Comma-separated methods |
| `SCAN_INTERVAL` | 24h | Scan frequency |
| `SSH_TIMEOUT` | 30 | SSH connection timeout |
| `SSH_RETRY` | 3 | SSH connection retries |
| `SNMP_TIMEOUT` | 5 | SNMP timeout |
| `LOG_LEVEL` | info | Logging level |
| `DB_PATH` | /app/data/agent.db | Local SQLite database |

### Sanitizer Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PREFER_TEXTFSM` | true | Prefer TextFSM templates |
| `FALLBACK_TO_REGEX` | true | Use regex if no template |
| `ENABLE_LLM` | false | Enable LLM sanitization |
| `OLLAMA_URL` | http://localhost:11434 | Ollama API URL |
| `OLLAMA_MODEL` | llama3.2:7b | Ollama model name |
| `SAFETY_CHECK_ENABLED` | true | Enable safety checks |
| `BLOCK_ON_FAILURE` | true | Block on sanitization failure |
| `MAX_CONFIG_SIZE_MB` | 50 | Maximum config size |
| `TIMEOUT_SECONDS` | 30 | Processing timeout |

## Frontend Configuration

**File:** `services/frontend/.env`

| Variable | Default | Description |
|----------|---------|-------------|
| `REACT_APP_API_URL` | http://localhost:8000 | API base URL |

## Docker Compose Configuration

**File:** `docker-compose.yml`

The Docker Compose file defines all services with their configuration. Key services:

### PostgreSQL

```yaml
postgres:
  image: pgvector/pgvector:pg16
  environment:
    POSTGRES_DB: ${POSTGRES_DB:-netdiscoverit}
    POSTGRES_USER: ${POSTGRES_USER:-netdiscoverit}
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme}
```

### Redis

```yaml
redis:
  image: redis:7-alpine
```

### Vault

```yaml
vault:
  image: hashicorp/vault:1.17
  environment:
    VAULT_ADDR: http://vault:8200
    VAULT_DEV_ROOT_TOKEN_ID: ${VAULT_TOKEN:-changeme}
```

### Ollama

```yaml
ollama:
  image: ollama/ollama:latest
  ports:
    - "11434:11434"
```

## Configuration Files

The agent loads additional configuration from YAML files:

- `services/agent/config/sanitizer.yaml` - Sanitizer rules and patterns

## Best Practices

1. **Never commit secrets** - Use environment variables, never hardcode credentials
2. **Fail loudly** - Required secrets must be set; the app does not start without them
3. **Use different keys per environment** - Development, staging, and production should have separate secrets
4. **Rotate secrets regularly** - Implement a rotation schedule for production deployments