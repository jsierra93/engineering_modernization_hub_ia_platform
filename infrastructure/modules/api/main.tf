# lambda api behind an HTTP API with optional JWT authorizer, plus routes and access logs.

locals {
  analysis_model_bare_id = replace(var.analysis_model_id, "/^(us|eu|apac|global)\\./", "")

  analysis_model_arns = compact([
    "arn:${data.aws_partition.current.partition}:bedrock:*::foundation-model/${local.analysis_model_bare_id}",
    local.analysis_model_bare_id != var.analysis_model_id
    ? "arn:${data.aws_partition.current.partition}:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.analysis_model_id}"
    : "",
  ])
}

data "aws_partition" "current" {}
data "aws_caller_identity" "current" {}

module "lambda" {
  source = "../lambda-function"

  function_name      = "${var.name_prefix}-api"
  tags               = var.tags
  package_zip_path   = var.lambda_package_zip_path
  handler            = var.lambda_handler
  architectures      = var.lambda_architectures
  timeout_seconds    = var.lambda_timeout_seconds
  memory_mb          = var.lambda_memory_mb
  log_retention_days = var.log_retention_days

  environment = merge(
    {
      RUNS_TABLE_NAME          = var.runs_table_name
      MODHUB_STATE_MACHINE_ARN = var.state_machine_arn
      BEDROCK_MODEL_ANALYSIS   = var.analysis_model_id
      MODHUB_WORKSPACE_BUCKET  = var.workspaces_bucket_name
      EVENTS_TABLE_NAME        = var.events_table_name
    },
    var.extra_environment_variables
  )
}

moved {
  from = aws_iam_role.api_lambda
  to   = module.lambda.aws_iam_role.this
}

moved {
  from = aws_iam_role_policy_attachment.lambda_basic_logs
  to   = module.lambda.aws_iam_role_policy_attachment.basic_logs
}

moved {
  from = aws_cloudwatch_log_group.api_lambda
  to   = module.lambda.aws_cloudwatch_log_group.this
}

moved {
  from = aws_lambda_function.api
  to   = module.lambda.aws_lambda_function.this
}

data "aws_iam_policy_document" "api_lambda_scope" {
  statement {
    sid    = "RunsTableReadWrite"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:UpdateItem",
    ]
    resources = [
      var.runs_table_arn,
      "${var.runs_table_arn}/index/*",
    ]
  }

  statement {
    sid       = "EventsTableReadOnly"
    effect    = "Allow"
    actions   = ["dynamodb:Query"]
    resources = [var.events_table_arn, "${var.events_table_arn}/index/*"]
  }

  statement {
    sid       = "ReadRunDiffOnly"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.workspaces_bucket_arn}/ws/*/diff.patch"]
  }

  statement {
    sid       = "StartOrchestration"
    effect    = "Allow"
    actions   = ["states:StartExecution"]
    resources = [var.state_machine_arn]
  }

  statement {
    sid       = "CompleteApprovalCallback"
    effect    = "Allow"
    actions   = ["states:SendTaskSuccess", "states:SendTaskFailure"]
    resources = [var.state_machine_arn]
  }

  statement {
    sid       = "ResolveObjectiveToStrategy"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel"]
    resources = local.analysis_model_arns
  }
}

resource "aws_iam_role_policy" "api_lambda_scope" {
  name   = "${var.name_prefix}-api-lambda-scope"
  role   = module.lambda.role_id
  policy = data.aws_iam_policy_document.api_lambda_scope.json
}

resource "aws_apigatewayv2_api" "http_api" {
  name          = "${var.name_prefix}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = var.cors_allow_origins
    allow_methods = ["GET", "POST"]
    allow_headers = ["content-type", "authorization"]
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-api"
  })
}

resource "aws_apigatewayv2_integration" "api_lambda" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.lambda.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  count = var.enable_jwt_authorizer ? 1 : 0

  api_id           = aws_apigatewayv2_api.http_api.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "${var.name_prefix}-jwt-authorizer"

  jwt_configuration {
    audience = var.jwt_audience
    issuer   = var.jwt_issuer
  }
}

resource "aws_apigatewayv2_route" "create_run" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /modhub/v1/runs"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"

  authorization_type = var.enable_jwt_authorizer ? "JWT" : "NONE"
  authorizer_id      = var.enable_jwt_authorizer ? aws_apigatewayv2_authorizer.jwt[0].id : null
}

resource "aws_apigatewayv2_route" "get_run" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /modhub/v1/runs/{run_id}"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"

  authorization_type = var.enable_jwt_authorizer ? "JWT" : "NONE"
  authorizer_id      = var.enable_jwt_authorizer ? aws_apigatewayv2_authorizer.jwt[0].id : null
}

resource "aws_apigatewayv2_route" "get_report" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /modhub/v1/runs/{run_id}/report"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"

  authorization_type = var.enable_jwt_authorizer ? "JWT" : "NONE"
  authorizer_id      = var.enable_jwt_authorizer ? aws_apigatewayv2_authorizer.jwt[0].id : null
}

resource "aws_apigatewayv2_route" "list_runs" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /modhub/v1/runs"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"

  authorization_type = var.enable_jwt_authorizer ? "JWT" : "NONE"
  authorizer_id      = var.enable_jwt_authorizer ? aws_apigatewayv2_authorizer.jwt[0].id : null
}

resource "aws_apigatewayv2_route" "approve_run" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /modhub/v1/runs/{run_id}/approval"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"

  authorization_type = var.enable_jwt_authorizer ? "JWT" : "NONE"
  authorizer_id      = var.enable_jwt_authorizer ? aws_apigatewayv2_authorizer.jwt[0].id : null
}

resource "aws_cloudwatch_log_group" "api_gateway_access_logs" {
  name              = "/aws/apigateway/${var.name_prefix}-api"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway_access_logs.arn
    format = jsonencode({
      requestId       = "$context.requestId"
      routeKey        = "$context.routeKey"
      status          = "$context.status"
      integrationTime = "$context.integration.integrationLatency"
      responseLength  = "$context.responseLength"
    })
  }

  tags = var.tags
}

resource "aws_lambda_permission" "apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_apigatewayv2_integration" "open_pr" {
  count = var.enable_open_pr_route ? 1 : 0

  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.open_pr_lambda_invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "open_pr" {
  count = var.enable_open_pr_route ? 1 : 0

  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /modhub/v1/runs/{run_id}/pull-request"
  target    = "integrations/${aws_apigatewayv2_integration.open_pr[0].id}"

  authorization_type = var.enable_jwt_authorizer ? "JWT" : "NONE"
  authorizer_id      = var.enable_jwt_authorizer ? aws_apigatewayv2_authorizer.jwt[0].id : null
}

resource "aws_lambda_permission" "open_pr_apigw_invoke" {
  count = var.enable_open_pr_route ? 1 : 0

  statement_id  = "AllowAPIGatewayInvokeOpenPr"
  action        = "lambda:InvokeFunction"
  function_name = var.open_pr_lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}
