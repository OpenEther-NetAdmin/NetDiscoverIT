# NetDiscoverIT

AI-powered network discovery and self-documenting platform.

## Overview

NetDiscoverIT automatically discovers network devices, collects configurations, and uses AI to generate living documentation and proactive recommendations — all while keeping customer data secure with a privacy-first local agent architecture.

## Features

- **Auto-Discovery** — SSH/SNMP/NMAP/Masscan device discovery
- **Topology Mapping** — CDP/LLDP neighbor discovery, arp-scan, switch-mapper
- **Flow Analysis** — NetFlow/sFlow collection via fprobe
- **IVRE Integration** — Full network recon framework (Nmap/Masscan/Zeek/p0f)
- **AI Documentation** — Config → JSON → dynamic diagrams
- **ML Classification** — Automatically determines device roles
- **Graph Visualization** — Neo4j-powered topology maps
- **Path Visualizer** — Interactive src/dst path tracing
- **Privacy-First** — Local agent keeps data on-prem

## Database Setup

### Alembic Migrations

NetDiscoverIT uses Alembic for database schema management. All database changes should be made through migrations rather than direct schema modifications.

#### Running Migrations

```bash
# Apply all pending migrations
cd services/api
alembic upgrade head

# Create a new migration (after making model changes)
alembic revision --autogenerate -m "description of changes"
```

#### Migration Files

- `alembic/versions/001_initial_migration.py` - Initial schema creation
- `alembic/versions/002_add_vector_indexes.py` - HNSW vector indexes for device embeddings

#### Database Initialization

The application automatically runs migrations on startup via FastAPI's lifespan events. No manual initialization is required.

### Development

```bash
# Clone the repo
git clone https://github.com/OpenEther-NetAdmin/NetDiscoverIT.git
cd NetDiscoverIT

# Copy environment variables
cp .env.example .env

# Start services
docker-compose up -d

# View logs
docker-compose logs -f
```

### Production

```bash
# Production deployment
docker-compose -f docker-compose.prod.yml up -d
```

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐
│  LOCAL AGENT        │     │  CLOUD              │
│  (Customer Network) │     │  (NetDiscoverIT)    │
├─────────────────────┤     ├─────────────────────┤
│  - Collector        │     │  - API (FastAPI)    │
│  - Normalizer       │────▶│  - PostgreSQL       │
│  - Sanitizer        │     │  - Neo4j            │
│  - Vectorizer       │     │  - Vector DB        │
│  - NMAP/Masscan    │     │  - React Frontend   │
│  - CDP/LLDP        │     │                     │
│  - fprobe          │     │                     │
└─────────────────────┘     └─────────────────────┘
```

## Project Structure

```
NetDiscoverIT/
├── .github/workflows/     # CI/CD pipelines
├── docker/                 # Docker configurations
│   ├── agent/             # Local agent Dockerfile
│   ├── api/               # API service Dockerfile
│   └── frontend/          # Frontend Dockerfile
├── services/
│   ├── api/               # FastAPI backend
│   ├── agent/             # Local agent
│   └── frontend/          # React frontend
├── configs/               # Configuration files
├── scripts/               # Utility scripts
└── tests/                 # Test suites
```

## Environment Variables

See `.env.example` for all available variables.

## API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Agent/Assistant Memory Repo(to be updated after each task completion)
- Refer to [https://github.com/OpenEther-NetAdmin/claw-memory.git](https://github.com/OpenEther-NetAdmin/claw-memory.git) for design and implementation instructions.
- all files are stored in /tmp/claw-memory

## License

MIT

---

*Building the self-documenting network.*
