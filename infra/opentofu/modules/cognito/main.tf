variable "environment" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "callback_urls" {
  type = list(string)
}

variable "logout_urls" {
  type = list(string)
}

variable "mfa_configuration" {
  type    = string
  default = "OFF"
}

resource "aws_cognito_user_pool" "main" {
  name = "civilai-${var.environment}"

  mfa_configuration = var.mfa_configuration

  password_policy {
    minimum_length    = 10
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]

  tags = {
    Environment = var.environment
    Service     = "platform"
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "civilai-fe-${var.environment}"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  callback_urls = var.callback_urls
  logout_urls   = var.logout_urls

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  supported_identity_providers         = ["COGNITO"]
}

resource "aws_cognito_user_pool_domain" "main" {
  domain       = "civilai-${var.environment}-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.main.id
}

data "aws_caller_identity" "current" {}

output "user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "user_pool_arn" {
  value = aws_cognito_user_pool.main.arn
}

output "app_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "user_pool_domain" {
  value = aws_cognito_user_pool_domain.main.domain
}

output "hosted_ui_base_url" {
  value = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.aws_region}.amazoncognito.com"
}
