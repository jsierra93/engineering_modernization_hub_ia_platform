# fetch_repo Lambda and the GitHub token secret container (value is set out of band).

resource "aws_secretsmanager_secret" "github_token" {
  name        = "${var.name_prefix}-fetch-repo-github-token"
  description = "GitHub token used by lambda fetch_repo. Real value set out-of-band by a human -- NEVER via Terraform or git."

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-fetch-repo-github-token"
  })
}

resource "aws_secretsmanager_secret_version" "github_token" {
  secret_id     = aws_secretsmanager_secret.github_token.id
  secret_string = "REPLACE_OUT_OF_BAND_NOT_A_REAL_TOKEN"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

module "lambda" {
  source = "../lambda-function"

  function_name      = "${var.name_prefix}-fetch-repo"
  tags               = var.tags
  package_zip_path   = var.lambda_package_zip_path
  handler            = var.lambda_handler
  architectures      = var.lambda_architectures
  timeout_seconds    = var.lambda_timeout_seconds
  memory_mb          = var.lambda_memory_mb
  log_retention_days = var.log_retention_days

  environment = merge(
    {
      MODHUB_WORKSPACE_BUCKET = var.workspaces_bucket_name
      GITHUB_TOKEN_SECRET_ARN = aws_secretsmanager_secret.github_token.arn
    },
    var.extra_environment_variables
  )
}

moved {
  from = aws_iam_role.fetch_repo_lambda
  to   = module.lambda.aws_iam_role.this
}

moved {
  from = aws_iam_role_policy_attachment.lambda_basic_logs
  to   = module.lambda.aws_iam_role_policy_attachment.basic_logs
}

moved {
  from = aws_cloudwatch_log_group.fetch_repo_lambda
  to   = module.lambda.aws_cloudwatch_log_group.this
}

moved {
  from = aws_lambda_function.fetch_repo
  to   = module.lambda.aws_lambda_function.this
}

data "aws_iam_policy_document" "fetch_repo_lambda_scope" {
  statement {
    sid    = "WorkspacePrefixReadWrite"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
    ]
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
  role   = module.lambda.role_id
  policy = data.aws_iam_policy_document.fetch_repo_lambda_scope.json
}
