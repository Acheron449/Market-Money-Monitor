#!/bin/sh
set -eu

# ADR-002: Alembic owns schema changes; production applies them before serving.
echo "applying database migrations"
uv run --no-dev alembic upgrade head

exec "$@"
