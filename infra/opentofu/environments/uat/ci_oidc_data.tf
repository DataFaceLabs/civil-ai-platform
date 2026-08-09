# CI role for the scheduled data-side reconciliation checks (Wave 0) and the
# WAP audit-plane bind check (R1.4).
#
# Companion to ci_oidc.tf. That role watches materialization 4 (infrastructure);
# this one lets `civil-ai-data` watch materializations 2 and 6 — the Athena DDL
# applied-markers (H0-DDLHASH) and the lake audit trail (H0-MANIFEST) — plus
# whether `:8001` still serves `dev/serving` (dev-plane-audit.yml via SSM).
#
# Why it exists: those checks work today but only run when a human types
# `deploy-uat.sh reconcile`. On-demand auditing is the exact reason the ETJ fix
# sat merged-but-unapplied for 5 days and the Austin Energy guard for months —
# the detector existed, nobody ran it. A detector that depends on someone
# remembering is not a detector.
#
# SECURITY — this role is deliberately much narrower than ci_drift:
#
#   * It gets an explicit S3 read policy on ONE bucket, NOT `ReadOnlyAccess`.
#     ci_drift needs the broad policy because `tofu plan` refreshes every
#     resource in the stack; these checks only ever run `aws s3 ls` and
#     `aws s3 cp`. There is no reason to grant more, so we don't.
#   * It has NO Terraform state access, and therefore — unlike ci_drift — no
#     path to the plaintext secrets in state. The "get secrets out of state"
#     work does not gate this role.
#   * Trust is pinned to one repo and one ref with StringEquals. A wildcard
#     would let a fork's PR assume it.
#
# The OIDC provider itself is account-scoped and owned by ci_oidc.tf; this file
# references it rather than declaring a second one.

variable "ci_data_checks_github_repo" {
  type        = string
  default     = "DataFaceLabs/civil-ai-data"
  description = "owner/repo permitted to assume the data-checks role."
}

variable "ci_data_checks_github_ref" {
  type        = string
  default     = "refs/heads/main"
  description = <<-EOT
    Git ref permitted to assume the role. Keep pinned to a branch ref; `*` would
    let any PR branch, including from a fork, assume it.
  EOT
}

variable "ci_data_checks_bucket" {
  type        = string
  default     = "civilai-data"
  description = "Lake bucket the reconciliation checks read."
}

data "aws_iam_policy_document" "ci_data_checks_assume" {
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
      values   = ["repo:${var.ci_data_checks_github_repo}:ref:${var.ci_data_checks_github_ref}"]
    }
  }
}

variable "ci_data_checks_instance_id" {
  type        = string
  default     = "i-0658b3db749e9e5cb"
  description = "Data-api EC2 instance id for WAP audit-plane SSM probes (dev-plane-audit workflow)."
}

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "ci_data_checks" {
  name                 = "${var.environment}-civilai-ci-data-checks"
  description          = "Read-only role for scheduled lake reconciliation + WAP audit-plane checks (H0-DDLHASH, H0-MANIFEST, R1.4). S3 read on one bucket; SSM shell on the data-api instance only; no state access."
  assume_role_policy   = data.aws_iam_policy_document.ci_data_checks_assume.json
  max_session_duration = 3600

  tags = {
    Environment = var.environment
    Service     = "ci"
    Purpose     = "H0-RECONCILE"
  }
}

# Both checks shell out to the AWS CLI and do nothing else:
#
#   check_ddl_applied.py    aws s3 cp s3://<bucket>/<env>/_ddl_applied/<f>.json -
#   check_snapshot_age.py   aws s3 ls s3://<bucket>/<env>/...
#
# So: ListBucket on the bucket, GetObject on its contents. Nothing writes.
# Covers dev and prod prefixes because the schedule checks both — prod is what
# customers are served, and it was prod that carried the stale DDL for months.
data "aws_iam_policy_document" "ci_data_checks_read" {
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.ci_data_checks_bucket}"]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["", "dev/*", "prod/*", "dev", "prod"]
    }
  }

  statement {
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "arn:aws:s3:::${var.ci_data_checks_bucket}/dev/*",
      "arn:aws:s3:::${var.ci_data_checks_bucket}/prod/*",
    ]
  }
}

resource "aws_iam_role_policy" "ci_data_checks_read" {
  name   = "${var.environment}-civilai-ci-data-checks-read"
  role   = aws_iam_role.ci_data_checks.id
  policy = data.aws_iam_policy_document.ci_data_checks_read.json
}

# WAP audit-plane probe (civil-ai-data `.github/workflows/dev-plane-audit.yml`).
# GitHub-hosted runners cannot reach the Tailscale/CGNAT EIP on :8001; operators
# already use SSM for data-api-dev. This grants the minimum: RunShellScript that
# curls localhost:8001/healthz on the one known instance, then GetCommandInvocation
# to read the JSON. No S3 writes, no docker, no broader SSM documents.
data "aws_iam_policy_document" "ci_data_checks_ssm_audit" {
  statement {
    sid    = "SendAuditHealthzCommand"
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
    sid    = "ReadAuditCommandInvocation"
    effect = "Allow"
    actions = [
      "ssm:GetCommandInvocation",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ci_data_checks_ssm_audit" {
  name   = "${var.environment}-civilai-ci-data-checks-ssm-audit"
  role   = aws_iam_role.ci_data_checks.id
  policy = data.aws_iam_policy_document.ci_data_checks_ssm_audit.json
}

# Explicit deny on mutation. The allow policy above grants no write verbs, so
# this is redundant today — it exists so that attaching a broader policy later
# cannot silently turn a watcher into something that can change the lake it
# watches.
data "aws_iam_policy_document" "ci_data_checks_deny_writes" {
  statement {
    effect = "Deny"
    actions = [
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:DeleteObjectVersion",
      "s3:PutBucketPolicy",
      "glue:Create*",
      "glue:Update*",
      "glue:Delete*",
      "athena:StartQueryExecution",
      "iam:*",
      "sts:AssumeRole",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ci_data_checks_deny_writes" {
  name   = "${var.environment}-civilai-ci-data-checks-deny-writes"
  role   = aws_iam_role.ci_data_checks.id
  policy = data.aws_iam_policy_document.ci_data_checks_deny_writes.json
}

output "ci_data_checks_role_arn" {
  value       = aws_iam_role.ci_data_checks.arn
  description = "Assume-role ARN for the scheduled lake reconciliation workflow in civil-ai-data."
}
