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

variable "lambda_package_zip_path" {
  description = "Path to the deployment zip built by infrastructure/scripts/build_lambda.sh for fetch_repo."
  type        = string
}

variable "lambda_architectures" {
  description = "Lambda instruction set. arm64 (Graviton2) is the default for production AWS deployments."
  type        = list(string)
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
