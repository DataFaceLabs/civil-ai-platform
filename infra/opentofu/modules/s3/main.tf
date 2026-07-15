variable "environment" {
  type = string
}

variable "cors_origins" {
  type        = list(string)
  description = "Browser Origins allowed to PUT/GET via S3 presigned URLs."
  default     = []
}

locals {
  bucket_name = "civilai-app-${var.environment}"
}

resource "aws_s3_bucket" "app" {
  bucket = local.bucket_name

  tags = {
    Environment = var.environment
    Service     = "platform"
  }
}

resource "aws_s3_bucket_public_access_block" "app" {
  bucket = aws_s3_bucket.app.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "app" {
  bucket = aws_s3_bucket.app.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "app" {
  bucket = aws_s3_bucket.app.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "app" {
  bucket = aws_s3_bucket.app.id

  rule {
    id     = "expire-temp-exports"
    status = "Enabled"

    filter {
      prefix = "tenant/"
    }

    expiration {
      days = 90
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "app" {
  count  = length(var.cors_origins) > 0 ? 1 : 0
  bucket = aws_s3_bucket.app.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "HEAD"]
    allowed_origins = var.cors_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

output "bucket_name" {
  value = aws_s3_bucket.app.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.app.arn
}
