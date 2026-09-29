# Personal AWS environment: wires every module together.

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  platform_ceiling_env = {
    MODHUB_CEILING_MAX_USD        = "10"
    MODHUB_CEILING_MAX_ITERATIONS = "5"
    MODHUB_CEILING_MAX_MINUTES    = "60"
  }

  api_package_path         = "${path.module}/../scripts/build/api_lambda_${var.lambda_architecture}.zip"
  fetch_repo_package_path  = "${path.module}/../scripts/build/fetch_repo_lambda_${var.lambda_architecture}.zip"
  core_ops_package_path    = "${path.module}/../scripts/build/core_ops_lambda_${var.lambda_architecture}.zip"
  fetch_doc_package_path   = "${path.module}/../scripts/build/fetch_doc_lambda_${var.lambda_architecture}.zip"
  agent_phase_package_path = "${path.module}/../scripts/build/agent_phase_lambda_${var.lambda_architecture}.zip"
  open_pr_package_path     = "${path.module}/../scripts/build/open_pr_lambda_${var.lambda_architecture}.zip"

  lambda_architectures = [var.lambda_architecture]

  common_tags = {
    Project     = "engineering-modernization-hub"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

module "persistence" {
  source = "../modules/persistence"

  name_prefix      = local.name_prefix
  tags             = local.common_tags
  s3_force_destroy = true
}

module "sandbox_network" {
  source = "../modules/sandbox-network"

  name_prefix          = local.name_prefix
  tags                 = local.common_tags
  aws_region           = var.aws_region
  sandbox_architecture = var.lambda_architecture
  ecr_force_delete     = true
  sandbox_profiles     = { python = { image_tag = var.sandbox_image_tag } }
}

module "notifications" {
  source = "../modules/notifications"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}

module "orchestration" {
  source = "../modules/orchestration"

  name_prefix = local.name_prefix
  tags        = local.common_tags

  sandbox_cluster_arn          = module.sandbox_network.ecs_cluster_arn
  sandbox_task_definition_arns = values(module.sandbox_network.task_definition_arns)
  sandbox_execution_role_arn   = module.sandbox_network.execution_role_arn
  sandbox_container_name       = module.sandbox_network.container_name
  sandbox_subnet_ids           = [module.sandbox_network.public_subnet_id]
  sandbox_security_group_ids   = [module.sandbox_network.security_group_id]
  fetch_repo_lambda_arn        = module.fetch_repo.lambda_function_arn
  agent_phase_lambda_arn       = module.agent_phase.lambda_function_arn
  core_ops_lambda_arn          = module.core_ops.lambda_function_arn
  notifications_queue_arn      = module.notifications.queue_arn
  notifications_queue_url      = module.notifications.queue_url
}

module "identity" {
  source = "../modules/identity"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}

module "api" {
  source = "../modules/api"

  name_prefix                  = local.name_prefix
  tags                         = local.common_tags
  runs_table_name              = module.persistence.runs_table_name
  runs_table_arn               = module.persistence.runs_table_arn
  state_machine_arn            = module.orchestration.state_machine_arn
  lambda_package_zip_path      = local.api_package_path
  lambda_architectures         = local.lambda_architectures
  aws_region                   = var.aws_region
  analysis_model_id            = var.analysis_model_id
  cors_allow_origins           = var.cors_allow_origins
  sandbox_task_definition_arns = module.sandbox_network.task_definition_arns
  workspaces_bucket_name       = module.persistence.workspaces_bucket_name
  workspaces_bucket_arn        = module.persistence.workspaces_bucket_arn
  events_table_name            = module.persistence.events_table_name
  events_table_arn             = module.persistence.events_table_arn

  enable_open_pr_route         = true
  open_pr_lambda_invoke_arn    = module.open_pr.lambda_invoke_arn
  open_pr_lambda_function_name = module.open_pr.lambda_function_name

  extra_environment_variables = merge(local.platform_ceiling_env, {
    MODHUB_APPROVAL_MAX_AUTH_AGE_SECONDS = "3600"
  })

  enable_jwt_authorizer = true
  jwt_issuer            = module.identity.issuer_url
  jwt_audience          = [module.identity.cli_client_id, module.identity.backstage_client_id]
}

module "open_pr" {
  source = "../modules/open-pr"

  name_prefix             = local.name_prefix
  tags                    = local.common_tags
  runs_table_name         = module.persistence.runs_table_name
  runs_table_arn          = module.persistence.runs_table_arn
  workspaces_bucket_name  = module.persistence.workspaces_bucket_name
  workspaces_bucket_arn   = module.persistence.workspaces_bucket_arn
  github_token_secret_arn = module.fetch_repo.github_token_secret_arn
  lambda_package_zip_path = local.open_pr_package_path
  lambda_architectures    = local.lambda_architectures
}

module "fetch_repo" {
  source = "../modules/fetch-repo"

  name_prefix             = local.name_prefix
  tags                    = local.common_tags
  workspaces_bucket_name  = module.persistence.workspaces_bucket_name
  workspaces_bucket_arn   = module.persistence.workspaces_bucket_arn
  lambda_package_zip_path = local.fetch_repo_package_path
  lambda_architectures    = local.lambda_architectures
}

module "core_ops" {
  source = "../modules/core-ops"

  name_prefix             = local.name_prefix
  tags                    = local.common_tags
  runs_table_name         = module.persistence.runs_table_name
  runs_table_arn          = module.persistence.runs_table_arn
  events_table_name       = module.persistence.events_table_name
  events_table_arn        = module.persistence.events_table_arn
  workspaces_bucket_arn   = module.persistence.workspaces_bucket_arn
  lambda_package_zip_path = local.core_ops_package_path
  lambda_architectures    = local.lambda_architectures

  extra_environment_variables = local.platform_ceiling_env
}

module "fetch_doc" {
  source = "../modules/fetch-doc"

  name_prefix             = local.name_prefix
  tags                    = local.common_tags
  lambda_package_zip_path = local.fetch_doc_package_path
  lambda_architectures    = local.lambda_architectures
}

module "agent_phase" {
  source = "../modules/agent-phase"

  name_prefix             = local.name_prefix
  tags                    = local.common_tags
  aws_region              = var.aws_region
  workspaces_bucket_name  = module.persistence.workspaces_bucket_name
  workspaces_bucket_arn   = module.persistence.workspaces_bucket_arn
  fetch_doc_lambda_arn    = module.fetch_doc.lambda_function_arn
  fetch_doc_lambda_name   = module.fetch_doc.lambda_function_name
  analysis_model_id       = var.analysis_model_id
  code_model_id           = var.code_model_id
  model_pricing           = var.model_pricing
  lambda_package_zip_path = local.agent_phase_package_path
  lambda_architectures    = local.lambda_architectures

  extra_environment_variables = local.platform_ceiling_env

  enable_invocation_logging = true
}
