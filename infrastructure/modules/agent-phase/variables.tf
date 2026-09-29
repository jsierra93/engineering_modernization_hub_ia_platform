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
  description = "Task 3.7-tf: create a real Bedrock Guardrail (prompt-attack filter, CLAUDE.md's Layer-1 defense backstop) and wire it into this Lambda. True for production deployments."
  type        = bool
  default     = true
}

variable "aws_region" {
  type = string
}

variable "model_pricing" {
  description = "USD per 1k tokens for each configured Bedrock model ID, keyed exactly as configured in analysis_model_id / code_model_id. Passed to the Lambda as MODHUB_MODEL_PRICING (core_py.pricing)."
  type = map(object({
    input_usd_per_1k  = number
    output_usd_per_1k = number
  }))
}

variable "lambda_package_zip_path" {
  description = "Path to the built deployment zip (infrastructure/scripts/build_lambda.sh ... agent_phase). Required -- the real handler already exists (PLAN.md 3.3/3.4/3.5/3.8)."
  type        = string
}

variable "lambda_architectures" {
  description = "Lambda CPU architecture. arm64 (Graviton2) is the default for production AWS deployments."
  type        = list(string)
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

variable "enable_invocation_logging" {
  description = <<-EOT
    Log every Bedrock request and response to CloudWatch. Account- and
    region-wide, not per-model: it also captures the api resolver's call.
    Off by default -- prompts carry repository content verbatim, so this
    is a deliberate choice, not a default.
  EOT
  type        = bool
  default     = false
}

variable "invocation_log_retention_days" {
  type    = number
  default = 7
}
