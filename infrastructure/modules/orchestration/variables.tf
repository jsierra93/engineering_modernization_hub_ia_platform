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

variable "sandbox_task_timeout_seconds" {
  description = "Wall-clock cap on one sandbox task. Without it an ecs:runTask.sync state has no bound of its own and a hung container holds the run open until the service's own limits apply. Generous on purpose: it is a stuck-task backstop, not a performance budget -- max_minutes is what bounds the work."
  type        = number
  default     = 1800 # 30 min
}

variable "agent_task_timeout_seconds" {
  description = "Backstop for one agent_phase invocation; kept above that Lambda's own timeout."
  type        = number
  default     = 330
}

variable "lambda_task_timeout_seconds" {
  description = "Backstop for the fast Lambda and SQS states (fetch_repo, core_ops, notifications)."
  type        = number
  default     = 90
}

variable "approval_timeout_seconds" {
  description = "How long AwaitApproval waits for a human before the run stops. Step Functions' own default for a waitForTaskToken state is one year, which leaves the run's task token live and the run sitting in AWAITING_APPROVAL indefinitely. This is platform policy, not a per-run limit: the requester's max_minutes deliberately excludes approval wait, because it bounds the work and not the deliberation."
  type        = number
  default     = 86400 # 24 h
}

variable "sandbox_assign_public_ip" {
  description = "Whether the sandbox Fargate task gets a public IP. Must be true in the public network mode (no NAT gateway) so the task can reach the internet for its HTTPS egress (presigned S3 URLs, package indexes)."
  type        = bool
  default     = true
}

variable "fetch_repo_lambda_arn" {
  description = "ARN of the fetch_repo Lambda (module fetch-repo, task 2.2-tf). The FetchRepo state's arn:aws:states:::lambda:invoke integration targets this, and the state machine's IAM role is granted lambda:InvokeFunction scoped to exactly this ARN -- never a wildcard across all functions."
  type        = string
}

variable "agent_phase_lambda_arn" {
  description = "ARN of the agent_phase Lambda (module agent-phase, task 3.3-tf). DiscoveryPlan, Implement and Fix states invoke this with a different `phase` in the payload each time -- same Lambda, per the design's own 'una fase por llamada'."
  type        = string
}

variable "core_ops_lambda_arn" {
  description = "ARN of the core_ops Lambda (module core-ops, task 2.6-tf). Invoked at every checkpoint (record_plan after DiscoveryPlan, compute_verdict after Baseline/Verify) -- never given a task token or any write path other than through this narrow, named-action interface."
  type        = string
}

variable "notifications_queue_arn" {
  description = "ARN of the notifications module's SQS queue (task 4.3-tf). NotifyApprovalPending drops a message here the moment a run reaches AWAITING_APPROVAL -- Fase 5.4's approval bell reads from this same queue via modhub-backend's own scoped identity (task 5.2-tf), never this role's."
  type        = string
}

variable "notifications_queue_url" {
  description = "URL of the notifications module's SQS queue -- arn:aws:states:::sqs:sendMessage takes a QueueUrl, not an ARN."
  type        = string
}
