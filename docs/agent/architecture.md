# Architecture Patterns

## Database

### PostgreSQL (Structured Data)

- Use Alembic migrations for schema changes (not `create_all()`)
- Migrations live in `services/api/alembic/versions/`
- HNSW indexes for vector columns (not IVFFlat)
- Encrypted columns use `EncryptedText` type (Fernet)
- Vector columns: 768-dim HNSW indexed (pgvector)

### Neo4j (Graph Relationships)

- Use for topology and relationship data
- AsyncGraphDatabase client

## API Structure

- Routes in `api/routes.py` with `/api/v1` prefix
- Dependencies in `api/dependencies.py`
- Config in `core/config.py` (Pydantic Settings)
- `get_current_user()` is a stub — JWT not yet implemented

## Agent Architecture

### Sanitizer Module

The sanitizer strips passwords, keys, secrets, and usernames before any data leaves the customer network. This is the **critical privacy path**.

Tiers:
- **Tier 1:** TextFSM template-driven (precise)
- **Tier 2:** Section-aware regex (heuristic)
- **Tier 3:** Aggressive regex (catch-all)

See `services/agent/agent/sanitizer/` for implementation.

### Key Patterns

- All DB models in `models/models.py`
- All schemas in `api/schemas.py`
- Configuration loaded from YAML with environment overrides
