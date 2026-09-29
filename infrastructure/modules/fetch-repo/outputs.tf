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
