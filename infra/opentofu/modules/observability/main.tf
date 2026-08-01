variable "environment" {
  type = string
}

variable "lambda_function_name" {
  type = string
}

variable "alarm_notification_email" {
  type        = string
  default     = ""
  description = <<-EOT
    Email subscribed to the alerts SNS topic. Empty = the topic and alarms
    still exist (so `tofu apply` alone is enough to wire alarm state), but
    nothing is notified until either this is set or the topic is subscribed
    another way (Slack webhook Lambda is the target per
    civil1-data-platform-architecture.md Sec 4.5 -- not built yet).
  EOT
}

locals {
  name_prefix = "civilai-${var.environment}"
}

resource "aws_sns_topic" "alerts" {
  name = "${local.name_prefix}-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  count     = var.alarm_notification_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alarm_notification_email
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
  # Pre-existing alarm had no alarm_actions -- it could fire and nobody
  # would ever know. Wired to the shared alerts topic alongside H3-ALARM.
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = var.lambda_function_name
  }
}

# H3-ALARM: data-api has no per-request access log (deploy/entrypoint.sh
# runs uvicorn with --no-access-log by design) and, before this, no error
# metric of any kind -- a human clicking a broken link was the detection
# mechanism for the 2026-07-31 Parcel Lookup incident. Watches the
# [Environment]-only aggregate dimension set that
# civil-ai-data/src/civilai/api/emf_metrics.py emits on every >=500
# response; per-endpoint breakdown is the [Environment, Path] set on the
# same metric, for investigation once this fires.
resource "aws_cloudwatch_metric_alarm" "data_api_5xx" {
  alarm_name          = "${local.name_prefix}-data-api-5xx"
  alarm_description   = "data-api served a 5xx in the last 5 minutes. See CivilAI/DataAPI/FiveHundredCount by Path for which endpoint."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FiveHundredCount"
  namespace           = "CivilAI/DataAPI"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    Environment = var.environment
  }
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.lambda.name
}

output "alerts_topic_arn" {
  value       = aws_sns_topic.alerts.arn
  description = "Subscribe a Slack webhook Lambda here when it exists (civil1-data-platform-architecture.md Sec 4.5)."
}
