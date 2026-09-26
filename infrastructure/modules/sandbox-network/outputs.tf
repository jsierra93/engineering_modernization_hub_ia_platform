output "vpc_id" {
  description = "ID of the sandbox VPC."
  value       = aws_vpc.sandbox.id
}

output "public_subnet_id" {
  description = "ID of the single public subnet the sandbox Fargate task runs in."
  value       = aws_subnet.public.id
}

output "security_group_id" {
  description = "ID of the sandbox security group (egress 443 only, no ingress)."
  value       = aws_security_group.sandbox.id
}

output "ecr_repository_url" {
  description = "URL of the ECR repository the sandbox image is pushed to (by the parallel sandbox-image task, not by this module)."
  value       = aws_ecr_repository.sandbox.repository_url
}

output "ecr_repository_arn" {
  description = "ARN of the ECR repository the sandbox image is pushed to."
  value       = aws_ecr_repository.sandbox.arn
}

output "ecs_cluster_arn" {
  description = "ARN of the Fargate ECS cluster the sandbox task runs on."
  value       = aws_ecs_cluster.sandbox.arn
}

output "ecs_cluster_name" {
  description = "Name of the Fargate ECS cluster the sandbox task runs on."
  value       = aws_ecs_cluster.sandbox.name
}

output "task_definition_arn" {
  description = "ARN of the sandbox task definition (specific revision). infrastructure/modules/orchestration's IAM role is scoped to exactly this ARN for ecs:RunTask."
  value       = aws_ecs_task_definition.sandbox.arn
}

output "task_definition_family" {
  description = "Family name of the sandbox task definition."
  value       = aws_ecs_task_definition.sandbox.family
}

output "execution_role_arn" {
  description = "ARN of the sandbox task's execution role (NOT a task role -- used only by the ECS agent to pull the image and ship logs). infrastructure/modules/orchestration's iam:PassRole grant is scoped to exactly this ARN."
  value       = aws_iam_role.execution.arn
}

output "container_name" {
  description = "Name of the sandbox task's single container, for ECS RunTask ContainerOverrides."
  value       = var.sandbox_container_name
}
