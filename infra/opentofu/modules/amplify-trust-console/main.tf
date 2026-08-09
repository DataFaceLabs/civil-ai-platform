# Trust Console Amplify app — Stage 3 sketch (not wired into UAT apply yet).
#
# Instantiation is gated by environments/uat `create_amplify_trust_app` (default false).
# See docs/TRUST-CONSOLE-AMPLIFY.md before the first plan/apply.

variable "environment" {
  type = string
}

variable "repository_url" {
  type        = string
  description = "GitHub HTTPS URL for civil-ai-fe (same repo as product Amplify)."
}

variable "github_access_token" {
  type      = string
  sensitive = true
}

variable "branch_name" {
  type    = string
  default = "develop"
}

variable "platform_api_base" {
  type = string
}

variable "cognito_user_pool_id" {
  type = string
}

variable "cognito_client_id" {
  type        = string
  description = "Dedicated Trust Console Hosted UI app client (not the product web client)."
}

variable "cognito_hosted_ui_base" {
  type = string
}

variable "mapbox_public_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "basic_auth_username" {
  type    = string
  default = "civil1ai-trust"
}

variable "basic_auth_password" {
  type      = string
  sensitive = true
  default   = ""
}

locals {
  # Include environment so multi-env applies do not collide on Amplify app name.
  name = "${var.environment}-civilai-trust-console"
}

data "aws_iam_policy_document" "amplify_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["amplify.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "amplify" {
  name               = "${var.environment}-civilai-trust-amplify"
  assume_role_policy = data.aws_iam_policy_document.amplify_assume.json

  tags = {
    Environment = var.environment
    Service     = "trust-console"
  }
}

resource "aws_iam_role_policy_attachment" "amplify_backend" {
  role       = aws_iam_role.amplify.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess-Amplify"
}

resource "aws_amplify_app" "trust" {
  name       = local.name
  repository = var.repository_url

  access_token = var.github_access_token

  platform             = "WEB_COMPUTE"
  iam_service_role_arn = aws_iam_role.amplify.arn

  build_spec = <<-EOT
    version: 1
    frontend:
      phases:
        preBuild:
          commands:
            - npm ci
        build:
          commands:
            - NODE_OPTIONS=--max-old-space-size=4096 npm run build
      artifacts:
        baseDirectory: .amplify-hosting
        files:
          - '**/*'
      cache:
        paths:
          - node_modules/**/*
  EOT

  environment_variables = {
    VITE_CIVILAI_PLATFORM_MODE          = "true"
    VITE_CIVILAI_PLATFORM_API           = var.platform_api_base
    VITE_CIVILAI_COGNITO_CLIENT_ID      = var.cognito_client_id
    VITE_CIVILAI_COGNITO_HOSTED_UI_BASE = var.cognito_hosted_ui_base
    VITE_MAPBOX_PUBLIC_TOKEN            = var.mapbox_public_token
    VITE_CIVILAI_AGENT_DEV_MODE         = "false"
    # Isolates Trust Console entry from product civil1.ai builds.
    VITE_CIVILAI_TRUST_CONSOLE          = "true"
    VITE_CIVILAI_DATA_EXPLORER          = "true"
  }

  tags = {
    Environment = var.environment
    Service     = "trust-console"
  }
}

resource "aws_amplify_branch" "main" {
  app_id      = aws_amplify_app.trust.id
  branch_name = var.branch_name

  enable_auto_build = true
  framework         = "Web Compute"
  stage             = "DEVELOPMENT"

  enable_basic_auth = var.basic_auth_password != ""
  basic_auth_credentials = var.basic_auth_password != "" ? base64encode(
    "${var.basic_auth_username}:${var.basic_auth_password}"
  ) : null

  lifecycle {
    ignore_changes = [basic_auth_credentials]
  }
}

output "app_id" {
  value = aws_amplify_app.trust.id
}

output "default_domain" {
  value = aws_amplify_app.trust.default_domain
}

output "branch_url" {
  value = "https://${var.branch_name}.${aws_amplify_app.trust.default_domain}"
}
