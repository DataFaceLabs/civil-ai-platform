# CI role for the scheduled Athena health workflow (civil-ai-data
# .github/workflows/athena-recurring-health.yml).
#
# WHY THIS IS SEPARATE FROM ci_data_checks
#
# ci_data_checks is deliberately read-only with an explicit Deny on
# athena:StartQueryExecution. That is correct for reconciliation, which only
# reads S3 objects. The health workflow is a different job: it runs the Phase 1
# smoke queries, a latency benchmark, and runtime probes against a live API. It
# has to execute Athena queries, so it cannot reuse that role and must not have
# the Deny relaxed on it.
#
# WHY IT EXISTS AT ALL
#
# athena-recurring-health.yml referenced `secrets.AWS_ROLE_TO_ASSUME`. That
# secret has never been set on the repository -- `gh secret list` is empty -- so
# the workflow failed at its first step, "Validate required secret", every day
# from at least 2026-07-31 through 2026-08-05. Six consecutive red runs that
# said nothing about Athena's health.
#
# Same defect as accuracy-sampling.yml, fixed there on 2026-08-03 by defaulting
# the role ARN instead of requiring a secret. A role ARN is not a secret, and a
# secret someone must remember to set is the failure mode being guarded against.
# That fix was applied to one workflow and not swept across the others; this
# closes the last one.
#
# Athena writes query results to S3, so unlike the read-only role this one needs
# PutObject -- scoped to the athena-query-results prefix only. It cannot write
# conformed, reference, or serving.

variable "ci_athena_health_github_repo" {
  type        = string
  default     = "DataFaceLabs/civil-ai-data"
  description = "owner/repo permitted to assume the Athena health role."
}

variable "ci_athena_health_github_ref" {
  type        = string
  default     = "refs/heads/main"
  description = <<-EOT
    Git ref permitted to assume the role. Keep pinned to a branch ref; `*` would
    let any PR branch, including from a fork, run queries in our account.
  EOT
}

data "aws_iam_policy_document" "ci_athena_health_assume" {
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
      values   = ["repo:${var.ci_athena_health_github_repo}:ref:${var.ci_athena_health_github_ref}"]
    }
  }
}

resource "aws_iam_role" "ci_athena_health" {
  name                 = "${var.environment}-civilai-ci-athena-health"
  description          = "Scheduled Athena smoke, latency and runtime-probe checks. Query-capable; cannot write lake data."
  assume_role_policy   = data.aws_iam_policy_document.ci_athena_health_assume.json
  max_session_duration = 3600

  tags = {
    Environment = var.environment
    Service     = "ci"
    Purpose     = "athena-recurring-health"
  }
}

data "aws_iam_policy_document" "ci_athena_health" {
  # Athena execution. GetWorkGroup is required for the workgroup's result
  # configuration; without it StartQueryExecution fails on an opaque error.
  statement {
    effect = "Allow"
    actions = [
      "athena:StartQueryExecution",
      "athena:StopQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:GetWorkGroup",
      "athena:ListWorkGroups",
    ]
    resources = ["*"]
  }

  # Athena resolves tables through the Glue Data Catalog. Read only -- the
  # health check must never alter a table definition.
  statement {
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetPartition",
      "glue:GetPartitions",
    ]
    resources = ["*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = ["arn:aws:s3:::${var.ci_data_checks_bucket}"]
  }

  statement {
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "arn:aws:s3:::${var.ci_data_checks_bucket}/dev/*",
      "arn:aws:s3:::${var.ci_data_checks_bucket}/prod/*",
    ]
  }

  # Athena writes result sets and metadata here. Deliberately the only prefix
  # this role may write, and deliberately not conformed/, reference/ or serving/.
  statement {
    effect  = "Allow"
    actions = ["s3:PutObject", "s3:AbortMultipartUpload"]
    resources = [
      "arn:aws:s3:::${var.ci_data_checks_bucket}/dev/athena-query-results/*",
      "arn:aws:s3:::${var.ci_data_checks_bucket}/prod/athena-query-results/*",
    ]
  }
}

resource "aws_iam_role_policy" "ci_athena_health" {
  name   = "${var.environment}-civilai-ci-athena-health"
  role   = aws_iam_role.ci_athena_health.id
  policy = data.aws_iam_policy_document.ci_athena_health.json
}

# Belt and braces. The allow policy already omits these, but a health check that
# could rewrite a table definition or delete lake data would be a strictly worse
# problem than the one it detects.
data "aws_iam_policy_document" "ci_athena_health_deny" {
  statement {
    effect = "Deny"
    actions = [
      "sts:AssumeRole",
      "iam:*",
      "glue:Create*",
      "glue:Update*",
      "glue:Delete*",
      "s3:DeleteObject",
      "s3:DeleteObjectVersion",
      "s3:PutBucketPolicy",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ci_athena_health_deny" {
  name   = "${var.environment}-civilai-ci-athena-health-deny"
  role   = aws_iam_role.ci_athena_health.id
  policy = data.aws_iam_policy_document.ci_athena_health_deny.json
}

output "ci_athena_health_role_arn" {
  value       = aws_iam_role.ci_athena_health.arn
  description = "Assume-role ARN for athena-recurring-health.yml in civil-ai-data."
}
