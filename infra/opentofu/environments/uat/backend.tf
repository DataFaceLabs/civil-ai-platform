terraform {
  backend "s3" {
    bucket         = "civilai-tofu-state"
    key            = "platform/uat/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "civilai-tofu-locks"
    encrypt        = true
  }
}
