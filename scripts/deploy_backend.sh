#!/usr/bin/env bash
# Production-shape backend for the deployment smoke test.
# Mirrors the container entrypoint: alembic upgrade head, then uvicorn without --reload.
set -euo pipefail

cd "$(dirname "$0")/../backend"

export ENVIRONMENT="production"
export DATABASE_URL="sqlite+aiosqlite:///./deploy.db"
export SEC_USER_AGENT="Smart Money Monitor deploy-smoke@example.net"
export ADMIN_TOKEN="deploy-smoke-admin-token"
export CORS_ORIGINS="http://127.0.0.1:5184"
export CONFIG_FILE="../smm.yaml"
export SCHEDULER_ENABLED=false
export PROVIDERS_ENABLED=false

rm -f deploy.db deploy.db-wal deploy.db-shm
uv run alembic upgrade head
uv run python scripts/seed_demo.py
exec uv run uvicorn app.main:app --host 127.0.0.1 --port 8020
