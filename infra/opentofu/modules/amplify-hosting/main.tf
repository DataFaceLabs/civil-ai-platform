variable "environment" {
  type = string
}

variable "repository_url" {
  type        = string
  description = "GitHub HTTPS URL for civil-ai-fe."
}

variable "github_access_token" {
  type        = string
  sensitive   = true
  description = "GitHub PAT with repo access for Amplify CI."
}

variable "branch_name" {
  type    = string
  default = "develop"
}

variable "platform_api_base" {
  type = string
}

variable "data_api_base" {
  type = string
}

variable "cognito_user_pool_id" {
  type = string
}

variable "cognito_client_id" {
  type = string
}

variable "cognito_domain" {
  type = string
}

variable "mapbox_public_token" {
  type      = string
  sensitive = true
  default   = ""
}

locals {
  name = "civilai-fe-${var.environment}"
}

resource "aws_amplify_app" "fe" {
  name       = local.name
  repository = var.repository_url

  access_token = var.github_access_token

  platform = "WEB"

  build_spec = <<-EOT
    version: 1
    frontend:
      phases:
        preBuild:
          commands:
            - npm ci
        build:
          commands:
            - npm run build
      artifacts:
        baseDirectory: dist
        files:
          - '**/*'
      cache:
        paths:
          - node_modules/**/*
  EOT

  environment_variables = {
    VITE_CIVILAI_PLATFORM_MODE   = "true"
    VITE_CIVILAI_PLATFORM_API    = var.platform_api_base
    VITE_CIVILAI_API_BASE        = var.data_api_base
    VITE_CIVILAI_COGNITO_CLIENT_ID = var.cognito_client_id
    VITE_CIVILAI_COGNITO_DOMAIN  = var.cognito_domain
    VITE_MAPBOX_PUBLIC_TOKEN     = var.mapbox_public_token
  }

  tags = {
    Environment = var.environment
    Service     = "frontend"
  }
}

resource "aws_amplify_branch" "main" {
  app_id      = aws_amplify_app.fe.id
  branch_name = var.branch_name

  enable_auto_build = true
  framework         = "Web"
  stage             = var.environment == "prod" ? "PRODUCTION" : "DEVELOPMENT"
}

output "app_id" {
  value = aws_amplify_app.fe.id
}

output "default_domain" {
  value = aws_amplify_app.fe.default_domain
}

output "branch_url" {
  value = "https://${var.branch_name}.${aws_amplify_app.fe.default_domain}"
}
