variable "name_prefix" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}
variable "runs_table_name" { type = string }
variable "runs_table_arn" { type = string }
variable "workspaces_bucket_name" { type = string }
variable "workspaces_bucket_arn" { type = string }
variable "github_token_secret_arn" { type = string }
variable "lambda_package_zip_path" { type = string }
variable "lambda_runtime" {
  type    = string
  default = "python3.14"
}
variable "lambda_architectures" {
  type    = list(string)
  default = ["arm64"]
}
variable "lambda_timeout_seconds" {
  type    = number
  default = 60
}
variable "lambda_memory_mb" {
  type    = number
  default = 512
}
variable "log_retention_days" {
  type    = number
  default = 14
}
