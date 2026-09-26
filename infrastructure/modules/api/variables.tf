variable "name_prefix" {
  description = "Prefix applied to all resource names created by this module (e.g. \"modhub-personal\")."
  type        = string
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}

variable "runs_table_name" {
  description = "Name of the DynamoDB runs table (from the persistence module)."
  type        = string
}

variable "runs_table_arn" {
  description = "ARN of the DynamoDB runs table (from the persistence module). The Lambda role is scoped to this table and its indexes only."
  type        = string
}

variable "state_machine_arn" {
  description = "ARN of the orchestration state machine (from the orchestration module). The Lambda role may only StartExecution on this state machine."
  type        = string
}

variable "lambda_source_dir" {
  description = <<-EOT
    Directory zipped (via data.archive_file) into the deployment artifact for
    lambda api. The real Python build for services/api is being produced in
    parallel (see PLAN.md 1.6) and is not wired yet; this defaults to a
    placeholder stub handler shipped inside this module so the module stays
    structurally valid on its own. Once the real Lambda package exists,
    point this at its build output directory (e.g.
    "../../../services/api/dist") to wire it in - no other change needed.
  EOT
  type        = string
  default     = null
}

variable "lambda_package_zip_path" {
  description = <<-EOT
    Path to an already-built deployment zip (e.g. the output of
    infrastructure/scripts/build_lambda.sh). When set, this is deployed
    directly and `lambda_source_dir` / data.archive_file are skipped
    entirely - use this for a real, dependency-bundled artifact. Leave
    null to keep using the placeholder (or any other) source directory
    zipped on the fly.
  EOT
  type        = string
  default     = null
}

variable "lambda_runtime" {
  description = "Lambda runtime for lambda api. python3.14 is GA (not preview -- that's python3.15), and every direct dependency (strands-agents, pydantic, pydantic-core, boto3, moto) publishes cp314 wheels as of 2026-09-25."
  type        = string
  default     = "python3.14"
}

variable "lambda_architectures" {
  description = "Lambda instruction set. arm64 (Graviton2) for the same reason the sandbox Fargate task uses ARM64 in the design artifact: better price-performance. Deliberate here, not the AWS default (x86_64) left unset."
  type        = list(string)
  default     = ["arm64"]
}

variable "lambda_handler" {
  description = "Lambda handler entrypoint for lambda api. Matches services/api/src/api/handler.py's module path (package api, module handler, function handler) now that the real artifact is wired in - not the placeholder stub's own handler.main."
  type        = string
  default     = "api.handler.handler"
}

variable "extra_environment_variables" {
  description = "Additional Lambda environment variables merged on top of the module's own (RUNS_TABLE_NAME, MODHUB_STATE_MACHINE_ARN). Used by envs/local to point the bundled boto3 clients at a local emulator endpoint (AWS_ENDPOINT_URL) - never needed against real AWS."
  type        = map(string)
  default     = {}
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout for lambda api. Kept short - this Lambda only creates a Run record and starts a Step Functions execution, or reads a Run back."
  type        = number
  default     = 10
}

variable "lambda_memory_mb" {
  description = "Lambda memory for lambda api."
  type        = number
  default     = 256
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the api Lambda."
  type        = number
  default     = 14
}

variable "cors_allow_origins" {
  description = "Allowed CORS origins for the HTTP API. Tightened later once Backstage (Fase 5) has a fixed origin."
  type        = list(string)
  default     = ["*"]
}
