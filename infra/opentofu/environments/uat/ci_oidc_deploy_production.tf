# TPO R3.3 — GitHub OIDC role for workflow_dispatch "Deploy production".
#
# Updates ONLY the customer Lambda (civilai-uat-api) and SSM-rebuilds :8000.
# Denies the develop-plane function when it exists. Trust is GitHub Environment
# `production` on DataFaceLabs/civil-ai. Not pull_request. Not forks.

variable "ci_deploy_production_github_repo" {
  type        = string
  default     = "DataFaceLabs/civil-ai"
  description = "owner/repo allowed to assume the deploy-production role."
}

variable "ci_deploy_production_github_environment" {
  type        = string
  default     = "production"
  description = "GitHub Environment name in the sub claim (not a git branch)."
}

locals {
  deploy_production_enabled = var.create_platform_http_api && var.create_platform_persistence
}

data "aws_iam_policy_document" "ci_deploy_production_assume" {
  count = local.deploy_production_enabled ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.ci_deploy_production_github_repo}:environment:${var.ci_deploy_production_github_environment}",
      ]
    }
  }
}

resource "aws_iam_role" "ci_deploy_production" {
  count                = local.deploy_production_enabled ? 1 : 0
  name                 = "${var.environment}-civilai-gha-deploy-production"
  description          = "TPO Deploy production: UpdateFunctionCode on customer Lambda + SSM :8000 only."
  assume_role_policy   = data.aws_iam_policy_document.ci_deploy_production_assume[0].json
  max_session_duration = 3600

  tags = {
    Environment = var.environment
    Service     = "ci"
    Purpose     = "TPO-R3-DEPLOY-PRODUCTION"
  }
}

data "aws_iam_policy_document" "ci_deploy_production" {
  count = local.deploy_production_enabled ? 1 : 0

  statement {
    sid    = "UpdateCustomerLambdaCode"
    effect = "Allow"
    actions = [
      "lambda:UpdateFunctionCode",
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
    ]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${module.api_gateway[0].lambda_function_name}",
    ]
  }

  dynamic "statement" {
    for_each = local.refresh_develop_enabled ? [1] : []
    content {
      sid    = "DenyDevelopLambdaCode"
      effect = "Deny"
      actions = [
        "lambda:UpdateFunctionCode",
        "lambda:PublishVersion",
        "lambda:UpdateFunctionConfiguration",
      ]
      resources = [
        "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${module.api_gateway_develop[0].lambda_function_name}",
      ]
    }
  }

  statement {
    sid    = "SsmRebuildPort8000"
    effect = "Allow"
    actions = [
      "ssm:SendCommand",
    ]
    resources = [
      "arn:aws:ssm:${var.aws_region}::document/AWS-RunShellScript",
      "arn:aws:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/${var.ci_data_checks_instance_id}",
    ]
  }

  statement {
    sid       = "SsmReadInvocation"
    effect    = "Allow"
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ci_deploy_production" {
  count  = local.deploy_production_enabled ? 1 : 0
  name   = "${var.environment}-civilai-gha-deploy-production"
  role   = aws_iam_role.ci_deploy_production[0].id
  policy = data.aws_iam_policy_document.ci_deploy_production[0].json
}

output "ci_deploy_production_role_arn" {
  value       = local.deploy_production_enabled ? aws_iam_role.ci_deploy_production[0].arn : null
  description = "Assume-role ARN for civil-ai Deploy production (GitHub Environment production)."
}
