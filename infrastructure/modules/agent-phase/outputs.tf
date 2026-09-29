output "lambda_function_name" {
  value = module.lambda.function_name
}

output "lambda_function_arn" {
  value = module.lambda.function_arn
}

output "lambda_role_arn" {
  value = module.lambda.role_arn
}

output "guardrail_id" {
  value = local.guardrail_id
}

output "guardrail_version" {
  value = local.guardrail_version
}
