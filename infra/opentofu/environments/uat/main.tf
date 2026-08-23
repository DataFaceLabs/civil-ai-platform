terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "civilai"
      Environment = var.environment
      ManagedBy   = "opentofu"
    }
  }
}

data "aws_s3_bucket" "data_lake" {
  bucket = var.data_lake_bucket
}

# Browser PUTs of exhibits/logos use S3 presigned URLs against this bucket, so
# the browser Origin (www.civil1.ai) must be allowed here — API Gateway CORS
# does not cover the S3 host. Without this, uploads fail with:
#   No 'Access-Control-Allow-Origin' header is present on the requested resource.
resource "aws_s3_bucket_cors_configuration" "data_lake" {
  bucket = data.aws_s3_bucket.data_lake.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "HEAD"]
    allowed_origins = var.cors_origins
    # Range headers are required, not cosmetic: PMTiles fetches map tiles as HTTP
    # byte ranges, and a browser cannot read the response without Accept-Ranges /
    # Content-Range / Content-Length being exposed. These were set directly on the
    # bucket during the 2026-07-24 PMTiles work and never recorded here, so a
    # `tofu apply` would have silently reverted them and broken Explorer overlays.
    # Found 2026-08-02 by the H0-IACDRIFT check.
    expose_headers  = ["ETag", "Accept-Ranges", "Content-Range", "Content-Length", "Content-Type"]
    max_age_seconds = 3600
  }
}

module "secrets" {
  source = "../../modules/secrets"

  environment         = var.environment
  mapbox_access_token = var.mapbox_access_token
  github_access_token = var.github_access_token
  tavily_api_key      = var.tavily_api_key
}

module "cognito" {
  count  = var.create_platform_persistence ? 1 : 0
  source = "../../modules/cognito"

  environment    = var.environment
  aws_region     = var.aws_region
  callback_urls  = var.cognito_callback_urls
  logout_urls    = var.cognito_logout_urls
  ses_from_email = var.ses_from_email
}

module "bedrock" {
  count       = var.create_platform_persistence || var.create_platform_http_api ? 1 : 0
  source      = "../../modules/bedrock"
  environment = var.environment
}

module "dynamodb" {
  count       = var.create_platform_persistence ? 1 : 0
  source      = "../../modules/dynamodb"
  environment = var.environment
}

# Isolated TPO develop-plane table. Name is civilai-app-develop, not civilai-app-dev
# (that table is the laptop ensure_dev_persistence default and is dirty).
module "dynamodb_develop" {
  count       = var.create_develop_plane && var.create_platform_persistence ? 1 : 0
  source      = "../../modules/dynamodb"
  environment = "develop"
}

module "s3_app" {
  count        = var.create_platform_persistence ? 1 : 0
  source       = "../../modules/s3"
  environment  = var.environment
  cors_origins = var.cors_origins
}

module "s3_agent_corpus" {
  count       = var.create_platform_persistence ? 1 : 0
  source      = "../../modules/s3-agent-corpus"
  environment = var.environment
}

module "data_api_ec2" {
  source = "../../modules/data-api-ec2"

  environment                = var.environment
  aws_region                 = var.aws_region
  instance_type              = var.data_api_instance_type
  allowed_ssh_cidr_blocks    = var.allowed_ssh_cidr_blocks
  allowed_api_cidr_blocks    = var.allowed_api_cidr_blocks
  serving_s3_uri             = var.serving_s3_uri
  dev_serving_s3_uri         = var.dev_serving_s3_uri
  data_lake_bucket           = var.data_lake_bucket
  data_lake_prefix           = var.data_lake_prefix
  data_service_key_parameter = module.secrets.data_service_key_parameter_name
  mapbox_parameter           = module.secrets.mapbox_parameter_name
  cors_origins               = join(",", var.cors_origins)
  github_repo_url            = var.data_api_github_repo_url
  github_token_parameter     = module.secrets.github_token_parameter_name
  git_ref                    = var.data_api_git_ref
}

module "api_gateway" {
  count  = var.create_platform_http_api ? 1 : 0
  source = "../../modules/api-gateway"

  environment                = var.environment
  aws_region                 = var.aws_region
  cognito_user_pool_arn      = module.cognito[0].user_pool_arn
  cognito_user_pool_id       = module.cognito[0].user_pool_id
  cognito_client_id          = module.cognito[0].app_client_id
  # Trust Hosted UI client id — set via tfvars from amplify_trust_cognito_client_id
  # output (avoids api_gateway ↔ amplify_trust cycle). Empty until Trust Amplify exists.
  cognito_trust_client_id    = var.cognito_trust_client_id
  bedrock_policy_arn         = module.bedrock[0].invoke_policy_arn
  dynamodb_table_arn         = module.dynamodb[0].table_arn
  dynamodb_table_name        = module.dynamodb[0].table_name
  denied_dynamodb_table_arns = (
    var.create_develop_plane && var.create_platform_persistence
    ? [module.dynamodb_develop[0].table_arn]
    : []
  )
  app_bucket_arn             = data.aws_s3_bucket.data_lake.arn
  agent_corpus_bucket        = module.s3_agent_corpus[0].bucket_name
  agent_corpus_bucket_arn    = module.s3_agent_corpus[0].bucket_arn
  data_api_base_url          = module.data_api_ec2.data_api_base_url_http
  dev_data_api_base_url      = module.data_api_ec2.dev_data_api_base_url_http
  dev_data_origins           = var.dev_data_origins
  data_service_key_parameter = module.secrets.data_service_key_parameter_name
  data_service_key           = module.secrets.data_service_key
  tavily_api_key             = module.secrets.tavily_api_key
  create_http_api            = true
  lambda_package_path        = var.lambda_package_path
  dev_auth                   = var.dev_auth
}

# Second HTTP API + Lambda (civilai-develop-api). Same Cognito pool. Data API is
# always :8001 on this function (empty Origin split). Do not apply until plan review.
module "api_gateway_develop" {
  count  = var.create_develop_plane && var.create_platform_http_api && var.create_platform_persistence ? 1 : 0
  source = "../../modules/api-gateway"

  environment                = "develop"
  aws_region                 = var.aws_region
  cognito_user_pool_arn      = module.cognito[0].user_pool_arn
  cognito_user_pool_id       = module.cognito[0].user_pool_id
  cognito_client_id          = module.cognito[0].app_client_id
  cognito_trust_client_id    = var.cognito_trust_client_id
  bedrock_policy_arn         = module.bedrock[0].invoke_policy_arn
  dynamodb_table_arn         = module.dynamodb_develop[0].table_arn
  dynamodb_table_name        = module.dynamodb_develop[0].table_name
  denied_dynamodb_table_arns = [module.dynamodb[0].table_arn]
  ssm_parameter_path_prefix  = "/civilai/uat"
  app_bucket_arn             = data.aws_s3_bucket.data_lake.arn
  agent_corpus_bucket        = module.s3_agent_corpus[0].bucket_name
  agent_corpus_bucket_arn    = module.s3_agent_corpus[0].bucket_arn
  data_api_base_url          = module.data_api_ec2.dev_data_api_base_url_http
  dev_data_api_base_url      = ""
  dev_data_origins           = []
  data_service_key_parameter = module.secrets.data_service_key_parameter_name
  data_service_key           = module.secrets.data_service_key
  tavily_api_key             = module.secrets.tavily_api_key
  create_http_api            = true
  lambda_package_path        = var.lambda_package_path
  dev_auth                   = var.dev_auth
}

module "observability" {
  count  = var.create_platform_http_api ? 1 : 0
  source = "../../modules/observability"

  environment              = var.environment
  lambda_function_name     = module.api_gateway[0].lambda_function_name
  alarm_notification_email = var.alarm_notification_email
}

module "agentcore" {
  count  = var.create_platform_http_api ? 1 : 0
  source = "../../modules/agentcore"

  environment       = var.environment
  aws_region        = var.aws_region
  lambda_role_arn   = module.api_gateway[0].lambda_role_arn
  app_bucket_arn    = data.aws_s3_bucket.data_lake.arn
  data_api_base_url = module.data_api_ec2.data_api_base_url_http
}

module "agentcore_develop" {
  count  = var.create_develop_plane && var.create_platform_http_api && var.create_platform_persistence ? 1 : 0
  source = "../../modules/agentcore"

  environment       = "develop"
  aws_region        = var.aws_region
  lambda_role_arn   = module.api_gateway_develop[0].lambda_role_arn
  app_bucket_arn    = data.aws_s3_bucket.data_lake.arn
  data_api_base_url = module.data_api_ec2.dev_data_api_base_url_http
}

module "observability_develop" {
  count  = var.create_develop_plane && var.create_platform_http_api && var.create_platform_persistence ? 1 : 0
  source = "../../modules/observability"

  environment              = "develop"
  lambda_function_name     = module.api_gateway_develop[0].lambda_function_name
  alarm_notification_email = var.alarm_notification_email
}

module "amplify" {
  count  = var.create_amplify_app ? 1 : 0
  source = "../../modules/amplify-hosting"

  environment                 = var.environment
  repository_url              = var.fe_github_repository_url
  github_access_token         = var.github_access_token
  branch_name                 = var.fe_branch_name
  production_branch_name      = var.fe_production_branch_name
  develop_basic_auth_password = module.secrets.develop_basic_auth_password
  platform_api_base           = var.create_platform_http_api ? module.api_gateway[0].api_endpoint : "http://localhost:8001"
  develop_platform_api_base   = (
    var.create_develop_plane && var.create_platform_http_api && var.create_platform_persistence
    ? module.api_gateway_develop[0].api_endpoint
    : ""
  )
  cognito_user_pool_id        = var.create_platform_persistence ? module.cognito[0].user_pool_id : ""
  cognito_client_id           = var.create_platform_persistence ? module.cognito[0].app_client_id : ""
  cognito_hosted_ui_base      = var.create_platform_persistence ? module.cognito[0].hosted_ui_base_url : ""
  mapbox_public_token         = var.mapbox_access_token
  data_lake_bucket_name       = var.data_lake_bucket
}

# Trust Console — separate Amplify app (H0-AMPLIFY: must not replace product d3joxyeudajkza).
# Cognito trust-reviewer group ships with module.cognito; dedicated Hosted UI client is
# created inside amplify-trust-console once the app default_domain is known.
module "amplify_trust" {
  count  = var.create_amplify_trust_app ? 1 : 0
  source = "../../modules/amplify-trust-console"

  environment            = var.environment
  repository_url         = var.fe_github_repository_url
  github_access_token    = var.github_access_token
  branch_name            = var.fe_branch_name
  platform_api_base      = var.create_platform_http_api ? module.api_gateway[0].api_endpoint : "http://localhost:8001"
  cognito_user_pool_id   = var.create_platform_persistence ? module.cognito[0].user_pool_id : ""
  cognito_hosted_ui_base = var.create_platform_persistence ? module.cognito[0].hosted_ui_base_url : ""
  mapbox_public_token    = var.mapbox_access_token
}
