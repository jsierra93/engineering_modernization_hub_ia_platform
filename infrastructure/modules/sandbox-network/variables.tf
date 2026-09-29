variable "name_prefix" {
  description = "Prefix applied to all resource names created by this module (e.g. \"modhub-personal\")."
  type        = string
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}

variable "aws_region" {
  description = "Region this network is created in. Used to derive a default availability zone and for the sandbox task's awslogs configuration."
  type        = string
}

variable "availability_zone" {
  description = "Availability zone for the single public subnet. Defaults to \"<aws_region>a\" when left null -- a prototype needs exactly one AZ, not multi-AZ redundancy nobody asked for."
  type        = string
  default     = null
}

variable "vpc_cidr" {
  description = "CIDR block for the sandbox VPC."
  type        = string
  default     = "10.60.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the single public subnet the sandbox Fargate task runs in."
  type        = string
  default     = "10.60.1.0/24"
}

variable "sandbox_cpu" {
  description = "Fargate task-level CPU units for the sandbox task definition (e.g. 256 = 0.25 vCPU). Must be a valid Fargate cpu/memory combination together with var.sandbox_memory."
  type        = string
  default     = "256"
}

variable "sandbox_memory" {
  description = "Fargate task-level memory (MiB) for the sandbox task definition. Must be a valid Fargate cpu/memory combination together with var.sandbox_cpu."
  type        = string
  default     = "512"
}

variable "sandbox_architecture" {
  description = <<-EOT
    CPU architecture for the sandbox Fargate task. arm64 (Graviton) is the
    default for production AWS deployments for price-performance reasons.
  EOT
  type        = string
  default     = "arm64"

  validation {
    condition     = contains(["arm64", "x86_64"], var.sandbox_architecture)
    error_message = "sandbox_architecture must be \"arm64\" or \"x86_64\"."
  }
}

variable "sandbox_image_tag" {
  description = <<-EOT
    Image tag the sandbox task definition references, inside the ECR
    repository this module creates. Defaults to a tag that does not exist
    yet on purpose -- pushing the actual sandbox image (built under
    sandbox/ by a parallel task) is out of this module's scope. The task
    definition is still structurally valid Terraform; it just cannot
    successfully RunTask until an image is pushed under this tag.
  EOT
  type        = string
  default     = "unbuilt"
}

variable "sandbox_container_name" {
  description = "Name of the single container in the sandbox task definition. Referenced by infrastructure/modules/orchestration's ECS RunTask.sync ContainerOverrides -- keep these in sync."
  type        = string
  default     = "sandbox"
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the sandbox task's awslogs driver."
  type        = number
  default     = 14
}

variable "ecr_force_delete" {
  description = "Allow Terraform to delete the sandbox ECR repository even if it still holds images. Convenient for a throwaway prototype env; leave false anywhere images matter."
  type        = bool
  default     = false
}
