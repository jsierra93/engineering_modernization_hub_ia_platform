# The only component that writes outside the platform. Its role carries
# exactly three permissions: read the GitHub token, read one run, read that
# run's produced workspace. No DynamoDB writes, no Step Functions, no
# Bedrock, no other bucket prefix.

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

resource "aws_iam_role" "open_pr" {
  name               = "${var.name_prefix}-open-pr-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic_logs" {
  role       = aws_iam_role.open_pr.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
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

  # UpdateItem exists for one purpose: recording the PR this Lambda just
  # created. The attribute condition is what keeps it to that -- without
  # it, "can write the runs table" would mean this Lambda could move a
  # verdict or an approval state. Kept in its own statement so the
  # condition applies to the write and never narrows the read.
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
  role   = aws_iam_role.open_pr.id
  policy = data.aws_iam_policy_document.open_pr_scope.json
}

resource "aws_cloudwatch_log_group" "open_pr" {
  name              = "/aws/lambda/${var.name_prefix}-open-pr"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_lambda_function" "open_pr" {
  function_name    = "${var.name_prefix}-open-pr"
  role             = aws_iam_role.open_pr.arn
  handler          = "open_pr.handler.handler"
  runtime          = var.lambda_runtime
  architectures    = var.lambda_architectures
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_mb
  filename         = var.lambda_package_zip_path
  source_code_hash = filebase64sha256(var.lambda_package_zip_path)

  environment {
    variables = {
      MODHUB_WORKSPACE_BUCKET = var.workspaces_bucket_name
      GITHUB_TOKEN_SECRET_ARN = var.github_token_secret_arn
      RUNS_TABLE_NAME         = var.runs_table_name
    }
  }

  tags       = var.tags
  depends_on = [aws_cloudwatch_log_group.open_pr]
}
