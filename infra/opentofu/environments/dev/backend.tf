# Remote state — configure bucket/table before first apply.
# Example:
#   terraform {
#     backend "s3" {
#       bucket         = "civilai-tofu-state"
#       key            = "platform/dev/terraform.tfstate"
#       region         = "us-east-1"
#       dynamodb_table = "civilai-tofu-locks"
#       encrypt        = true
#     }
#   }
