# Step Functions state machine (ASL rendered with templatefile) and its IAM role.

locals {
  asl_definition_path = coalesce(var.asl_definition_path, "${path.module}/asl/state_machine.asl.json")

  asl_definition = templatefile(local.asl_definition_path, {
    sandbox_cluster_arn          = var.sandbox_cluster_arn
    sandbox_task_definition_arn  = var.sandbox_task_definition_arn
    sandbox_container_name       = var.sandbox_container_name
    sandbox_subnet_ids           = jsonencode(var.sandbox_subnet_ids)
    sandbox_security_group_ids   = jsonencode(var.sandbox_security_group_ids)
    sandbox_assign_public_ip     = var.sandbox_assign_public_ip ? "ENABLED" : "DISABLED"
    approval_timeout_seconds     = var.approval_timeout_seconds
    sandbox_task_timeout_seconds = var.sandbox_task_timeout_seconds
    agent_task_timeout_seconds   = var.agent_task_timeout_seconds
    lambda_task_timeout_seconds  = var.lambda_task_timeout_seconds
    fetch_repo_lambda_arn        = var.fetch_repo_lambda_arn
    agent_phase_lambda_arn       = var.agent_phase_lambda_arn
    core_ops_lambda_arn          = var.core_ops_lambda_arn
    notifications_queue_url      = var.notifications_queue_url
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
      "arn:${data.aws_partition.current.partition}:events:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:rule/StepFunctionsGetEventsForECSTaskRule"
    ]
  }
}

resource "aws_iam_role_policy" "sandbox_run_task" {
  name   = "${var.name_prefix}-orchestration-sandbox-run-task"
  role   = aws_iam_role.state_machine.id
  policy = data.aws_iam_policy_document.sandbox_run_task.json
}

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

  depends_on = [
    aws_iam_role_policy.logging,
    aws_iam_role_policy.sandbox_run_task,
    aws_iam_role_policy.invoke_fetch_repo,
    aws_iam_role_policy.invoke_agent_phase_and_core_ops,
    aws_iam_role_policy.send_notification,
  ]
}
