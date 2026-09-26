output "state_machine_arn" {
  description = "ARN of the modernization run state machine."
  value       = aws_sfn_state_machine.run.arn
}

output "state_machine_name" {
  description = "Name of the modernization run state machine."
  value       = aws_sfn_state_machine.run.name
}

output "state_machine_role_arn" {
  description = "ARN of the IAM role assumed by the state machine."
  value       = aws_iam_role.state_machine.arn
}
