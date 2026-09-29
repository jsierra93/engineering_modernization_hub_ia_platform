# fetch_doc Lambda: no AWS permissions beyond logging.

module "lambda" {
  source = "../lambda-function"

  function_name      = "${var.name_prefix}-fetch-doc"
  tags               = var.tags
  package_zip_path   = var.lambda_package_zip_path
  handler            = var.lambda_handler
  architectures      = var.lambda_architectures
  environment        = var.extra_environment_variables
  timeout_seconds    = var.lambda_timeout_seconds
  memory_mb          = var.lambda_memory_mb
  log_retention_days = var.log_retention_days
}

moved {
  from = aws_iam_role.fetch_doc_lambda
  to   = module.lambda.aws_iam_role.this
}

moved {
  from = aws_iam_role_policy_attachment.lambda_basic_logs
  to   = module.lambda.aws_iam_role_policy_attachment.basic_logs
}

moved {
  from = aws_cloudwatch_log_group.fetch_doc_lambda
  to   = module.lambda.aws_cloudwatch_log_group.this
}

moved {
  from = aws_lambda_function.fetch_doc
  to   = module.lambda.aws_lambda_function.this
}
