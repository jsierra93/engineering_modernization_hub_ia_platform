output "runs_table_name" {
  value = module.persistence.runs_table_name
}

output "events_table_name" {
  value = module.persistence.events_table_name
}

output "workspaces_bucket_name" {
  value = module.persistence.workspaces_bucket_name
}

output "state_machine_arn" {
  value = module.orchestration.state_machine_arn
}

output "api_endpoint" {
  description = "Base URL to hit for POST /modhub/v1/runs and GET /modhub/v1/runs/{run_id}."
  value       = module.api.api_endpoint
}
