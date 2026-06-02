terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "random_password" "admin" {
  count   = var.admin_password == null ? 1 : 0
  length  = 16
  special = true
}

resource "random_password" "secret_key" {
  count   = var.secret_key == null ? 1 : 0
  length  = 32
  special = false
}

resource "random_password" "mcp_pepper" {
  count   = var.mcp_token_pepper == null ? 1 : 0
  length  = 32
  special = false
}

resource "random_password" "postgres" {
  count   = var.postgres_password == null ? 1 : 0
  length  = 20
  special = true
}

resource "random_password" "redis" {
  count   = var.redis_password == null ? 1 : 0
  length  = 20
  special = true
}

locals {
  bucket_name       = "${var.project_name}-files-${random_id.suffix.hex}"
  admin_password    = coalesce(var.admin_password, try(random_password.admin[0].result, ""))
  secret_key        = coalesce(var.secret_key, try(random_password.secret_key[0].result, ""))
  mcp_pepper        = coalesce(var.mcp_token_pepper, try(random_password.mcp_pepper[0].result, ""))
  postgres_password = coalesce(var.postgres_password, try(random_password.postgres[0].result, ""))
  redis_password    = coalesce(var.redis_password, try(random_password.redis[0].result, ""))
  s3_endpoint = "s3.${var.aws_region}.amazonaws.com"
}

resource "aws_s3_bucket" "arkon" {
  bucket = local.bucket_name
}

resource "aws_s3_bucket_versioning" "arkon" {
  bucket = aws_s3_bucket.arkon.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "arkon" {
  bucket                  = aws_s3_bucket.arkon.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_iam_role" "ec2" {
  name = "${var.project_name}-ec2-${random_id.suffix.hex}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

data "aws_iam_policy_document" "arkon_app" {
  statement {
    sid    = "S3ArkonBucket"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [aws_s3_bucket.arkon.arn]
  }

  statement {
    sid    = "S3ArkonObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.arkon.arn}/*"]
  }

  statement {
    sid    = "BedrockInvoke"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock:Converse",
      "bedrock:ConverseStream",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ec2" {
  name   = "${var.project_name}-ec2-policy"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.arkon_app.json
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${var.project_name}-profile-${random_id.suffix.hex}"
  role = aws_iam_role.ec2.name
}

# Long-lived keys for Docker Compose (session creds from IMDS expire ~1h)
resource "aws_iam_user" "arkon_app" {
  name = "${var.project_name}-app-${random_id.suffix.hex}"
}

resource "aws_iam_user_policy" "arkon_app" {
  name   = "${var.project_name}-app-policy"
  user   = aws_iam_user.arkon_app.name
  policy = data.aws_iam_policy_document.arkon_app.json
}

resource "aws_iam_access_key" "arkon_app" {
  user = aws_iam_user.arkon_app.name
}

resource "aws_security_group" "arkon" {
  name        = "${var.project_name}-sg-${random_id.suffix.hex}"
  description = "Arkon EC2 one-box (POC)"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_cidr]
  }

  ingress {
    description = "Arkon API"
    from_port   = 5055
    to_port     = 5055
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Arkon UI"
    from_port   = 3119
    to_port     = 3119
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "arkon" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = var.key_name
  subnet_id              = tolist(data.aws_subnets.default.ids)[0]
  vpc_security_group_ids = [aws_security_group.arkon.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

  root_block_device {
    volume_size = var.root_volume_gb
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/templates/user-data.sh.tftpl", {
    aws_region            = var.aws_region
    arkon_repo_url        = var.arkon_repo_url
    arkon_repo_branch     = var.arkon_repo_branch
    bucket_name           = local.bucket_name
    s3_endpoint           = local.s3_endpoint
    admin_email           = var.admin_email
    admin_password        = local.admin_password
    secret_key            = local.secret_key
    mcp_pepper            = local.mcp_pepper
    postgres_password     = local.postgres_password
    redis_password        = local.redis_password
    poc_configure_bedrock = var.poc_configure_bedrock ? "1" : "0"
    poc_llm_spec_id       = var.poc_llm_spec_id
    poc_embedding_spec_id = var.poc_embedding_spec_id
    aws_access_key_id     = aws_iam_access_key.arkon_app.id
    aws_secret_access_key = aws_iam_access_key.arkon_app.secret
  })

  user_data_replace_on_change = true

  tags = {
    Name    = "${var.project_name}-onebox"
    Project = var.project_name
  }
}

# Patch public IP into env after instance has an IP (user-data uses instance metadata for API URL on boot)
resource "aws_eip" "arkon" {
  count    = 1
  domain   = "vpc"
  instance = aws_instance.arkon.id
}
