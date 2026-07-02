terraform {
  required_version = ">= 1.6.0"
}

variable "environment" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "lambda_role_arn" {
  type        = string
  description = "IAM role ARN for AgentCore runtime / Lambda orchestrator"
}

variable "app_bucket_arn" {
  type = string
}

variable "data_api_base_url" {
  type        = string
  description = "Internal URL for civil-ai-data API (Gateway target)"
}

# AgentCore resources are provisioned when the service is available in the target account.
# This module defines IAM boundaries and outputs for runtime wiring.

data "aws_iam_policy_document" "agentcore_runtime" {
  statement {
    sid    = "AgentRunArtifacts"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      var.app_bucket_arn,
      "${var.app_bucket_arn}/tenant/*/project/*/agent-runs/*",
    ]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${var.aws_region}:*:log-group:/civilai/${var.environment}/agentcore*"]
  }
}

resource "aws_iam_policy" "agentcore_runtime" {
  name        = "civilai-${var.environment}-agentcore-runtime"
  description = "AgentCore runtime — S3 agent-runs artifacts and observability"
  policy      = data.aws_iam_policy_document.agentcore_runtime.json
}

resource "aws_iam_role_policy_attachment" "agentcore_runtime" {
  role       = element(split("/", var.lambda_role_arn), length(split("/", var.lambda_role_arn)) - 1)
  policy_arn = aws_iam_policy.agentcore_runtime.arn
}

output "agentcore_runtime_policy_arn" {
  value = aws_iam_policy.agentcore_runtime.arn
}

output "gateway_data_api_target" {
  value = var.data_api_base_url
}
