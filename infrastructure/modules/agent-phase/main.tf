# agent_phase Lambda: the only role with bedrock:InvokeModel, scoped to the resolved model ARNs.

data "aws_partition" "current" {}
data "aws_caller_identity" "current" {}

locals {
  model_ids = compact([var.analysis_model_id, var.code_model_id])

  model_arns = concat(
    [for id in local.model_ids :
      "arn:${data.aws_partition.current.partition}:bedrock:*::foundation-model/${replace(id, "/^(us|eu|apac|global)\\./", "")}"
    ],
    [for id in local.model_ids :
      "arn:${data.aws_partition.current.partition}:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/${id}"
      if replace(id, "/^(us|eu|apac|global)\\./", "") != id
    ],
  )

  guardrail_id      = var.create_guardrail ? aws_bedrock_guardrail.prompt_attack[0].guardrail_id : null
  guardrail_version = var.create_guardrail ? aws_bedrock_guardrail_version.prompt_attack[0].version : null
}

resource "aws_bedrock_guardrail" "prompt_attack" {
  count = var.create_guardrail ? 1 : 0

  name                      = "${var.name_prefix}-prompt-attack-guardrail"
  description               = "Blocks prompt-injection/jailbreak attempts in content passed to agent_phase (repo files, fetched docs) -- Layer 2 behind the untrusted-content delimiting in code."
  blocked_input_messaging   = "This input was blocked by the modernization platform's guardrail."
  blocked_outputs_messaging = "This output was blocked by the modernization platform's guardrail."

  content_policy_config {
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE" # PROMPT_ATTACK is an input-only filter type
    }
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-prompt-attack-guardrail"
  })
}

# The guardrail resource itself only exposes DRAFT; a numbered version is immutable, so the Lambda never runs against an unpublished configuration.
resource "aws_bedrock_guardrail_version" "prompt_attack" {
  count = var.create_guardrail ? 1 : 0

  guardrail_arn = aws_bedrock_guardrail.prompt_attack[0].guardrail_arn
  description   = "Published by Terraform for ${var.name_prefix}"
  skip_destroy  = true

  lifecycle {
    replace_triggered_by = [aws_bedrock_guardrail.prompt_attack[0]]
  }
}

module "lambda" {
  source = "../lambda-function"

  function_name      = "${var.name_prefix}-agent-phase"
  tags               = var.tags
  package_zip_path   = var.lambda_package_zip_path
  handler            = var.lambda_handler
  architectures      = var.lambda_architectures
  timeout_seconds    = var.lambda_timeout_seconds
  memory_mb          = var.lambda_memory_mb
  log_retention_days = var.log_retention_days

  environment = merge(
    {
      MODHUB_WORKSPACE_BUCKET        = var.workspaces_bucket_name
      MODHUB_FETCH_DOC_FUNCTION_NAME = var.fetch_doc_lambda_name
      BEDROCK_MODEL_ANALYSIS         = var.analysis_model_id
      MODHUB_MODEL_PRICING           = jsonencode(var.model_pricing)
    },
    var.code_model_id == null ? {} : {
      BEDROCK_MODEL_CODE = var.code_model_id
    },
    var.create_guardrail ? {
      MODHUB_BEDROCK_GUARDRAIL_ID      = local.guardrail_id
      MODHUB_BEDROCK_GUARDRAIL_VERSION = local.guardrail_version
      } : {
      MODHUB_GUARDRAIL_OPTIONAL = "true"
    },
    var.extra_environment_variables
  )
}

moved {
  from = aws_iam_role.agent_phase_lambda
  to   = module.lambda.aws_iam_role.this
}

moved {
  from = aws_iam_role_policy_attachment.lambda_basic_logs
  to   = module.lambda.aws_iam_role_policy_attachment.basic_logs
}

moved {
  from = aws_cloudwatch_log_group.agent_phase_lambda
  to   = module.lambda.aws_cloudwatch_log_group.this
}

moved {
  from = aws_lambda_function.agent_phase
  to   = module.lambda.aws_lambda_function.this
}

data "aws_iam_policy_document" "agent_phase_lambda_scope" {
  statement {
    sid       = "InvokeOnlyTheResolvedModelIds"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = local.model_arns
  }

  statement {
    sid       = "CountTokensBeforeEachCall"
    effect    = "Allow"
    actions   = ["bedrock:CountTokens"]
    resources = local.model_arns
  }

  statement {
    sid       = "ReadWorkspaces"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.workspaces_bucket_arn}/ws/*"]
  }

  statement {
    sid       = "WriteOnlyTheWorkingCopyAndPhaseTrail"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${var.workspaces_bucket_arn}/ws/*/v1/*", "${var.workspaces_bucket_arn}/ws/*/phases/*"]
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

  statement {
    sid       = "InvokeFetchDocLambdaOnly"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [var.fetch_doc_lambda_arn]
  }

  dynamic "statement" {
    for_each = var.create_guardrail ? [1] : []
    content {
      sid       = "ApplyTheOneConfiguredGuardrailOnly"
      effect    = "Allow"
      actions   = ["bedrock:ApplyGuardrail"]
      resources = [aws_bedrock_guardrail.prompt_attack[0].guardrail_arn]
    }
  }
}

resource "aws_iam_role_policy" "agent_phase_lambda_scope" {
  name   = "${var.name_prefix}-agent-phase-lambda-scope"
  role   = module.lambda.role_id
  policy = data.aws_iam_policy_document.agent_phase_lambda_scope.json

  lifecycle {
    precondition {
      condition     = alltrue([for id in local.model_ids : contains(keys(var.model_pricing), id)])
      error_message = "Every configured Bedrock model needs an entry in model_pricing -- an unpriced model would fail the first phase that spends budget."
    }
  }
}

resource "aws_cloudwatch_log_group" "bedrock_invocations" {
  count = var.enable_invocation_logging ? 1 : 0

  name              = "/aws/bedrock/${var.name_prefix}-invocations"
  retention_in_days = var.invocation_log_retention_days

  tags = var.tags
}

data "aws_iam_policy_document" "bedrock_logging_assume_role" {
  count = var.enable_invocation_logging ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "bedrock_logging" {
  count = var.enable_invocation_logging ? 1 : 0

  name               = "${var.name_prefix}-bedrock-logging-role"
  assume_role_policy = data.aws_iam_policy_document.bedrock_logging_assume_role[0].json

  tags = var.tags
}

resource "aws_iam_role_policy" "bedrock_logging" {
  count = var.enable_invocation_logging ? 1 : 0

  name = "${var.name_prefix}-bedrock-logging"
  role = aws_iam_role.bedrock_logging[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.bedrock_invocations[0].arn}:*"
    }]
  })
}

resource "aws_bedrock_model_invocation_logging_configuration" "this" {
  count = var.enable_invocation_logging ? 1 : 0

  logging_config {
    embedding_data_delivery_enabled = false
    image_data_delivery_enabled     = false
    text_data_delivery_enabled      = true

    cloudwatch_config {
      log_group_name = aws_cloudwatch_log_group.bedrock_invocations[0].name
      role_arn       = aws_iam_role.bedrock_logging[0].arn
    }
  }

  depends_on = [aws_iam_role_policy.bedrock_logging]
}
