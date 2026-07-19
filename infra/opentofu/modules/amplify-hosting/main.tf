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

variable "production_branch_name" {
  type        = string
  default     = ""
  description = "Optional second Amplify branch (e.g. \"main\") built alongside branch_name, for the dev/prod release split. Empty string skips it entirely -- inert for any caller that hasn't opted in."
}

variable "platform_api_base" {
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

variable "develop_basic_auth_username" {
  type    = string
  default = "civil1ai-team"
}

variable "develop_basic_auth_password" {
  type        = string
  sensitive   = true
  default     = ""
  description = "HTTP Basic Auth password gating the branch_name (team test space) URL -- an outer, network-level gate in front of Cognito, so an unauthenticated visitor can't reach any page (including the real login screen) without it. Empty string leaves the branch open, matching prior behavior."
}

locals {
  # Fixed product name, not per-environment: since the release migration this one app
  # hosts two branches (branch_name = the team's test space, production_branch_name =
  # deliberate releases), so a suffix tied to a single environment no longer fits either.
  # The Environment tag below still identifies which tofu environment owns the app.
  name = "civilai-fe"
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
            # Heap headroom for the Vite production build: the FE client bundle is large
            # enough (mapbox, recharts, tiptap, html-to-docx polyfill graph) that chunk
            # rendering can exceed Node's default ~2GB old-space cap and OOM (exit 134).
            # Scoped to the build command so it does not affect the SSR compute runtime.
            - NODE_OPTIONS=--max-old-space-size=4096 npm run build
      artifacts:
        baseDirectory: .amplify-hosting
        files:
          - '**/*'
      cache:
        paths:
          - node_modules/**/*
  EOT

  # Do NOT set VITE_CIVILAI_API_BASE here. UAT/prod FE builds use PLATFORM_MODE + the
  # HTTPS platform data-proxy; baking the EC2 HTTP data API (`http://{eip}:8000`) into
  # Amplify caused Chrome mixed-content ("Not secure" with a valid certificate).
  # Lambda still uses CIVILAI_DATA_API_BASE (server-side) for lake reads.
  # Prompt Lab config is resolved by platform agent-runs; deployed builds have one
  # production section-draft path through Strands.
  environment_variables = {
    VITE_CIVILAI_PLATFORM_MODE          = "true"
    VITE_CIVILAI_PLATFORM_API           = var.platform_api_base
    VITE_CIVILAI_COGNITO_CLIENT_ID      = var.cognito_client_id
    VITE_CIVILAI_COGNITO_HOSTED_UI_BASE = var.cognito_hosted_ui_base
    VITE_MAPBOX_PUBLIC_TOKEN            = var.mapbox_public_token
    VITE_CIVILAI_AGENT_DEV_MODE         = "false"
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

  # Release migration Phase 4: gate the team test-space branch behind HTTP Basic Auth, an
  # outer network-level gate in front of Cognito -- unlike production_branch_name below,
  # which never gets this (it's the real product, reached through civil1.ai).
  enable_basic_auth = var.develop_basic_auth_password != ""
  basic_auth_credentials = var.develop_basic_auth_password != "" ? base64encode(
    "${var.develop_basic_auth_username}:${var.develop_basic_auth_password}"
  ) : null

  lifecycle {
    # Provider quirk: the Amplify API never echoes basic_auth_credentials back in a
    # form that matches what we send, so this attribute re-plans as an in-place
    # update on EVERY run — even immediately after a successful apply with
    # -refresh=false (verified 2026-07-19). Live value was converged to the SSM
    # parameter (/civilai/<env>/develop-basic-auth-password) on that date. To
    # rotate: change the password source, then run a targeted apply with this
    # ignore temporarily removed, or `aws amplify update-branch` directly.
    ignore_changes = [basic_auth_credentials]
  }
}

# Release migration (RELEASE-MIGRATION-PLAN.md, Phase 2): a second branch on the same app,
# built from the same app-level config/env vars as branch_name -- so it is byte-identical
# in every way that matters except which git branch it tracks. This is what lets the custom
# domain later point at "main" (deliberate releases) while branch_name ("develop") stays the
# team's continuous test space, with zero config drift between them.
resource "aws_amplify_branch" "production" {
  count       = var.production_branch_name != "" ? 1 : 0
  app_id      = aws_amplify_app.fe.id
  branch_name = var.production_branch_name

  enable_auto_build = true
  framework         = "Web Compute"
  stage             = "PRODUCTION"
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

output "production_branch_url" {
  value = var.production_branch_name != "" ? "https://${var.production_branch_name}.${aws_amplify_app.fe.default_domain}" : null
}
