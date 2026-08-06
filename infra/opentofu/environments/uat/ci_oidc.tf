# CI drift detection (H0-IACDRIFT) — GitHub OIDC role for `tofu plan` only.
#
# Why this exists: on 2026-08-01 a single session found six production problems of
# one shape — merged to git, downstream action never run. Two involved Terraform that
# had been merged but never applied; one of those caused a customer-facing outage, and
# a bare `tofu apply` would have replaced the Amplify app serving www.civil1.ai.
# Nothing was watching. A scheduled `tofu plan -detailed-exitcode` would have caught
# both. See DATA-PLATFORM-HARDENING-PLAN.md §7.1 / Wave 0.
#
# SECURITY NOTES — read before widening any of this:
#
#   1. This role can read Terraform state, and **state contains secrets in plaintext**
#      (this stack's own `data_service_key` output is one). "Read-only" is therefore
#      not as benign as it sounds. Mitigations below, plus: the drift workflow never
#      prints or uploads plan output — it consumes only the exit code. Moving secrets
#      out of state into SSM references is the real fix and is tracked separately.
#   2. Trust is scoped to ONE repo and ONE ref (`main`). Pull requests — including
#      from forks — cannot assume this role, which is the main OIDC footgun.
#   3. No write permissions and no DynamoDB access: the workflow plans with
#      `-lock=false`, so it never needs to take the state lock.
#   4. OIDC is deliberately chosen over long-lived access keys: credentials are
#      minted per-run and expire, and there is no secret to leak or rotate.
#
# This provider is account-scoped. If a second environment is added, move it out of
# `environments/uat/` so the two do not both try to own it.

variable "ci_drift_github_repo" {
  type        = string
  default     = "DataFaceLabs/civil-ai-platform"
  description = "owner/repo permitted to assume the drift-detection role."
}

variable "ci_drift_github_ref" {
  type        = string
  default     = "refs/heads/main"
  description = <<-EOT
    Git ref permitted to assume the role. Keep this pinned to a branch ref.
    Widening to `*` would let any PR branch — including from a fork — assume a
    role that can read state, and therefore secrets.
  EOT
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS validates GitHub's certificate against its own trust store; this value is
  # required by the API but not load-bearing for well-known IdPs.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = {
    Environment = var.environment
    Service     = "ci"
    Purpose     = "H0-IACDRIFT"
  }
}

data "aws_iam_policy_document" "ci_drift_assume" {
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

    # Pinned to a single repo + ref. StringEquals, not StringLike -- a wildcard
    # here is how OIDC roles get assumed by untrusted fork PRs.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.ci_drift_github_repo}:ref:${var.ci_drift_github_ref}"]
    }
  }
}

resource "aws_iam_role" "ci_drift" {
  name                 = "${var.environment}-civilai-ci-drift"
  description          = "Read-only role for scheduled tofu plan drift detection (H0-IACDRIFT). Cannot apply."
  assume_role_policy   = data.aws_iam_policy_document.ci_drift_assume.json
  max_session_duration = 3600

  tags = {
    Environment = var.environment
    Service     = "ci"
    Purpose     = "H0-IACDRIFT"
  }
}

# `tofu plan` refreshes every resource in the stack, so it needs read across every
# service the stack touches (amplify, apigateway, lambda, ec2, iam, s3, dynamodb,
# cloudwatch, sns, cognito, ssm). Enumerating those by hand is brittle -- a missing
# verb makes plan fail with a permissions error that looks like drift. ReadOnlyAccess
# is the honest choice here; the guard rails are the trust policy above and the
# explicit deny below, not a hand-maintained allow list.
resource "aws_iam_role_policy_attachment" "ci_drift_read" {
  role       = aws_iam_role.ci_drift.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# Belt and braces. ReadOnlyAccess grants no mutations today, but this makes the
# intent explicit and survives someone attaching a broader policy later.
#
# Deny IAM *writes* specifically -- NOT `iam:*`. `tofu plan` must read IAM (this
# stack manages several roles), so a blanket IAM deny makes plan fail with a
# permissions error that is easily mistaken for drift. Same reasoning for keeping
# every other entry to a mutating verb.
data "aws_iam_policy_document" "ci_drift_deny_writes" {
  statement {
    effect = "Deny"
    actions = [
      "s3:PutObject",
      "s3:DeleteObject",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "iam:Create*",
      "iam:Delete*",
      "iam:Update*",
      "iam:Put*",
      "iam:Attach*",
      "iam:Detach*",
      "iam:Tag*",
      "iam:Untag*",
      "iam:PassRole",
      "sts:AssumeRole",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ci_drift_deny_writes" {
  name   = "${var.environment}-civilai-ci-drift-deny-writes"
  role   = aws_iam_role.ci_drift.id
  policy = data.aws_iam_policy_document.ci_drift_deny_writes.json
}

# The drift check pulls environment config from SSM (see scripts/tofu-config.sh):
# without it, 8 of 16 variables fall back to defaults that differ from reality and
# the plan proposes destroying live modules. ReadOnlyAccess grants ssm:GetParameter
# but deliberately NOT kms:Decrypt, which a SecureString needs -- hence this.
#
# Note this lets CI read the two tokens in that blob. That is not a new exposure:
# the role can already read Terraform state, which holds the same values in
# plaintext. Reducing both is the same piece of work (get secrets out of state),
# tracked separately. Scoped to this one parameter path regardless.
data "aws_iam_policy_document" "ci_drift_config_read" {
  statement {
    effect    = "Allow"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = ["arn:aws:ssm:*:*:parameter/civilai/${var.environment}/tofu/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "ci_drift_config_read" {
  name   = "${var.environment}-civilai-ci-drift-config-read"
  role   = aws_iam_role.ci_drift.id
  policy = data.aws_iam_policy_document.ci_drift_config_read.json
}

output "ci_drift_role_arn" {
  value       = aws_iam_role.ci_drift.arn
  description = "Assume-role ARN for the scheduled drift-detection workflow."
}
