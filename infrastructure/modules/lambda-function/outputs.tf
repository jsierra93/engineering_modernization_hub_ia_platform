output "function_name" {
  value = aws_lambda_function.this.function_name
}

output "function_arn" {
  value = aws_lambda_function.this.arn
}

output "role_arn" {
  value = aws_iam_role.this.arn
}

output "role_name" {
  value = aws_iam_role.this.name
}

output "role_id" {
  value = aws_iam_role.this.id
}

output "invoke_arn" {
  value = aws_lambda_function.this.invoke_arn
}
