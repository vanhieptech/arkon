# Deploy Arkon lên AWS (nhanh nhất) — EC2 + Docker Compose + S3 + Bedrock

Tài liệu này hướng dẫn **step-by-step** để deploy Arkon lên AWS theo hướng **nhanh nhất để chạy được end-to-end**:

- App chạy trên **1 EC2** bằng **Docker Compose** (API, workers, frontend, Postgres, Redis).
- File storage dùng **AWS S3** (thay MinIO).
- LLM + Embedding dùng **Amazon Bedrock** (IAM auth).
- Dùng Terraform template: `deploy/terraform/aws-ec2-onebox/` (1 lệnh `terraform apply`).

---

## 1) Kiến trúc triển khai

**Terraform tạo:**
- S3 bucket (private)
- IAM role + instance profile (S3 + Bedrock)
- IAM user + access keys (cho Docker Compose dùng lâu dài; tránh session creds IMDS hết hạn)
- Security group (SSH/5055/3119)
- EC2 + Elastic IP
- User-data bootstrap: cài Docker → clone repo → tạo `.env.docker` → `docker compose up -d --build`

**Docker chạy trên EC2:**
- Postgres (pgvector)
- Redis
- API (FastAPI)
- Workers (ARQ)
- Frontend (Next.js)

---

## 2) Chuẩn bị (máy local của bạn)

### 2.1 Cài công cụ

- Terraform >= 1.5
- AWS CLI (đã login)

Kiểm tra:

```bash
aws sts get-caller-identity
terraform version
```

### 2.2 Chọn region

Bedrock model không có ở mọi region. POC ổn định nhất thường là **`us-east-1`**.

Bạn sẽ set `aws_region` trong `terraform.tfvars`.

---

## 3) Bật Bedrock Model Access (bắt buộc)

Trên AWS Console:

- **Amazon Bedrock → Model access**
- Enable:
  - **Claude 3.5 Sonnet**
  - **Titan Text Embeddings V2**

Nếu không enable, Arkon sẽ lỗi `AccessDenied` khi test LLM/embedding.

---

## 4) Tạo (hoặc chọn) EC2 Key Pair

Trong **đúng region** bạn chọn:

- EC2 → Key pairs → Create key pair (ví dụ `arkon-keypair`)
- Tải file `.pem` và chmod:

```bash
chmod 400 ~/Downloads/arkon-keypair.pem
```

Ghi nhớ:
- `key_name` = **tên key pair** trên AWS (không phải tên file).

---

## 5) Deploy bằng Terraform template (1 lệnh)

### 5.1 Chuẩn bị tfvars

```bash
cd deploy/terraform/aws-ec2-onebox
cp terraform.tfvars.example terraform.tfvars
```

Sửa `terraform.tfvars` tối thiểu:

- `aws_region`
- `key_name`
- `ssh_cidr` (khuyến nghị IP của bạn dạng `/32`)
- `admin_email`

Lấy IP public:

```bash
curl -s ifconfig.me
```

Ví dụ:

```hcl
aws_region = "us-east-1"
key_name   = "arkon-keypair"
ssh_cidr   = "203.0.113.10/32"
admin_email = "admin@yourcompany.com"
```

### 5.2 Apply

```bash
chmod +x apply.sh
./apply.sh
```

Hoặc manual:

```bash
terraform init -upgrade
terraform plan
terraform apply
```

---

## 6) Lấy thông tin sau khi deploy

```bash
terraform output ui_url
terraform output api_url
terraform output -raw public_ip
terraform output -raw admin_password
terraform output bootstrap_log
```

- `ui_url`: trang web
- `api_url`: API
- `admin_password`: mật khẩu admin (Terraform generate nếu bạn không set)
- `bootstrap_log`: lệnh xem log bootstrap

---

## 7) Theo dõi bootstrap trên EC2

SSH:

```bash
ssh -i ~/Downloads/arkon-keypair.pem ubuntu@$(terraform output -raw public_ip)
```

Xem log:

```bash
sudo tail -f /var/log/arkon-bootstrap.log
```

Kiểm tra containers:

```bash
docker ps
```

---

## 8) Verify end-to-end (S3 + Bedrock)

Trên EC2:

```bash
docker exec arkon_api python -m app.scripts.poc_verify
```

Kỳ vọng:
- `storage: PASS` (S3)
- `embedding: PASS` (Bedrock)
- `llm: PASS` (Bedrock)
- `vision`: có thể FAIL nếu chưa cấu hình vision model (không bắt buộc cho POC)

---

## 9) Đăng nhập UI

Mở `ui_url` và đăng nhập:

- Email: `admin_email` trong `terraform.tfvars`
- Password: `terraform output -raw admin_password`

---

## 10) Troubleshooting nhanh

### 10.1 Bedrock AccessDenied

- Bạn chưa enable model trong **Bedrock → Model access**.
- Hoặc region không có model.

### 10.2 UI/API không vào được

- Kiểm tra SG có mở port `3119/5055` không.
- Check logs:

```bash
docker logs arkon_api --tail 200
docker logs arkon_frontend --tail 200
```

### 10.3 Build Next.js bị SIGKILL (OOM)

- Tăng instance type (ví dụ `t3.2xlarge`) hoặc tăng swap.

---

## 11) Production hóa (sau POC)

Template này ưu tiên “chạy được nhanh nhất”. Để production:

- **HTTPS + Domain** (ALB + ACM hoặc Nginx + Certbot)
- Siết Security Group (chỉ 443 public; SSH theo IP)
- Tách Postgres → **RDS PostgreSQL 16 + pgvector**
- Redis → **ElastiCache**
- App → **ECS Fargate** + autoscaling

---

## 12) Reference trong repo

- Template: `deploy/terraform/aws-ec2-onebox/README.md`
- Bootstrap script: `deploy/terraform/aws-ec2-onebox/templates/user-data.sh.tftpl`
- POC verify: `app/scripts/poc_verify.py`

