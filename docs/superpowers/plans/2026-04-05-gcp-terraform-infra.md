# GCP Terraform Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create Terraform infrastructure in `infra/gcp/` that provisions two GCP VMs (cloud platform + on-prem agent) across separate VPCs with VPC peering, startup scripts that auto-configure each VM on first boot, Containerlab topology for simulated network devices, and Makefile convenience targets.

**Architecture:** Two VPCs (`cloud-vpc 10.0.0.0/16`, `onprem-vpc 10.1.0.0/16`) connected via bidirectional VPC peering to simulate a real customer WAN link. `cloud-vm` runs the full docker-compose stack (minus agent); `agent-vm` runs Containerlab (SR Linux spine-leaf topology) and the NetDiscoverIT agent pointed at cloud-vm's internal IP.

**Tech Stack:** Terraform >= 1.5, hashicorp/google provider ~> 5.0, Debian 12 VMs, Containerlab, Nokia SR Linux (free GHCR images)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `infra/gcp/variables.tf` | Create | All input variables with defaults |
| `infra/gcp/main.tf` | Create | Terraform + Google provider config |
| `infra/gcp/network.tf` | Create | Two VPCs, subnets, bidirectional VPC peering |
| `infra/gcp/firewall.tf` | Create | Four firewall rules (cloud-ingress, agent-to-api, iap-ssh x2, internal-clab) |
| `infra/gcp/scripts/cloud-startup.sh` | Create | Boot: install Docker, clone repo, generate secrets, `docker compose up` |
| `infra/gcp/clab/topology.yml` | Create | Nokia SR Linux spine-leaf: spine1, spine2, leaf1, leaf2, server1 |
| `infra/gcp/scripts/agent-startup.sh` | Create | Boot: install Docker+Containerlab, deploy clab, extract IPs, start agent |
| `infra/gcp/compute.tf` | Create | cloud-vm and agent-vm instances with startup scripts |
| `infra/gcp/outputs.tf` | Create | External IPs, SSH commands, API/frontend URLs |
| `Makefile` | Modify | Add gcp-init, gcp-up, gcp-down, gcp-ssh-* targets |

---

### Task 1: Variables

**Files:**
- Create: `infra/gcp/variables.tf`

- [ ] **Step 1: Create variables.tf**

```hcl
# infra/gcp/variables.tf

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone"
  type        = string
  default     = "us-central1-a"
}

variable "cloud_machine_type" {
  description = "Machine type for the cloud VM (API + all platform services, including Ollama)"
  type        = string
  default     = "e2-highmem-4"
}

variable "agent_machine_type" {
  description = "Machine type for the agent VM (Containerlab + agent)"
  type        = string
  default     = "e2-standard-4"
}

variable "ssh_username" {
  description = "Linux username for SSH access (must match your gcloud account username)"
  type        = string
}

variable "ssh_pub_key" {
  description = "SSH public key to inject into both VMs (content of ~/.ssh/id_rsa.pub)"
  type        = string
}

variable "repo_url" {
  description = "Git URL of the NetDiscoverIT repo to clone on boot"
  type        = string
  default     = "https://github.com/OpenEther-NetAdmin/NetDiscoverIT.git"
}

variable "disk_size_gb" {
  description = "Boot disk size in GB for each VM (50 minimum for Docker images)"
  type        = number
  default     = 50
}
```

- [ ] **Step 2: Create terraform.tfvars.example** (users copy this — never commit filled-in values)

```hcl
# infra/gcp/terraform.tfvars.example
# Copy to terraform.tfvars and fill in your values

project_id   = "your-gcp-project-id"
region       = "us-central1"
zone         = "us-central1-a"
ssh_username = "your-gcp-username"
ssh_pub_key  = "ssh-rsa AAAA..."
```

- [ ] **Step 3: Add terraform.tfvars to .gitignore**

Open `infra/gcp/.gitignore` (create it) with content:
```
terraform.tfvars
.terraform/
*.tfstate
*.tfstate.backup
.terraform.lock.hcl
```

- [ ] **Step 4: Commit**

```bash
cd /home/openether/NetDiscoverIT
git add infra/gcp/variables.tf infra/gcp/terraform.tfvars.example infra/gcp/.gitignore
git commit -m "feat(infra): add Terraform variable definitions for GCP test env"
```

---

### Task 2: Provider Configuration

**Files:**
- Create: `infra/gcp/main.tf`

- [ ] **Step 1: Create main.tf**

```hcl
# infra/gcp/main.tf

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}
```

- [ ] **Step 2: Run terraform init to verify provider downloads**

```bash
cd infra/gcp
terraform init
```

Expected output: `Terraform has been successfully initialized!`

If terraform is not installed: `sudo apt-get install -y terraform` or follow https://developer.hashicorp.com/terraform/install

- [ ] **Step 3: Commit**

```bash
git add infra/gcp/main.tf
git commit -m "feat(infra): add Terraform provider configuration"
```

---

### Task 3: Network (VPCs + Subnets + Peering)

**Files:**
- Create: `infra/gcp/network.tf`

- [ ] **Step 1: Create network.tf**

```hcl
# infra/gcp/network.tf

# ─── Cloud VPC (platform services) ──────────────────────────────────────────
resource "google_compute_network" "cloud" {
  name                    = "cloud-vpc"
  auto_create_subnetworks = false
  description             = "NetDiscoverIT cloud platform (API, databases, frontend)"
}

resource "google_compute_subnetwork" "cloud" {
  name          = "cloud-subnet"
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.cloud.id
  description   = "cloud-vm subnet"
}

# ─── On-prem VPC (agent + Containerlab) ─────────────────────────────────────
resource "google_compute_network" "onprem" {
  name                    = "onprem-vpc"
  auto_create_subnetworks = false
  description             = "Simulated on-premises network (agent + Containerlab devices)"
}

resource "google_compute_subnetwork" "onprem" {
  name          = "onprem-subnet"
  ip_cidr_range = "10.1.1.0/24"
  region        = var.region
  network       = google_compute_network.onprem.id
  description   = "agent-vm subnet"
}

# ─── VPC Peering (bidirectional — both directions required by GCP) ───────────
resource "google_compute_network_peering" "cloud_to_onprem" {
  name         = "cloud-to-onprem"
  network      = google_compute_network.cloud.self_link
  peer_network = google_compute_network.onprem.self_link
}

resource "google_compute_network_peering" "onprem_to_cloud" {
  name         = "onprem-to-cloud"
  network      = google_compute_network.onprem.self_link
  peer_network = google_compute_network.cloud.self_link

  # Must wait for first peering to be established before creating the reverse
  depends_on = [google_compute_network_peering.cloud_to_onprem]
}
```

- [ ] **Step 2: Validate**

```bash
cd infra/gcp
terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 3: Commit**

```bash
git add infra/gcp/network.tf
git commit -m "feat(infra): add two VPCs with subnets and bidirectional VPC peering"
```

---

### Task 4: Firewall Rules

**Files:**
- Create: `infra/gcp/firewall.tf`

- [ ] **Step 1: Create firewall.tf**

```hcl
# infra/gcp/firewall.tf

# ─── Cloud VM: public ingress for testing ────────────────────────────────────
# Allows direct access to API (8000) and frontend (3000) from anywhere.
# Lock these down or remove for any non-test deployment.
resource "google_compute_firewall" "cloud_ingress" {
  name        = "cloud-ingress"
  network     = google_compute_network.cloud.name
  description = "Testing only: allow HTTP access to API and frontend from anywhere"

  allow {
    protocol = "tcp"
    ports    = ["80", "443", "3000", "8000"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["cloud-vm"]
}

# ─── Agent VM → Cloud VM: API port ───────────────────────────────────────────
resource "google_compute_firewall" "agent_to_api" {
  name        = "agent-to-api"
  network     = google_compute_network.cloud.name
  description = "Allow agent VM to reach the API over VPC peering"

  allow {
    protocol = "tcp"
    ports    = ["8000"]
  }

  source_ranges = [google_compute_subnetwork.onprem.ip_cidr_range]
  target_tags   = ["cloud-vm"]
}

# ─── IAP SSH: cloud VMs ──────────────────────────────────────────────────────
# 35.235.240.0/20 is Google's IAP proxy range — required for gcloud compute ssh --tunnel-through-iap
resource "google_compute_firewall" "iap_ssh_cloud" {
  name        = "iap-ssh-cloud"
  network     = google_compute_network.cloud.name
  description = "Allow IAP SSH tunneling to cloud-vm"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
}

resource "google_compute_firewall" "iap_ssh_onprem" {
  name        = "iap-ssh-onprem"
  network     = google_compute_network.onprem.name
  description = "Allow IAP SSH tunneling to agent-vm"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
}

# ─── Containerlab internal traffic ───────────────────────────────────────────
# Containerlab creates Docker bridge networks; virtual nodes communicate over
# the host's Docker networking. Allow all intra-subnet traffic.
resource "google_compute_firewall" "internal_clab" {
  name        = "internal-clab"
  network     = google_compute_network.onprem.name
  description = "Allow all intra-subnet traffic for Containerlab virtual nodes"

  allow {
    protocol = "all"
  }

  source_ranges = [google_compute_subnetwork.onprem.ip_cidr_range]
}
```

- [ ] **Step 2: Validate**

```bash
cd infra/gcp
terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 3: Commit**

```bash
git add infra/gcp/firewall.tf
git commit -m "feat(infra): add firewall rules (cloud ingress, IAP SSH, agent-to-api, clab internal)"
```

---

### Task 5: Cloud VM Startup Script

**Files:**
- Create: `infra/gcp/scripts/cloud-startup.sh`

This script runs once on first boot via GCP's `startup-script` metadata key. It reads the VM's own external IP from the GCP metadata server (no Terraform templating needed).

- [ ] **Step 1: Create the script**

```bash
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
```

- [ ] **Step 2: Make executable**

```bash
chmod +x infra/gcp/scripts/cloud-startup.sh
```

- [ ] **Step 3: Commit**

```bash
git add infra/gcp/scripts/cloud-startup.sh
git commit -m "feat(infra): add cloud-vm startup script (Docker + stack bootstrap)"
```

---

### Task 6: Containerlab Topology

**Files:**
- Create: `infra/gcp/clab/topology.yml`

SR Linux is used (not Arista cEOS) because images are freely available from GHCR with no account required.

- [ ] **Step 1: Create topology.yml**

```yaml
# infra/gcp/clab/topology.yml
# Nokia SR Linux spine-leaf topology for NetDiscoverIT agent testing.
# 4 routers/switches the agent will discover via SSH + LLDP neighbor detection.

name: netdiscoverit-test-lab

topology:
  nodes:
    spine1:
      kind: nokia_srlinux
      image: ghcr.io/nokia/srlinux:24.10.1
      startup-config: |
        set / system name host-name spine1
        set / interface ethernet-1/1 admin-state enable
        set / interface ethernet-1/2 admin-state enable

    spine2:
      kind: nokia_srlinux
      image: ghcr.io/nokia/srlinux:24.10.1
      startup-config: |
        set / system name host-name spine2
        set / interface ethernet-1/1 admin-state enable
        set / interface ethernet-1/2 admin-state enable

    leaf1:
      kind: nokia_srlinux
      image: ghcr.io/nokia/srlinux:24.10.1
      startup-config: |
        set / system name host-name leaf1
        set / interface ethernet-1/1 admin-state enable
        set / interface ethernet-1/49 admin-state enable
        set / interface ethernet-1/50 admin-state enable

    leaf2:
      kind: nokia_srlinux
      image: ghcr.io/nokia/srlinux:24.10.1
      startup-config: |
        set / system name host-name leaf2
        set / interface ethernet-1/1 admin-state enable
        set / interface ethernet-1/49 admin-state enable
        set / interface ethernet-1/50 admin-state enable

    server1:
      kind: linux
      image: alpine:latest

  links:
    # Spine-leaf uplinks
    - endpoints: [spine1:e1-1, leaf1:e1-49]
    - endpoints: [spine1:e1-2, leaf2:e1-49]
    - endpoints: [spine2:e1-1, leaf1:e1-50]
    - endpoints: [spine2:e1-2, leaf2:e1-50]
    # Server access link
    - endpoints: [leaf1:e1-1, server1:eth1]
```

- [ ] **Step 2: Commit**

```bash
git add infra/gcp/clab/topology.yml
git commit -m "feat(infra): add Containerlab SR Linux spine-leaf topology for agent testing"
```

---

### Task 7: Agent VM Startup Script

**Files:**
- Create: `infra/gcp/scripts/agent-startup.sh`

This file is used as a Terraform `templatefile()`. Terraform interpolates `${cloud_vm_internal_ip}` and `${repo_url}` before passing it to the VM. **All bash `$` variables must be escaped as `$$`** to survive Terraform's template rendering.

- [ ] **Step 1: Create the script**

```bash
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
```

- [ ] **Step 2: Make executable**

```bash
chmod +x infra/gcp/scripts/agent-startup.sh
```

- [ ] **Step 3: Commit**

```bash
git add infra/gcp/scripts/agent-startup.sh
git commit -m "feat(infra): add agent-vm startup script (Containerlab + agent bootstrap)"
```

---

### Task 8: Compute Instances

**Files:**
- Create: `infra/gcp/compute.tf`

- [ ] **Step 1: Create compute.tf**

```hcl
# infra/gcp/compute.tf

# ─── Cloud VM (API + databases + frontend) ───────────────────────────────────
resource "google_compute_instance" "cloud_vm" {
  name         = "cloud-vm"
  machine_type = var.cloud_machine_type
  zone         = var.zone
  tags         = ["cloud-vm"]
  description  = "NetDiscoverIT cloud platform: API, PostgreSQL, Neo4j, Redis, MinIO, Vault, Ollama, Frontend"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = var.disk_size_gb
      type  = "pd-ssd"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.cloud.id
    access_config {
      # Ephemeral public IP — sufficient for testing
    }
  }

  metadata = {
    ssh-keys = "${var.ssh_username}:${var.ssh_pub_key}"
  }

  metadata_startup_script = file("${path.module}/scripts/cloud-startup.sh")
}

# ─── Agent VM (Containerlab + NetDiscoverIT agent) ───────────────────────────
resource "google_compute_instance" "agent_vm" {
  name         = "agent-vm"
  machine_type = var.agent_machine_type
  zone         = var.zone
  tags         = ["agent-vm"]
  description  = "Simulated on-prem: Containerlab SR Linux devices + NetDiscoverIT agent"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = var.disk_size_gb
      type  = "pd-ssd"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.onprem.id
    access_config {
      # Ephemeral public IP — needed for IAP SSH access
    }
  }

  metadata = {
    ssh-keys = "${var.ssh_username}:${var.ssh_pub_key}"
  }

  # templatefile() injects cloud VM's internal IP and repo URL into the bash script.
  # Bash variables in the script are escaped as $$ to survive Terraform rendering.
  metadata_startup_script = templatefile("${path.module}/scripts/agent-startup.sh", {
    cloud_vm_internal_ip = google_compute_instance.cloud_vm.network_interface[0].network_ip
    repo_url             = var.repo_url
  })

  # Agent VM must be created after cloud VM so we can inject the cloud IP
  depends_on = [
    google_compute_instance.cloud_vm,
    google_compute_network_peering.onprem_to_cloud,
  ]
}
```

- [ ] **Step 2: Validate**

```bash
cd infra/gcp
terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 3: Commit**

```bash
git add infra/gcp/compute.tf
git commit -m "feat(infra): add cloud-vm and agent-vm compute instances"
```

---

### Task 9: Outputs

**Files:**
- Create: `infra/gcp/outputs.tf`

- [ ] **Step 1: Create outputs.tf**

```hcl
# infra/gcp/outputs.tf

output "cloud_vm_external_ip" {
  description = "Public IP of cloud-vm (access API and frontend from here)"
  value       = google_compute_instance.cloud_vm.network_interface[0].access_config[0].nat_ip
}

output "cloud_vm_internal_ip" {
  description = "Internal IP of cloud-vm (used by agent to reach API over VPC peering)"
  value       = google_compute_instance.cloud_vm.network_interface[0].network_ip
}

output "agent_vm_external_ip" {
  description = "Public IP of agent-vm"
  value       = google_compute_instance.agent_vm.network_interface[0].access_config[0].nat_ip
}

output "api_url" {
  description = "NetDiscoverIT API URL"
  value       = "http://${google_compute_instance.cloud_vm.network_interface[0].access_config[0].nat_ip}:8000"
}

output "frontend_url" {
  description = "NetDiscoverIT frontend URL"
  value       = "http://${google_compute_instance.cloud_vm.network_interface[0].access_config[0].nat_ip}:3000"
}

output "ssh_cloud_vm" {
  description = "Command to SSH into cloud-vm via IAP"
  value       = "gcloud compute ssh cloud-vm --zone=${var.zone} --project=${var.project_id} --tunnel-through-iap"
}

output "ssh_agent_vm" {
  description = "Command to SSH into agent-vm via IAP"
  value       = "gcloud compute ssh agent-vm --zone=${var.zone} --project=${var.project_id} --tunnel-through-iap"
}

output "startup_log_cloud" {
  description = "Command to tail cloud-vm startup log"
  value       = "gcloud compute ssh cloud-vm --zone=${var.zone} --project=${var.project_id} --tunnel-through-iap -- 'tail -f /var/log/startup-script.log'"
}

output "startup_log_agent" {
  description = "Command to tail agent-vm startup log"
  value       = "gcloud compute ssh agent-vm --zone=${var.zone} --project=${var.project_id} --tunnel-through-iap -- 'tail -f /var/log/startup-script.log'"
}
```

- [ ] **Step 2: Final validate of complete config**

```bash
cd infra/gcp
terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 3: Commit**

```bash
git add infra/gcp/outputs.tf
git commit -m "feat(infra): add Terraform outputs (IPs, SSH commands, URLs)"
```

---

### Task 10: Makefile Targets

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add GCP section to the Makefile**

Add after the `# RELEASE` section at the bottom of `Makefile`:

```makefile
# =============================================================================
# GCP TEST ENVIRONMENT
# =============================================================================
# Prerequisites: gcloud CLI authenticated, terraform installed, terraform.tfvars
# filled in at infra/gcp/terraform.tfvars (see terraform.tfvars.example).
# =============================================================================
GCP_ZONE ?= us-central1-a
GCP_PROJECT ?= $(shell cd infra/gcp && terraform output -raw project_id 2>/dev/null || echo "not-initialized")

gcp-init:
	cd infra/gcp && terraform init

gcp-plan:
	cd infra/gcp && terraform plan

gcp-up:
	cd infra/gcp && terraform apply -auto-approve
	@echo ""
	@echo "Startup scripts are running on the VMs. Monitor with:"
	@echo "  make gcp-log-cloud"
	@echo "  make gcp-log-agent"

gcp-down:
	cd infra/gcp && terraform destroy -auto-approve

gcp-status:
	cd infra/gcp && terraform output

gcp-ssh-cloud:
	gcloud compute ssh cloud-vm --zone=$(GCP_ZONE) --tunnel-through-iap

gcp-ssh-agent:
	gcloud compute ssh agent-vm --zone=$(GCP_ZONE) --tunnel-through-iap

gcp-log-cloud:
	gcloud compute ssh cloud-vm --zone=$(GCP_ZONE) --tunnel-through-iap -- 'tail -f /var/log/startup-script.log'

gcp-log-agent:
	gcloud compute ssh agent-vm --zone=$(GCP_ZONE) --tunnel-through-iap -- 'tail -f /var/log/startup-script.log'
```

- [ ] **Step 2: Update help target** — add GCP entries to the `@echo` block inside the `help:` target:

```makefile
	@echo ""
	@echo "GCP test environment:"
	@echo "  $(YELLOW)gcp-init$(NC)        - Initialize Terraform"
	@echo "  $(YELLOW)gcp-plan$(NC)        - Dry-run Terraform plan"
	@echo "  $(YELLOW)gcp-up$(NC)          - Provision GCP test environment"
	@echo "  $(YELLOW)gcp-down$(NC)        - Destroy GCP test environment"
	@echo "  $(YELLOW)gcp-status$(NC)      - Show VM IPs and URLs"
	@echo "  $(YELLOW)gcp-ssh-cloud$(NC)   - SSH into cloud-vm"
	@echo "  $(YELLOW)gcp-ssh-agent$(NC)   - SSH into agent-vm"
	@echo "  $(YELLOW)gcp-log-cloud$(NC)   - Tail cloud-vm startup log"
	@echo "  $(YELLOW)gcp-log-agent$(NC)   - Tail agent-vm startup log"
```

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "feat(infra): add GCP Makefile targets (gcp-init, gcp-up, gcp-down, gcp-ssh-*, gcp-log-*)"
```

---

### Task 11: Final Validation + Dry Run

- [ ] **Step 1: Run full terraform validate**

```bash
cd infra/gcp
terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 2: Run terraform plan against real project (dry run — no resources created)**

Create `infra/gcp/terraform.tfvars` from the example:
```bash
cp infra/gcp/terraform.tfvars.example infra/gcp/terraform.tfvars
# Edit and fill in your project_id, ssh_username, ssh_pub_key
```

Then:
```bash
cd infra/gcp
terraform plan
```

Expected output includes:
- `Plan: 12 to add, 0 to change, 0 to destroy.`
- Resources: 2 networks, 2 subnets, 2 peerings, 5 firewall rules, 2 instances

If you see auth errors: `gcloud auth application-default login`

- [ ] **Step 3: Verify file structure**

```bash
find infra/gcp -type f | sort
```

Expected:
```
infra/gcp/.gitignore
infra/gcp/clab/topology.yml
infra/gcp/compute.tf
infra/gcp/firewall.tf
infra/gcp/main.tf
infra/gcp/network.tf
infra/gcp/outputs.tf
infra/gcp/scripts/agent-startup.sh
infra/gcp/scripts/cloud-startup.sh
infra/gcp/terraform.tfvars.example
infra/gcp/variables.tf
```

- [ ] **Step 4: Commit final state**

```bash
git add -A
git commit -m "chore(infra): validate complete Terraform GCP config — plan: 12 resources"
```

---

## Verification Checklist (Post-Apply)

After `make gcp-up` completes:

1. `make gcp-status` shows all outputs (IPs, URLs, SSH commands)
2. `make gcp-log-cloud` — tail log until you see `cloud-vm startup complete`
3. `curl http://<cloud_vm_external_ip>:8000/api/v1/health` → 200
4. `make gcp-log-agent` — tail log until you see `agent-vm startup complete`
5. SSH into agent-vm → `containerlab inspect -t /opt/clab/topology.yml` shows 5 running containers
6. SSH into agent-vm → `ssh admin@<spine1-ip>` (password: `NokiaSrl1!`) connects to SR Linux CLI
7. Agent logs show a completed discovery cycle: `collector → normalizer → sanitizer → vectorizer → uploader`
8. `curl http://<cloud_vm_external_ip>:8000/api/v1/devices` returns discovered devices

## Cost Reminder

- cloud-vm (e2-highmem-4) + agent-vm (e2-standard-4): ~$0.40/hr (~$9.60/day)
- Always run `make gcp-down` when done testing
- Add `--preemptible` to machine configs in `compute.tf` to cut cost 60-80% (acceptable for testing)
