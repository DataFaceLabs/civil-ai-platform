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

variable "ses_from_email" {
  type        = string
  default     = ""
  description = <<-EOT
    Verified SES identity to send Cognito emails (password reset, invites) from. When
    empty, Cognito uses its built-in COGNITO_DEFAULT sender (rate-limited, poor
    deliverability, not for production). When set, the address must be a verified SES
    identity in this account/region.
  EOT
}

resource "aws_cognito_user_pool" "main" {
  name = "civilai-${var.environment}"

  # Real user accounts (incl. platform admins) live in this pool -- an accidental
  # `tofu destroy` or a change that forces pool replacement would delete every login.
  # ACTIVE makes AWS reject the delete until this is flipped off deliberately.
  deletion_protection = "ACTIVE"

  mfa_configuration = var.mfa_configuration

  # Send account email (password reset / invites) via SES when a verified sender is
  # configured; otherwise fall back to Cognito's built-in sender. SES source_arn is the
  # verified email identity; same-account so no explicit SES sending-authorization policy
  # is needed.
  #
  # This block is always emitted (not a conditional `dynamic`): `email_configuration` is a
  # computed attribute, so *omitting* it makes Terraform leave whatever is live in place
  # rather than reverting to the default. Emitting COGNITO_DEFAULT explicitly is what lets
  # an empty `ses_from_email` actually switch the pool back to the built-in sender.
  email_configuration {
    email_sending_account = var.ses_from_email == "" ? "COGNITO_DEFAULT" : "DEVELOPER"
    from_email_address    = var.ses_from_email == "" ? null : var.ses_from_email
    source_arn = var.ses_from_email == "" ? null : format(
      "arn:aws:ses:%s:%s:identity/%s",
      var.aws_region,
      data.aws_caller_identity.current.account_id,
      var.ses_from_email,
    )
  }

  password_policy {
    minimum_length    = 10
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true

    # Invites are onboarding emails to outside contractors and client staff, who often do
    # not act within a week. Cognito's default is 7 days, after which Hosted UI rejects the
    # temp password with "must be reset by an administrator" and the invite has to be
    # reissued by hand. 21 days covers a normal onboarding lag without leaving a
    # never-redeemed invite valid indefinitely.
    #
    # Set here rather than via `admin_create_user_config.unused_account_validity_days` --
    # the two are mutually exclusive in the Cognito API and this is the non-deprecated one.
    # In-place update; does not force pool replacement.
    temporary_password_validity_days = 21
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

  # Enables AdminInitiateAuth(ADMIN_USER_PASSWORD_AUTH) for UAT smoke scripts only.
  # Does not change the Hosted UI login path used by the FE.
  explicit_auth_flows = [
    "ALLOW_ADMIN_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]
}

resource "aws_cognito_user_pool_domain" "main" {
  domain       = "civilai-${var.environment}-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.main.id
}

# Trust Console (hardening plan §5 Stage 3): SMEs invited into this group on the shared
# pool. Amplify trust app + Hosted UI client (separate module) will require membership;
# product civil1.ai continues to use the existing web client without this group gate.
resource "aws_cognito_user_group" "trust_reviewer" {
  name         = "trust-reviewer"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Data Trust Console reviewers (land/feasibility SMEs)"
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

output "trust_reviewer_group_name" {
  value = aws_cognito_user_group.trust_reviewer.name
}
