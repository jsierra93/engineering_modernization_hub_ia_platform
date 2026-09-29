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

output "cognito_user_pool_id" {
  description = "Cognito user pool ID for token generation"
  value       = module.identity.user_pool_id
}

output "cognito_issuer_url" {
  value = module.identity.issuer_url
}

output "cognito_cli_client_id" {
  value = module.identity.cli_client_id
}

output "cognito_backstage_client_id" {
  value = module.identity.backstage_client_id
}

output "cognito_backstage_client_secret" {
  value     = module.identity.backstage_client_secret
  sensitive = true
}

output "notifications_queue_url" {
  value = module.notifications.queue_url
}

output "sandbox_ecr_repository_url" {
  value = module.sandbox_network.ecr_repository_url
}
