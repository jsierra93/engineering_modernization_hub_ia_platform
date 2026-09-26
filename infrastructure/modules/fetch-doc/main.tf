# infrastructure/modules/fetch-doc
#
# Task 3.6-tf (PLAN.md). lambda fetch_doc fetches an allowlisted
# documentation URL for agent_phase (invoked as a real, separate Lambda --
# see services/agent_phase/src/agent_phase/fetch_doc_client.py's own
# reasoning for why this stays a genuine cross-Lambda call rather than an
# in-process import).
#
# IAM: this Lambda's execution role gets ONLY CloudWatch Logs permissions
# -- no S3, no Bedrock, no Secrets Manager, nothing else, ever. That's not
# a starting point to grow from; it's the whole invariant (CLAUDE.md's
# permissions table: fetch_doc gets "Ningún permiso AWS"). If a future
# change to this module adds any other statement, that is itself a design
# regression worth stopping and re-reading CLAUDE.md over.

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

resource "aws_iam_role" "fetch_doc_lambda" {
  name               = "${var.name_prefix}-fetch-doc-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-fetch-doc-lambda-role"
  })
}

# The ONLY permission this role will ever have. See file header.
resource "aws_iam_role_policy_attachment" "lambda_basic_logs" {
  role       = aws_iam_role.fetch_doc_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_cloudwatch_log_group" "fetch_doc_lambda" {
  name              = "/aws/lambda/${var.name_prefix}-fetch-doc"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

resource "aws_lambda_function" "fetch_doc" {
  function_name    = "${var.name_prefix}-fetch-doc"
  role             = aws_iam_role.fetch_doc_lambda.arn
  handler          = var.lambda_handler
  runtime          = var.lambda_runtime
  architectures    = var.lambda_architectures
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_mb
  filename         = var.lambda_package_zip_path
  source_code_hash = filebase64sha256(var.lambda_package_zip_path)

  environment {
    variables = var.extra_environment_variables
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-fetch-doc"
  })

  depends_on = [aws_cloudwatch_log_group.fetch_doc_lambda]
}
