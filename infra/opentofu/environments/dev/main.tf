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
}

module "bedrock" {
  source      = "../../modules/bedrock"
  environment = var.environment
}

module "api_gateway" {
  source             = "../../modules/api-gateway"
  environment        = var.environment
  cognito_user_pool  = module.cognito.user_pool_arn
  bedrock_policy_arn = module.bedrock.invoke_policy_arn
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
