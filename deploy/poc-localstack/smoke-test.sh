#!/usr/bin/env bash
# Verify Arkon API + LocalStack S3 read/write.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "==> Storage round-trip (inside api container)"
docker exec arkon_api python - <<'PY'
import asyncio
from app.services.storage_service import storage_service

async def main() -> None:
    await storage_service.ensure_bucket()
    key = "poc/localstack-smoke.txt"
    body = b"arkon-localstack-poc-ok"
    storage_service.upload_file(key, body, "text/plain")
    got = storage_service.download_file(key)
    assert got == body, (got, body)
    url = storage_service.get_presigned_url(key, expiry_hours=1)
    assert "poc/localstack-smoke.txt" in url
    print("storage OK")
    print("presign sample:", url[:120], "...")

asyncio.run(main())
PY

echo "==> Auth login"
HTTP=$(curl -s -o /tmp/arkon-login.json -w "%{http_code}" \
  -X POST "http://localhost:5055/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@arkon.local","password":"admin123"}')
if [[ "$HTTP" != "200" ]]; then
  echo "Login failed HTTP $HTTP"
  cat /tmp/arkon-login.json
  exit 1
fi
echo "login OK"

echo "==> LocalStack bucket listing"
docker run --rm --network arkon_default \
  -e AWS_ACCESS_KEY_ID=test \
  -e AWS_SECRET_ACCESS_KEY=test \
  -e AWS_DEFAULT_REGION=us-east-1 \
  amazon/aws-cli:2.22.35 \
  --endpoint-url=http://localstack:4566 s3 ls s3://arkon-files/poc/ || true

echo ""
echo "All smoke checks passed."
