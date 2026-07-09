terraform {
  required_version = ">= 1.6.0"
}

provider "aws" {
  region = var.aws_region
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

module "cognito" {
  source      = "../../modules/cognito"
  environment = var.environment
  aws_region  = var.aws_region

  callback_urls = [
    "http://localhost:5173/fstudio/*/login/callback",
  ]
  logout_urls = [
    "http://localhost:5173/fstudio/*/login",
  ]
}

module "bedrock" {
  source      = "../../modules/bedrock"
  environment = var.environment
}

module "dynamodb" {
  source      = "../../modules/dynamodb"
  environment = var.environment
}

module "s3_app" {
  source      = "../../modules/s3"
  environment = var.environment
}

data "aws_s3_bucket" "data_lake" {
  bucket = "civilai-data"
}

module "api_gateway" {
  source        = "../../modules/api-gateway"
  environment   = var.environment
  aws_region    = var.aws_region
  cognito_user_pool_arn = module.cognito.user_pool_arn
  cognito_user_pool_id  = module.cognito.user_pool_id
  cognito_client_id     = module.cognito.app_client_id
  bedrock_policy_arn    = module.bedrock.invoke_policy_arn
  dynamodb_table_arn    = module.dynamodb.table_arn
  app_bucket_arn        = data.aws_s3_bucket.data_lake.arn
  data_api_base_url     = "http://localhost:8000"
  data_service_key_parameter = "/civilai/dev/data-service-key"
  data_service_key           = "dev-platform-service-key"
  create_http_api            = false
}

output "api_endpoint" {
  value = module.api_gateway.api_endpoint
}

output "cognito_user_pool_id" {
  value = module.cognito.user_pool_id
}

output "cognito_client_id" {
  value = module.cognito.app_client_id
}

output "dynamodb_table" {
  value = module.dynamodb.table_name
}
