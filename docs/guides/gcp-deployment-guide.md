# GCP Deployment Guide for NetDiscoverIT

A complete beginner's guide to deploying NetDiscoverIT to Google Cloud Platform for end-to-end testing.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Step 1: Install Required Tools](#step-1-install-required-tools)
4. [Step 2: Configure GCP Project](#step-2-configure-gcp-project)
5. [Step 3: Enable Required APIs](#step-3-enable-required-apis)
6. [Step 4: Authenticate gcloud CLI](#step-4-authenticate-gcloud-cli)
7. [Step 5: Create SSH Key](#step-5-create-ssh-key)
8. [Step 6: Configure Terraform Variables](#step-6-configure-terraform-variables)
9. [Step 7: Initialize Terraform](#step-7-initialize-terraform)
10. [Step 8: Preview Deployment](#step-8-preview-deployment)
11. [Step 9: Deploy to GCP](#step-9-deploy-to-gcp)
12. [Step 10: Monitor Startup Scripts](#step-10-monitor-startup-scripts)
13. [Step 11: Verify Deployment](#step-11-verify-deployment)
14. [Step 12: Access the Application](#step-12-access-the-application)
15. [Cleanup (Important!)](#cleanup-important)
16. [Troubleshooting](#troubleshooting)

---

## Overview

This deployment creates a two-tier architecture in GCP that mirrors a real customer deployment:

```
┌─────────────────────────────────────────────────────────────────┐
│                    GCP Project: netdiscoverit-test              │
│                                                                 │
│  ┌─────────────────────────┐    VPC     ┌─────────────────────┐│
│  │     cloud-vpc           │   Peering  │     onprem-vpc      ││
│  │     (10.0.0.0/16)       │◄──────────►│     (10.1.0.0/16)   ││
│  │                         │            │                     ││
│  │  ┌─────────────────┐    │            │  ┌───────────────┐  ││
│  │  │   cloud-vm      │    │            │  │   agent-vm    │  ││
│  │  │   (e2-highmem-4)     │            │  │(e2-standard-4)│  ││
│  │  │                 │    │            │  │               │  ││
│  │  │  • API (:8000)  │    │            │  │ • Agent       │  ││
│  │  │  • Frontend     │    │            │  │ • Containerlab│  ││
│  │  │  • PostgreSQL   │    │            │  │   - spine1    │  ││
│  │  │  • Neo4j        │    │            │  │   - spine2    │  ││
│  │  │  • Redis        │    │            │  │   - leaf1     │  ││
│  │  │  • MinIO        │    │            │  │   - leaf2     │  ││
│  │  │  • Vault        │    │            │  │   - server1   │  ││
│  │  │  • Ollama       │    │            │  │               │  ││
│  │  └─────────────────┘    │            │  └───────────────┘  ││
│  └─────────────────────────┘            └─────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

**What you'll get:**
- **cloud-vm**: The full NetDiscoverIT platform (API, databases, frontend)
- **agent-vm**: Simulated on-premises environment with Containerlab network devices

---

## Prerequisites

Before starting, ensure you have:

- [ ] A GCP account with billing enabled
- [ ] A GCP project created (or permission to create one)
- [ ] Local machine with internet access
- [ ] Admin access to your GCP project

---

## Step 1: Install Required Tools

### 1.1 Install gcloud CLI

**Linux (Debian/Ubuntu):**
```bash
# Add Google Cloud SDK repository
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list

# Import Google Cloud public key
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -

# Update and install
sudo apt-get update && sudo apt-get install google-cloud-cli
```

**macOS:**
```bash
brew install google-cloud-sdk
```

**Windows:**
Download from: https://cloud.google.com/sdk/docs/install

### 1.2 Install Terraform

**Linux (Debian/Ubuntu):**
```bash
# Add HashiCorp GPG key
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg

# Add repository
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list

# Install
sudo apt update && sudo apt install terraform
```

**macOS:**
```bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

**Windows:**
Download from: https://developer.hashicorp.com/terraform/install

### 1.3 Verify Installations

```bash
gcloud --version
terraform version
```

---

## Step 2: Configure GCP Project

### 2.1 Find Your Project ID

1. Go to [GCP Console](https://console.cloud.google.com/)
2. Click the project selector at the top (next to "Google Cloud")
3. Note your **Project ID** (not the Project Name)

If you need to create a new project:
```bash
# Create project (replace with your desired ID)
gcloud projects create netdiscoverit-test --name="NetDiscoverIT Test"

# Set as default project
gcloud config set project netdiscoverit-test
```

### 2.2 Set Default Project

```bash
# Set your project as default
gcloud config set project YOUR_PROJECT_ID

# Example:
# gcloud config set project netdiscoverit-test-123456
```

---

## Step 3: Enable Required APIs

GCP requires specific APIs to be enabled. Run this single command:

```bash
gcloud services enable compute.googleapis.com \
                       servicenetworking.googleapis.com \
                       cloudresourcemanager.googleapis.com \
                       iam.googleapis.com
```

This may take 1-2 minutes. Wait for the message:
```
Operation finished successfully.
```

---

## Step 4: Authenticate gcloud CLI

### 4.1 Login to GCP

```bash
gcloud auth login
```

This will:
1. Open a browser window
2. Ask you to sign in with your Google account
3. Ask for permission to access GCP
4. Return to terminal with confirmation

### 4.2 Set Application Default Credentials

```bash
gcloud auth application-default login
```

This is **required** for Terraform to authenticate with GCP.

---

## Step 5: Create SSH Key

You need an SSH key to access the VMs.

### 5.1 Check for Existing Key

```bash
ls -la ~/.ssh/id_rsa.pub
```

If the file exists, skip to Step 5.3.

### 5.2 Create New SSH Key (if needed)

```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""
```

This creates:
- `~/.ssh/id_rsa` (private key - keep secret!)
- `~/.ssh/id_rsa.pub` (public key - will be uploaded to VMs)

### 5.3 Copy Your Public Key

```bash
cat ~/.ssh/id_rsa.pub
```

Copy the entire output, which looks like:
```
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQ... user@hostname
```

---

## Step 6: Configure Terraform Variables

### 6.1 Navigate to the Terraform Directory

```bash
cd /home/openether/NetDiscoverIT/infra/gcp
```

### 6.2 Copy the Example Variables File

```bash
cp terraform.tfvars.example terraform.tfvars
```

### 6.3 Edit terraform.tfvars

Open the file in your preferred editor:

```bash
nano terraform.tfvars
# or
vim terraform.tfvars
# or
code terraform.tfvars
```

### 6.4 Fill in Your Values

Replace the placeholder values with your actual information:

```hcl
# infra/gcp/terraform.tfvars

project_id   = "your-actual-project-id"     # From Step 2.1
region       = "us-central1"                 # Change if you prefer another region
zone         = "us-central1-a"               # Change if you prefer another zone
ssh_username = "your-gcp-username"           # Your GCP account username (e.g., jane.doe@gmail.com)
ssh_pub_key  = "ssh-rsa AAAA... user@host"   # Your public key from Step 5.3
```

**Important Notes:**

| Variable | Description | Example |
|----------|-------------|---------|
| `project_id` | Your GCP Project ID (not name) | `my-project-123456` |
| `region` | GCP region for resources | `us-central1`, `europe-west1` |
| `zone` | Specific zone within region | `us-central1-a`, `europe-west1-b` |
| `ssh_username` | Your GCP account email or username | `jane.doe@gmail.com` |
| `ssh_pub_key` | Full contents of your public key file | `ssh-rsa AAAA... user@host` |

### 6.5 Example Complete terraform.tfvars

```hcl
project_id   = "netdiscoverit-test-123456"
region       = "us-central1"
zone         = "us-central1-a"
ssh_username = "jane.doe@gmail.com"
ssh_pub_key  = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDH9... jane.doe@MacBook-Pro.local"
```

---

## Step 7: Initialize Terraform

Terraform needs to download the Google Cloud provider.

```bash
cd /home/openether/NetDiscoverIT/infra/gcp
terraform init
```

**Expected output:**
```
Initializing the backend...

Initializing provider plugins...
- Finding hashicorp/google versions matching "~> 5.0"...
- Installing hashicorp/google v5.x.x...

Terraform has been successfully initialized!
```

---

## Step 8: Preview Deployment

Before creating resources, preview what Terraform will do:

```bash
terraform plan
```

This shows a detailed plan of all resources to be created. You should see:

```
Plan: 12 to add, 0 to change, 0 to destroy.
```

**Resources to be created:**
- 2 VPC networks (cloud-vpc, onprem-vpc)
- 2 Subnets
- 2 VPC peerings (bidirectional)
- 5 Firewall rules
- 2 Compute instances (cloud-vm, agent-vm)

---

## Step 9: Deploy to GCP

### 9.1 Run the Deployment

From the project root directory:

```bash
cd /home/openether/NetDiscoverIT
make gcp-up
```

Or from the infra/gcp directory:

```bash
cd /home/openether/NetDiscoverIT/infra/gcp
terraform apply -auto-approve
```

### 9.2 Wait for Completion

The deployment takes approximately **5-10 minutes**:

```
google_compute_network.cloud: Creating...
google_compute_network.onprem: Creating...
...
google_compute_instance.agent_vm: Creation complete after 2m30s

Apply complete! Resources: 12 added, 0 changed, 0 destroyed.
```

### 9.3 Note Your Outputs

After completion, Terraform outputs important information:

```
Outputs:

api_url = "http://XX.XXX.XXX.XXX:8000"
cloud_vm_external_ip = "XX.XXX.XXX.XXX"
frontend_url = "http://XX.XXX.XXX.XXX:3000"
ssh_agent_vm = "gcloud compute ssh agent-vm --zone=us-central1-a --project=your-project --tunnel-through-iap"
ssh_cloud_vm = "gcloud compute ssh cloud-vm --zone=us-central1-a --project=your-project --tunnel-through-iap"
```

**Save these values!** You'll need them to access your deployment.

---

## Step 10: Monitor Startup Scripts

The VMs run startup scripts automatically. Monitor their progress:

### 10.1 Monitor Cloud VM (API + Frontend)

```bash
make gcp-log-cloud
```

Or directly:
```bash
gcloud compute ssh cloud-vm --zone=us-central1-a --tunnel-through-iap -- 'tail -f /var/log/startup-script.log'
```

**Wait for:**
```
=== cloud-vm startup complete ===
  API:      http://XX.XXX.XXX.XXX:8000
  Frontend: http://XX.XXX.XXX.XXX:3000
```

This takes approximately **5-8 minutes** (downloading Docker images takes time).

### 10.2 Monitor Agent VM

In a separate terminal:
```bash
make gcp-log-agent
```

**Wait for:**
```
=== agent-vm startup complete ===
  Agent pointed at cloud API: http://10.0.1.2:8000
  Containerlab nodes: spine1=172.20.20.X spine2=172.20.20.X leaf1=172.20.20.X leaf2=172.20.20.X
```

This takes approximately **3-5 minutes** (Containerlab nodes need to boot).

---

## Step 11: Verify Deployment

### 11.1 Check API Health

```bash
curl http://YOUR_CLOUD_VM_IP:8000/api/v1/health
```

Expected response:
```json
{"status": "healthy", "version": "0.1.0"}
```

### 11.2 Check Frontend

Open in browser:
```
http://YOUR_CLOUD_VM_IP:3000
```

You should see the NetDiscoverIT login page.

### 11.3 Verify Containerlab on Agent VM

SSH into agent VM:
```bash
make gcp-ssh-agent
```

Check Containerlab status:
```bash
containerlab inspect -t /opt/clab/topology.yml
```

Expected output:
```
+---+-----------------+--------------+-----------------------+------+---------+----------------+----------------------+
| # |      Name       | Container ID |        Image          | Kind |  State  |  IPv4 Address  |     IPv6 Address     |
+---+-----------------+--------------+-----------------------+------+---------+----------------+----------------------+
| 1 | clab-netdis...  | abc123       | ghcr.io/nokia/srlinux | srl  | running | 172.20.20.2/24 | 3fff:172:20:20::2/80 |
| 2 | clab-netdis...  | def456       | ghcr.io/nokia/srlinux | srl  | running | 172.20.20.3/24 | 3fff:172:20:20::3/80 |
| 3 | clab-netdis...  | ghi789       | ghcr.io/nokia/srlinux | srl  | running | 172.20.20.4/24 | 3fff:172:20:20::4/80 |
| 4 | clab-netdis...  | jkl012       | ghcr.io/nokia/srlinux | srl  | running | 172.20.20.5/24 | 3fff:172:20:20::5/80 |
| 5 | clab-netdis...  | mno345       | alpine:latest         | linux| running | 172.20.20.6/24 | 3fff:172:20:20::6/80 |
+---+-----------------+--------------+-----------------------+------+---------+----------------+----------------------+
```

### 11.4 Test SSH to a Containerlab Device

```bash
ssh admin@<spine1-ip>
```

Password: `NokiaSrl1!`

You should see the SR Linux CLI:
```
Welcome to the SR Linux CLI.
--{ running }--[ ]--
A:spine1#
```

Type `exit` to leave.

---

## Step 12: Access the Application

### 12.1 Get Your URLs

```bash
make gcp-status
```

This displays:
```
api_url = "http://XX.XXX.XXX.XXX:8000"
frontend_url = "http://XX.XXX.XXX.XXX:3000"
```

### 12.2 Access Frontend

Open `http://YOUR_CLOUD_VM_IP:3000` in your browser.

### 12.3 Access API Documentation

Open `http://YOUR_CLOUD_VM_IP:8000/docs` in your browser.

### 12.4 Check Discovered Devices

After the agent completes a discovery cycle:
```bash
curl http://YOUR_CLOUD_VM_IP:8000/api/v1/devices
```

---

## Cleanup (Important!)

**GCP resources cost money!** Always clean up when not testing.

### Destroy All Resources

```bash
make gcp-down
```

Or:
```bash
cd /home/openether/NetDiscoverIT/infra/gcp
terraform destroy -auto-approve
```

Expected output:
```
Plan: 0 to add, 0 to change, 12 to destroy.
...
Destroy complete! Resources: 12 destroyed.
```

### Cost Estimate

| Resource | Cost |
|----------|------|
| cloud-vm (e2-highmem-4) + agent-vm (e2-standard-4) | ~$0.40/hour (~$9.60/day) |
| Persistent disks | ~$0.10/GB/month |
| Network egress | ~$0.12/GB |

**Tips to minimize costs:**
1. Always run `make gcp-down` when done
2. Use preemptible/spot VMs for 60-80% savings (acceptable for testing)
3. Set up billing alerts in GCP Console

---

## Troubleshooting

### Common Issues and Solutions

#### Error: "Permission denied" or "Access denied"

**Cause:** Your account lacks permissions.

**Solution:**
1. Ensure you're logged in: `gcloud auth login`
2. Ensure application credentials are set: `gcloud auth application-default login`
3. Verify your account has Owner or Editor role on the project

---

#### Error: "API not enabled"

**Cause:** Required GCP APIs not enabled.

**Solution:**
```bash
gcloud services enable compute.googleapis.com \
                       servicenetworking.googleapis.com \
                       cloudresourcemanager.googleapis.com \
                       iam.googleapis.com
```

---

#### Error: "Quota exceeded"

**Cause:** Project has insufficient quota.

**Solution:**
1. Go to GCP Console → IAM & Admin → Quotas
2. Request quota increase for:
   - Compute Engine API: In-use IPs
   - Compute Engine API: CPUs

---

#### SSH Connection Failed

**Cause:** IAP not enabled or firewall misconfigured.

**Solution:**
1. Enable IAP API:
```bash
gcloud services enable iap.googleapis.com
```

2. Verify firewall rules exist:
```bash
gcloud compute firewall-rules list --filter="name~iap"
```

---

#### VM Startup Script Stuck

**Cause:** Script may be waiting on network or package download.

**Solution:**
1. SSH into the VM: `make gcp-ssh-cloud`
2. Check the log: `tail -f /var/log/startup-script.log`
3. Check Docker status: `docker ps -a`
4. Check if containers are running: `docker compose ps`

---

#### API Not Responding

**Cause:** Services may still be starting or crashed.

**Solution:**
1. SSH into cloud-vm: `make gcp-ssh-cloud`
2. Check container status: `docker compose ps`
3. Check logs: `docker compose logs api`
4. Check if port is listening: `netstat -tlnp | grep 8000`

---

#### Containerlab Nodes Not Starting

**Cause:** Docker may not have enough resources.

**Solution:**
1. SSH into agent-vm: `make gcp-ssh-agent`
2. Check Docker: `docker ps -a`
3. Check Containerlab: `containerlab inspect -t /opt/clab/topology.yml`
4. Check logs: `journalctl -u docker --no-pager -n 50`

---

### Getting Help

1. **Check logs first:**
   - `make gcp-log-cloud`
   - `make gcp-log-agent`

2. **Check Terraform state:**
   ```bash
   cd infra/gcp
   terraform show
   ```

3. **Check GCP Console:**
   - Compute Engine → VM instances
   - VPC network → VPC networks
   - Logging → Logs Explorer

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `make gcp-init` | Initialize Terraform |
| `make gcp-plan` | Preview changes |
| `make gcp-up` | Deploy to GCP |
| `make gcp-down` | Destroy all resources |
| `make gcp-status` | Show IPs and URLs |
| `make gcp-ssh-cloud` | SSH into cloud VM |
| `make gcp-ssh-agent` | SSH into agent VM |
| `make gcp-log-cloud` | Tail cloud VM startup log |
| `make gcp-log-agent` | Tail agent VM startup log |

---

## File Locations

| File | Purpose |
|------|---------|
| `infra/gcp/variables.tf` | Input variable definitions |
| `infra/gcp/main.tf` | Terraform and provider config |
| `infra/gcp/network.tf` | VPCs, subnets, peering |
| `infra/gcp/firewall.tf` | Firewall rules |
| `infra/gcp/compute.tf` | VM instances |
| `infra/gcp/outputs.tf` | Output values |
| `infra/gcp/terraform.tfvars` | Your configuration (do not commit!) |
| `infra/gcp/scripts/cloud-startup.sh` | Cloud VM bootstrap |
| `infra/gcp/scripts/agent-startup.sh` | Agent VM bootstrap |
| `infra/gcp/clab/topology.yml` | Containerlab topology |

---

## Next Steps

After successful deployment:

1. **Explore the frontend** at `http://YOUR_IP:3000`
2. **Test the API** at `http://YOUR_IP:8000/docs`
3. **SSH into agent VM** and explore Containerlab devices
4. **Run agent discovery** manually to test the pipeline
5. **Review the architecture** to understand the two-tier model

**Remember:** Always run `make gcp-down` when finished testing!
