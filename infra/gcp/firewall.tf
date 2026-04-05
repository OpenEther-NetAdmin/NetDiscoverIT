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
