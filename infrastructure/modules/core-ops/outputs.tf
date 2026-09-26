output "lambda_function_name" {
  description = "Name of the core_ops Lambda function."
  value       = aws_lambda_function.core_ops.function_name
}

output "lambda_function_arn" {
  description = "ARN of the core_ops Lambda function."
  value       = aws_lambda_function.core_ops.arn
}

output "lambda_role_arn" {
  description = "ARN of the core_ops Lambda's execution role. Never grant this role any bedrock:* action -- CLAUDE.md invariant #1."
  value       = aws_iam_role.core_ops_lambda.arn
}
