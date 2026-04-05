#!/bin/bash
# infra/gcp/scripts/cloud-startup.sh
# Runs on first boot of cloud-vm. Sets up the full NetDiscoverIT cloud stack.
set -euo pipefail
exec > /var/log/startup-script.log 2>&1
echo "=== NetDiscoverIT cloud-vm startup: $(date) ==="

# ─── Install Docker ──────────────────────────────────────────────────────────
apt-get update -y
apt-get install -y ca-certificates curl gnupg git python3 openssl

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

pip3 install cryptography --break-system-packages 2>/dev/null || pip3 install cryptography

systemctl enable docker
systemctl start docker

# ─── Clone repo ──────────────────────────────────────────────────────────────
cd /opt
git clone https://github.com/OpenEther-NetAdmin/NetDiscoverIT.git netdiscoverit
cd /opt/netdiscoverit

# ─── Get this VM's external IP from GCP metadata server ─────────────────────
EXTERNAL_IP=$(curl -sf -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip")
echo "External IP: ${EXTERNAL_IP}"

# ─── Generate secrets ────────────────────────────────────────────────────────
POSTGRES_PASSWORD=$(openssl rand -hex 24)
NEO4J_PASSWORD=$(openssl rand -hex 24)
JWT_SECRET_KEY=$(openssl rand -hex 48)
INTERNAL_API_KEY=$(openssl rand -hex 24)
CREDENTIAL_ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
MINIO_ACCESS_KEY=$(openssl rand -hex 12)
MINIO_SECRET_KEY=$(openssl rand -hex 24)
VAULT_TOKEN=$(openssl rand -hex 24)

# ─── Write .env ──────────────────────────────────────────────────────────────
cat > /opt/netdiscoverit/.env << EOF
APP_NAME=NetDiscoverIT
APP_ENV=testing
APP_DEBUG=false
APP_URL=http://${EXTERNAL_IP}:3000
APP_API_URL=http://${EXTERNAL_IP}:8000

POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=netdiscoverit
POSTGRES_USER=netdiscoverit
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=

NEO4J_HOST=neo4j
NEO4J_PORT=7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=${NEO4J_PASSWORD}

JWT_SECRET_KEY=${JWT_SECRET_KEY}
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15

INTERNAL_API_KEY=${INTERNAL_API_KEY}
CREDENTIAL_ENCRYPTION_KEY=${CREDENTIAL_ENCRYPTION_KEY}

VAULT_ENABLED=true
VAULT_ADDR=http://vault:8200
VAULT_TOKEN=${VAULT_TOKEN}
VAULT_SECRET_PATH=secret/data/netdiscoverit

MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY}
MINIO_SECRET_KEY=${MINIO_SECRET_KEY}
MINIO_BUCKET=netdiscoverit
MINIO_ENDPOINT=http://minio:9000

CORS_ORIGINS=http://${EXTERNAL_IP}:3000,http://localhost:3000
EOF

# ─── Start cloud services (all except agent) ─────────────────────────────────
docker compose up -d postgres redis neo4j vault ollama minio minio-init api frontend

# ─── Wait for API health ─────────────────────────────────────────────────────
echo "Waiting for API to become healthy..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null 2>&1; then
    echo "API healthy after ${i} attempts ($(( i * 10 ))s)"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "WARNING: API did not become healthy after 300s. Check: docker compose logs api"
  fi
  sleep 10
done

echo "=== cloud-vm startup complete ==="
echo "  API:      http://${EXTERNAL_IP}:8000"
echo "  Frontend: http://${EXTERNAL_IP}:3000"
