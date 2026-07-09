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
  type    = string
  default = "s3://civilai-data/dev/serving/snapshot_date=2026-07-02/civil_ai_serving.duckdb"
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
  type    = string
  default = "develop"
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
  type    = list(string)
  default = ["http://localhost:5173", "http://localhost:3000"]
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
  type    = bool
  default = false
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

variable "create_amplify_app" {
  type    = bool
  default = false
}

variable "fe_github_repository_url" {
  type    = string
  default = "https://github.com/DataFaceLabs/civil-ai-fe"
}

variable "fe_branch_name" {
  type    = string
  default = "develop"
}

variable "github_access_token" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GitHub PAT for Amplify and/or EC2 clone of private repos."
}
