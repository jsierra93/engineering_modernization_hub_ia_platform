# SQS queue that carries approval events to Backstage.

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
