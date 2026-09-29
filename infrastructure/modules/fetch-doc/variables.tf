variable "name_prefix" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "lambda_package_zip_path" {
  description = "Path to the built deployment zip (infrastructure/scripts/build_lambda.sh ... fetch_doc). Unlike fetch-repo/api, this module has no placeholder source -- the real handler already exists (PLAN.md 3.6), so this is required."
  type        = string
}

variable "lambda_runtime" {
  type    = string
  default = "python3.14"
}

variable "lambda_architectures" {
  description = "Lambda CPU architecture. arm64 (Graviton2) is the default for production AWS deployments."
  type        = list(string)
  default     = ["arm64"]
}

variable "lambda_handler" {
  type    = string
  default = "fetch_doc.handler.handler"
}

variable "extra_environment_variables" {
  type    = map(string)
  default = {}
}

variable "lambda_timeout_seconds" {
  type    = number
  default = 30
}

variable "lambda_memory_mb" {
  type    = number
  default = 256
}

variable "log_retention_days" {
  type    = number
  default = 14
}
