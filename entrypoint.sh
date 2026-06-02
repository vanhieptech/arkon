#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete."

echo "Seeding built-in skills..."
python -m app.scripts.seed_skills
echo "Skills seeding complete."

if [ "${POC_CONFIGURE_BEDROCK:-0}" = "1" ]; then
  echo "Configuring Bedrock POC (active LLM + embedding)..."
  python -m app.scripts.poc_configure
  echo "Bedrock POC config complete."
fi

exec "$@"
