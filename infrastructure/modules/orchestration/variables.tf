variable "name_prefix" {
  description = "Prefix applied to all resource names created by this module (e.g. \"modhub-personal\")."
  type        = string
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}

variable "asl_definition_path" {
  description = "Path to the Amazon States Language JSON definition for the modernization run state machine. Defaults to the ASL file shipped inside this module (./asl/state_machine.asl.json) when left null."
  type        = string
  default     = null
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the state machine execution logs."
  type        = number
  default     = 14
}
