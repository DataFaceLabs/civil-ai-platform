variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "instance_type" {
  type    = string
  default = "t4g.medium"
}

variable "volume_size_gb" {
  type    = number
  default = 30
}

variable "allowed_ssh_cidr_blocks" {
  type        = list(string)
  description = "CIDR blocks allowed to SSH (port 22)."
}

variable "allowed_api_cidr_blocks" {
  type        = list(string)
  description = "CIDR blocks allowed to reach the data API (ports 443 and 8000)."
}

variable "serving_s3_uri" {
  type        = string
  description = "S3 URI for the serving DuckDB artifact."
}

variable "data_lake_bucket" {
  type    = string
  default = "civilai-data"
}

variable "data_lake_prefix" {
  type    = string
  default = "dev"
}

variable "data_service_key_parameter" {
  type = string
}

variable "mapbox_parameter" {
  type    = string
  default = ""
}

variable "cors_origins" {
  type    = string
  default = "http://localhost:5173,http://localhost:3000"
}

variable "github_repo_url" {
  type    = string
  default = "https://github.com/DataFaceLabs/civil-ai-data.git"
}

variable "github_token_parameter" {
  type        = string
  default     = ""
  description = "Optional SSM parameter name holding a GitHub PAT for private clone."
}

variable "git_ref" {
  type    = string
  default = "develop"
}

data "aws_ami" "al2023_arm" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-kernel-6.1-arm64"]
  }

  filter {
    name   = "architecture"
    values = ["arm64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

locals {
  name_prefix = "civilai-${var.environment}-data-api"
}

resource "aws_iam_role" "ec2" {
  name = "${local.name_prefix}-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

data "aws_iam_policy_document" "ec2" {
  statement {
    sid    = "ServingArtifactRead"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      "arn:aws:s3:::${var.data_lake_bucket}",
      "arn:aws:s3:::${var.data_lake_bucket}/${var.data_lake_prefix}/serving/*",
    ]
  }

  statement {
    sid    = "ReadDeploySecrets"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
    ]
    resources = [
      "arn:aws:ssm:${var.aws_region}:*:parameter/civilai/${var.environment}/*",
    ]
  }

  dynamic "statement" {
    for_each = var.github_token_parameter != "" ? [1] : []
    content {
      sid    = "ReadGithubToken"
      effect = "Allow"
      actions = [
        "ssm:GetParameter",
      ]
      resources = [
      "arn:aws:ssm:${var.aws_region}:*:parameter${startswith(var.github_token_parameter, "/") ? var.github_token_parameter : "/${var.github_token_parameter}"}",
    ]
    }
  }
}

resource "aws_iam_role_policy" "ec2" {
  name   = "${local.name_prefix}-policy"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.ec2.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${local.name_prefix}-profile"
  role = aws_iam_role.ec2.name
}

resource "aws_security_group" "data_api" {
  name        = "${local.name_prefix}-sg"
  description = "Civil AI data API (${var.environment})"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_ssh_cidr_blocks
  }

  ingress {
    description = "HTTPS (nginx)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.allowed_api_cidr_blocks
  }

  ingress {
    description = "HTTP redirect / ACME"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.allowed_api_cidr_blocks
  }

  ingress {
    description = "Data API direct (smoke / pre-nginx)"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = var.allowed_api_cidr_blocks
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = local.name_prefix
    Environment = var.environment
    Service     = "data-api"
  }
}

resource "aws_instance" "data_api" {
  ami                    = data.aws_ami.al2023_arm.id
  instance_type          = var.instance_type
  iam_instance_profile   = aws_iam_instance_profile.ec2.name
  vpc_security_group_ids = [aws_security_group.data_api.id]

  root_block_device {
    volume_size = var.volume_size_gb
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/user_data.sh.tpl", {
    environment                = var.environment
    aws_region                 = var.aws_region
    serving_s3_uri             = var.serving_s3_uri
    data_service_key_parameter = var.data_service_key_parameter
    mapbox_parameter           = var.mapbox_parameter
    cors_origins               = var.cors_origins
    github_repo_url            = var.github_repo_url
    github_token_parameter     = var.github_token_parameter
    git_ref                    = var.git_ref
  })

  tags = {
    Name        = local.name_prefix
    Environment = var.environment
    Service     = "data-api"
  }

  lifecycle {
    ignore_changes = [ami]
  }
}

resource "aws_eip" "data_api" {
  domain = "vpc"
  instance = aws_instance.data_api.id

  tags = {
    Name        = "${local.name_prefix}-eip"
    Environment = var.environment
    Service     = "data-api"
  }
}

output "instance_id" {
  value = aws_instance.data_api.id
}

output "public_ip" {
  value = aws_eip.data_api.public_ip
}

output "data_api_base_url_http" {
  value = "http://${aws_eip.data_api.public_ip}:8000"
}

output "security_group_id" {
  value = aws_security_group.data_api.id
}

output "iam_role_arn" {
  value = aws_iam_role.ec2.arn
}
