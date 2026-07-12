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

module "secrets" {
  source = "../../modules/secrets"

  environment         = var.environment
  mapbox_access_token = var.mapbox_access_token
  github_access_token = var.github_access_token
}

module "cognito" {
  count  = var.create_platform_persistence ? 1 : 0
  source = "../../modules/cognito"

  environment     = var.environment
  aws_region      = var.aws_region
  callback_urls   = var.cognito_callback_urls
  logout_urls     = var.cognito_logout_urls
  ses_from_email  = var.ses_from_email
}

module "bedrock" {
  count  = var.create_platform_persistence || var.create_platform_http_api ? 1 : 0
  source = "../../modules/bedrock"
  environment = var.environment
}

module "dynamodb" {
  count  = var.create_platform_persistence ? 1 : 0
  source = "../../modules/dynamodb"
  environment = var.environment
}

module "s3_app" {
  count  = var.create_platform_persistence ? 1 : 0
  source = "../../modules/s3"
  environment = var.environment
}

module "s3_agent_corpus" {
  count  = var.create_platform_persistence ? 1 : 0
  source = "../../modules/s3-agent-corpus"
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
  bedrock_policy_arn         = module.bedrock[0].invoke_policy_arn
  dynamodb_table_arn         = module.dynamodb[0].table_arn
  app_bucket_arn             = data.aws_s3_bucket.data_lake.arn
  agent_corpus_bucket        = module.s3_agent_corpus[0].bucket_name
  agent_corpus_bucket_arn    = module.s3_agent_corpus[0].bucket_arn
  data_api_base_url          = module.data_api_ec2.data_api_base_url_http
  data_service_key_parameter = module.secrets.data_service_key_parameter_name
  data_service_key           = module.secrets.data_service_key
  create_http_api            = true
  lambda_package_path        = var.lambda_package_path
  dev_auth                   = var.dev_auth
}

module "observability" {
  count  = var.create_platform_http_api ? 1 : 0
  source = "../../modules/observability"

  environment          = var.environment
  lambda_function_name = module.api_gateway[0].lambda_function_name
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

module "amplify" {
  count  = var.create_amplify_app ? 1 : 0
  source = "../../modules/amplify-hosting"

  environment          = var.environment
  repository_url       = var.fe_github_repository_url
  github_access_token  = var.github_access_token
  branch_name          = var.fe_branch_name
  platform_api_base    = var.create_platform_http_api ? module.api_gateway[0].api_endpoint : "http://localhost:8001"
  data_api_base        = module.data_api_ec2.data_api_base_url_http
  cognito_user_pool_id   = var.create_platform_persistence ? module.cognito[0].user_pool_id : ""
  cognito_client_id      = var.create_platform_persistence ? module.cognito[0].app_client_id : ""
  cognito_hosted_ui_base = var.create_platform_persistence ? module.cognito[0].hosted_ui_base_url : ""
  mapbox_public_token  = var.mapbox_access_token
}
