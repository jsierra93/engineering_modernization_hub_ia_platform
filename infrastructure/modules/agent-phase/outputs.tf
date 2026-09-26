output "lambda_function_name" {
  value = aws_lambda_function.agent_phase.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.agent_phase.arn
}

output "lambda_role_arn" {
  value = aws_iam_role.agent_phase_lambda.arn
}

output "guardrail_id" {
  value = local.guardrail_id
}

output "guardrail_version" {
  value = local.guardrail_version
}
