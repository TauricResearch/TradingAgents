"""Aggregate live-health verdict (go-live Phase 5).

One honest answer to "is the whole system healthy enough to place a new
order right now?", assembled from signals that already exist: feed
health (newest run's missing_feeds), venue reachability, clock skew,
reconciliation/run recency, and arming state. Shaped like the preflight
``ReadinessReport`` for consistency.

Consumed three ways: the ``GET /health/live`` endpoint (503 when not ok),
the loop's pre-entry gate (degraded blocks NEW entries only, never
exits), and the dead-man switch's heartbeat. Read-only and cheap — it
never places or cancels anything itself.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field

# a run older than this is stale liveness (default hourly loop + slack)
DEFAULT_MAX_RUN_AGE_SECONDS = 5400.0


@dataclass(frozen=True)
class HealthCheck:
    name: str
    ok: bool
    detail: str


@dataclass
class HealthReport:
    checks: list[HealthCheck] = field(default_factory=list)
    live_armed: bool = False

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def degraded(self) -> list[str]:
        return [c.name for c in self.checks if not c.ok]

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append(HealthCheck(name, ok, detail))

    def as_dict(self) -> dict:
        return {"ok": self.ok, "live_armed": self.live_armed,
                "degraded": self.degraded,
                "checks": [c.__dict__ for c in self.checks]}


def live_health(state, arming=None, *, now: float | None = None,
                max_run_age_seconds: float = DEFAULT_MAX_RUN_AGE_SECONDS
                ) -> HealthReport:
    """Build the verdict from ``state`` (a DashboardState). Every probe is
    guarded — a health check must never raise into the caller."""
    now = now if now is not None else time.time()
    report = HealthReport()
    report.live_armed = bool(arming) and any(
        v["tier"] in ("canary", "live") for v in arming.status().values()
    ) if arming is not None else False

    # feed health: the newest run's missing feeds
    latest = state.latest_run() if hasattr(state, "latest_run") else None
    if latest is not None:
        try:
            missing = latest.snapshot_summary().get("missing_feeds") or []
        except Exception:
            missing = []
        report.add("feeds", not missing,
                   "all feeds present" if not missing
                   else f"degraded: {missing}")

    # run recency (heartbeat): the loop bumps last_run_ts each iteration
    metrics = getattr(state, "metrics", None)
    if metrics is not None:
        last_run = metrics.gauge("last_run_ts")
        if last_run > 0:
            age = now - last_run
            report.add("run_recency", age <= max_run_age_seconds,
                       f"last run {age:.0f}s ago")

    router = getattr(state, "router", None)
    if router is not None:
        # venue/adapter reachability — a cheap guarded account() call
        try:
            router.adapter.account()
            report.add("venue", True, "venue reachable")
        except Exception as exc:
            report.add("venue", False, f"venue unreachable: {type(exc).__name__}")
        # clock skew (only when the adapter supports it; cached by adapter)
        check_clock = getattr(router.adapter, "check_clock", None)
        if callable(check_clock):
            try:
                check_clock()
                report.add("clock", True, "skew within budget")
            except Exception as exc:
                report.add("clock", False, f"{exc}")
        # not halted
        with contextlib.suppress(Exception):
            report.add("kill_switch", not router.kill_switch.engaged,
                       router.kill_switch.reason or "clear")

    return report
