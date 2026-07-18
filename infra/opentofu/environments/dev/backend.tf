# OpenTofu remote state — configure before first apply in each environment.
terraform {
  backend "s3" {
    # bucket         = "civilai-tofu-state-dev"
    # key            = "platform/dev/terraform.tfstate"
    # region         = "us-east-1"
    # dynamodb_table = "civilai-tofu-locks"
    # encrypt        = true
  }
}
