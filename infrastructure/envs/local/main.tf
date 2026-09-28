# infrastructure/envs/local
#
# Local-only composition against Floci (https://floci.io), mirroring
# infrastructure/envs/personal's module wiring. Exists to prove Fase 1's
# persistence/orchestration/api modules actually fit together end to end
# before ever touching a real AWS account.
#
# name_prefix is deliberately just "modhub" (no "-local" suffix) so the
# DynamoDB table names this creates ("modhub-runs", "modhub-events") match
# the hardcoded defaults in packages/core_py/src/core_py/persistence.py
# (DEFAULT_RUNS_TABLE / DEFAULT_EVENTS_TABLE) exactly. That module does not
# currently read a table-name env var, so name-matching is the only way to
# wire the real handler.py to the tables this env creates without editing
# services/api or packages/core_py (out of scope for infrastructure/).

locals {
  name_prefix = var.project_name

  # x86_64 in every filename -- envs/local always builds for Floci, which
  # does not cross-emulate arm64 (see the api module's lambda_architectures
  # override below for the full story). envs/personal's equivalents build
  # the arm64 versions of the same services; both can coexist on disk
  # without one overwriting the other now that build_lambda.sh's default
  # output name includes the architecture.
  lambda_package_path = coalesce(
    var.lambda_package_path,
    "${path.module}/../../scripts/build/api_lambda_x86_64.zip"
  )

  fetch_repo_package_path  = "${path.module}/../../scripts/build/fetch_repo_lambda_x86_64.zip"
  core_ops_package_path    = "${path.module}/../../scripts/build/core_ops_lambda_x86_64.zip"
  fetch_doc_package_path   = "${path.module}/../../scripts/build/fetch_doc_lambda_x86_64.zip"
  agent_phase_package_path = "${path.module}/../../scripts/build/agent_phase_lambda_x86_64.zip"

  floci_env = {
    AWS_ENDPOINT_URL      = "http://host.docker.internal:4566"
    AWS_ACCESS_KEY_ID     = "test"
    AWS_SECRET_ACCESS_KEY = "test"
    AWS_DEFAULT_REGION    = var.aws_region
  }

  common_tags = {
    Project     = "engineering-modernization-hub"
    Environment = "local"
    ManagedBy   = "terraform"
  }
}

module "persistence" {
  source = "../../modules/persistence"

  name_prefix      = local.name_prefix
  tags             = local.common_tags
  s3_force_destroy = true
}

module "sandbox_network" {
  source = "../../modules/sandbox-network"

  name_prefix = local.name_prefix
  tags        = local.common_tags
  aws_region  = var.aws_region

  # Override the arm64 default for the same reason as the api module's
  # lambda_architectures override just below: Floci runs container
  # workloads (Fargate included) as the Docker host's native architecture
  # and does not cross-emulate arm64.
  sandbox_architecture = "x86_64"
}

module "notifications" {
  source = "../../modules/notifications"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}

module "orchestration" {
  source = "../../modules/orchestration"

  name_prefix = local.name_prefix
  tags        = local.common_tags

  sandbox_cluster_arn         = module.sandbox_network.ecs_cluster_arn
  sandbox_task_definition_arn = module.sandbox_network.task_definition_arn
  sandbox_execution_role_arn  = module.sandbox_network.execution_role_arn
  sandbox_container_name      = module.sandbox_network.container_name
  sandbox_subnet_ids          = [module.sandbox_network.public_subnet_id]
  sandbox_security_group_ids  = [module.sandbox_network.security_group_id]
  fetch_repo_lambda_arn       = module.fetch_repo.lambda_function_arn
  agent_phase_lambda_arn      = module.agent_phase.lambda_function_arn
  core_ops_lambda_arn         = module.core_ops.lambda_function_arn
  notifications_queue_arn     = module.notifications.queue_arn
  notifications_queue_url     = module.notifications.queue_url
}

module "identity" {
  source = "../../modules/identity"

  name_prefix     = local.name_prefix
  tags            = local.common_tags
  issuer_base_url = var.floci_endpoint
}

module "api" {
  source = "../../modules/api"

  name_prefix             = local.name_prefix
  tags                    = local.common_tags
  runs_table_name         = module.persistence.runs_table_name
  runs_table_arn          = module.persistence.runs_table_arn
  state_machine_arn       = module.orchestration.state_machine_arn
  workspaces_bucket_name  = module.persistence.workspaces_bucket_name
  workspaces_bucket_arn   = module.persistence.workspaces_bucket_arn
  events_table_name       = module.persistence.events_table_name
  events_table_arn        = module.persistence.events_table_arn
  lambda_package_zip_path = local.lambda_package_path

  # Override the arm64 default: confirmed empirically (2026-09-25, via a
  # direct boto3 invoke against a deployed function) that Floci runs Lambda
  # containers as the Docker host's native architecture and does not
  # cross-emulate arm64 -- an arm64 .so there fails to import with a
  # misleading "No module named 'pydantic_core._pydantic_core'". Build with
  # `infrastructure/scripts/build_lambda.sh <zip> x86_64` to match.
  lambda_architectures = ["x86_64"]

  # The Lambda executes inside Floci's own Docker-backed Lambda runner, on
  # the bridge Docker network - NOT on this host's network namespace. From
  # inside that container, "localhost:4566" resolves to the container
  # itself, not to Floci. host.docker.internal is the standard Docker
  # Desktop bridge back to the host, where Floci's port is published.
  extra_environment_variables = {
    AWS_ENDPOINT_URL      = "http://host.docker.internal:4566"
    AWS_ACCESS_KEY_ID     = "test"
    AWS_SECRET_ACCESS_KEY = "test"
    AWS_DEFAULT_REGION    = var.aws_region
    # Local-dev-only escape hatch (2026-09-26): Floci doesn't emulate real
    # Bedrock inference, so create_run's resolve_strategy call always
    # comes back unusable here regardless of `objetivo` -- confirmed
    # empirically. This skips it and always resolves to
    # python-pydantic-v2 (the only registered strategy), so the rest of
    # the flow (FetchRepo, Baseline, ...) stays exercisable against
    # Floci. NEVER set in envs/personal (real AWS) -- see
    # services/api/src/api/handler.py's own comment on this env var.
    MODHUB_DEV_STRATEGY_ID = "python-pydantic-v2"
  }

  enable_jwt_authorizer = true
  jwt_issuer             = module.identity.issuer_url
  jwt_audience           = [module.identity.cli_client_id, module.identity.backstage_client_id]
}

module "fetch_repo" {
  source = "../../modules/fetch-repo"

  name_prefix             = local.name_prefix
  tags                    = local.common_tags
  workspaces_bucket_name  = module.persistence.workspaces_bucket_name
  workspaces_bucket_arn   = module.persistence.workspaces_bucket_arn
  lambda_architectures    = ["x86_64"]
  lambda_package_zip_path = local.fetch_repo_package_path

  extra_environment_variables = {
    AWS_ENDPOINT_URL      = "http://host.docker.internal:4566"
    AWS_ACCESS_KEY_ID     = "test"
    AWS_SECRET_ACCESS_KEY = "test"
    AWS_DEFAULT_REGION    = var.aws_region
  }
}

module "core_ops" {
  source = "../../modules/core-ops"

  name_prefix             = local.name_prefix
  tags                    = local.common_tags
  runs_table_name         = module.persistence.runs_table_name
  runs_table_arn          = module.persistence.runs_table_arn
  events_table_name       = module.persistence.events_table_name
  events_table_arn        = module.persistence.events_table_arn
  workspaces_bucket_arn   = module.persistence.workspaces_bucket_arn
  lambda_architectures    = ["x86_64"]
  lambda_package_zip_path = local.core_ops_package_path

  extra_environment_variables = local.floci_env
}

module "fetch_doc" {
  source = "../../modules/fetch-doc"

  name_prefix             = local.name_prefix
  tags                    = local.common_tags
  lambda_architectures    = ["x86_64"]
  lambda_package_zip_path = local.fetch_doc_package_path

  # fetch_doc gets ZERO AWS permissions (CLAUDE.md's permissions table) --
  # no Floci endpoint override needed, it never calls boto3 at all.
  extra_environment_variables = {}
}

module "agent_phase" {
  source = "../../modules/agent-phase"

  name_prefix             = local.name_prefix
  tags                    = local.common_tags
  aws_region              = var.aws_region
  workspaces_bucket_name  = module.persistence.workspaces_bucket_name
  workspaces_bucket_arn   = module.persistence.workspaces_bucket_arn
  fetch_doc_lambda_arn    = module.fetch_doc.lambda_function_arn
  fetch_doc_lambda_name   = module.fetch_doc.lambda_function_name
  analysis_model_id       = "anthropic.claude-haiku-4-5-20251001-v1:0"
  lambda_architectures    = ["x86_64"]
  lambda_package_zip_path = local.agent_phase_package_path

  # Bedrock Guardrails are a control-plane API, a different surface than
  # bedrock-runtime InvokeModel -- support on Floci is unconfirmed (see
  # infrastructure/modules/agent-phase/variables.tf's create_guardrail
  # comment). Skip it locally; envs/personal creates a real one.
  create_guardrail = false

  extra_environment_variables = local.floci_env
}
