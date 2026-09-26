# infrastructure/envs/local
#
# NOT a deployable target for real AWS. Every endpoint below is pinned to
# http://localhost:4566 (Floci - https://floci.io - a local, credential-free
# AWS emulator claiming LocalStack-compatible endpoints/behavior). Dummy
# "test"/"test" credentials are the LocalStack convention Floci also
# documents. If this file were ever pointed at a real AWS account it would
# need every `endpoints { ... }` override and the skip_* flags removed -
# that is a deliberate tripwire, not an oversight.

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "aws" {
  region                      = var.aws_region
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

  default_tags {
    tags = local.common_tags
  }

  endpoints {
    dynamodb     = var.floci_endpoint
    s3           = var.floci_endpoint
    lambda       = var.floci_endpoint
    sfn          = var.floci_endpoint
    apigatewayv2 = var.floci_endpoint
    iam          = var.floci_endpoint
    sts          = var.floci_endpoint
    cloudwatch   = var.floci_endpoint
    logs         = var.floci_endpoint
    # Added for the sandbox-network (2.1-tf) / fetch-repo (2.2-tf) modules.
    # Floci's support for ECS/ECR/Secrets Manager emulation is unconfirmed
    # as of this writing (only DynamoDB/S3/Lambda/SFN/API Gateway were
    # empirically verified per envs/local's own history) - if `terraform
    # apply` fails against one of these, that is the first thing to check.
    ecs            = var.floci_endpoint
    ecr            = var.floci_endpoint
    secretsmanager = var.floci_endpoint
    events         = var.floci_endpoint
    # ec2 was missing entirely (not just unconfirmed) -- without it, the
    # sandbox-network module's VPC/subnet/security-group calls silently
    # fell through to the real AWS endpoint and failed with a real 401
    # AuthFailure against the fake test/test credentials. Confirmed via a
    # live `terraform apply`, 2026-09-26 -- not a hypothetical.
    ec2 = var.floci_endpoint
    # sqs was likewise missing -- added for the notifications module
    # (4.3-tf). Confirmed via a live `terraform apply`, 2026-09-26: without
    # it, aws_sqs_queue.dlq's CreateQueue call fell through to the real AWS
    # endpoint and failed with InvalidClientTokenId against the fake
    # test/test credentials -- the exact same failure mode as the ec2
    # omission above, not a coincidence.
    sqs = var.floci_endpoint
    # cognitoidp/cognitoidentity: Floci's own service list (floci.io/aws)
    # marks Cognito with a star as one of the services exclusive to Floci
    # among free AWS emulators -- confirmed via the site itself,
    # 2026-09-26, correcting an earlier assumption in this file that
    # treated it as unconfirmed the same way ECS/ECR/Secrets Manager were.
    cognitoidp       = var.floci_endpoint
    cognitoidentity  = var.floci_endpoint
  }
}
