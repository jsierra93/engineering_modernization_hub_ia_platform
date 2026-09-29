variable "function_name" {
  description = "Lambda function name; the log group /aws/lambda/<function_name>."
  type        = string
}

variable "role_name" {
  description = "Execution role name. Defaults to \"<function_name>-lambda-role\"; set it to keep a name an existing role already has."
  type        = string
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "package_zip_path" {
  description = "Path to the deployment zip built by infrastructure/scripts/build_lambda.sh."
  type        = string
}

variable "handler" {
  type = string
}

variable "architectures" {
  type = list(string)
}

variable "runtime" {
  type    = string
  default = "python3.14"
}

variable "environment" {
  type    = map(string)
  default = {}
}

variable "timeout_seconds" {
  type = number
}

variable "memory_mb" {
  type = number
}

variable "log_retention_days" {
  type    = number
  default = 14
}
