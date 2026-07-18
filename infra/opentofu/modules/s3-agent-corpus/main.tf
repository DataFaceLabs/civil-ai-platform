variable "environment" {
  type = string
}

locals {
  bucket_name = "civilai-agent-corpus-${var.environment}"
}

# Permanent training corpus of agent generation traces (draft + SME resolution per
# section). Deliberately separate from the app bucket: this data never expires, has
# different access/governance (used to tune the shared agent), and must not be caught by
# the app bucket's temp-export lifecycle. No lifecycle expiry here -- the corpus is
# write-once and kept.
resource "aws_s3_bucket" "corpus" {
  bucket = local.bucket_name

  tags = {
    Environment = var.environment
    Service     = "agent-corpus"
  }
}

resource "aws_s3_bucket_public_access_block" "corpus" {
  bucket = aws_s3_bucket.corpus.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "corpus" {
  bucket = aws_s3_bucket.corpus.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Versioning on: traces are written once and never overwritten, but versioning guards the
# corpus against an accidental overwrite/delete becoming permanent.
resource "aws_s3_bucket_versioning" "corpus" {
  bucket = aws_s3_bucket.corpus.id

  versioning_configuration {
    status = "Enabled"
  }
}

output "bucket_name" {
  value = aws_s3_bucket.corpus.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.corpus.arn
}
