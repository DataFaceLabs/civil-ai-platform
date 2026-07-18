variable "environment" {
  type = string
}

data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid    = "BedrockInvoke"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "bedrock_invoke" {
  name   = "civilai-${var.environment}-bedrock-invoke"
  policy = data.aws_iam_policy_document.bedrock_invoke.json
}

output "invoke_policy_arn" {
  value = aws_iam_policy.bedrock_invoke.arn
}
