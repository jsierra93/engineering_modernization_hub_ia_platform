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

variable "events_table_name" {
  description = "Name of the DynamoDB events table (from the persistence module)."
  type        = string
}

variable "events_table_arn" {
  description = "ARN of the DynamoDB events table (from the persistence module). The Lambda role is scoped to this table only."
  type        = string
}

variable "workspaces_bucket_arn" {
  description = "ARN of the S3 workspaces bucket (from the persistence module). The Lambda role is scoped to read-only access on the JUnit results prefix only (ws/*/junit/*)."
  type        = string
}

variable "lambda_source_dir" {
  description = <<-EOT
    Directory zipped (via data.archive_file) into the deployment artifact
    for lambda core_ops. The real Python build for services/core_ops is
    being produced in parallel (see PLAN.md 2.4/2.5/2.6) and is not wired
    yet; this defaults to a placeholder stub handler shipped inside this
    module so it stays structurally valid on its own, mirroring
    infrastructure/modules/api's pattern exactly. Once the real Lambda
    package exists, point this at its build output directory -- no other
    change needed.
  EOT
  type        = string
  default     = null
}

variable "lambda_package_zip_path" {
  description = <<-EOT
    Path to an already-built deployment zip (e.g. the output of
    infrastructure/scripts/build_lambda.sh, once it grows a core_ops
    target). When set, this is deployed directly and `lambda_source_dir` /
    data.archive_file are skipped entirely. Leave null to keep using the
    placeholder source directory zipped on the fly.
  EOT
  type        = string
  default     = null
}

variable "lambda_runtime" {
  description = "Lambda runtime for lambda core_ops. python3.14 is GA, matching infrastructure/modules/api."
  type        = string
  default     = "python3.14"
}

variable "lambda_architectures" {
  description = "Lambda instruction set. arm64 (Graviton2) is the default for production AWS deployments."
  type        = list(string)
  default     = ["arm64"]
}

variable "lambda_handler" {
  description = "Lambda handler entrypoint for lambda core_ops. Matches services/core_ops/src/core_ops's expected module path once its real handler exists."
  type        = string
  default     = "core_ops.handler.handler"
}

variable "extra_environment_variables" {
  description = "Additional Lambda environment variables merged on top of this module's own."
  type        = map(string)
  default     = {}
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout for lambda core_ops."
  type        = number
  default     = 30
}

variable "lambda_memory_mb" {
  description = "Lambda memory for lambda core_ops."
  type        = number
  default     = 256
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the core_ops Lambda."
  type        = number
  default     = 14
}
