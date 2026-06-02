# Arkon × LocalStack S3 POC

Simplest path to validate **S3-compatible storage on LocalStack** before AWS.

Arkon still runs as Docker Compose (Postgres, Redis, API, workers, frontend). Only **MinIO is replaced** by LocalStack S3.

## Prerequisites

- Docker Compose v2
- `.env.docker` (copy from `.env.docker.example`)
- Optional: [LocalStack auth token](https://app.localstack.cloud/) in env:

  ```bash
  export LOCALSTACK_AUTH_TOKEN=your-token
  ```

## Start

```bash
chmod +x deploy/poc-localstack/*.sh
./deploy/poc-localstack/up.sh
```

## Smoke test only (stack already running)

```bash
./deploy/poc-localstack/smoke-test.sh
```

## Stop

```bash
./deploy/poc-localstack/down.sh
```

## What passes

1. LocalStack healthy (`:4566`)
2. Bucket `arkon-files` created
3. Upload / download / presign via `storage_service`
4. `POST /api/auth/login` → 200

## URLs

| Service | URL |
|---------|-----|
| UI | http://localhost:3119 |
| API | http://localhost:5055 |
| LocalStack | http://localhost:4566 |

## Env overrides (set in compose overlay)

| Variable | POC value |
|----------|-----------|
| `MINIO_ENDPOINT` | `localstack:4566` |
| `MINIO_PUBLIC_ENDPOINT` | `localhost:4566` |
| `MINIO_ACCESS_KEY` / `SECRET` | `test` / `test` |
| `MINIO_REGION` | `us-east-1` |

## Next: real AWS

Same env shape — point endpoints to `s3.<region>.amazonaws.com`, `MINIO_SECURE=true`, IAM credentials or task role.
