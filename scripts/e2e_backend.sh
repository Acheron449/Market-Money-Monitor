#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../backend"

export DATABASE_URL="sqlite+aiosqlite:///./e2e.db"
export SCHEDULER_ENABLED=false
export PROVIDERS_ENABLED=false
export SEC_USER_AGENT="Smart Money Monitor e2e e2e@example.com"
export ADMIN_TOKEN="e2e-admin-token"

rm -f e2e.db
uv run python scripts/seed_demo.py
exec uv run uvicorn app.main:app --host 127.0.0.1 --port 8010
