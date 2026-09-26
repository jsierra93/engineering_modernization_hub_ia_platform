variable "aws_region" {
  description = "AWS region to deploy the personal prototype environment into. No account ID is ever hardcoded - it is resolved from the credentials used to run Terraform."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short project name used to build the resource name prefix."
  type        = string
  default     = "modhub"
}

variable "environment" {
  description = "Environment name, used in the resource name prefix and tags."
  type        = string
  default     = "personal"
}
