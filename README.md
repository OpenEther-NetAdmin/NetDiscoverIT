# NetDiscoverIT

AI-powered network discovery and self-documenting platform.

## Overview

NetDiscoverIT automatically discovers network devices, collects configurations, and uses AI to generate living documentation and proactive recommendations — all while keeping customer data secure with a privacy-first local agent architecture.

## Features

- **Auto-Discovery** — SSH/SNMP device discovery
- **AI Documentation** — Config → JSON → dynamic diagrams
- **ML Classification** — Automatically determines device roles
- **Path Visualizer** — Interactive src/dst path tracing
- **Privacy-First** — Local agent keeps data on-prem

## Quick Start

### Prerequisites

- Docker & Docker Compose
- PostgreSQL (managed via Docker)
- Python 3.11+ (for local development)

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
│  - Sanitizer        │     │  - Vector DB       │
│  - Vectorizer       │     │  - React Frontend  │
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

## License

MIT

---

*Building the self-documenting network.*
