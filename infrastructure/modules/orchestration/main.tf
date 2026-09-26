# infrastructure/modules/orchestration
#
# Task 1.5-tf (PLAN.md), extended by task 2.3/2.3-tf. The Step Functions
# state machine that drives a modernization run through its seven phases:
#   fetch_repo -> baseline -> discovery/plan -> [await approval] -> implement -> verify -> core_ops
#
# The ASL itself lives in ./asl/state_machine.asl.json (tightly coupled to
# this resource, so it is authored alongside it rather than in services/).
# As of 2.3-tf, "Baseline" is a real arn:aws:states:::ecs:runTask.sync
# integration against the sandbox-network module (see the ASL file's own
# comment on that state for the exact contract and its documented
# assumption about the sandbox image's entrypoint). "await approval" is
# modeled as a Task with a PLACEHOLDER function ARN because it is the one
# remaining stub whose real shape (waitForTaskToken callback, Fase 4) is
# already known and worth encoding now. Every other phase is still a
# Pass-state stub - see the ASL file's per-state comments for what each
# becomes in later Fases.
#
# IAM: kept intentionally minimal, growing only with the phase that needs
# it, per CLAUDE.md's IAM-per-service philosophy - a role only ever grows
# to match a capability that actually exists:
#   - logs:* (this file, 1.5-tf): write its own execution logs
#   - ecs:RunTask + iam:PassRole, scoped to the sandbox task definition and
#     its execution role only (this file, 2.3-tf)
#   - lambda:InvokeFunction for fetch_repo (2.2-tf, this file) - added
#   - lambda:InvokeFunction for agent_phase / core_ops (3.3-tf, 2.6-tf) - NOT YET ADDED
#   - sqs:SendMessage to the notifications queue (4.3-tf) - NOT YET ADDED
# It does NOT get DynamoDB or S3 permissions directly - those live behind
# the Lambdas the state machine invokes, not on the state machine's own role.

locals {
  asl_definition_path = coalesce(var.asl_definition_path, "${path.module}/asl/state_machine.asl.json")

  # Task 2.3-tf: the Baseline state's ECS RunTask.sync integration needs the
  # sandbox's cluster/task-definition/network wiring rendered into the
  # static ASL JSON. templatefile() substitutes these ${...} placeholders;
  # the rest of the ASL file is untouched JSON (no other ${} usage exists
  # in it today).
  asl_definition = templatefile(local.asl_definition_path, {
    sandbox_cluster_arn         = var.sandbox_cluster_arn
    sandbox_task_definition_arn = var.sandbox_task_definition_arn
    sandbox_container_name      = var.sandbox_container_name
    sandbox_subnet_ids          = jsonencode(var.sandbox_subnet_ids)
    sandbox_security_group_ids  = jsonencode(var.sandbox_security_group_ids)
    sandbox_assign_public_ip    = var.sandbox_assign_public_ip ? "ENABLED" : "DISABLED"
    fetch_repo_lambda_arn       = var.fetch_repo_lambda_arn
    agent_phase_lambda_arn      = var.agent_phase_lambda_arn
    core_ops_lambda_arn         = var.core_ops_lambda_arn
    notifications_queue_url    = var.notifications_queue_url
  })
}

data "aws_partition" "current" {}
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

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

# Task 2.3-tf: ecs:RunTask + iam:PassRole, scoped exactly to the sandbox
# task definition and its execution role - never a wildcard across all task
# definitions or all roles. ecs:StopTask/DescribeTasks (needed by the
# .sync integration to poll/stop the task it started) and the
# events:PutRule/PutTargets/DescribeRule trio (needed by .sync to manage
# the AWS-owned "StepFunctionsGetEventForECSTaskRule" EventBridge rule that
# reports task completion back to the state machine) cannot be scoped to a
# single task/rule ARN ahead of time - AWS's ecs:RunTask.sync contract
# requires them at the API level - so they are instead conditioned on the
# specific sandbox cluster (ecs:cluster) or restricted to that one
# AWS-managed rule ARN. See CLAUDE.md's "no wildcard IAM" rule.
data "aws_iam_policy_document" "sandbox_run_task" {
  statement {
    sid       = "RunSandboxTaskDefinitionOnly"
    effect    = "Allow"
    actions   = ["ecs:RunTask"]
    resources = [var.sandbox_task_definition_arn]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [var.sandbox_cluster_arn]
    }
  }

  statement {
    sid    = "ManageSandboxTaskLifecycle"
    effect = "Allow"
    actions = [
      "ecs:StopTask",
      "ecs:DescribeTasks",
    ]
    resources = ["*"]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [var.sandbox_cluster_arn]
    }
  }

  statement {
    sid       = "PassSandboxExecutionRoleOnly"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [var.sandbox_execution_role_arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }

  statement {
    sid    = "EcsRunTaskSyncManagedEventRule"
    effect = "Allow"
    actions = [
      "events:PutTargets",
      "events:PutRule",
      "events:DescribeRule",
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:events:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:rule/StepFunctionsGetEventForECSTaskRule"
    ]
  }
}

resource "aws_iam_role_policy" "sandbox_run_task" {
  name   = "${var.name_prefix}-orchestration-sandbox-run-task"
  role   = aws_iam_role.state_machine.id
  policy = data.aws_iam_policy_document.sandbox_run_task.json
}

# Task 2.2-tf integration: the FetchRepo state invokes exactly one Lambda.
# No wildcard across functions -- this state machine can never invoke
# anything but the specific fetch_repo function it was wired to.
data "aws_iam_policy_document" "invoke_fetch_repo" {
  statement {
    sid       = "InvokeFetchRepoLambdaOnly"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [var.fetch_repo_lambda_arn]
  }
}

resource "aws_iam_role_policy" "invoke_fetch_repo" {
  name   = "${var.name_prefix}-orchestration-invoke-fetch-repo"
  role   = aws_iam_role.state_machine.id
  policy = data.aws_iam_policy_document.invoke_fetch_repo.json
}

# Fase 3 integration: DiscoveryPlan/Implement/Fix invoke agent_phase;
# CoreOps (and record_plan after DiscoveryPlan) invokes core_ops. Each
# scoped to exactly one function ARN, same pattern as invoke_fetch_repo.
data "aws_iam_policy_document" "invoke_agent_phase_and_core_ops" {
  statement {
    sid       = "InvokeAgentPhaseLambdaOnly"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [var.agent_phase_lambda_arn]
  }

  statement {
    sid       = "InvokeCoreOpsLambdaOnly"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [var.core_ops_lambda_arn]
  }
}

resource "aws_iam_role_policy" "invoke_agent_phase_and_core_ops" {
  name   = "${var.name_prefix}-orchestration-invoke-agent-phase-core-ops"
  role   = aws_iam_role.state_machine.id
  policy = data.aws_iam_policy_document.invoke_agent_phase_and_core_ops.json
}

# Task 4.3-tf: NotifyApprovalPending's arn:aws:states:::sqs:sendMessage
# integration, scoped to exactly the one notifications queue.
data "aws_iam_policy_document" "send_notification" {
  statement {
    sid       = "SendToNotificationsQueueOnly"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [var.notifications_queue_arn]
  }
}

resource "aws_iam_role_policy" "send_notification" {
  name   = "${var.name_prefix}-orchestration-send-notification"
  role   = aws_iam_role.state_machine.id
  policy = data.aws_iam_policy_document.send_notification.json
}

resource "aws_sfn_state_machine" "run" {
  name     = "${var.name_prefix}-run"
  role_arn = aws_iam_role.state_machine.arn
  type     = "STANDARD"

  definition = local.asl_definition

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.state_machine.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-run"
  })
}
