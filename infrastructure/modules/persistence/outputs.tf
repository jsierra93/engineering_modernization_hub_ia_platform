output "runs_table_name" {
  description = "Name of the DynamoDB runs table."
  value       = aws_dynamodb_table.runs.name
}

output "runs_table_arn" {
  description = "ARN of the DynamoDB runs table."
  value       = aws_dynamodb_table.runs.arn
}

output "events_table_name" {
  description = "Name of the DynamoDB events table."
  value       = aws_dynamodb_table.events.name
}

output "events_table_arn" {
  description = "ARN of the DynamoDB events table."
  value       = aws_dynamodb_table.events.arn
}

output "workspaces_bucket_name" {
  description = "Name of the S3 bucket holding ws/vN workspaces, JUnit results, diffs and reports."
  value       = aws_s3_bucket.workspaces.bucket
}

output "workspaces_bucket_arn" {
  description = "ARN of the S3 bucket holding ws/vN workspaces, JUnit results, diffs and reports."
  value       = aws_s3_bucket.workspaces.arn
}
