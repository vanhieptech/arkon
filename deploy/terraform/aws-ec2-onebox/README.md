# Arkon AWS one-box (EC2 + Docker Compose) — Terraform template

**One `terraform apply`** creates:

| Resource | Purpose |
|----------|---------|
| S3 bucket | File storage (replaces MinIO) |
| IAM role + instance profile | S3 + Bedrock on EC2 |
| Security group | SSH, API `:5055`, UI `:3119` |
| EC2 + Elastic IP | Runs `docker compose` |
| User-data bootstrap | Install Docker, clone repo, write `.env.docker`, start stack |

Postgres, Redis, API, workers, frontend still run **in Docker on the instance** (fastest path).

## Prerequisites

1. [Terraform](https://www.terraform.io/) >= 1.5
2. AWS CLI configured (`aws sts get-caller-identity`)
3. **EC2 key pair** in target region (`key_name`)
4. **Bedrock model access** enabled in console:
   - Claude 3.5 Sonnet
   - Titan Text Embeddings V2
5. Service quotas: default VPC, enough vCPU for `t3.xlarge`

## Deploy

```bash
cd deploy/terraform/aws-ec2-onebox
cp terraform.tfvars.example terraform.tfvars
# Edit: key_name, ssh_cidr, admin_email, region

terraform init
terraform plan
terraform apply
```

After apply (~10–15 min first boot for Docker build):

```bash
terraform output ui_url
terraform output api_url
terraform output -raw admin_password
terraform output bootstrap_log
```

Login: `admin_email` from tfvars + generated password.

## Verify on instance

```bash
ssh -i ~/.ssh/my-key.pem ubuntu@$(terraform output -raw public_ip)
sudo tail -f /var/log/arkon-bootstrap.log
docker exec arkon_api python -m app.scripts.poc_verify
```

## What is **not** auto-created (yet)

| Item | Why | Next step |
|------|-----|-----------|
| HTTPS / domain | Needs ACM + ALB or Nginx + DNS | Add ALB module or Certbot on EC2 |
| RDS | Kept in Docker for speed | Separate `aws-ec2-rds` module |
| CI/CD | Out of scope | GitHub Actions → SSM deploy |

## Destroy

```bash
terraform destroy
```

## Promote from local MinIO to AWS S3

On EC2, point storage at real S3:

- `MINIO_ENDPOINT` → `s3.<region>.amazonaws.com`
- `MINIO_SECURE=true`
- `AWS_REGION` + IAM credentials (instance profile on EC2)
