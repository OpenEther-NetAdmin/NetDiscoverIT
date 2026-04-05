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
  description = "Machine type for the cloud VM (API + all platform services)"
  type        = string
  default     = "e2-standard-4"
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
