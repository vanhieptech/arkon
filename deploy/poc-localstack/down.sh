#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
ENV_DOCKER="${ENV_DOCKER:-.env.docker}"
docker compose \
  -f docker-compose.yml \
  -f deploy/poc-localstack/docker-compose.localstack.yml \
  --env-file "$ENV_DOCKER" \
  down "$@"
