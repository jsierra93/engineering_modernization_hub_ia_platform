variable "name_prefix" {
  description = "Prefix applied to all resource names created by this module (e.g. \"modhub-personal\")."
  type        = string
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}

variable "max_receive_count" {
  description = "How many times a message may be received before it's routed to the DLQ. Fase 5.2's modhub-backend is the only intended consumer; a message that fails this many times almost certainly means the backend itself is broken, not a transient error worth retrying forever."
  type        = number
  default     = 5
}

variable "message_retention_seconds" {
  description = "How long an unconsumed notification stays in the queue -- 4 days, long enough to survive a demo-day gap between a run reaching AWAITING_APPROVAL and someone actually looking at Backstage."
  type        = number
  default     = 345600
}
