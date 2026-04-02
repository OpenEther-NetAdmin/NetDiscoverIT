# TLS/mTLS Infrastructure Design

**Date:** 2026-04-02
**Status:** Implementation-ready for Phase 3
**Owner:** NetDiscoverIT Platform Team

---

## Overview

This document specifies how NetDiscoverIT handles transport-layer security (TLS) for all service-to-service and client-to-service communication. The design covers three layers:

1. **External TLS** — HTTPS termination for client-facing APIs and frontend
2. **Internal TLS** — Service-to-service communication within the cluster/VPC
3. **mTLS for Agents** — Mutual TLS so agents can authenticate to the API without shared secrets

The design treats TLS as **deployment infrastructure** wherever possible, using environment variables and configuration rather than application code changes.

---

## 1. External TLS (HTTPS)

### Current State
The API and frontend run on plain HTTP (ports 8000 and 3000). There is no TLS termination in the Docker Compose stack.

### Target State
A reverse proxy (Traefik or nginx) terminates TLS in front of the API and frontend. Certificates are provisioned via Let's Encrypt (auto-renewal) or a provided wildcard cert.

### Implementation

**Traefik** is recommended over nginx because:
- Native Docker label support (no config file changes per service)
- Automatic HTTPS with Let's Encrypt
- Per-route middleware support (rate limiting, auth forwarding)

**Minimum Traefik configuration (docker-compose overlay):**

```yaml
services:
  traefik:
    image: traefik:v3.0
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./certs:/certs:ro
    command:
      - --api.insecure=true
      - --providers.docker
      - --providers.docker.exposedbydefault=false
      - --entrypoints.websecure.address=:443
      - --entrypoints.web.address=:80
      - --certificatesresolvers.letsencrypt.acme.email=ops@netdiscoverit.com
      - --certificatesresolvers.letsencrypt.acme.storage=/certs/acme.json
      - --certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web
```

**API service labels (docker-compose.yml):**

```yaml
services:
  api:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.api.rule=PathPrefix(`/api`)"
      - "traefik.http.routers.api.entrypoints=websecure"
      - "traefik.http.routers.api.tls=true"
      - "traefik.http.services.api.loadbalancer.server.port=8000"
```

**Environment variables needed:**
```bash
EXTERNAL_URL=https://api.netdiscoverit.com    # Used for JWT audience/issuer
FRONTEND_URL=https://app.netdiscoverit.com
```

### Application Changes Required
- None — TLS termination is entirely at the proxy layer
- The `EXTERNAL_URL` env var should be used for JWT audience/issuer validation in production

---

## 2. Internal TLS (Service-to-Service)

### Current State
PostgreSQL, Redis, Neo4j, MinIO, and Ollama communicate over plain HTTP on the Docker network.

### Target State
All internal services use TLS. Certificates are provisioned via an internal CA (Smallstep/step-ca or Cloudflare CFSSL) or Kubernetes cert-manager.

### Implementation

**Option A — Smallstep CA (recommended for self-hosted):**
- step-ca runs as a sidecar or separate container
- Each service gets a certificate signed by the internal CA
- Certificates rotated automatically via cert-manager or a renewal cron

**Option B — cert-manager (Kubernetes only):**
- Automatically provisions certificates from Let's Encrypt or an internal issuer
- Each service gets a Kubernetes Secret with TLS cert + key
- Services mount the secret as a volume

**Minimum configuration changes:**

For PostgreSQL (app connects via `DATABASE_URL`):
```bash
# Add to app .env
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/netdiscoverit?ssl=true&sslcert=/certs/postgres.crt&sslkey=/certs/postgres.key&sslrootcert=/certs/ca.crt
```

For Neo4j (already has `NEO4J_SCHEME` setting):
```bash
NEO4J_SCHEME=neo4j+s   # was: bolt
```

For MinIO:
```bash
MINIO_ENDPOINT=https://minio:9000   # was: http://minio:9000
MINIO_CA_BUNDLE=/certs/ca.crt       # new env var for CA cert
```

### Application Changes Required
- Add `MINIO_CA_BUNDLE` env var to `config.py` and pass to boto3 client
- Change `NEO4J_SCHEME` default to `neo4j+s` in config.py
- Update `DATABASE_URL` handling to support SSL parameters (SQLAlchemy asyncpg supports `ssl_cert`, `ssl_key`, `ssl_root_cert`)

**Minimal code change in `app/db/database.py`:**
```python
# When ssl_mode is "require" or higher, pass SSL context to asyncpg
# This is a runtime configuration, not a code change for cert validation
```

---

## 3. mTLS for Local Agents

### Current State
Agents authenticate to the API using an API key sent via `X-Agent-Key` header. The key is a bcrypt hash stored in the database. This is a shared-secret model.

### Target State
Agents authenticate using client certificates (mTLS). The API validates the agent certificate against the internal CA. This removes the shared secret from the request path.

### Implementation

**Certificate issuance flow:**
1. Agent boots and generates a private key + CSR (or uses an HSM-backed key)
2. Agent sends CSR + device serial to `/agent/enroll` endpoint
3. API validates the device against the organization database
4. API signs the CSR with the internal Agent CA (or forwards to step-ca)
5. Agent receives certificate + CA bundle, stores them securely
6. Agent uses certificate for all subsequent API calls

**Enrollment endpoint (new route in auth.py):**
```
POST /api/v1/auth/agent/enroll
Body: { "device_serial": "...", "csr_pem": "..." }
Response: { "cert_pem": "...", "ca_cert_pem": "...", "expires_at": "..." }
```

**Agent certificate requirements:**
- CN = agent UUID (agent_id)
- O = organization UUID
- Extended Key Usage = `clientAuth`
- Certificate lifetime: 90 days (rotated via re-enrollment)
- Serial number tracked in `LocalAgent` table for revocation

**API validates mTLS client cert using:**
```python
# In the API server (Traefik or uvicorn with SSL):
ssl_context = ssl.create_default_context(
    ssl.Purpose.CLIENT_AUTH,
    cafile="/certs/agent-ca.crt"
)
ssl_context.verify_mode = ssl.CERT_REQUIRED   # mTLS — we require client cert
ssl_context.load_cert_chain(certfile="server.crt", keyfile="server.key")
```

**For the initial implementation (Phase 3), the X-Agent-Key path is retained as a fallback.**

### Application Changes Required
- New `/agent/enroll` endpoint (signs CSRs for approved agents)
- Update `LocalAgent` model to store `certificate_serial`, `certificate_expires_at`
- Add `AGENT_CA_CERT`, `AGENT_CA_KEY` env vars for CSR signing
- Update `get_agent_auth` dependency to accept either X-Agent-Key OR mTLS client cert

---

## 4. Key Configuration Variables

| Variable | Purpose | Default |
|---|---|---|
| `EXTERNAL_URL` | Public HTTPS URL of the API | `http://localhost:8000` |
| `NEO4J_SCHEME` | `bolt` or `neo4j+s` | `bolt` |
| `MINIO_ENDPOINT` | `http://...` or `https://...` | `http://minio:9000` |
| `MINIO_CA_BUNDLE` | Path to internal CA cert for MinIO | unset |
| `AGENT_CA_CERT` | Path to agent signing CA cert | unset |
| `AGENT_CA_KEY` | Path to agent signing CA private key | unset |
| `SSL_MODE` | PostgreSQL SSL mode (`disable`, `require`, `verify-ca`, `verify-full`) | `disable` |
| `SSL_CERT_PATH` | Path to PostgreSQL client cert | unset |
| `SSL_KEY_PATH` | Path to PostgreSQL client key | unset |
| `SSL_ROOT_CERT_PATH` | Path to PostgreSQL CA cert | unset |

---

## 5. Certificate Rotation

| Component | Rotation Frequency | Method |
|---|---|---|
| Let's Encrypt (external) | 90 days (auto) | ACME HTTP01 or DNS01 |
| Internal services (step-ca) | 30 days | step-certificates auto-renewal |
| Agent certificates | 90 days | Agent re-enrollment via `/agent/enroll` |
| Database client certs | Annual | Cron job, update Kubernetes secret |

---

## 6. Development Environment

**Local development without TLS is acceptable** — the application runs on HTTP internally. TLS is a deployment concern.

For local mTLS testing:
```bash
# Generate test CA and agent certs using step CLI
step ca certificate agent-001 agent-001.crt agent-001.key --ca=/certs/root.crt --ca-key=/certs/root.key
```

**Environment:**
```bash
# .env for local development (no TLS)
NEO4J_SCHEME=bolt
MINIO_ENDPOINT=http://minio:9000
SSL_MODE=disable
```

---

## 7. Security Considerations

- Private keys for internal CAs must never leave the infrastructure
- Agent CA key should be stored in a vault (HashiCorp Vault, AWS KMS) in production
- mTLS certificates should use an EKU of `clientAuth` to prevent agent certs from being used as server certs
- Certificate revocation must be checked via CRL or OCSP for production mTLS
- `X-Agent-Key` fallback should be deprecated after mTLS is proven in production (with a deprecation warning)

---

## 8. Phasing

**Phase 3A (minimal viable):**
- Add Traefik with Let's Encrypt for external HTTPS
- Set `EXTERNAL_URL` in configuration

**Phase 3B (internal TLS):**
- Configure PostgreSQL SSL with `ssl_mode=require`
- Set `NEO4J_SCHEME=neo4j+s`
- Add `MINIO_ENDPOINT=https://...`

**Phase 3C (agent mTLS):**
- Add `/agent/enroll` endpoint
- Implement CSR signing
- Update agent SDK to support certificate-based auth
- Retain X-Agent-Key as fallback

---

## 9. Verification

After each phase, verify with:
```bash
# External TLS
curl -v https://api.netdiscoverit.com/health

# Internal TLS (PostgreSQL)
psql "postgresql://user:pass@postgres:5432/netdiscoverit?sslmode=verify-ca&sslrootcert=/certs/ca.crt"

# Agent mTLS (after Phase 3C)
curl --cert agent-001.crt --key agent-001.key https://api.netdiscoverit.com/api/v1/agents
```
