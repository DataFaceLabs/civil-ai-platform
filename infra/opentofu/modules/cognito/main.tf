variable "environment" {
  type = string
}

resource "aws_cognito_user_pool" "main" {
  name = "civilai-${var.environment}"

  # MFA off until policy requires it (per product decision).
  mfa_configuration = "OFF"

  password_policy {
    minimum_length    = 10
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "civilai-fe-${var.environment}"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  callback_urls = [
    "http://localhost:5173/fstudio/*/login/callback",
    "https://civil.ai/fstudio/*/login/callback",
  ]
  logout_urls = [
    "http://localhost:5173/fstudio/*/login",
    "https://civil.ai/fstudio/*/login",
  ]

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  supported_identity_providers         = ["COGNITO"]
}

output "user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "user_pool_arn" {
  value = aws_cognito_user_pool.main.arn
}

output "app_client_id" {
  value = aws_cognito_user_pool_client.web.id
}
