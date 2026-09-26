output "lambda_function_name" {
  description = "Name of the fetch_repo Lambda function."
  value       = aws_lambda_function.fetch_repo.function_name
}

output "lambda_function_arn" {
  description = "ARN of the fetch_repo Lambda function."
  value       = aws_lambda_function.fetch_repo.arn
}

output "lambda_role_arn" {
  description = "ARN of the fetch_repo Lambda's execution role."
  value       = aws_iam_role.fetch_repo_lambda.arn
}

output "github_token_secret_arn" {
  description = "ARN of the GitHub token secret container. Set its real value out-of-band -- never via Terraform."
  value       = aws_secretsmanager_secret.github_token.arn
}

output "github_token_secret_name" {
  description = "Name of the GitHub token secret container."
  value       = aws_secretsmanager_secret.github_token.name
}
