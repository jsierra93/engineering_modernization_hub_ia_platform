# core_ops Lambda: deterministic core. No Bedrock permission.

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
  output_path = "${path.module}/build/core_ops_lambda.zip"
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

resource "aws_iam_role" "core_ops_lambda" {
  name               = "${var.name_prefix}-core-ops-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-core-ops-lambda-role"
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_logs" {
  role       = aws_iam_role.core_ops_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
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
  role   = aws_iam_role.core_ops_lambda.id
  policy = data.aws_iam_policy_document.core_ops_lambda_scope.json
}

resource "aws_cloudwatch_log_group" "core_ops_lambda" {
  name              = "/aws/lambda/${var.name_prefix}-core-ops"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

resource "aws_lambda_function" "core_ops" {
  function_name    = "${var.name_prefix}-core-ops"
  role             = aws_iam_role.core_ops_lambda.arn
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
        RUNS_TABLE_NAME   = var.runs_table_name
        EVENTS_TABLE_NAME = var.events_table_name
      },
      var.extra_environment_variables
    )
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-core-ops"
  })

  depends_on = [aws_cloudwatch_log_group.core_ops_lambda]
}
