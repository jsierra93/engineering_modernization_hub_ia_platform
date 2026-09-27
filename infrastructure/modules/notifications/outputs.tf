output "queue_arn" {
  value = aws_sqs_queue.notifications.arn
}

output "queue_url" {
  value = aws_sqs_queue.notifications.url
}

output "dlq_arn" {
  value = aws_sqs_queue.dlq.arn
}

output "consumer_policy_arn" {
  value = aws_iam_policy.notifications_consumer.arn
}
