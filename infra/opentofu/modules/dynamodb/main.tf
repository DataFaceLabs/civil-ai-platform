variable "environment" {
  type = string
}

variable "enable_pitr" {
  type    = bool
  default = true
}

locals {
  table_name = "civilai-app-${var.environment}"
}

resource "aws_dynamodb_table" "app" {
  name         = local.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  # User profiles, tenant memberships, and platform-admin flags live here -- guard the
  # table against accidental `tofu destroy` / forced replacement. PITR (below) covers
  # data-level restores; this covers losing the whole table.
  deletion_protection_enabled = true

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "GSI1PK"
    type = "S"
  }

  attribute {
    name = "GSI1SK"
    type = "S"
  }

  attribute {
    name = "GSI2PK"
    type = "S"
  }

  attribute {
    name = "GSI2SK"
    type = "S"
  }

  global_secondary_index {
    name            = "GSI1"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "GSI2"
    hash_key        = "GSI2PK"
    range_key       = "GSI2SK"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Environment = var.environment
    Service     = "platform"
  }
}

output "table_name" {
  value = aws_dynamodb_table.app.name
}

output "table_arn" {
  value = aws_dynamodb_table.app.arn
}
