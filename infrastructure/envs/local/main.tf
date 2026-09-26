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

  lambda_package_path = coalesce(
    var.lambda_package_path,
    "${path.module}/../../scripts/build/api_lambda_real.zip"
  )

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

module "orchestration" {
  source = "../../modules/orchestration"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}

module "api" {
  source = "../../modules/api"

  name_prefix             = local.name_prefix
  tags                    = local.common_tags
  runs_table_name         = module.persistence.runs_table_name
  runs_table_arn          = module.persistence.runs_table_arn
  state_machine_arn       = module.orchestration.state_machine_arn
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
  }
}
