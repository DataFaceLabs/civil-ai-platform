# Trust Console Amplify app — separate WEB_COMPUTE app on *.amplifyapp.com.
# Same civil-ai-fe repo as product Amplify; VITE_CIVILAI_TRUST_CONSOLE=true only here.
# See docs/TRUST-CONSOLE-AMPLIFY.md.

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
  description = "Optional HTTP Basic Auth on the Trust branch. Empty = Cognito-only (preferred for SME share links)."
}

locals {
  # Include environment so multi-env applies do not collide on Amplify app name.
  name       = "${var.environment}-civilai-trust-console"
  branch_url = "https://${var.branch_name}.${aws_amplify_app.trust.default_domain}"
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

# Dedicated Hosted UI client — callbacks use this app's default domain (known after
# aws_amplify_app.trust is created). Client id is injected on the branch so we avoid
# a cycle with app-level environment_variables.
resource "aws_cognito_user_pool_client" "trust" {
  name         = "civilai-trust-fe-${var.environment}"
  user_pool_id = var.cognito_user_pool_id

  generate_secret = false

  callback_urls = [
    "${local.branch_url}/auth/callback",
  ]
  # FE logout helper for *.amplifyapp.com lands on www.civil1.ai/login (basic-auth
  # safe); also allow the Trust app's own /login for Cognito-only flows.
  logout_urls = [
    "${local.branch_url}/login",
    "https://www.civil1.ai/login",
  ]

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  supported_identity_providers         = ["COGNITO"]

  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]
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

  # App-level env shared by branches. Cognito client id is branch-only (see below).
  environment_variables = {
    VITE_CIVILAI_PLATFORM_MODE          = "true"
    VITE_CIVILAI_PLATFORM_API           = var.platform_api_base
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

  # H0-AMPLIFY: this resource must never share app_id with product civilai-fe
  # (d3joxyeudajkza). Name + separate IAM role keep identity distinct.
  lifecycle {
    precondition {
      condition     = local.name != "civilai-fe"
      error_message = "Trust Amplify app name must not collide with product civilai-fe."
    }
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

  # Branch overrides merge over app-level env — client id lives here to break the
  # amplify_app ↔ cognito_client cycle (callbacks need default_domain).
  environment_variables = {
    VITE_CIVILAI_COGNITO_CLIENT_ID = aws_cognito_user_pool_client.trust.id
  }

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
  value = local.branch_url
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.trust.id
}
