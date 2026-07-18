variable "environment" {
  type    = string
  default = "uat"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "allowed_ssh_cidr_blocks" {
  type        = list(string)
  description = "Your IP(s) for SSH, e.g. [\"203.0.113.10/32\"]."
}

variable "allowed_api_cidr_blocks" {
  type        = list(string)
  default     = ["0.0.0.0/0"]
  description = "Restrict in production; UAT may start open then tighten."
}

variable "serving_s3_uri" {
  type = string
  # MUST track s3://civilai-data/dev/serving/current.json (the published pointer). A stale
  # value here is a silent data revert: deploy/entrypoint.sh only fetches when /data is
  # EMPTY, so a running box keeps whatever it has, but a REPLACED instance boots from this
  # URI. This default sat at snapshot_date=2026-07-02 while current.json pointed at
  # 2026-07-15e -- an instance replacement would have silently rolled back the D7/D8/D10/D11
  # data fixes (incl. D8's *_ft/*_pct column renames, which the serving code now expects).
  default = "s3://civilai-data/dev/serving/snapshot_date=2026-07-15e/civil_ai_serving.duckdb"
}

variable "data_lake_bucket" {
  type    = string
  default = "civilai-data"
}

variable "data_lake_prefix" {
  type    = string
  default = "dev"
}

variable "data_api_instance_type" {
  type    = string
  default = "t4g.medium"
}

variable "data_api_github_repo_url" {
  type    = string
  default = "https://github.com/DataFaceLabs/civil-ai-data.git"
}

variable "data_api_git_ref" {
  type = string
  # Same replacement-time hazard as serving_s3_uri above: a REPLACED instance clones
  # civil-ai-data from this ref at boot. Post release-migration (RELEASE-MIGRATION-PLAN.md),
  # the customer-facing backend builds from `main` -- leaving this at develop meant a
  # rebuilt box would silently run unreleased code while deploy-uat.sh deploys main.
  default = "main"
}

variable "github_token_parameter_name" {
  type        = string
  default     = ""
  description = "SSM parameter (name only) with GitHub PAT for EC2 user_data clone."
}

variable "mapbox_access_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "cors_origins" {
  type = list(string)
  # Used by the data-API EC2 CORSMiddleware *and* S3 bucket CORS for
  # browser→presigned-URL artifact uploads (exhibits, logos). Must include every
  # FE Origin that puts directly to s3://civilai-data.
  default = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "https://www.civil1.ai",
    "https://civil1.ai",
  ]
}

variable "cognito_callback_urls" {
  type    = list(string)
  default = ["http://localhost:5173/fstudio/*/login/callback"]
}

variable "cognito_logout_urls" {
  type    = list(string)
  default = ["http://localhost:5173/fstudio/*/login"]
}

variable "data_api_only" {
  type        = bool
  default     = true
  description = "When true, deploy only secrets + EC2 data API (skip platform/FE/AgentCore)."
}

variable "create_platform_persistence" {
  type        = bool
  default     = false
  description = "DynamoDB + S3 app bucket + Cognito + Bedrock IAM (for hosted platform)."
}

variable "lambda_package_path" {
  type    = string
  default = "../../../dist/platform-lambda.zip"
}

variable "create_platform_http_api" {
  type        = bool
  default     = false
  description = "Lambda + HTTP API Gateway (not needed for local FE + local platform)."
}

variable "dev_auth" {
  type        = bool
  default     = false
  description = "Enable POST /v1/dev/bootstrap email-only login. See api-gateway module for the security caveat -- only for URLs not meant to be publicly discoverable."
}

variable "create_amplify_app" {
  type    = bool
  default = false
}

variable "ses_from_email" {
  type        = string
  default     = ""
  description = "Verified SES sender for Cognito emails (password reset/invites); empty = Cognito default sender."
}

variable "fe_github_repository_url" {
  type    = string
  default = "https://github.com/DataFaceLabs/civil-ai-fe"
}

variable "fe_branch_name" {
  type    = string
  default = "develop"
}

variable "fe_production_branch_name" {
  type        = string
  default     = ""
  description = "Optional second Amplify branch for the release migration (RELEASE-MIGRATION-PLAN.md). Empty skips it; set to \"main\" in Phase 2 to stand it up alongside fe_branch_name."
}

variable "github_access_token" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GitHub PAT for Amplify and/or EC2 clone of private repos."
}
