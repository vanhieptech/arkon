# Arkon POC — LocalStack (S3) + Amazon Bedrock (LLM & Embedding)

End-to-end path to validate AWS deployment locally, then promote the same Terraform/env to real AWS.

## Architecture

| Component | POC runtime | Production AWS |
|-----------|-------------|----------------|
| Object storage | LocalStack S3 (`:4566`) | S3 |
| LLM + embeddings | **Real Bedrock** (IAM) | Bedrock |
| Postgres + pgvector | Docker | RDS PostgreSQL 16 |
| Redis + workers | Docker | ElastiCache + ECS |
| Frontend + API | Docker | ECS / ALB |

Bedrock is **not** fully emulated on LocalStack Community — use real AWS credentials with model access enabled in the [Bedrock console](https://console.aws.amazon.com/bedrock/).

## Prerequisites

1. Docker + Docker Compose v2
2. [LocalStack account](https://app.localstack.cloud/) → `LOCALSTACK_AUTH_TOKEN`
3. AWS IAM user/role with:
   - `bedrock:InvokeModel`, `bedrock:Converse`
   - Model access: **Claude 3.5 Sonnet**, **Titan Text Embeddings V2**
4. Region: `us-east-1` recommended (model availability)

## Quick start

```bash
cd arkon
cp .env.localstack.example .env.docker
# Edit: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, LOCALSTACK_AUTH_TOKEN

chmod +x scripts/poc-up.sh
./scripts/poc-up.sh
```

Manual equivalent:

```bash
docker compose -f docker-compose.yml -f docker-compose.localstack.yml \
  --env-file .env.docker up -d --build

docker exec arkon_api python -m app.scripts.poc_verify
```

## Environment

| Variable | Purpose |
|----------|---------|
| `POC_CONFIGURE_BEDROCK=1` | Auto-set active models on startup |
| `POC_LLM_SPEC_ID` | Default `bedrock/claude-3-5-sonnet` |
| `POC_EMBEDDING_SPEC_ID` | Default `bedrock/titan-embed-v2` |
| `AWS_REGION` | Bedrock region |
| `MINIO_*` | Point SDK at LocalStack S3 (see overlay) |

## Catalog models (Settings)

- **LLM:** `bedrock/claude-3-5-sonnet`, `bedrock/claude-3-haiku`
- **Embedding:** `bedrock/titan-embed-v2` (1024d → `wiki_page_embeddings_1024`)

No API key in Settings — Bedrock uses the AWS credential chain inside containers.

## Terraform (optional)

```bash
cd deploy/terraform/localstack
# LocalStack:
tflocal init && tflocal apply
# Real AWS:
terraform init && terraform apply
```

## Promote to AWS

1. `terraform apply` on real AWS (S3, Secrets Manager, ECR, RDS, ECS).
2. Replace `MINIO_ENDPOINT` with `s3.<region>.amazonaws.com`, `MINIO_SECURE=true`.
3. Keep the same Bedrock catalog spec IDs — only IAM task role required.
4. Set `NEXT_PUBLIC_API_URL` + HTTPS (required for MCP OAuth).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Bedrock LLM error: AccessDenied` | Enable model in Bedrock console → Model access |
| `relation ... does not exist` | `docker compose down -v` and re-up (fresh DB) |
| S3 connection refused | Wait for `arkon_localstack` healthy; check `localstack-init` logs |
| Embedding dimension error | Use `bedrock/titan-embed-v2` (1024d), re-embed after switch |

## Verify

```bash
docker exec arkon_api python -m app.scripts.poc_verify
curl -s http://localhost:5055/health
```

Login: `http://localhost:3119` — Settings → test LLM / test embedding should pass.
