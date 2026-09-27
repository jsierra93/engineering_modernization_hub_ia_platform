# infrastructure/modules/notifications
#
# Task 4.3-tf (PLAN.md). One SQS queue + DLQ. The orchestration module's
# state machine role gets sqs:SendMessage scoped to this queue (wired in
# infrastructure/modules/orchestration, not here -- this module only owns
# the queue itself, matching the persistence/orchestration split
# elsewhere: a module owns a resource's lifecycle, IAM to reach it lives
# with whichever caller needs it). Fase 5.2's modhub-backend gets its own
# read-only identity (task 5.2-tf) scoped to sqs:ReceiveMessage +
# sqs:DeleteMessage on this same queue -- built when Fase 5 lands, not
# here.

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name_prefix}-notifications-dlq"
  message_retention_seconds = var.message_retention_seconds

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-notifications-dlq"
  })
}

resource "aws_sqs_queue" "notifications" {
  name                      = "${var.name_prefix}-notifications"
  message_retention_seconds = var.message_retention_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-notifications"
  })
}

# Task 5.2-tf. Backstage runs on the operator's machine in this prototype,
# under their own credentials, so nothing attaches this yet -- it exists so
# the least-privilege boundary is defined in code rather than described in
# prose, and is ready to attach the day Backstage gets its own identity.
resource "aws_iam_policy" "notifications_consumer" {
  name        = "${var.name_prefix}-notifications-consumer"
  description = "Receive and delete from the modhub notifications queue. Nothing else."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
      Resource = aws_sqs_queue.notifications.arn
    }]
  })

  tags = var.tags
}
