# Runbook — deployment and operations

Covers the production stack in `ops/docker-compose.yml`: `db` (PostgreSQL 16), `api` (FastAPI)
and `web` (nginx serving the built dashboard). Requirement: NFR-10, SRS §3.

## 1. Prerequisites

- Docker Engine with the Compose plugin, and a host with outbound HTTPS for provider traffic.
- `ops/.env` with at least `SEC_USER_AGENT` (a descriptive agent with a contact email) and
  `ADMIN_TOKEN` (a long random string). Compose refuses to start without both.
- `POSTGRES_PASSWORD` set to a real secret; `WEB_ORIGIN` set to the public origin that serves the
  dashboard, so the API CORS allow-list matches it.

## 2. First deploy

```bash
cp ops/.env.example ops/.env      # fill in the values above; never commit it
docker compose -f ops/docker-compose.yml up -d --build
docker compose -f ops/docker-compose.yml ps
```

The API container's entrypoint runs `alembic upgrade head` before uvicorn starts, so an empty
database volume is migrated on first boot. `web` waits for the API's `/readyz` health check before
starting, and nginx proxies `/api`, `/healthz`, `/readyz` and `/metrics` to it.

Verify:

```bash
curl -fsS http://localhost:3000/healthz          # {"status":"ok"}
curl -fsS http://localhost:3000/readyz           # {"status":"ready"}
curl -fsS http://localhost:3000/api/dashboard | head -c 200
```

The dashboard is served at `http://localhost:3000/` (or your `WEB_ORIGIN`). Seeded data is not
created in production: the scheduler fills the store from the configured providers on first run.

## 3. Migrations

`alembic upgrade head` runs automatically on every API start. To run it by hand:

```bash
docker compose -f ops/docker-compose.yml exec api uv run --no-dev alembic upgrade head
docker compose -f ops/docker-compose.yml exec api uv run --no-dev alembic current
```

Rollback a release that shipped a migration:

```bash
docker compose -f ops/docker-compose.yml exec api uv run --no-dev alembic downgrade -1
```

## 4. Backups and restore

```bash
# Backup
docker compose -f ops/docker-compose.yml exec -T db \
  pg_dump -U smm -d smm -Fc > smm-$(date +%Y%m%dT%H%M%S).dump

# Restore into an empty database
docker compose -f ops/docker-compose.yml stop api web
docker compose -f ops/docker-compose.yml exec -T db \
  pg_restore -U smm -d smm --clean --if-exists < smm-20260115T020000.dump
docker compose -f ops/docker-compose.yml start api web
```

Back up before every upgrade. SQLite is supported for a single node (ADR-002); back it up by
copying the database file while the API is stopped.

## 5. Upgrade and rollback

```bash
git pull
docker compose -f ops/docker-compose.yml build
docker compose -f ops/docker-compose.yml up -d
```

If the new version fails its health check, roll back the images to the previous build, or check out
the previous tag and run the same commands; use the Alembic downgrade above when a migration must be
reverted.

## 6. Health, logs and troubleshooting

| Symptom | Check |
| --- | --- |
| `web` unhealthy | `docker compose -f ops/docker-compose.yml logs web`; nginx proxies `/healthz`, so a failing API also fails this check |
| `api` unhealthy | `logs api`; `/readyz` fails when the database is unreachable |
| `api` exits at start-up | The production guard names the missing value (`SEC_USER_AGENT`, `ADMIN_TOKEN`, wildcard `CORS_ORIGINS`) |
| Empty dashboard | Providers may be unset or disabled; check `logs api` for ingest warnings and `/api/data-quality` |
| Stale badges | A provider outage; the API still serves last-good data (NFR-03) |

`SCHEDULER_ENABLED=false` runs the API without jobs, which is useful for a read-only replica or a
maintenance window.

## 7. What CI verifies

- Both images build (`docker build` for `backend/` and `frontend/`).
- `docker compose config --quiet` accepts the production Compose file with the required secrets.
- Locally, `cd frontend && pnpm smoke:deploy` builds the production bundle, applies migrations to an
  empty SQLite database, seeds fixtures, serves the bundle with the same proxied paths and checks
  health, hashed assets, SPA fallback, the dashboard and the AC-07 axe scan.
