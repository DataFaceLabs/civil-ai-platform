# CI role for deploying platform Lambda CODE on pushes to `develop`.
#
# Companion to ci_oidc.tf (drift, read-only, main-only). This role is write-
# scoped and develop-only on purpose:
#
#   * Merging platform API changes to develop previously required a human to
#     remember `scripts/deploy-lambda.sh`. That is the same "merged but never
#     ran" failure class as H0-IACDRIFT — and it bit us on 2026-08-20 when
#     Amplify develop had FE tip while civilai-uat-api was still on Aug 18 code.
#   * There is still only one platform Lambda (no Phase-6 develop/prod split).
#     Deploying from develop therefore updates the shared UAT API that both
#     Amplify develop and www.civil1.ai currently call. That matches today's
#     manual practice; treat develop merges that touch the Lambda package as
#     customer-facing until a separate develop function exists.
#
# SECURITY
#
#   * Trust is StringEquals on repo + refs/heads/develop. PRs and forks cannot
#     assume this role.
#   * Permissions are UpdateFunctionCode (+ read for waiters) on one function,
#     and S3 put/get on one deploy prefix (the zip is ~48MB and times out on
#     direct upload from CI).
#   * No tofu state access, no PassRole, no IAM mutations.

variable "ci_lambda_deploy_github_repo" {
  type        = string
  default     = "DataFaceLabs/civil-ai-platform"
  description = "owner/repo permitted to assume the Lambda deploy role."
}

variable "ci_lambda_deploy_github_ref" {
  type        = string
  default     = "refs/heads/develop"
  description = <<-EOT
    Git ref permitted to assume the role. Keep pinned to develop; do not widen
    to `*` (fork PR footgun) or to main until a dedicated prod deploy path exists.
  EOT
}

variable "ci_lambda_deploy_function_name" {
  type        = string
  default     = "civilai-uat-api"
  description = "Lambda function whose code CI may replace."
}

variable "ci_lambda_deploy_s3_bucket" {
  type        = string
  default     = "civilai-app-uat"
  description = "Bucket that holds ephemeral CI Lambda zip uploads."
}

variable "ci_lambda_deploy_s3_prefix" {
  type        = string
  default     = "ci/platform-lambda/"
  description = "Key prefix for CI zip uploads (trailing slash)."
}

data "aws_iam_policy_document" "ci_lambda_deploy_assume" {
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
      values   = ["repo:${var.ci_lambda_deploy_github_repo}:ref:${var.ci_lambda_deploy_github_ref}"]
    }
  }
}

resource "aws_iam_role" "ci_lambda_deploy" {
  name                 = "${var.environment}-civilai-ci-lambda-deploy"
  description          = "Develop-only OIDC role: update civilai-uat-api code via S3 zip. No tofu/state/IAM writes."
  assume_role_policy   = data.aws_iam_policy_document.ci_lambda_deploy_assume.json
  max_session_duration = 3600

  tags = {
    Environment = var.environment
    Service     = "ci"
    Purpose     = "lambda-code-deploy-develop"
  }
}

data "aws_iam_policy_document" "ci_lambda_deploy" {
  statement {
    sid    = "UpdatePlatformLambdaCode"
    effect = "Allow"
    actions = [
      "lambda:UpdateFunctionCode",
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
    ]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.ci_lambda_deploy_function_name}",
    ]
  }

  statement {
    sid    = "ListDeployPrefix"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
    ]
    resources = ["arn:aws:s3:::${var.ci_lambda_deploy_s3_bucket}"]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        var.ci_lambda_deploy_s3_prefix,
        "${var.ci_lambda_deploy_s3_prefix}*",
      ]
    }
  }

  statement {
    sid    = "PutGetDeployZips"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = [
      "arn:aws:s3:::${var.ci_lambda_deploy_s3_bucket}/${var.ci_lambda_deploy_s3_prefix}*",
    ]
  }
}

resource "aws_iam_role_policy" "ci_lambda_deploy" {
  name   = "${var.environment}-civilai-ci-lambda-deploy"
  role   = aws_iam_role.ci_lambda_deploy.id
  policy = data.aws_iam_policy_document.ci_lambda_deploy.json
}

output "ci_lambda_deploy_role_arn" {
  value       = aws_iam_role.ci_lambda_deploy.arn
  description = "Assume-role ARN for the develop Lambda code-deploy workflow."
}

output "ci_lambda_deploy_s3_uri" {
  value       = "s3://${var.ci_lambda_deploy_s3_bucket}/${var.ci_lambda_deploy_s3_prefix}"
  description = "S3 prefix CI uses for platform Lambda zip uploads."
}
