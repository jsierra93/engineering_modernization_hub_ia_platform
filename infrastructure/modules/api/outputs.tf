output "api_endpoint" {
  description = "Base invoke URL for the HTTP API ($default stage)."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "lambda_function_name" {
  description = "Name of the api Lambda function."
  value       = aws_lambda_function.api.function_name
}

output "lambda_function_arn" {
  description = "ARN of the api Lambda function."
  value       = aws_lambda_function.api.arn
}

output "lambda_role_arn" {
  description = "ARN of the api Lambda's execution role."
  value       = aws_iam_role.api_lambda.arn
}

output "http_api_id" {
  description = "ID of the HTTP API."
  value       = aws_apigatewayv2_api.http_api.id
}
