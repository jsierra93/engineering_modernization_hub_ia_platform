output "queue_arn" {
  value = aws_sqs_queue.notifications.arn
}

output "queue_url" {
  value = aws_sqs_queue.notifications.url
}

output "dlq_arn" {
  value = aws_sqs_queue.dlq.arn
}
