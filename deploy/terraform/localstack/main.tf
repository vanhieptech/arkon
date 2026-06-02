# Minimal S3 bucket for Arkon POC — apply with tflocal (LocalStack) or terraform (AWS).
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "bucket_name" {
  type    = string
  default = "arkon-files"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

provider "aws" {
  region = var.aws_region
  # For LocalStack: export TF_VAR_aws_region=us-east-1 and use tflocal
  # endpoints { s3 = "http://localhost:4566" } — tflocal sets this automatically
}

resource "aws_s3_bucket" "arkon_files" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_versioning" "arkon_files" {
  bucket = aws_s3_bucket.arkon_files.id
  versioning_configuration {
    status = "Enabled"
  }
}

output "bucket_name" {
  value = aws_s3_bucket.arkon_files.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.arkon_files.arn
}
