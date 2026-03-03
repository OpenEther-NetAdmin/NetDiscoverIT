# AGENTS.md

This file provides guidance to AI coding agents working in this repository.

## Build/Test/Lint Commands

### Docker (primary development)
```bash
make setup          # First-time: copies .env.example → .env
make up             # Start all services (API: :8000, Frontend: :3000)
make up-build       # Rebuild images then start
make down           # Stop all services
make logs-api       # Tail API logs
make logs-agent     # Tail agent logs
```

### Testing
```bash
make test                          # Run all tests
make test-cov                      # Run tests with coverage report
pytest tests/path/test_file.py::test_name -v   # Single test
```

### Linting & Formatting
```bash
make lint           # Run flake8 + black check + eslint
make format         # Auto-format with black + prettier

# Manual linting
flake8 services/api --max-line-length=120 --ignore=E501,W503
black --check services/api
black services/api
cd services/frontend && npm run lint
```

### Database Migrations
```bash
make db-migrate                        # Apply pending migrations
make db-migrate-create MESSAGE="..."   # Generate new migration
make db-shell                          # psql into database
```

## Code Style Guidelines

### Python (API)

**Imports** (grouped with blank lines):
1. Standard library
2. Third-party packages
3. Local app modules (`from app.xxx import ...`)

```python
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, String
from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.db.database import get_db
```

**Formatting:**
- Max line length: 120 (enforced via flake8)
- Use double quotes for strings
- Black for auto-formatting

**Types:**
- Use type hints for function signatures
- Use Pydantic v2 models for schemas (`model_dump()` not `dict()`)
- Async SQLAlchemy: `AsyncSession`, `await` all DB operations

**Naming:**
- `snake_case` for variables, functions, methods
- `PascalCase` for classes
- `UPPER_CASE` for constants/settings
- Model classes match table name (e.g., `Device` → `devices`)

**Error Handling:**
- Use FastAPI `HTTPException` for API errors
- Log warnings for non-fatal failures during startup
- Fail loudly at startup if required secrets unset (no defaults for secrets)

**Key Patterns:**
- All DB models in `models/models.py`
- All schemas in `api/schemas.py`
- Encrypted columns use `EncryptedText` type (Fernet)
- Vector columns: 768-dim HNSW indexed (pgvector)
- Neo4j for graph relationships, PostgreSQL for structured data

### JavaScript/TypeScript (Frontend)

**Commands:**
```bash
cd services/frontend && npm start      # Dev server on :3000
npm run build                          # Production build
npm run lint                           # ESLint check
npm run format                         # Prettier format
npm run typecheck                      # TypeScript check
```

**Style:**
- React 19, Chakra UI v3, React Query
- Functional components with hooks
- Prettier for formatting

## Architecture Reminders

**Critical Privacy Rule:** Raw device configs NEVER leave customer network. Only structured metadata, topology relationships, and vector embeddings are uploaded.

**Required Environment Variables** (app fails loudly if unset):
- `POSTGRES_PASSWORD`
- `JWT_SECRET_KEY`
- `INTERNAL_API_KEY`
- `CREDENTIAL_ENCRYPTION_KEY`

**Database:**
- Use Alembic migrations for schema changes (not `create_all()`)
- Migrations live in `services/api/alembic/versions/`
- HNSW indexes for vector columns (not IVFFlat)

**API Structure:**
- Routes in `api/routes.py` with `/api/v1` prefix
- Dependencies in `api/dependencies.py`
- Config in `core/config.py` (Pydantic Settings)
- `get_current_user()` is a stub — JWT not yet implemented

## Testing

- pytest with asyncio support
- Tests directory at repo root (create if adding tests)
- Coverage target: include in PR reviews

## Memory repository (mandatory)

The memory repo at https://github.com/OpenEther-NetAdmin/claw-memory must be updated after **every** completed task or any time something of value is produced or changed — including but not limited to:
- Completed implementation tasks
- Architectural decisions or ADRs
- Schema or model changes
- New patterns, conventions, or debugging insights discovered
- Updates to project docs or plans

The repo is cloned to `/tmp/claw-memory`. After updating files there, commit and push:
```bash
cd /tmp/claw-memory
git add -A
git commit -m "update: <brief description>"
git push
```
If the clone does not exist: `git clone https://github.com/OpenEther-NetAdmin/claw-memory.git /tmp/claw-memory`

The in-project auto-memory files (`/home/openether/.claude/projects/-home-openether-NetDiscoverIT/memory/`) should also be kept in sync — they are loaded into context at session start.