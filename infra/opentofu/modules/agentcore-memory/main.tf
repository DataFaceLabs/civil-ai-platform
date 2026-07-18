terraform {
  required_version = ">= 1.6.0"
}

variable "environment" {
  type = string
}

# AgentCore Memory store placeholder — session continuity, not system-of-record.
# Wire to Bedrock AgentCore Memory when enabled in the target account.

output "memory_store_name" {
  value = "civilai-${var.environment}-agent-memory"
}

output "memory_enabled" {
  value = false
  description = "Set true when AgentCore Memory is provisioned in this environment"
}
