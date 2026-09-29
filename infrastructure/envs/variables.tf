variable "aws_region" {
  description = "AWS region to deploy the personal prototype environment into. No account ID is ever hardcoded - it is resolved from the credentials used to run Terraform. us-east-2 because that is where this account's Bedrock model access was granted -- model access is per-region, so deploying elsewhere would fail InvokeModel with AccessDenied despite correct IAM."
  type        = string
  default     = "us-east-2"
}

variable "analysis_model_id" {
  description = "Bedrock model ID (or inference profile) for ModelRole.ANALYSIS. Any model works as long as it has an entry in model_pricing."
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "code_model_id" {
  description = "Bedrock model ID (or inference profile) for ModelRole.CODE. Any model works as long as it has an entry in model_pricing."
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "model_pricing" {
  description = "USD per 1k tokens for every model ID used above, keyed exactly as configured. Versioned by hand; the budget ledger depends on it."
  type = map(object({
    input_usd_per_1k  = number
    output_usd_per_1k = number
  }))
  default = {
    "us.anthropic.claude-haiku-4-5-20251001-v1:0" = {
      input_usd_per_1k  = 0.001
      output_usd_per_1k = 0.005
    }
  }
}

variable "cors_allow_origins" {
  description = "Origins allowed by the HTTP API's CORS. Backstage reaches the API through its own backend, so the browser origin is only needed for direct browser clients."
  type        = list(string)
  default     = ["http://localhost:3000"]
}

variable "lambda_architecture" {
  description = "CPU architecture for every Lambda and the sandbox task. x86_64 because the machine that builds the zips and the sandbox image cannot produce arm64; switch to arm64 where it can."
  type        = string
  default     = "x86_64"

  validation {
    condition     = contains(["arm64", "x86_64"], var.lambda_architecture)
    error_message = "lambda_architecture must be \"arm64\" or \"x86_64\"."
  }
}

variable "sandbox_image_tag" {
  description = "Tag of the sandbox image in ECR. deploy.sh --sandbox <tag> writes it to sandbox.auto.tfvars."
  type        = string
  default     = "v4"
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
