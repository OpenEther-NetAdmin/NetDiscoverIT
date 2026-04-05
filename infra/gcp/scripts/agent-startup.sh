#!/bin/bash
# infra/gcp/scripts/agent-startup.sh
# Terraform templatefile — ${cloud_vm_internal_ip} and ${repo_url} are injected by Terraform.
# All other bash variables use $$ to escape Terraform interpolation.
set -euo pipefail
exec > /var/log/startup-script.log 2>&1
echo "=== NetDiscoverIT agent-vm startup: $$(date) ==="

CLOUD_VM_IP="${cloud_vm_internal_ip}"
REPO_URL="${repo_url}"

# ─── Install Docker ──────────────────────────────────────────────────────────
apt-get update -y
apt-get install -y ca-certificates curl gnupg git python3 openssl jq

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian $$(. /etc/os-release && echo "$$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

systemctl enable docker
systemctl start docker

# ─── Install Containerlab ────────────────────────────────────────────────────
echo "Installing Containerlab..."
bash -c "$$(curl -sL https://get.containerlab.dev)"

# ─── Clone repo ──────────────────────────────────────────────────────────────
cd /opt
git clone $$REPO_URL netdiscoverit

# ─── Deploy Containerlab topology ────────────────────────────────────────────
mkdir -p /opt/clab
cp /opt/netdiscoverit/infra/gcp/clab/topology.yml /opt/clab/
cd /opt/clab

echo "Deploying Containerlab topology..."
containerlab deploy -t topology.yml --reconfigure

# Wait for nodes to initialize (SR Linux takes ~30s to boot)
echo "Waiting 60s for SR Linux nodes to initialize..."
sleep 60

# ─── Extract Containerlab management IPs ─────────────────────────────────────
extract_ip() {
  local node_name="$$1"
  containerlab inspect -t /opt/clab/topology.yml --format json 2>/dev/null \
    | python3 -c "
import sys, json
data = json.load(sys.stdin)
for c in data.get('Containers', []):
    name = c.get('Name', '')
    if '$$node_name' in name:
        ip = c.get('IPv4Address', '').split('/')[0]
        if ip:
            print(ip)
            break
"
}

SPINE1_IP=$$(extract_ip spine1)
SPINE2_IP=$$(extract_ip spine2)
LEAF1_IP=$$(extract_ip leaf1)
LEAF2_IP=$$(extract_ip leaf2)

echo "Containerlab IPs: spine1=$$SPINE1_IP spine2=$$SPINE2_IP leaf1=$$LEAF1_IP leaf2=$$LEAF2_IP"

# ─── Write agent config ───────────────────────────────────────────────────────
cat > /opt/netdiscoverit/configs/agent-gcp.yaml << EOF
VERSION: "0.1.0"

API_KEY: "changeme-register-this-agent"
API_ENDPOINT: "http://$$CLOUD_VM_IP:8000"

DISCOVERY_METHODS:
  - ssh
  - lldp

SCAN_INTERVAL: "1h"
SSH_TIMEOUT: 30
SNMP_TIMEOUT: 5
LOG_LEVEL: "info"

devices:
  - hostname: spine1
    ip: "$$SPINE1_IP"
    type: router
    vendor: nokia
    methods: [ssh]
    credentials:
      username: admin
      password: NokiaSrl1!

  - hostname: spine2
    ip: "$$SPINE2_IP"
    type: router
    vendor: nokia
    methods: [ssh]
    credentials:
      username: admin
      password: NokiaSrl1!

  - hostname: leaf1
    ip: "$$LEAF1_IP"
    type: switch
    vendor: nokia
    methods: [ssh]
    credentials:
      username: admin
      password: NokiaSrl1!

  - hostname: leaf2
    ip: "$$LEAF2_IP"
    type: switch
    vendor: nokia
    methods: [ssh]
    credentials:
      username: admin
      password: NokiaSrl1!

db_path: "/app/data/agent.db"
db_retention_days: 90

cloud:
  api_url: "http://$$CLOUD_VM_IP:8000"
  upload_batch_size: 100
  upload_interval_seconds: 300

sanitizer:
  enable_tier1: true
  enable_tier2: true
  enable_tier3: true
EOF

# ─── Write agent .env ────────────────────────────────────────────────────────
cat > /opt/netdiscoverit/.env << EOF
AGENT_API_KEY=changeme-register-this-agent
AGENT_API_ENDPOINT=http://$$CLOUD_VM_IP:8000
AGENT_ORG_ID=default
AGENT_LOG_LEVEL=info
CREDENTIAL_ENCRYPTION_KEY=placeholder-not-used-by-agent
EOF

# ─── Start agent (one-shot discovery cycle) ──────────────────────────────────
cd /opt/netdiscoverit
docker compose run --rm \
  -v /opt/netdiscoverit/configs/agent-gcp.yaml:/app/config/agent.yaml:ro \
  agent python -m agent.main --once

echo "=== agent-vm startup complete ==="
echo "  Agent pointed at cloud API: http://$$CLOUD_VM_IP:8000"
echo "  Containerlab nodes: spine1=$$SPINE1_IP spine2=$$SPINE2_IP leaf1=$$LEAF1_IP leaf2=$$LEAF2_IP"
