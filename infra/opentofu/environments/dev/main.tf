terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

module "cognito" {
  source      = "../../modules/cognito"
  environment = "dev"
  aws_region  = var.aws_region
}

module "dynamodb" {
  source      = "../../modules/dynamodb"
  environment = "dev"
  enable_pitr = true
}

module "s3" {
  source      = "../../modules/s3"
  environment = "dev"
}

module "api" {
  source                = "../../modules/api-gateway"
  environment           = "dev"
  aws_region            = var.aws_region
  dynamodb_table_arn    = module.dynamodb.table_arn
  dynamodb_table_name   = module.dynamodb.table_name
  s3_bucket_arn         = module.s3.bucket_arn
  s3_bucket_name        = module.s3.bucket_name
  cognito_user_pool_id  = module.cognito.user_pool_id
  cognito_app_client_id = module.cognito.app_client_id
  cognito_issuer        = module.cognito.issuer
}

module "observability" {
  source               = "../../modules/observability"
  environment          = "dev"
  lambda_function_name = "civilai-dev-api"
}

output "api_endpoint" {
  value = module.api.api_endpoint
}

output "cognito_hosted_ui" {
  value = module.cognito.hosted_ui_domain
}

output "dynamodb_table" {
  value = module.dynamodb.table_name
}

output "s3_bucket" {
  value = module.s3.bucket_name
}
