# infrastructure/modules/orchestration
#
# Task 1.5-tf (PLAN.md). The Step Functions state machine that drives a
# modernization run through its seven stub phases:
#   fetch_repo -> baseline -> discovery/plan -> [await approval] -> implement -> verify -> core_ops
#
# The ASL itself lives in ./asl/state_machine.asl.json (tightly coupled to
# this resource, so it is authored alongside it rather than in services/).
# All phases besides "await approval" are Pass-state stubs today; the
# "await approval" phase is modeled as a Task with a PLACEHOLDER function ARN
# because it is the one phase whose real shape (waitForTaskToken callback,
# Fase 4) is already known and worth encoding now — see the ASL file's
# per-state comments for what each stub becomes in later Fases.
#
# IAM: kept intentionally minimal. Today the state machine only needs to be
# able to write its own execution logs. It does NOT get DynamoDB or S3
# permissions yet, because every phase is a stub that touches no real
# resource. Those permissions arrive with the phase that needs them:
#   - ecs:RunTask + iam:PassRole scoped to the sandbox task definition (2.3-tf)
#   - lambda:InvokeFunction for fetch_repo / agent_phase / core_ops (2.2-tf, 3.3-tf, 2.6-tf)
#   - sqs:SendMessage to the notifications queue (4.3-tf)
# per CLAUDE.md's IAM-per-service philosophy: a role only ever grows to match
# a capability that actually exists.

locals {
  asl_definition_path = coalesce(var.asl_definition_path, "${path.module}/asl/state_machine.asl.json")
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "state_machine" {
  name               = "${var.name_prefix}-orchestration-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-orchestration-role"
  })
}

resource "aws_cloudwatch_log_group" "state_machine" {
  name              = "/aws/vendedlogs/states/${var.name_prefix}-run"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

# Minimal logging permissions only - no DynamoDB/S3/ECS/Lambda access yet.
data "aws_iam_policy_document" "logging" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "logging" {
  name   = "${var.name_prefix}-orchestration-logging"
  role   = aws_iam_role.state_machine.id
  policy = data.aws_iam_policy_document.logging.json
}

resource "aws_sfn_state_machine" "run" {
  name     = "${var.name_prefix}-run"
  role_arn = aws_iam_role.state_machine.arn
  type     = "STANDARD"

  definition = file(local.asl_definition_path)

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.state_machine.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-run"
  })
}
