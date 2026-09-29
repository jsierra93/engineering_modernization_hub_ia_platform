# core_ops Lambda: deterministic core. No Bedrock permission.

module "lambda" {
  source = "../lambda-function"

  function_name      = "${var.name_prefix}-core-ops"
  tags               = var.tags
  package_zip_path   = var.lambda_package_zip_path
  handler            = var.lambda_handler
  architectures      = var.lambda_architectures
  timeout_seconds    = var.lambda_timeout_seconds
  memory_mb          = var.lambda_memory_mb
  log_retention_days = var.log_retention_days

  environment = merge(
    {
      RUNS_TABLE_NAME   = var.runs_table_name
      EVENTS_TABLE_NAME = var.events_table_name
    },
    var.extra_environment_variables
  )
}

moved {
  from = aws_iam_role.core_ops_lambda
  to   = module.lambda.aws_iam_role.this
}

moved {
  from = aws_iam_role_policy_attachment.lambda_basic_logs
  to   = module.lambda.aws_iam_role_policy_attachment.basic_logs
}

moved {
  from = aws_cloudwatch_log_group.core_ops_lambda
  to   = module.lambda.aws_cloudwatch_log_group.this
}

moved {
  from = aws_lambda_function.core_ops
  to   = module.lambda.aws_lambda_function.this
}

data "aws_iam_policy_document" "core_ops_lambda_scope" {
  statement {
    sid    = "RunsTableReadWrite"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]
    resources = [
      var.runs_table_arn,
      "${var.runs_table_arn}/index/*",
    ]
  }

  statement {
    sid    = "EventsTableReadWrite"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:Query",
    ]
    resources = [var.events_table_arn]
  }

  statement {
    sid       = "WorkspaceReadOnly"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.workspaces_bucket_arn}/ws/*"]
  }

  statement {
    sid       = "WriteRunDiffOnly"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${var.workspaces_bucket_arn}/ws/*/diff.patch"]
  }

  statement {
    sid     = "WriteWorkingCopyAndSandboxHandoff"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = [
      "${var.workspaces_bucket_arn}/ws/*/v1/*",
      "${var.workspaces_bucket_arn}/ws/*/v1.tar.gz",
      "${var.workspaces_bucket_arn}/ws/*/junit/*",
    ]
  }

  statement {
    sid       = "ListWorkspacePrefixOnly"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.workspaces_bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["ws/*"]
    }
  }
}

resource "aws_iam_role_policy" "core_ops_lambda_scope" {
  name   = "${var.name_prefix}-core-ops-lambda-scope"
  role   = module.lambda.role_id
  policy = data.aws_iam_policy_document.core_ops_lambda_scope.json
}
