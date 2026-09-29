# fetch_doc Lambda: no AWS permissions beyond logging.

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
