variable "environment" {
  type = string
}

variable "lambda_function_name" {
  type = string
}

locals {
  name_prefix = "civilai-${var.environment}"
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.lambda_function_name}"
  retention_in_days = 30
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${local.name_prefix}-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_name
  }
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.lambda.name
}
