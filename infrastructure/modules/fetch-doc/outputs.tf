output "lambda_function_name" {
  value = aws_lambda_function.fetch_doc.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.fetch_doc.arn
}

output "lambda_role_arn" {
  value = aws_iam_role.fetch_doc_lambda.arn
}
