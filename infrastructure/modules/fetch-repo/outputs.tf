output "lambda_function_name" {
  description = "Name of the fetch_repo Lambda function."
  value       = module.lambda.function_name
}

output "lambda_function_arn" {
  description = "ARN of the fetch_repo Lambda function."
  value       = module.lambda.function_arn
}

output "lambda_role_arn" {
  description = "ARN of the fetch_repo Lambda's execution role."
  value       = module.lambda.role_arn
}

output "github_token_secret_arn" {
  description = "ARN of the GitHub token secret container. Set its real value out-of-band -- never via Terraform."
  value       = aws_secretsmanager_secret.github_token.arn
}

output "github_token_secret_name" {
  description = "Name of the GitHub token secret container."
  value       = aws_secretsmanager_secret.github_token.name
}
