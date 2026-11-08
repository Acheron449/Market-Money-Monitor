# ADR-002: Storage and schema ownership

- Status: accepted
- Date: 9 November 2026
- Requirements: SRS §3, §6.1, NFR-10

## Decision

- **SQLAlchemy 2 async** models in `app/db/models.py`, one entity per table in SRS §6.1, plus
  `job_lock` for single-run scheduling (AUT-06).
- **SQLite (WAL) in development**, `sqlite+aiosqlite`; **PostgreSQL 16** in Docker and deployment,
  `postgresql+asyncpg`. The only difference is `DATABASE_URL`; no dialect-specific SQL is used in
  application code.
- **Alembic owns schema changes.** The app calls `create_all` at start-up only as a development
  convenience for a fresh database; production runs `alembic upgrade head`.
- Money, shares and percentages are `Numeric(20, 4)` mapped to `Decimal`. JSON responses convert to
  numbers at the edge (SRS §6.1).
- Timestamps are stored in UTC; trading dates are `Date` in the NYSE calendar's terms.
- Upserts use `Session.merge` on the natural keys (`(accession_no, line_no)` for insider rows,
  `(symbol, date)` for bars, `(symbol, report_period, institution_cik)` for holders), which keeps
  re-runs idempotent on every dialect.

## Consequences

- `api` and `web` are stateless; only the database persists. Compose mounts a named volume for it.
- SQLite serialises writers, which is acceptable for a small watchlist; the scheduler's job lock keeps
  a single writer per job anyway.
- Moving to PostgreSQL needs only the Compose environment variable and a `pg_dump`/restore for data.
