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

variable "cognito_hosted_ui_base" {
  type        = string
  description = "Full Hosted UI base URL (https://<domain>.auth.<region>.amazoncognito.com), e.g. cognito module's hosted_ui_base_url output."
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

  # WEB_COMPUTE, not WEB: the FE is a TanStack Start SSR app. `npm run build` runs nitro's
  # aws_amplify preset (vite.config.ts), which emits `.amplify-hosting/` -- static assets +
  # a Node compute bundle + deploy-manifest.json. WEB would host the artifact as plain
  # static files and never start the SSR server; WEB_COMPUTE reads the manifest and runs
  # compute/default/server.js on nodejs20.x.
  platform = "WEB_COMPUTE"

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
        baseDirectory: .amplify-hosting
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
    VITE_CIVILAI_COGNITO_HOSTED_UI_BASE = var.cognito_hosted_ui_base
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
  # Informational label; the SSR behavior itself comes from the app-level
  # WEB_COMPUTE platform + the build artifact's deploy-manifest.json.
  framework = "Web Compute"
  stage     = var.environment == "prod" ? "PRODUCTION" : "DEVELOPMENT"
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
