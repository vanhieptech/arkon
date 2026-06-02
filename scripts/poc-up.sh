#!/usr/bin/env bash
# Start Arkon POC: LocalStack S3 + Bedrock LLM/embedding.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env.docker ]]; then
  echo "Creating .env.docker from .env.localstack.example"
  cp .env.localstack.example .env.docker
  echo "Edit .env.docker: set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, LOCALSTACK_AUTH_TOKEN"
fi

docker compose -f docker-compose.yml -f docker-compose.localstack.yml \
  --env-file .env.docker up -d --build

echo "Waiting for API health..."
for _ in $(seq 1 60); do
  if curl -sf http://localhost:5055/health >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

echo "Running POC verify inside API container..."
docker exec arkon_api python -m app.scripts.poc_verify

echo ""
echo "UI:  http://localhost:3119"
echo "API: http://localhost:5055"
echo "Admin: admin@arkon.local / (see DEFAULT_ADMIN_PASSWORD in .env.docker)"
