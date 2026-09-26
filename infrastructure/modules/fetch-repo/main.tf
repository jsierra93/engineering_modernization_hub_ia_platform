# infrastructure/modules/fetch-repo
#
# Task 2.2-tf (PLAN.md). lambda fetch_repo downloads a repo tarball at an
# exact commit SHA, sanitizes it (extension/size checks -- Python side,
# services/fetch_repo, not here) and writes the result to S3 under ws/v0.
# This module provisions the Lambda + its least-privilege role, modeled on
# infrastructure/modules/api's lambda_source_dir / lambda_package_zip_path /
# lambda_architectures shape, plus the GitHub token's Secrets Manager
# container.
#
# IAM for this Lambda's execution role is scoped to exactly:
#   - s3:PutObject / s3:GetObject on the workspaces bucket, prefixed to
#     "ws/*" only -- never the whole bucket
#   - secretsmanager:GetSecretValue on exactly one secret (the GitHub token)
# Nothing else. No Bedrock, ever.
#
# The GitHub token secret container is created here with an obviously-fake
# placeholder value. The real value is set by a human, out-of-band, via
# `aws secretsmanager put-secret-value` or the console -- never through
# Terraform, never committed to git (see CLAUDE.md's "Never commit anything
# that could hold a credential"). `ignore_changes` on secret_string stops a
# later `terraform apply` from ever overwriting a real value a human has
# since set.

locals {
  lambda_source_dir  = coalesce(var.lambda_source_dir, "${path.module}/placeholder_src")
  use_prebuilt_zip   = var.lambda_package_zip_path != null
  lambda_filename    = local.use_prebuilt_zip ? var.lambda_package_zip_path : data.archive_file.lambda_package[0].output_path
  lambda_source_hash = local.use_prebuilt_zip ? filebase64sha256(var.lambda_package_zip_path) : data.archive_file.lambda_package[0].output_base64sha256
}

data "archive_file" "lambda_package" {
  count = local.use_prebuilt_zip ? 0 : 1

  type        = "zip"
  source_dir  = local.lambda_source_dir
  output_path = "${path.module}/build/fetch_repo_lambda.zip"
}

# Container only -- the real value is never set here. See file header.
resource "aws_secretsmanager_secret" "github_token" {
  name        = "${var.name_prefix}-fetch-repo-github-token"
  description = "GitHub token used by lambda fetch_repo. Real value set out-of-band by a human -- NEVER via Terraform or git."

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-fetch-repo-github-token"
  })
}

resource "aws_secretsmanager_secret_version" "github_token" {
  secret_id = aws_secretsmanager_secret.github_token.id
  # Obviously-fake placeholder -- satisfies the resource's required
  # argument only. A human sets the real token value out-of-band; Terraform
  # must never see it, so this attribute is excluded from future applies.
  secret_string = "REPLACE_OUT_OF_BAND_NOT_A_REAL_TOKEN"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "fetch_repo_lambda" {
  name               = "${var.name_prefix}-fetch-repo-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-fetch-repo-lambda-role"
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_logs" {
  role       = aws_iam_role.fetch_repo_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "fetch_repo_lambda_scope" {
  statement {
    sid    = "WorkspacePrefixReadWrite"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
    ]
    # Scoped to the ws/ prefix only -- never the whole bucket.
    resources = ["${var.workspaces_bucket_arn}/ws/*"]
  }

  statement {
    sid       = "GithubTokenSecretOnly"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.github_token.arn]
  }
}

resource "aws_iam_role_policy" "fetch_repo_lambda_scope" {
  name   = "${var.name_prefix}-fetch-repo-lambda-scope"
  role   = aws_iam_role.fetch_repo_lambda.id
  policy = data.aws_iam_policy_document.fetch_repo_lambda_scope.json
}

resource "aws_cloudwatch_log_group" "fetch_repo_lambda" {
  name              = "/aws/lambda/${var.name_prefix}-fetch-repo"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

resource "aws_lambda_function" "fetch_repo" {
  function_name    = "${var.name_prefix}-fetch-repo"
  role             = aws_iam_role.fetch_repo_lambda.arn
  handler          = var.lambda_handler
  runtime          = var.lambda_runtime
  architectures    = var.lambda_architectures
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_mb
  filename         = local.lambda_filename
  source_code_hash = local.lambda_source_hash

  environment {
    variables = merge(
      {
        WORKSPACES_BUCKET_NAME  = var.workspaces_bucket_name
        GITHUB_TOKEN_SECRET_ARN = aws_secretsmanager_secret.github_token.arn
      },
      var.extra_environment_variables
    )
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-fetch-repo"
  })

  depends_on = [aws_cloudwatch_log_group.fetch_repo_lambda]
}
