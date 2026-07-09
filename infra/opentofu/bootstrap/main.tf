# One-time bootstrap for OpenTofu remote state.
# Apply with LOCAL state first (this directory is not configured for remote backend).
#
#   cd infra/opentofu/bootstrap
#   tofu init
#   tofu apply
#
# Then uncomment backend blocks in environments/*/backend.tf and run tofu init -migrate-state.

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "state_bucket_name" {
  type    = string
  default = "civilai-tofu-state"
}

variable "lock_table_name" {
  type    = string
  default = "civilai-tofu-locks"
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name

  tags = {
    Project     = "civilai"
    Environment = "shared"
    Purpose     = "opentofu-remote-state"
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "locks" {
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Project     = "civilai"
    Environment = "shared"
    Purpose     = "opentofu-state-lock"
  }
}

output "state_bucket_name" {
  value = aws_s3_bucket.state.bucket
}

output "lock_table_name" {
  value = aws_dynamodb_table.locks.name
}

output "backend_config_snippet" {
  value = <<-EOT
    terraform {
      backend "s3" {
        bucket         = "${aws_s3_bucket.state.bucket}"
        key            = "platform/<env>/terraform.tfstate"
        region         = "${var.aws_region}"
        dynamodb_table = "${aws_dynamodb_table.locks.name}"
        encrypt        = true
      }
    }
  EOT
}
