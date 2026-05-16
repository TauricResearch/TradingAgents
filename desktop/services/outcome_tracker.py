"""Background task that records recommendation outcomes at checkpoints.

Checks active recommendations at 1d, 7d, 30d, and 90d intervals,
fetching current prices and recording return percentages plus
stop-loss / profit-target hit status.

Runs on app start and every 4 hours via ``threading.Timer``.
Thread-safe start/stop.

See also: PLAN-desktop.md, Phase 4.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone

from desktop.services.price_service import PriceService
from desktop.state.database import HistoryDB, RecommendationRow

logger = logging.getLogger(__name__)

# Checkpoints in days — outcomes are recorded once per checkpoint.
_CHECKPOINTS: tuple[int, ...] = (1, 7, 30, 90)

# Interval between background checks (4 hours in seconds).
_CHECK_INTERVAL: int = 4 * 60 * 60


def _days_since(created_at: str) -> float:
    """Return fractional days elapsed since *created_at* (ISO format)."""
    created = datetime.fromisoformat(created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    return (now - created).total_seconds() / 86_400


def _check_stop_hit(
    price: float, rec: RecommendationRow,
) -> bool:
    """Return True if the current price breached the stop-loss level."""
    if rec.stop_loss is None:
        return False
    return price <= rec.stop_loss


def _check_target_hit(
    price: float, rec: RecommendationRow,
) -> bool:
    """Return True if the current price reached the profit target."""
    if rec.profit_target is None:
        return False
    return price >= rec.profit_target


def _compute_return_pct(
    price_at_analysis: float | None, price_now: float,
) -> float:
    """Percentage return from analysis price to current price."""
    if price_at_analysis is None or price_at_analysis == 0.0:
        return 0.0
    return round(((price_now - price_at_analysis) / price_at_analysis) * 100, 4)


class OutcomeTracker:
    """Background service that records recommendation outcomes.

    Parameters
    ----------
    db : HistoryDB
        Database handle for reading recommendations and writing outcomes.
    price_service : PriceService
        Cached price fetcher for current quotes.
    """

    def __init__(self, db: HistoryDB, price_service: PriceService) -> None:
        self._db = db
        self._price_service = price_service
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._running = False

    # ── Public API ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background check loop (idempotent)."""
        with self._lock:
            if self._running:
                return
            self._running = True
        logger.info("OutcomeTracker started")
        self._schedule_next(initial=True)

    def stop(self) -> None:
        """Stop the background check loop and cancel pending timer."""
        with self._lock:
            self._running = False
            timer = self._timer
            self._timer = None
        if timer is not None:
            timer.cancel()
        logger.info("OutcomeTracker stopped")

    def run_check(self) -> int:
        """Run a single outcome check cycle.

        Returns the number of new outcome rows recorded.
        """
        recs = self._db.list_active_recommendations()
        if not recs:
            return 0

        # Batch-fetch prices for all unique tickers.
        tickers = list({r.ticker for r in recs})
        prices = self._price_service.get_prices(tickers)

        recorded = 0
        for rec in recs:
            price_result = prices.get(rec.ticker)
            if price_result is None or price_result.price is None:
                logger.debug("No price available for %s, skipping", rec.ticker)
                continue

            days_elapsed = _days_since(rec.created_at)
            current_price = price_result.price

            for checkpoint in _CHECKPOINTS:
                if days_elapsed < checkpoint:
                    break  # Sorted ascending — no later checkpoints apply.

                recorded += self._record_if_missing(
                    rec=rec,
                    checkpoint=checkpoint,
                    current_price=current_price,
                )

        if recorded:
            logger.info("Recorded %d new outcome(s)", recorded)
        return recorded

    # ── Private helpers ────────────────────────────────────────────────

    def _record_if_missing(
        self,
        *,
        rec: RecommendationRow,
        checkpoint: int,
        current_price: float,
    ) -> int:
        """Insert an outcome row if one does not already exist.

        Returns 1 on success, 0 if already exists or on error.
        """
        try:
            self._db.insert_outcome(
                recommendation_id=rec.id,
                days_elapsed=checkpoint,
                price_at_check=current_price,
                return_pct=_compute_return_pct(rec.price_at_analysis, current_price),
                stop_hit=_check_stop_hit(current_price, rec),
                target_hit=_check_target_hit(current_price, rec),
            )
            return 1
        except sqlite3.IntegrityError:
            # UNIQUE(recommendation_id, days_elapsed) — already recorded.
            return 0
        except Exception:
            logger.exception(
                "Failed to record outcome for rec #%d at %dd",
                rec.id, checkpoint,
            )
            return 0

    def _schedule_next(self, *, initial: bool = False) -> None:
        """Schedule the next check cycle via a daemon timer."""
        with self._lock:
            if not self._running:
                return

        # Run the check immediately on first call.
        if initial:
            try:
                self.run_check()
            except Exception:
                logger.exception("OutcomeTracker initial check failed")

        with self._lock:
            if not self._running:
                return
            self._timer = threading.Timer(_CHECK_INTERVAL, self._on_timer)
            self._timer.daemon = True
            self._timer.start()

    def _on_timer(self) -> None:
        """Timer callback — run check then reschedule."""
        try:
            self.run_check()
        except Exception:
            logger.exception("OutcomeTracker periodic check failed")
        self._schedule_next()
