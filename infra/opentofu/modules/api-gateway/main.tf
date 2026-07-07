variable "environment" {
  type = string
}

variable "cognito_user_pool" {
  type = string
}

variable "bedrock_policy_arn" {
  type = string
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid    = "DynamoDB"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "S3App"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = [
      "arn:aws:s3:::civilai-${var.environment}-app/*",
      "arn:aws:s3:::civilai-${var.environment}-app/tenant/*/branding/*",
    ]
  }

  statement {
    sid    = "CognitoAdmin"
    effect = "Allow"
    actions = [
      "cognito-idp:AdminCreateUser",
      "cognito-idp:AdminDisableUser",
      "cognito-idp:AdminGetUser",
    ]
    resources = [var.cognito_user_pool]
  }
}

resource "aws_iam_role" "lambda" {
  name = "civilai-${var.environment}-platform-lambda"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda" {
  name   = "civilai-${var.environment}-platform-lambda"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

resource "aws_iam_role_policy_attachment" "bedrock" {
  role       = aws_iam_role.lambda.name
  policy_arn = var.bedrock_policy_arn
}

output "lambda_role_arn" {
  value = aws_iam_role.lambda.arn
}

output "api_endpoint" {
  value = "https://api-${var.environment}.civil.ai"
}
