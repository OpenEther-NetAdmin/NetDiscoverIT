# Deployment Guide

This guide covers deploying NetDiscoverIT using Docker Compose. For production deployments, adapt these steps to your orchestration platform.

## Prerequisites

- Docker Engine 24.0 or later
- Docker Compose v2.20 or later
- At least 4GB RAM available
- 20GB disk space

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/OpenEther-NetAdmin/NetDiscoverIT.git
cd NetDiscoverIT
```

### 2. Configure Environment

Copy the example environment file and configure your settings:

```bash
make setup
```

Edit the `.env` file and set required secrets:

```bash
POSTGRES_PASSWORD=your_secure_password
JWT_SECRET_KEY=your_jwt_secret
INTERNAL_API_KEY=your_api_key
CREDENTIAL_ENCRYPTION_KEY=your_fernet_key
```

Generate a Fernet key for credential encryption:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Start Services

Start all services:

```bash
make up
```

This command starts:

- PostgreSQL (port 5432)
- Redis (port 6379)
- Vault (port 8200)
- Ollama (port 11434)
- API (port 8000)
- Frontend (port 3000)

### 4. Verify Deployment

Check service health:

```bash
curl http://localhost:8000/api/v1/health
```

Access the frontend at http://localhost:3000

## Service Management

### Start Services

```bash
make up
```

### Stop Services

```bash
make down
```

### View Logs

```bash
make logs-api    # API logs
make logs-agent  # Agent logs
```

### Rebuild Images

```bash
make up-build
```

## Database Operations

### Run Migrations

```bash
make db-migrate
```

### Create New Migration

```bash
make db-migrate-create MESSAGE="description"
```

### Access Database Shell

```bash
make db-shell
```

## Development Workflow

### Running Tests

```bash
make test
```

### Running Tests with Coverage

```bash
make test-cov
```

### Linting

```bash
make lint
```

### Code Formatting

```bash
make format
```

## Production Considerations

### Security Hardening

1. Change default passwords in `.env`
2. Use strong, randomly generated secrets
3. Enable TLS termination at the load balancer
4. Restrict access to Docker socket
5. Enable AppArmor or SELinux

### Scaling

For production, consider:

- Deploying behind a load balancer
- Using a managed PostgreSQL service
- Using a managed Neo4j service
- Configuring Redis for persistence
- Setting up monitoring and alerting

### Backup Strategy

Implement regular backups:

- PostgreSQL: Use `pg_dump` or managed backups
- Neo4j: Use `neo4j-admin dump`
- Configuration: Version control `.env` files
- Volumes: Snapshot Docker volumes

### Health Checks

All services include health checks. Verify they pass:

```bash
docker compose ps
```

### Troubleshooting

If services fail to start:

1. Check logs: `docker compose logs <service>`
2. Verify `.env` settings
3. Ensure ports are available
4. Verify Docker has sufficient resources

## Next Steps

After deployment:

1. Register an agent in the frontend
2. Configure target networks
3. Run initial discovery
4. Explore topology visualization