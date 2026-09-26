variable "name_prefix" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "workspaces_bucket_name" {
  type = string
}

variable "workspaces_bucket_arn" {
  description = "ARN of the S3 workspaces bucket. Scoped to ws/* -- the whole prefix tree, not one run: unlike a human-facing IAM policy, a Lambda invocation has no natural condition key for \"only this run's UUID\" without STS session tags (real per-run isolation is enforced by S3Workspace's prefix-joining in code, and by the policy gate's writable_paths check -- this IAM scope is the outer, coarser boundary, not the only one). Documented here rather than pretended away."
  type        = string
}

variable "analysis_model_id" {
  description = "Bedrock model ID resolved for ModelRole.ANALYSIS (core_py.bedrock_models) -- the IAM policy is scoped to exactly the model IDs actually used, never bedrock:* across all models."
  type        = string
}

variable "code_model_id" {
  description = "Bedrock model ID resolved for ModelRole.CODE, or null if not yet qualified (PLAN.md 3.4/3.8) -- when null, no IAM statement is added for it, matching bedrock_models.py's own fail-loud behavior for an unconfigured role."
  type        = string
  default     = null
}

variable "fetch_doc_lambda_arn" {
  description = "ARN of the fetch_doc Lambda. This module's role gets lambda:InvokeFunction scoped to exactly this ARN -- the only other Lambda agent_phase may ever call."
  type        = string
}

variable "fetch_doc_lambda_name" {
  type = string
}

variable "create_guardrail" {
  description = "Task 3.7-tf: create a real Bedrock Guardrail (prompt-attack filter, CLAUDE.md's Layer-1 defense backstop) and wire it into this Lambda. Default true for real AWS. infrastructure/envs/local sets this false -- Bedrock Guardrails are a control-plane API (creating/managing a guardrail resource), a different surface than bedrock-runtime's InvokeModel, and support on Floci is unconfirmed; skipping it locally keeps the rest of this module (and everything downstream) testable without depending on that unknown."
  type        = bool
  default     = true
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "lambda_package_zip_path" {
  description = "Path to the built deployment zip (infrastructure/scripts/build_lambda.sh ... agent_phase). Required -- the real handler already exists (PLAN.md 3.3/3.4/3.5/3.8)."
  type        = string
}

variable "lambda_runtime" {
  type    = string
  default = "python3.14"
}

variable "lambda_architectures" {
  description = "arm64 (Graviton2) default for real AWS; infrastructure/envs/local overrides to x86_64 -- Floci does not cross-emulate arm64."
  type        = list(string)
  default     = ["arm64"]
}

variable "lambda_handler" {
  type    = string
  default = "agent_phase.handler.handler"
}

variable "extra_environment_variables" {
  type    = map(string)
  default = {}
}

variable "lambda_timeout_seconds" {
  description = "Generous: a discovery/plan or implement phase involves multiple Bedrock round-trips plus tool calls, unlike the quicker fetch_repo/fetch_doc Lambdas."
  type        = number
  default     = 300
}

variable "lambda_memory_mb" {
  type    = number
  default = 1024
}

variable "log_retention_days" {
  type    = number
  default = 14
}
