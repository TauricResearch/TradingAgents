"""Background polling engine that checks recommendation price levels.

Loads active alerts from the DB, fetches current prices via PriceService,
and fires callbacks when a target price is breached.  Uses
``threading.Timer`` for non-blocking scheduling — each poll schedules the
next one, so no thread is blocked between polls.

Polling frequency adapts to US market hours:
- Every 5 min during market hours (9:30-16:00 ET, weekdays)
- Every 30 min outside market hours

Crash recovery: exponential backoff (5m -> 10m -> 20m, capped at 60m)
with automatic reset on success.

Thread-safe start/stop.
"""

from __future__ import annotations

import logging
import threading
import zoneinfo
from collections.abc import Callable
from datetime import datetime
from typing import Final

from desktop.services.price_service import PriceService
from desktop.state.database import (
    AlertHistoryRow,
    AlertRow,
    HistoryDB,
    RecommendationRow,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MARKET_POLL_SECONDS: Final[int] = 300  # 5 min
_OFF_HOURS_POLL_SECONDS: Final[int] = 1800  # 30 min
_INITIAL_BACKOFF_SECONDS: Final[int] = 300  # 5 min
_MAX_BACKOFF_SECONDS: Final[int] = 3600  # 60 min
_ET_ZONE: Final[zoneinfo.ZoneInfo] = zoneinfo.ZoneInfo("America/New_York")

# Alert type -> direction mapping for auto-creation from recommendations
_ALERT_SPECS: Final[list[tuple[str, str, str]]] = [
    # (attr on RecommendationRow, alert_type, direction)
    ("stop_loss", "stop_loss", "below"),
    ("entry_trigger", "entry_trigger", "below"),
    ("profit_target", "profit_target", "above"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_market_hours() -> bool:
    """Return True if the US stock market is currently open."""
    et = datetime.now(_ET_ZONE)
    if et.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    minutes = et.hour * 60 + et.minute
    return 9 * 60 + 30 <= minutes <= 16 * 60


def _poll_interval() -> int:
    """Return the appropriate poll interval in seconds."""
    return _MARKET_POLL_SECONDS if _is_market_hours() else _OFF_HOURS_POLL_SECONDS


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class AlertEngine:
    """Background polling engine for price alerts.

    Parameters
    ----------
    db:
        Database instance for reading/writing alerts.
    price_service:
        Price fetcher for current ticker prices.
    """

    def __init__(self, db: HistoryDB, price_service: PriceService) -> None:
        self._db = db
        self._price_service = price_service

        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._running = False
        self._degraded = False
        self._backoff = 0
        self._consecutive_failures = 0
        self._last_poll_at: str | None = None
        self._callbacks: list[Callable[[AlertHistoryRow], None]] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the polling loop in background."""
        with self._lock:
            if self._running:
                logger.warning("AlertEngine.start() called but already running")
                return
            self._running = True
            self._degraded = False
            self._backoff = 0
            self._consecutive_failures = 0

        logger.info("AlertEngine started")
        self._schedule_next(delay=0)

    def stop(self) -> None:
        """Stop the polling loop."""
        with self._lock:
            self._running = False
            timer = self._timer
            self._timer = None

        if timer is not None:
            timer.cancel()

        logger.info("AlertEngine stopped")

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def is_degraded(self) -> bool:
        """True if in exponential backoff after a failure."""
        with self._lock:
            return self._degraded

    @property
    def backoff_seconds(self) -> int:
        """Current backoff interval (0 if healthy)."""
        with self._lock:
            return self._backoff

    @property
    def last_poll_at(self) -> str | None:
        """ISO timestamp of last successful poll."""
        with self._lock:
            return self._last_poll_at

    @property
    def unseen_count(self) -> int:
        """Number of unseen alert history entries."""
        try:
            return self._db.count_unseen_alert_history()
        except Exception:
            logger.exception("Failed to count unseen alerts")
            return 0

    def on_alert(self, callback: Callable[[AlertHistoryRow], None]) -> None:
        """Register a callback for when an alert fires."""
        with self._lock:
            self._callbacks.append(callback)

    def create_alerts_for_recommendation(self, rec: RecommendationRow) -> int:
        """Auto-create alerts from a recommendation's price levels.

        Creates up to 3 alerts (stop_loss, entry_trigger, profit_target)
        if the recommendation has those price levels set.  Skips any
        alert type that already exists for the same recommendation.

        Returns the count of alerts created.
        """
        existing = self._db.list_alerts_for_recommendation(rec.id)
        existing_types = {a.alert_type for a in existing}

        created = 0
        for attr, alert_type, direction in _ALERT_SPECS:
            if alert_type in existing_types:
                continue
            price = getattr(rec, attr, None)
            if price is None:
                continue

            try:
                self._db.insert_alert(
                    recommendation_id=rec.id,
                    ticker=rec.ticker,
                    alert_type=alert_type,
                    target_price=price,
                    direction=direction,
                )
                created += 1
                logger.info(
                    "Created %s alert for %s at $%.2f (%s)",
                    alert_type, rec.ticker, price, direction,
                )
            except Exception:
                logger.exception(
                    "Failed to create %s alert for recommendation #%d",
                    alert_type, rec.id,
                )

        return created

    # ------------------------------------------------------------------
    # Internal scheduling
    # ------------------------------------------------------------------

    def _schedule_next(self, delay: int | None = None) -> None:
        """Schedule the next poll after *delay* seconds.

        If *delay* is None, uses the adaptive interval (market hours
        aware) or the current backoff value.
        """
        with self._lock:
            if not self._running:
                return

            if delay is None:
                delay = self._backoff if self._degraded else _poll_interval()

            self._timer = threading.Timer(float(max(delay, 0)), self._poll_cycle)
            self._timer.daemon = True
            self._timer.name = "alert-engine-poll"
            self._timer.start()

    def _poll_cycle(self) -> None:
        """Execute one poll cycle, then schedule the next."""
        with self._lock:
            if not self._running:
                return

        try:
            self._execute_poll()

            # Success: reset backoff state
            with self._lock:
                self._degraded = False
                self._backoff = 0
                self._consecutive_failures = 0
                self._last_poll_at = datetime.now(_ET_ZONE).isoformat(
                    timespec="seconds"
                )

        except Exception:
            logger.exception("Alert poll cycle failed")
            with self._lock:
                self._consecutive_failures += 1
                self._degraded = True
                # Exponential backoff: 5m -> 10m -> 20m -> 40m -> 60m (cap)
                self._backoff = min(
                    _INITIAL_BACKOFF_SECONDS * (2 ** (self._consecutive_failures - 1)),
                    _MAX_BACKOFF_SECONDS,
                )
                logger.warning(
                    "Alert engine degraded: %d consecutive failures, "
                    "next retry in %ds",
                    self._consecutive_failures,
                    self._backoff,
                )

        # Schedule next regardless of success/failure
        self._schedule_next()

    def _execute_poll(self) -> None:
        """Fetch prices and check all active alerts."""
        active_alerts = self._db.list_active_alerts()
        if not active_alerts:
            return

        # Group alerts by ticker to batch-fetch prices
        tickers = list({a.ticker for a in active_alerts})
        prices = self._price_service.get_prices(tickers)

        for alert in active_alerts:
            price_result = prices.get(alert.ticker)
            if price_result is None or price_result.price is None:
                continue
            if price_result.error is not None and not price_result.is_stale:
                continue

            current_price = price_result.price
            if self._is_triggered(alert, current_price):
                self._fire_alert(alert, current_price)

    @staticmethod
    def _is_triggered(alert: AlertRow, current_price: float) -> bool:
        """Check whether the current price breaches the alert threshold."""
        if alert.direction == "above":
            return current_price >= alert.target_price
        if alert.direction == "below":
            return current_price <= alert.target_price
        return False

    def _fire_alert(self, alert: AlertRow, price: float) -> None:
        """Trigger an alert: update DB, record history, invoke callbacks."""
        message = (
            f"{alert.ticker} {alert.alert_type.replace('_', ' ')} alert: "
            f"price ${price:.2f} hit {alert.direction} "
            f"target ${alert.target_price:.2f}"
        )

        try:
            self._db.trigger_alert(alert.id, price)
            history_id = self._db.insert_alert_history(
                alert_id=alert.id, price=price, message=message,
            )
            logger.info("Alert #%d fired: %s", alert.id, message)
        except Exception:
            logger.exception("Failed to persist alert #%d trigger", alert.id)
            return

        # Build the history row for callbacks
        history_row = AlertHistoryRow(
            id=history_id,
            alert_id=alert.id,
            fired_at=datetime.now(_ET_ZONE).isoformat(timespec="seconds"),
            price=price,
            message=message,
            seen=0,
        )

        # Invoke registered callbacks (best-effort)
        with self._lock:
            callbacks = list(self._callbacks)

        for cb in callbacks:
            try:
                cb(history_row)
            except Exception:
                logger.exception("Alert callback failed for alert #%d", alert.id)
