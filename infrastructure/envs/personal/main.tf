# infrastructure/envs/personal
#
# Composition root for the personal prototype environment. Wires together
# the persistence (1.4-tf), orchestration (1.5-tf), api (1.6-tf),
# sandbox-network (2.1-tf), fetch-repo (2.2-tf) and core-ops (2.6-tf)
# modules. agent_phase / fetch_doc / identity / notifications are
# deliberately not composed here yet - they are built in their own phases
# per PLAN.md.

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = "engineering-modernization-hub"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

module "persistence" {
  source = "../../modules/persistence"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}

module "sandbox_network" {
  source = "../../modules/sandbox-network"

  name_prefix = local.name_prefix
  tags        = local.common_tags
  aws_region  = var.aws_region
  # sandbox_architecture defaults to "arm64" (real-AWS default) - not
  # overridden here, only in envs/local.
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
  # sandbox_assign_public_ip defaults to true - correct for the public
  # network mode (no NAT gateway) this module builds.
}

module "api" {
  source = "../../modules/api"

  name_prefix       = local.name_prefix
  tags              = local.common_tags
  runs_table_name   = module.persistence.runs_table_name
  runs_table_arn    = module.persistence.runs_table_arn
  state_machine_arn = module.orchestration.state_machine_arn
}

module "fetch_repo" {
  source = "../../modules/fetch-repo"

  name_prefix            = local.name_prefix
  tags                   = local.common_tags
  workspaces_bucket_name = module.persistence.workspaces_bucket_name
  workspaces_bucket_arn  = module.persistence.workspaces_bucket_arn
}

module "core_ops" {
  source = "../../modules/core-ops"

  name_prefix           = local.name_prefix
  tags                  = local.common_tags
  runs_table_name       = module.persistence.runs_table_name
  runs_table_arn        = module.persistence.runs_table_arn
  events_table_name     = module.persistence.events_table_name
  events_table_arn      = module.persistence.events_table_arn
  workspaces_bucket_arn = module.persistence.workspaces_bucket_arn
}
