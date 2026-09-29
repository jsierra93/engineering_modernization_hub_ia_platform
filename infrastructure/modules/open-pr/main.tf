# open_pr Lambda: reads the GitHub token, the run and its workspace, nothing else.

module "lambda" {
  source = "../lambda-function"

  function_name      = "${var.name_prefix}-open-pr"
  role_name          = "${var.name_prefix}-open-pr-role"
  tags               = var.tags
  package_zip_path   = var.lambda_package_zip_path
  handler            = "open_pr.handler.handler"
  architectures      = var.lambda_architectures
  timeout_seconds    = var.lambda_timeout_seconds
  memory_mb          = var.lambda_memory_mb
  log_retention_days = var.log_retention_days

  environment = {
    MODHUB_WORKSPACE_BUCKET = var.workspaces_bucket_name
    GITHUB_TOKEN_SECRET_ARN = var.github_token_secret_arn
    RUNS_TABLE_NAME         = var.runs_table_name
  }
}

moved {
  from = aws_iam_role.open_pr
  to   = module.lambda.aws_iam_role.this
}

moved {
  from = aws_iam_role_policy_attachment.lambda_basic_logs
  to   = module.lambda.aws_iam_role_policy_attachment.basic_logs
}

moved {
  from = aws_cloudwatch_log_group.open_pr
  to   = module.lambda.aws_cloudwatch_log_group.this
}

moved {
  from = aws_lambda_function.open_pr
  to   = module.lambda.aws_lambda_function.this
}

data "aws_iam_policy_document" "open_pr_scope" {
  statement {
    sid       = "ReadTheGithubTokenOnly"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.github_token_secret_arn]
  }

  statement {
    sid       = "ReadRuns"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem"]
    resources = [var.runs_table_arn]
  }

  statement {
    sid       = "RecordPullRequestOnly"
    effect    = "Allow"
    actions   = ["dynamodb:UpdateItem"]
    resources = [var.runs_table_arn]

    condition {
      test     = "ForAllValues:StringEquals"
      variable = "dynamodb:Attributes"
      values   = ["run_id", "pull_request_url", "pull_request_branch"]
    }
  }

  statement {
    sid       = "ReadProducedWorkspaceOnly"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.workspaces_bucket_arn}/ws/*"]
  }
}

resource "aws_iam_role_policy" "open_pr_scope" {
  name   = "${var.name_prefix}-open-pr-scope"
  role   = module.lambda.role_id
  policy = data.aws_iam_policy_document.open_pr_scope.json
}
