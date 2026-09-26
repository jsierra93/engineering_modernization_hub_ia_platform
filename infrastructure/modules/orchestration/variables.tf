variable "name_prefix" {
  description = "Prefix applied to all resource names created by this module (e.g. \"modhub-personal\")."
  type        = string
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}

variable "asl_definition_path" {
  description = "Path to the Amazon States Language JSON definition for the modernization run state machine. Defaults to the ASL file shipped inside this module (./asl/state_machine.asl.json) when left null."
  type        = string
  default     = null
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the state machine execution logs."
  type        = number
  default     = 14
}

# --- Sandbox wiring (task 2.3/2.3-tf) -----------------------------------
# The Baseline state (see ./asl/state_machine.asl.json) is a real
# arn:aws:states:::ecs:runTask.sync integration against the sandbox-network
# module's cluster/task definition. These variables are templated into the
# ASL JSON (see templatefile() in main.tf) and also scope this module's own
# ecs:RunTask/iam:PassRole IAM grant to exactly one task definition -- never
# a wildcard across all task definitions or all roles.

variable "sandbox_cluster_arn" {
  description = "ARN of the sandbox-network module's ECS cluster. The state machine's ecs:RunTask grant is conditioned on this exact cluster."
  type        = string
}

variable "sandbox_task_definition_arn" {
  description = "ARN of the sandbox-network module's task definition (specific revision). The state machine's ecs:RunTask grant is scoped to exactly this ARN -- no other task definition can be launched with this role."
  type        = string
}

variable "sandbox_execution_role_arn" {
  description = "ARN of the sandbox-network module's task execution role (not a task role -- the sandbox has none, per CLAUDE.md invariant #8). The state machine's iam:PassRole grant is scoped to exactly this ARN, conditioned on it only ever being passed to ecs-tasks.amazonaws.com."
  type        = string
}

variable "sandbox_container_name" {
  description = "Name of the sandbox task's single container, for the Baseline state's ContainerOverrides. Must match sandbox-network's var.sandbox_container_name."
  type        = string
}

variable "sandbox_subnet_ids" {
  description = "Subnet IDs the sandbox Fargate task launches into (the sandbox-network module's public subnet)."
  type        = list(string)
}

variable "sandbox_security_group_ids" {
  description = "Security group IDs attached to the sandbox Fargate task (the sandbox-network module's egress-443-only security group)."
  type        = list(string)
}

variable "sandbox_assign_public_ip" {
  description = "Whether the sandbox Fargate task gets a public IP. Must be true in the public network mode (no NAT gateway) so the task can reach the internet for its HTTPS egress (presigned S3 URLs, package indexes)."
  type        = bool
  default     = true
}
