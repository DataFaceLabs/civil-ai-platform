# TPO R2.1 — GitHub OIDC role for workflow_dispatch "Refresh develop".
#
# This role may update ONLY the develop-plane Lambda and send SSM to rebuild
# the :8001 data-api container. Customer Lambda (civilai-uat-api) and :8000
# are denied. Count follows create_develop_plane so the role does not exist
# until the develop function exists to attach to.
#
# Trust is the civil-ai meta repo GitHub Environment `develop-backends`
# (workflow_dispatch + required reviewers). Not pull_request. Not forks.

variable "ci_refresh_develop_github_repo" {
  type        = string
  default     = "DataFaceLabs/civil-ai"
  description = "owner/repo allowed to assume the refresh-develop role."
}

variable "ci_refresh_develop_github_environment" {
  type        = string
  default     = "develop-backends"
  description = "GitHub Environment name in the sub claim (not a git branch)."
}

locals {
  refresh_develop_enabled = var.create_develop_plane && var.create_platform_http_api && var.create_platform_persistence
}

data "aws_iam_policy_document" "ci_refresh_develop_assume" {
  count = local.refresh_develop_enabled ? 1 : 0

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
        "repo:${var.ci_refresh_develop_github_repo}:environment:${var.ci_refresh_develop_github_environment}",
      ]
    }
  }
}

resource "aws_iam_role" "ci_refresh_develop" {
  count                = local.refresh_develop_enabled ? 1 : 0
  name                 = "${var.environment}-civilai-gha-refresh-develop"
  description          = "TPO Refresh develop: UpdateFunctionCode on develop Lambda + SSM :8001 only."
  assume_role_policy   = data.aws_iam_policy_document.ci_refresh_develop_assume[0].json
  max_session_duration = 3600

  tags = {
    Environment = var.environment
    Service     = "ci"
    Purpose     = "TPO-R2-REFRESH-DEVELOP"
  }
}

data "aws_iam_policy_document" "ci_refresh_develop" {
  count = local.refresh_develop_enabled ? 1 : 0

  statement {
    sid    = "UpdateDevelopLambdaCode"
    effect = "Allow"
    actions = [
      "lambda:UpdateFunctionCode",
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
    ]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${module.api_gateway_develop[0].lambda_function_name}",
    ]
  }

  statement {
    sid    = "DenyCustomerLambdaCode"
    effect = "Deny"
    actions = [
      "lambda:UpdateFunctionCode",
      "lambda:PublishVersion",
      "lambda:UpdateFunctionConfiguration",
    ]
    resources = concat(
      [
        "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${module.api_gateway[0].lambda_function_name}",
      ],
      module.api_gateway[0].export_pdf_function_name != "" ? [
        "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${module.api_gateway[0].export_pdf_function_name}",
      ] : [],
    )
  }

  statement {
    sid    = "SsmRebuildPort8001"
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

resource "aws_iam_role_policy" "ci_refresh_develop" {
  count  = local.refresh_develop_enabled ? 1 : 0
  name   = "${var.environment}-civilai-gha-refresh-develop"
  role   = aws_iam_role.ci_refresh_develop[0].id
  policy = data.aws_iam_policy_document.ci_refresh_develop[0].json
}

output "ci_refresh_develop_role_arn" {
  value       = local.refresh_develop_enabled ? aws_iam_role.ci_refresh_develop[0].arn : null
  description = "Assume-role ARN for civil-ai Refresh develop (GitHub Environment develop-backends)."
}
