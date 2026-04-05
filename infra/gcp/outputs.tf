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
