#!/usr/bin/env bash
# Start Arkon with LocalStack S3 instead of MinIO.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

ENV_DOCKER="${ENV_DOCKER:-.env.docker}"
if [[ ! -f "$ENV_DOCKER" ]]; then
  echo "Missing $ENV_DOCKER — run: cp .env.docker.example .env.docker"
  exit 1
fi

COMPOSE=(docker compose
  -f docker-compose.yml
  -f deploy/poc-localstack/docker-compose.localstack.yml
  --env-file "$ENV_DOCKER")

echo "==> LocalStack S3 POC (MinIO scaled to 0)"
"${COMPOSE[@]}" build api
"${COMPOSE[@]}" up -d --scale minio=0 --build

echo ""
echo "Waiting for API health..."
for i in $(seq 1 60); do
  if curl -sf "http://localhost:5055/health" >/dev/null 2>&1; then
    echo "API healthy."
    break
  fi
  if [[ "$i" -eq 60 ]]; then
    echo "API did not become healthy in time. Check: docker logs arkon_api"
    exit 1
  fi
  sleep 2
done

echo ""
echo "Running S3 smoke test..."
"$ROOT/deploy/poc-localstack/smoke-test.sh"

echo ""
echo "POC ready:"
echo "  UI:  http://localhost:3119"
echo "  API: http://localhost:5055"
echo "  S3:  http://localhost:4566 (LocalStack)"
