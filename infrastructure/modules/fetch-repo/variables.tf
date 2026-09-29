variable "name_prefix" {
  description = "Prefix applied to all resource names created by this module (e.g. \"modhub-personal\")."
  type        = string
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}

variable "workspaces_bucket_name" {
  description = "Name of the S3 workspaces bucket (from the persistence module)."
  type        = string
}

variable "workspaces_bucket_arn" {
  description = "ARN of the S3 workspaces bucket (from the persistence module). The Lambda role is scoped to this bucket's \"ws/*\" prefix only -- never the whole bucket."
  type        = string
}

variable "lambda_source_dir" {
  description = <<-EOT
    Directory zipped (via data.archive_file) into the deployment artifact
    for lambda fetch_repo. The real Python build for services/fetch_repo is
    being produced in parallel (see PLAN.md 2.2) and is not wired yet; this
    defaults to a placeholder stub handler shipped inside this module so it
    stays structurally valid on its own, mirroring infrastructure/modules/
    api's pattern exactly. Once the real Lambda package exists, point this
    at its build output directory -- no other change needed.
  EOT
  type        = string
  default     = null
}

variable "lambda_package_zip_path" {
  description = <<-EOT
    Path to an already-built deployment zip (e.g. the output of
    infrastructure/scripts/build_lambda.sh, once it grows a fetch_repo
    target). When set, this is deployed directly and `lambda_source_dir` /
    data.archive_file are skipped entirely. Leave null to keep using the
    placeholder source directory zipped on the fly.
  EOT
  type        = string
  default     = null
}

variable "lambda_runtime" {
  description = "Lambda runtime for lambda fetch_repo. python3.14 is GA, matching infrastructure/modules/api."
  type        = string
  default     = "python3.14"
}

variable "lambda_architectures" {
  description = "Lambda instruction set. arm64 (Graviton2) is the default for production AWS deployments."
  type        = list(string)
  default     = ["arm64"]
}

variable "lambda_handler" {
  description = "Lambda handler entrypoint for lambda fetch_repo. Matches services/fetch_repo/src/fetch_repo's expected module path once its real handler exists."
  type        = string
  default     = "fetch_repo.handler.handler"
}

variable "extra_environment_variables" {
  description = "Additional Lambda environment variables merged on top of this module's own."
  type        = map(string)
  default     = {}
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout for lambda fetch_repo. Longer than the api Lambda's default -- downloading and sanitizing a tarball over the network takes real time."
  type        = number
  default     = 60
}

variable "lambda_memory_mb" {
  description = "Lambda memory for lambda fetch_repo."
  type        = number
  default     = 512
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the fetch_repo Lambda."
  type        = number
  default     = 14
}
