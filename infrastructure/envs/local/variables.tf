variable "aws_region" {
  description = "Region Floci reports/accepts. Not a real AWS region call - Floci runs entirely on localhost."
  type        = string
  default     = "us-east-1"
}

variable "floci_endpoint" {
  description = "Floci's local AWS-emulator endpoint. Never point this anywhere but localhost."
  type        = string
  default     = "http://localhost:4566"

  validation {
    condition     = can(regex("^http://(localhost|127\\.0\\.0\\.1)(:[0-9]+)?$", var.floci_endpoint))
    error_message = "floci_endpoint must be an http://localhost or http://127.0.0.1 URL - this environment must never point at a real AWS endpoint."
  }
}

variable "project_name" {
  description = "Short project name used to build the resource name prefix."
  type        = string
  default     = "modhub"
}

variable "lambda_package_path" {
  description = "Path to the real lambda api deployment artifact, built by infrastructure/scripts/build_lambda.sh. Must exist before `terraform apply` - run the build script first."
  type        = string
  default     = null
}
