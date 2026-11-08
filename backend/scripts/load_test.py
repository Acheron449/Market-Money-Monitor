"""Measure ``/api/dashboard`` under concurrent load against NFR-01 (AC-05).

Run against a local fixture-seeded backend (the E2E one listens on 8010):

    uv run python scripts/load_test.py --url http://127.0.0.1:8010 \
      --users 50 --requests 3 --think-time-ms 500 --ramp-ms 20

The command warms the endpoint, runs the concurrent measurement and exits
non-zero when any request fails or p95 exceeds the 300 ms budget. It only reads
the API, so no provider credentials or external network calls are involved.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.load_test import (
    BUDGET_P95_MS,
    DASHBOARD_PATH,
    DEFAULT_RAMP_MS,
    DEFAULT_REQUESTS_PER_USER,
    DEFAULT_THINK_TIME_MS,
    DEFAULT_USERS,
    DEFAULT_WARMUP,
    run_load,
    warm_up,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8010", help="Backend origin")
    parser.add_argument("--path", default=DASHBOARD_PATH, help="Endpoint to measure")
    parser.add_argument("--users", type=int, default=DEFAULT_USERS, help="Concurrent clients")
    parser.add_argument(
        "--requests",
        type=int,
        default=DEFAULT_REQUESTS_PER_USER,
        help="Requests per client",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=DEFAULT_WARMUP,
        help="Sequential warm-up calls",
    )
    parser.add_argument(
        "--think-time-ms",
        type=float,
        default=DEFAULT_THINK_TIME_MS,
        help="Pause between a client's requests, modelling a browser user",
    )
    parser.add_argument(
        "--ramp-ms",
        type=float,
        default=DEFAULT_RAMP_MS,
        help="Stagger between successive client starts",
    )
    parser.add_argument(
        "--max-p95-ms",
        type=float,
        default=BUDGET_P95_MS,
        help="NFR-01 p95 budget in milliseconds",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    limits = httpx.Limits(
        max_connections=args.users + 1,
        max_keepalive_connections=args.users + 1,
    )
    async with httpx.AsyncClient(
        base_url=args.url,
        limits=limits,
        timeout=httpx.Timeout(30.0),
    ) as client:

        async def fetch() -> bool:
            response = await client.get(args.path)
            return response.status_code == 200

        await warm_up(fetch, args.warmup)
        result = await run_load(
            fetch,
            users=args.users,
            requests_per_user=args.requests,
            think_time_ms=args.think_time_ms,
            ramp_ms=args.ramp_ms,
        )

    print(result.summary(args.max_p95_ms))
    return 0 if result.within(args.max_p95_ms) else 1


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    if args.users < 1:
        parser.error("--users must be at least 1")
    if args.requests < 1:
        parser.error("--requests must be at least 1")
    if args.warmup < 0:
        parser.error("--warmup must be zero or more")
    if args.think_time_ms < 0:
        parser.error("--think-time-ms must be zero or more")
    if args.ramp_ms < 0:
        parser.error("--ramp-ms must be zero or more")
    if args.max_p95_ms <= 0:
        parser.error("--max-p95-ms must be positive")
    try:
        status = asyncio.run(_run(args))
    except httpx.HTTPError as exc:
        parser.error(f"load test could not reach {args.url}: {exc}")
    raise SystemExit(status)


if __name__ == "__main__":
    main()
