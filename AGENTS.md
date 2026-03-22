# NetDiscoverIT

Network discovery and topology mapping platform with privacy-first architecture.

## Critical: All Work in Containers

**All development, testing, and implementation MUST be done in Docker containers, not on the local machine.**

```bash
make up             # Start all services (API: :8000, Frontend: :3000)
make up-build       # Rebuild images then start
make down           # Stop all services
make logs-api       # Tail API logs
make logs-agent     # Tail agent logs
```

## Essential Commands

```bash
make setup          # First-time: copies .env.example → .env
make test           # Run all tests
make test-cov       # Run tests with coverage report
make lint           # Run flake8 + black check + eslint
make format         # Auto-format with black + prettier
make db-migrate     # Apply pending migrations
make db-shell       # psql into database
```

## Critical Rules

- **Privacy First:** Raw device configs NEVER leave customer network. All data must be sanitized before upload.
- **Required Secrets:** `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `INTERNAL_API_KEY`, `CREDENTIAL_ENCRYPTION_KEY` (fail loudly if unset)
- **Memory Repo:** Update claw-memory after every task completion

## Detailed Guidelines

- [Python Style](docs/agent/python-style.md)
- [JavaScript/TypeScript Style](docs/agent/javascript-style.md)
- [Testing Guidelines](docs/agent/testing.md)
- [Architecture Patterns](docs/agent/architecture.md)
- [Phase 2 Implementation](docs/agent/phase-2.md)
