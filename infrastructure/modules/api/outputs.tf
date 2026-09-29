output "api_endpoint" {
  description = "Base invoke URL for the HTTP API ($default stage)."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "lambda_function_name" {
  description = "Name of the api Lambda function."
  value       = module.lambda.function_name
}

output "lambda_function_arn" {
  description = "ARN of the api Lambda function."
  value       = module.lambda.function_arn
}

output "lambda_role_arn" {
  description = "ARN of the api Lambda's execution role."
  value       = module.lambda.role_arn
}

output "http_api_id" {
  description = "ID of the HTTP API."
  value       = aws_apigatewayv2_api.http_api.id
}
