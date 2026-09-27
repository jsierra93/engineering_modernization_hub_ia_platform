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

  # Remote state so the whole environment stays destroyable from any machine
  # after the demo. No dynamodb_table: state locking would need one on
  # Terraform 1.8, and this is a single-operator account.
  backend "s3" {
    bucket  = "engineering-modernization-hub-tf-state"
    key     = "personal/terraform.tfstate"
    region  = "us-east-2"
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}
