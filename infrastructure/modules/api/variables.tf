variable "name_prefix" {
  description = "Prefix applied to all resource names created by this module (e.g. \"modhub-personal\")."
  type        = string
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}

variable "runs_table_name" {
  description = "Name of the DynamoDB runs table (from the persistence module)."
  type        = string
}

variable "runs_table_arn" {
  description = "ARN of the DynamoDB runs table (from the persistence module). The Lambda role is scoped to this table and its indexes only."
  type        = string
}

variable "state_machine_arn" {
  description = "ARN of the orchestration state machine (from the orchestration module). The Lambda role may only StartExecution on this state machine."
  type        = string
}

variable "lambda_package_zip_path" {
  description = "Path to the deployment zip built by infrastructure/scripts/build_lambda.sh for api."
  type        = string
}

variable "lambda_architectures" {
  description = "Lambda instruction set. arm64 (Graviton2) for the same reason the sandbox Fargate task uses ARM64 in the design artifact: better price-performance. Deliberate here, not the AWS default (x86_64) left unset."
  type        = list(string)
}

variable "lambda_handler" {
  description = "Lambda handler entrypoint for lambda api. Matches services/api/src/api/handler.py's module path (package api, module handler, function handler) now that the real artifact is wired in - not the placeholder stub's own handler.main."
  type        = string
  default     = "api.handler.handler"
}

variable "events_table_name" {
  description = "Events table. lambda api reads it for GET /runs/{id}/report, which carries the run's SecurityBlocked events -- the brief requires the injection scenario to register the event, and an event only registered where nobody can see it is not evidence."
  type        = string
}

variable "events_table_arn" {
  type = string
}

variable "workspaces_bucket_name" {
  description = "Bucket holding each run's workspace. lambda api reads one object from it: the diff that core_ops wrote, which GET /runs/{id}/report inlines. The diff lives in S3 rather than on the run item because a DynamoDB item tops out at 400 KB."
  type        = string
}

variable "workspaces_bucket_arn" {
  type = string
}

variable "extra_environment_variables" {
  description = "Additional Lambda environment variables merged on top of the module's own (RUNS_TABLE_NAME, MODHUB_STATE_MACHINE_ARN)."
  type        = map(string)
  default     = {}
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout for lambda api. Kept short - this Lambda only creates a Run record and starts a Step Functions execution, or reads a Run back."
  type        = number
  default     = 10
}

variable "lambda_memory_mb" {
  description = "Lambda memory for lambda api."
  type        = number
  default     = 256
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the api Lambda."
  type        = number
  default     = 14
}

variable "cors_allow_origins" {
  description = "Allowed CORS origins for the HTTP API. Empty disables CORS; never default to a wildcard."
  type        = list(string)
  default     = []
}

variable "aws_region" {
  description = "Region used to build the analysis model's foundation-model ARN for IAM scoping (Fase 4, task 4.4-tf)."
  type        = string
}

variable "analysis_model_id" {
  description = "Bedrock model ID resolved for ModelRole.ANALYSIS (core_py.bedrock_models) -- CLAUDE.md's one documented Bedrock exception, the objective->strategy resolver in services/api/resolver. The IAM policy is scoped to exactly this model ID, never bedrock:* across all models."
  type        = string
}

variable "enable_jwt_authorizer" {
  description = "Task 4.2-tf: require a valid Cognito JWT on every route. False for development, true for production backed by real Cognito."
  type        = bool
  default     = false
}

variable "jwt_issuer" {
  description = "Cognito user pool issuer URL (module.identity.issuer_url). Required when enable_jwt_authorizer is true."
  type        = string
  default     = null
}

variable "jwt_audience" {
  description = "Accepted JWT audiences -- the Cognito app client ids (cli and backstage) from the identity module. Required when enable_jwt_authorizer is true."
  type        = list(string)
  default     = []
}

variable "open_pr_lambda_invoke_arn" {
  description = "Set to route POST /runs/{run_id}/pull-request at the open-pr Lambda. That Lambda is the only component that writes outside the platform, so it is deliberately a separate target rather than another branch inside lambda api."
  type        = string
  default     = null
}

variable "open_pr_lambda_function_name" {
  type    = string
  default = null
}

variable "enable_open_pr_route" {
  description = "Separate from the ARN variables because count must be resolvable at plan time, and those ARNs come from another module."
  type        = bool
  default     = false
}
