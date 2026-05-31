"""Cost / rate / backpressure guards for the F4 orchestrator.

Per IIC-FORGE program design Appendix A:
- Every guard is coded and toggleable.
- All ship with ``enabled=False`` during F0–F5.
- Measurement is always on, even when enforcement is disabled.

Flip ``enabled=True`` (via config flag or env override) after observing
the natural cost/rate profile from the F5 dashboard.
"""

from __future__ import annotations

import logging
import sqlite3

from tradingagents.orchestrator import queue_store


log = logging.getLogger(__name__)


class QueueBackpressure:
    """Promoter-side. Blocks new enqueues when (queued+running) >= max_pending."""

    def __init__(self, *, enabled: bool, max_pending: int) -> None:
        self.enabled = enabled
        self.max_pending = max_pending

    def gate(self, conn: sqlite3.Connection) -> bool:
        depth = queue_store.pending_count(conn)
        if not self.enabled:
            # measurement-only — never gate, always log
            log.debug("queue_depth=%d (backpressure guard disabled)", depth)
            return True
        if depth >= self.max_pending:
            log.warning(
                "queue backpressure: depth=%d >= max=%d, skipping cycle",
                depth, self.max_pending,
            )
            return False
        return True


class QueueRateGuard:
    """Promoter-side. Blocks new enqueues when daily-enqueue count >= max_per_day."""

    def __init__(self, *, enabled: bool, max_per_day: int) -> None:
        self.enabled = enabled
        self.max_per_day = max_per_day

    def gate(self, conn: sqlite3.Connection) -> bool:
        n = queue_store.daily_enqueue_count(conn)
        if not self.enabled:
            log.debug("daily_enqueue=%d (rate guard disabled)", n)
            return True
        if n >= self.max_per_day:
            log.warning(
                "queue rate guard: %d enqueues today >= max=%d, skipping",
                n, self.max_per_day,
            )
            return False
        return True


class DailyBudgetGuard:
    """Worker-side. Blocks new dispatch when SUM(cost_usd) today >= daily_usd."""

    def __init__(self, *, enabled: bool, daily_usd: float) -> None:
        self.enabled = enabled
        self.daily_usd = daily_usd

    def gate(self, conn: sqlite3.Connection) -> bool:
        total = queue_store.daily_cost_total(conn)
        if not self.enabled:
            log.debug("daily_cost_usd=%.4f (budget guard disabled)", total)
            return True
        if total >= self.daily_usd:
            log.warning(
                "daily budget guard: $%.2f spent today >= $%.2f limit",
                total, self.daily_usd,
            )
            return False
        return True
