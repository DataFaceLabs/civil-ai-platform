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

variable "approved_model_ids" {
  type    = list(string)
  default = ["us.anthropic.claude-haiku-4-5-20251001-v1:0"]
}

data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid    = "BedrockInvoke"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock:Converse",
      "bedrock:ConverseStream",
    ]
    resources = [for model_id in var.approved_model_ids : "arn:aws:bedrock:${var.aws_region}::foundation-model/${model_id}"]
  }
}

resource "aws_iam_policy" "bedrock_invoke" {
  name        = "civilai-${var.environment}-bedrock-invoke"
  description = "Allow Civil AI agent runtime to invoke approved Bedrock models"
  policy      = data.aws_iam_policy_document.bedrock_invoke.json
}

output "bedrock_invoke_policy_arn" {
  value = aws_iam_policy.bedrock_invoke.arn
}
