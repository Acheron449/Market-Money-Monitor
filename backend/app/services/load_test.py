"""AC-05: concurrent dashboard load measurement against NFR-01."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

DASHBOARD_PATH = "/api/dashboard"
DEFAULT_USERS = 50
DEFAULT_REQUESTS_PER_USER = 3
DEFAULT_THINK_TIME_MS = 1000.0
DEFAULT_RAMP_MS = 20.0
DEFAULT_WARMUP = 10
BUDGET_P95_MS = 300.0

Fetch = Callable[[], Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class LoadResult:
    """One measured run: latency percentiles, throughput and failed requests."""

    users: int
    requests_per_user: int
    think_time_ms: float
    ramp_ms: float
    duration_seconds: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    throughput_rps: float
    errors: int

    @property
    def requests(self) -> int:
        return self.users * self.requests_per_user

    def within(self, budget_ms: float = BUDGET_P95_MS) -> bool:
        return self.errors == 0 and self.p95_ms <= budget_ms

    def summary(self, budget_ms: float = BUDGET_P95_MS) -> str:
        verdict = "pass" if self.within(budget_ms) else "fail"
        return (
            f"load test: {self.users} users x {self.requests_per_user} requests "
            f"({self.requests} total, {self.think_time_ms:.0f} ms think, "
            f"{self.ramp_ms:.0f} ms ramp) in {self.duration_seconds:.2f}s "
            f"({self.throughput_rps:.1f} rps) · "
            f"p50 {self.p50_ms:.1f} ms · p95 {self.p95_ms:.1f} ms · "
            f"p99 {self.p99_ms:.1f} ms · {self.errors} errors · "
            f"budget {budget_ms:.0f} ms · {verdict}"
        )


def percentile(samples: list[float], quantile: float) -> float:
    """Nearest-rank percentile: the smallest sample covering ``quantile`` percent."""

    if not samples:
        raise ValueError("percentile needs at least one sample")
    if not 0 < quantile <= 100:
        raise ValueError("quantile must be in (0, 100]")
    ordered = sorted(samples)
    rank = math.ceil(quantile / 100 * len(ordered))
    return ordered[max(rank - 1, 0)]


async def warm_up(fetch: Fetch, attempts: int = DEFAULT_WARMUP) -> int:
    """Send ``attempts`` sequential requests so the measurement starts warm."""

    if attempts < 0:
        raise ValueError("warm-up attempts must be zero or more")
    for _ in range(attempts):
        await fetch()
    return attempts


async def run_load(
    fetch: Fetch,
    *,
    users: int = DEFAULT_USERS,
    requests_per_user: int = DEFAULT_REQUESTS_PER_USER,
    think_time_ms: float = DEFAULT_THINK_TIME_MS,
    ramp_ms: float = DEFAULT_RAMP_MS,
) -> LoadResult:
    """Run ``users`` concurrent clients, each issuing ``requests_per_user`` calls.

    ``think_time_ms`` pauses a client between requests and ``ramp_ms`` staggers
    successive client starts, so the run models a population of browser users
    rather than a single synchronized burst. Neither pauses after the last
    request.
    """

    if users < 1:
        raise ValueError("users must be at least 1")
    if requests_per_user < 1:
        raise ValueError("requests_per_user must be at least 1")
    if think_time_ms < 0:
        raise ValueError("think_time_ms must be zero or more")
    if ramp_ms < 0:
        raise ValueError("ramp_ms must be zero or more")

    latencies: list[float] = []
    errors = 0

    async def worker(index: int) -> None:
        nonlocal errors
        if index and ramp_ms:
            await asyncio.sleep(index * ramp_ms / 1000)
        for attempt in range(requests_per_user):
            if attempt and think_time_ms:
                await asyncio.sleep(think_time_ms / 1000)
            started = time.perf_counter()
            ok = await fetch()
            latencies.append((time.perf_counter() - started) * 1000)
            if not ok:
                errors += 1

    started = time.perf_counter()
    await asyncio.gather(*(worker(index) for index in range(users)))
    duration = time.perf_counter() - started

    return LoadResult(
        users=users,
        requests_per_user=requests_per_user,
        think_time_ms=think_time_ms,
        ramp_ms=ramp_ms,
        duration_seconds=duration,
        p50_ms=percentile(latencies, 50),
        p95_ms=percentile(latencies, 95),
        p99_ms=percentile(latencies, 99),
        throughput_rps=len(latencies) / duration if duration > 0 else 0.0,
        errors=errors,
    )
