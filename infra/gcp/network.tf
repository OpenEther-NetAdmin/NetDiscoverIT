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
