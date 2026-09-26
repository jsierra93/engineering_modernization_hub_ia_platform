variable "name_prefix" {
  description = "Prefix applied to all resource names created by this module (e.g. \"modhub-personal\")."
  type        = string
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}

variable "runs_table_billing_mode" {
  description = "DynamoDB billing mode for the runs and events tables. PAY_PER_REQUEST keeps the prototype cost near-zero."
  type        = string
  default     = "PAY_PER_REQUEST"
}

variable "s3_force_destroy" {
  description = "Allow Terraform to destroy the workspace bucket even if it still holds objects. Convenient for a throwaway prototype env; leave false anywhere state matters."
  type        = bool
  default     = false
}
