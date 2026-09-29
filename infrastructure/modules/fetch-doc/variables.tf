variable "name_prefix" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "lambda_package_zip_path" {
  description = "Path to the built deployment zip (infrastructure/scripts/build_lambda.sh ... fetch_doc)."
  type        = string
}

variable "lambda_architectures" {
  type = list(string)
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
