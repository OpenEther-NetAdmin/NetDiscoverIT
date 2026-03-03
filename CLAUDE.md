# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Docker (primary development method)
```bash
make setup          # First-time: copies .env.example → .env, creates data/logs dirs
make up             # Start all services (API: :8000, Frontend: :3000)
make up-build       # Rebuild images then start
make down           # Stop all services
make logs-api       # Tail API logs
make logs-agent     # Tail agent logs
```

### Database migrations
```bash
make db-migrate                        # Apply pending migrations (runs inside container)
make db-migrate-create MESSAGE="..."   # Generate new migration from model changes
make db-shell                          # psql into netdiscoverit database
```
Migrations live in `services/api/alembic/versions/`. After changing `models.py`, always create a migration rather than using `init_db()` directly.

### API development (outside Docker)
```bash
pip install -r services/api/requirements.txt
cd services/api && uvicorn app.main:app --reload
```
Swagger UI: `http://localhost:8000/docs`

### Testing & linting
```bash
make test           # pytest tests/ -v
make test-cov       # pytest with HTML coverage report
make lint           # flake8 + black check (API) + eslint (frontend)
make format         # black (API) + prettier (frontend)
pytest tests/path/to/test_file.py::test_name -v   # single test
```

### Frontend
```bash
cd services/frontend && npm install && npm start   # dev server on :3000
npm run build                                       # production build
npm run lint / npm run format
```

### Credential encryption key generation
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Required env var: `CREDENTIAL_ENCRYPTION_KEY` — no default, app fails loudly if unset.

## Architecture

### Two-tier hybrid deployment
```
Customer Network (Local Agent)       Cloud (NetDiscoverIT)
──────────────────────────────       ──────────────────────
Collector → Normalizer               FastAPI (services/api/)
         → Sanitizer       ────▶     PostgreSQL + pgvector
         → Vectorizer                Neo4j
         → Uploader                  React frontend
```

**Critical privacy invariant**: Raw device configs NEVER leave the customer network. Not even sanitized versions. Only structured metadata (JSONB), topology relationships (Neo4j), and vector embeddings (pgvector) are uploaded to the cloud.

### Services
| Path | Purpose |
|------|---------|
| `services/api/` | FastAPI backend — all cloud-side logic |
| `services/agent/` | Python local agent — runs on customer network |
| `services/frontend/` | React frontend (Chakra UI + ReactFlow + D3) |

### API service layout (`services/api/app/`)
- `main.py` — FastAPI app, lifespan events (DB init + Neo4j constraints on startup)
- `core/config.py` — Pydantic Settings; `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `INTERNAL_API_KEY`, `CREDENTIAL_ENCRYPTION_KEY` have no defaults and fail loudly if unset
- `models/models.py` — All SQLAlchemy models (see below)
- `db/database.py` — Async SQLAlchemy engine (asyncpg), session factory, Alembic runner
- `db/neo4j.py` — Neo4j async client singleton; `get_neo4j_client()` / `close_neo4j_client()`
- `api/routes.py` — API routes (many are TODO stubs with placeholder returns)
- `api/dependencies.py` — Auth dependencies (`get_current_user` is a placeholder stub; JWT not yet implemented)
- `api/schemas.py` — Pydantic request/response schemas

### Local agent pipeline (`services/agent/agent/`)
Six sequential phases per discovery cycle:
1. `collector.py` — SSH/SNMP device discovery + config retrieval
2. `normalizer.py` — TextFSM/Netmiko templates → JSON (Ollama LLM as fallback only)
3. `sanitizer.py` — PII removal (IPs, credentials, hostnames stripped from values)
4. `vectorizer.py` — 768-dim embeddings via Ollama
5. `uploader.py` — POST structured metadata + vectors to cloud API
6. `scheduler.py` — Interval-based scheduling (default 24h)

Run once: `python -m agent.main --once`
Scheduled: `python -m agent.main --config /app/config/agent.yaml`

### PostgreSQL models (key tables in `models/models.py`)
- `Organization` — multi-tenant root; MSP hierarchy via `parent_org_id`; `subscription_tier`
- `User` — belongs to org; roles: admin/engineer/viewer/msp_admin/msp_viewer
- `LocalAgent` — per-agent API key hash (bcrypt); replaces org-level key; `capabilities` JSONB
- `Site` — physical/logical groupings (on_premises, branch, datacenter, cloud_*)
- `Device` — core model; `metadata` JSONB (security posture, routing counts, interface facts); `compliance_scope` JSONB array (GIN indexed); four 768-dim HNSW vector columns
- `Configuration` — change-tracking log only (config_hash + metadata diff + timestamp); no config text
- `ChangeRecord` — audit-grade change evidence (CHG-YYYY-NNNN); lifecycle: draft→proposed→approved→implemented→verified; pre/post config hashes; simulation evidence
- `IntegrationConfig` — external ticketing (ServiceNow, Jira, Slack, etc.); `encrypted_credentials` via Fernet
- `AuditLog` — platform user action trail; `action` format: `"resource_type.verb"`
- `AlertRule` / `AlertEvent` — configurable alerts + fired instances
- `ACLSnapshot` — compliance vault (zero-knowledge encrypted ACL storage, opt-in add-on)
- `ExportDocument` — MinIO/S3 export tracking for PDF/DOCX/Drawio/Visio outputs

### Neo4j graph (`db/neo4j.py`)
Node types: `Device`, `Interface`, `VLAN`
Relationships: `HAS_INTERFACE`, `CONNECTED_TO` (bidirectional), `MEMBER_OF`
Used for: topology visualization, path tracing, network segmentation evidence for compliance.

### pgvector indexes
All four Device vector columns use HNSW (not IVFFlat): `m=16`, `ef_construction=64`, `vector_cosine_ops`. Created via migration `002_add_vector_indexes.py`.

### Authentication
- Users: JWT HS256, 15-minute access tokens (`JWT_SECRET_KEY` required)
- Local agents: `X-Agent-Key` header, bcrypt hash in `LocalAgent.api_key_hash`
- Internal services: `X-Internal-Api-Key` header vs `INTERNAL_API_KEY` env var
- `get_current_user()` in `dependencies.py` is a placeholder — JWT validation not yet implemented

### `EncryptedText` column type
Defined in `models.py` — transparent Fernet encryption/decryption. Used for `Credential.encrypted_value`, `IntegrationConfig.encrypted_credentials`, and `IntegrationConfig.webhook_secret`. Requires `CREDENTIAL_ENCRYPTION_KEY` to be set before any model import that touches those columns.

## Key development notes

- The API uses **async SQLAlchemy** (`asyncpg` driver). All DB operations must be `await`-ed; use `AsyncSession` from `get_db()`.
- `NullPool` is intentional — avoids connection reuse issues in async contexts.
- `APP_DEBUG=True` enables SQLAlchemy query echo.
- `CORS_ORIGINS` must be comma-separated with no spaces (parsed by `settings.CORS_ORIGINS.split(",")`).
- All new schema changes must go through Alembic migrations, not `Base.metadata.create_all()`.
- The `Configuration` table stores change-tracking metadata only — no `raw_config`, no `sanitized_config_path`. MinIO/S3 is for exports (PDF, DOCX, etc.), not configs.
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
