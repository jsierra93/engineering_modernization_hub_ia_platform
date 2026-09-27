output "lambda_function_arn" {
  value = aws_lambda_function.open_pr.arn
}

output "lambda_invoke_arn" {
  value = aws_lambda_function.open_pr.invoke_arn
}

output "lambda_function_name" {
  value = aws_lambda_function.open_pr.function_name
}
