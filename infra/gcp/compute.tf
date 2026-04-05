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
