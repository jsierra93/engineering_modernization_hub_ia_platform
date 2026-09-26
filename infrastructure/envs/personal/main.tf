# infrastructure/envs/personal
#
# Composition root for the personal prototype environment. Wires together
# the persistence (1.4-tf), orchestration (1.5-tf) and api (1.6-tf) modules.
# Fase 2-4 modules (sandbox-network, identity, notifications) and the
# core_ops/agent_phase/fetch_repo/fetch_doc Lambda roles are deliberately
# not composed here yet - they are built in their own phases per PLAN.md.

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

module "orchestration" {
  source = "../../modules/orchestration"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}

module "api" {
  source = "../../modules/api"

  name_prefix       = local.name_prefix
  tags              = local.common_tags
  runs_table_name   = module.persistence.runs_table_name
  runs_table_arn    = module.persistence.runs_table_arn
  state_machine_arn = module.orchestration.state_machine_arn
}
