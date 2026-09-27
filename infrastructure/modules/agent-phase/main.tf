# infrastructure/modules/agent-phase
#
# Tasks 3.3-tf/3.4/3.5/3.8 (PLAN.md). lambda agent_phase is the ONE
# exception to "core_ops never talks to Bedrock" running in reverse: this
# is the LLM-zone Lambda that DOES get bedrock:InvokeModel, scoped to
# exactly the model IDs core_py.bedrock_models resolves -- never a
# wildcard across all foundation models. It also gets its own run's S3
# workspace access (see variables.tf's note on the real per-run boundary
# living in code, not IAM) and permission to invoke exactly one other
# Lambda: fetch_doc.
#
# It does NOT get: DynamoDB access (core_ops owns the verdict/ledger),
# SendTaskSuccess (Step Functions itself calls that, not this Lambda), or
# any permission beyond what a single phase invocation needs to propose,
# never decide.

data "aws_partition" "current" {}
data "aws_caller_identity" "current" {}

locals {
  # Claude 4.5 models are INFERENCE_PROFILE-only: IAM needs the profile ARN
  # plus the underlying model in any region the profile may route to.
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
  guardrail_version = var.create_guardrail ? aws_bedrock_guardrail.prompt_attack[0].version : null
}

# Task 3.7-tf. CLAUDE.md's retrospective names this as the missing second
# layer behind the untrusted-content prompt delimiting (Layer 1, in
# agent_phase.untrusted) -- a Guardrail catching a prompt-attack pattern
# the model itself might still comply with. PROMPT_ATTACK is Bedrock's own
# filter type for exactly this (jailbreak/injection attempts), distinct
# from the content-safety filters (HATE, VIOLENCE, ...) this prototype has
# no particular need for beyond a conservative default.
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

resource "aws_iam_role" "agent_phase_lambda" {
  name               = "${var.name_prefix}-agent-phase-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-agent-phase-lambda-role"
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_logs" {
  role       = aws_iam_role.agent_phase_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "agent_phase_lambda_scope" {
  statement {
    sid       = "InvokeOnlyTheResolvedModelIds"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = local.model_arns
  }

  statement {
    sid    = "WorkspacePrefixReadWrite"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
    ]
    resources = ["${var.workspaces_bucket_arn}/ws/*"]
  }

  # s3:ListBucket is a bucket-level action: on an object ARN it can never
  # match. Scoped by prefix condition instead, so this stays limited to ws/.
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
  role   = aws_iam_role.agent_phase_lambda.id
  policy = data.aws_iam_policy_document.agent_phase_lambda_scope.json
}

resource "aws_cloudwatch_log_group" "agent_phase_lambda" {
  name              = "/aws/lambda/${var.name_prefix}-agent-phase"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

resource "aws_lambda_function" "agent_phase" {
  function_name    = "${var.name_prefix}-agent-phase"
  role             = aws_iam_role.agent_phase_lambda.arn
  handler          = var.lambda_handler
  runtime          = var.lambda_runtime
  architectures    = var.lambda_architectures
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_mb
  filename         = var.lambda_package_zip_path
  source_code_hash = filebase64sha256(var.lambda_package_zip_path)

  environment {
    variables = merge(
      {
        MODHUB_WORKSPACE_BUCKET        = var.workspaces_bucket_name
        MODHUB_FETCH_DOC_FUNCTION_NAME = var.fetch_doc_lambda_name
        # Same vars that scope the IAM policy above, so invoked and allowed
        # models cannot drift.
        BEDROCK_MODEL_ANALYSIS = var.analysis_model_id
      },
      var.code_model_id == null ? {} : {
        BEDROCK_MODEL_CODE = var.code_model_id
      },
      var.create_guardrail ? {
        MODHUB_BEDROCK_GUARDRAIL_ID      = local.guardrail_id
        MODHUB_BEDROCK_GUARDRAIL_VERSION = local.guardrail_version
      } : {},
      var.extra_environment_variables
    )
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-agent-phase"
  })

  depends_on = [aws_cloudwatch_log_group.agent_phase_lambda]
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
