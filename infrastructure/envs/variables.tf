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

variable "resolver_model_id" {
  description = "Bedrock model ID (or inference profile) for ModelRole.RESOLVER, the objective-to-strategy classifier in λ api. A small, cheap model is enough: it needs no tools and its answer is checked against the closed candidate list. It is not part of a run's spend, so it needs no model_pricing entry."
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "code_model_id" {
  description = "Bedrock model ID (or inference profile) for ModelRole.CODE. Any model works as long as it has an entry in model_pricing."
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "model_pricing" {
  description = <<-EOT
    USD per 1k tokens for every model ID used above, keyed exactly as configured. Versioned by hand; the budget ledger depends on it.
    Base rates (per million tokens): Claude Haiku 4.5 $1 in / $5 out; Claude Sonnet 4.6 $3 in / $15 out
    (https://platform.claude.com/docs/en/about-claude/pricing, 2026-09-29). On Bedrock, regional profiles (`us.`, `eu.`, ...)
    carry a 10% premium over `global.` profiles for these models, so the `us.` entries are base x 1.1.
    Every model is on-demand, billed per token with no monthly fee. Sonnet 4.6 is the second option: it answers in this
    account on both profiles (checked 2026-09-29; Sonnet 4.5 answers too, but 4.6 is the newer one at the same price;
    Sonnet 5 / 5.5 are not available to the account). Re-check the rates against the AWS Bedrock pricing page before relying
    on them for a real budget.
  EOT
  type = map(object({
    input_usd_per_1k  = number
    output_usd_per_1k = number
  }))
  default = {
    "us.anthropic.claude-haiku-4-5-20251001-v1:0" = {
      input_usd_per_1k  = 0.0011
      output_usd_per_1k = 0.0055
    }
    "global.anthropic.claude-haiku-4-5-20251001-v1:0" = {
      input_usd_per_1k  = 0.001
      output_usd_per_1k = 0.005
    }
    "us.anthropic.claude-sonnet-4-6" = {
      input_usd_per_1k  = 0.0033
      output_usd_per_1k = 0.0165
    }
    "global.anthropic.claude-sonnet-4-6" = {
      input_usd_per_1k  = 0.003
      output_usd_per_1k = 0.015
    }
    # Not usable yet: the account gets "not available for this account" on Converse and InvokeModel (checked 2026-09-29).
    # Only a global profile exists, so there is no regional premium. Its newer tokenizer yields about 30% more tokens per text.
    "global.anthropic.claude-sonnet-5-5" = {
      input_usd_per_1k  = 0.002
      output_usd_per_1k = 0.010
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
