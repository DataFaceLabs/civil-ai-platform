variable "environment" {
  type = string
}

variable "mapbox_access_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "github_access_token" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GitHub PAT for EC2 clone of private civil-ai-data repo."
}

resource "random_password" "data_service_key" {
  length  = 48
  special = false
}

resource "aws_ssm_parameter" "data_service_key" {
  name  = "/civilai/${var.environment}/data-service-key"
  type  = "SecureString"
  value = random_password.data_service_key.result

  tags = {
    Environment = var.environment
    Service     = "data-api"
  }
}

resource "aws_ssm_parameter" "mapbox_access_token" {
  count = var.mapbox_access_token != "" ? 1 : 0
  name  = "/civilai/${var.environment}/mapbox-access-token"
  type  = "SecureString"
  value = var.mapbox_access_token

  tags = {
    Environment = var.environment
    Service     = "data-api"
  }
}

output "data_service_key_parameter_name" {
  value = aws_ssm_parameter.data_service_key.name
}

output "data_service_key" {
  value     = random_password.data_service_key.result
  sensitive = true
}

output "mapbox_parameter_name" {
  value = length(aws_ssm_parameter.mapbox_access_token) > 0 ? aws_ssm_parameter.mapbox_access_token[0].name : ""
}

resource "aws_ssm_parameter" "github_access_token" {
  count = var.github_access_token != "" ? 1 : 0
  name  = "/civilai/${var.environment}/github-token"
  type  = "SecureString"
  value = var.github_access_token

  tags = {
    Environment = var.environment
    Service     = "deploy"
  }
}

output "github_token_parameter_name" {
  value = length(aws_ssm_parameter.github_access_token) > 0 ? aws_ssm_parameter.github_access_token[0].name : ""
}
