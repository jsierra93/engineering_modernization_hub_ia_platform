# Shared Lambda skeleton: execution role with basic logging, log group, function. Service-specific permissions attach to the role output.

locals {
  role_name = coalesce(var.role_name, "${var.function_name}-lambda-role")
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = local.role_name
  assume_role_policy = data.aws_iam_policy_document.assume_role.json

  tags = merge(var.tags, {
    Name = local.role_name
  })
}

resource "aws_iam_role_policy_attachment" "basic_logs" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

resource "aws_lambda_function" "this" {
  function_name    = var.function_name
  role             = aws_iam_role.this.arn
  handler          = var.handler
  runtime          = var.runtime
  architectures    = var.architectures
  timeout          = var.timeout_seconds
  memory_size      = var.memory_mb
  filename         = var.package_zip_path
  source_code_hash = filebase64sha256(var.package_zip_path)

  environment {
    variables = var.environment
  }

  tags = merge(var.tags, {
    Name = var.function_name
  })

  depends_on = [aws_cloudwatch_log_group.this]
}
