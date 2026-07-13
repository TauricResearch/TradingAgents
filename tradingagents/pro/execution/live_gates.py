"""Live-capital risk gates (go-live Phase 3).

Evaluated in the router chain AFTER the circuit breaker, only when a
``LiveGateChain`` is wired (paper wiring passes None — zero behavior
change). Every gate is a pure deterministic check; a rejection is final
and audited, and no override path exists anywhere in code.

Also here: ``LossLimitMonitor`` — daily/weekly loss and drawdown-from-
high-water-mark tracking against VENUE-REPORTED equity (never book
equity), evaluated on every fill and on a timer. A breach cancels all
resting orders, flattens every position (operator decision), and
engages the kill switch — re-enabling requires the manual ceremony.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from tradingagents.contracts import LiveRiskLimits

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GateResult:
    ok: bool
    gate: str = ""
    reason: str = ""

    @staticmethod
    def passed() -> GateResult:
        return GateResult(ok=True)

    @staticmethod
    def rejected(gate: str, reason: str) -> GateResult:
        return GateResult(ok=False, gate=gate, reason=reason)


class LiveGateChain:
    """Pre-entry gates over account allocation, sizing, rate limits, and
    venue-error cooldowns. State that matters across restarts (order
    timestamps for rate limits) is intentionally conservative: a restart
    resets the window, but ``max_orders_per_day`` breaches were already
    audited, and the loss monitor's persistent state is the backstop."""

    def __init__(self, limits: LiveRiskLimits):
        self.limits = limits
        self._order_times: list[float] = []
        self._venue_errors: list[float] = []
        self._lock = threading.Lock()

    # --- event feeds ---------------------------------------------------------------

    def record_order(self, now: float | None = None) -> None:
        with self._lock:
            self._order_times.append(now if now is not None else time.time())

    def record_venue_error(self, now: float | None = None) -> None:
        with self._lock:
            self._venue_errors.append(now if now is not None else time.time())

    # --- the chain -------------------------------------------------------------------

    def check_entry(self, *, notional: float, equity: float,
                    open_notional: float, open_positions: int,
                    max_open_positions: int = 3,
                    risk_amount: float | None = None,
                    max_risk_pct: float = 1.0,
                    spread_bps: float | None = None,
                    now: float | None = None) -> GateResult:
        """All pre-entry gates, first failure wins. ``risk_amount`` is
        |entry - stop| * quantity when a stop exists (checked against
        ``max_risk_pct`` from the base RiskLimits — finally enforced);
        ``spread_bps`` when a live quote exists (no quote is the
        data-health gate's problem)."""
        now = now if now is not None else time.time()
        limits = self.limits

        if open_positions >= max_open_positions:
            # RiskLimits.max_open_positions finally enforced (gap 5)
            return GateResult.rejected(
                "live_max_positions",
                f"{open_positions} open positions at the limit "
                f"({max_open_positions})")

        if notional > limits.max_notional_per_trade:
            return GateResult.rejected(
                "live_notional_cap",
                f"notional {notional:.2f} exceeds max_notional_per_trade "
                f"{limits.max_notional_per_trade:.2f}")

        if equity > 0:
            allocation_pct = 100.0 * (open_notional + notional) / equity
            if allocation_pct > limits.live_max_account_allocation_pct:
                return GateResult.rejected(
                    "live_allocation",
                    f"total allocation {allocation_pct:.1f}% of equity would "
                    f"exceed {limits.live_max_account_allocation_pct}%")

        if risk_amount is not None and equity > 0:
            # RiskLimits.max_risk_per_trade_pct finally enforced here for
            # live capital: the stop distance bounds the worst-case loss
            risk_pct = 100.0 * risk_amount / equity
            if risk_pct > max_risk_pct:
                return GateResult.rejected(
                    "live_risk_per_trade",
                    f"stop-distance risk {risk_pct:.2f}% of equity exceeds "
                    f"{max_risk_pct}%")

        with self._lock:
            hour_ago, day_ago = now - 3600, now - 86400
            self._order_times = [t for t in self._order_times if t > day_ago]
            per_hour = sum(1 for t in self._order_times if t > hour_ago)
            if per_hour >= limits.max_orders_per_hour:
                return GateResult.rejected(
                    "live_rate_hourly",
                    f"{per_hour} orders in the last hour (max "
                    f"{limits.max_orders_per_hour})")
            if len(self._order_times) >= limits.max_orders_per_day:
                return GateResult.rejected(
                    "live_rate_daily",
                    f"{len(self._order_times)} orders in the last 24h (max "
                    f"{limits.max_orders_per_day})")

            window = now - limits.venue_error_cooldown_seconds
            self._venue_errors = [t for t in self._venue_errors if t > window]
            if len(self._venue_errors) >= limits.venue_error_burst_threshold:
                return GateResult.rejected(
                    "live_error_cooldown",
                    f"{len(self._venue_errors)} venue errors within "
                    f"{limits.venue_error_cooldown_seconds:.0f}s — cooling "
                    "down before new entries")

        if spread_bps is not None and spread_bps > limits.max_spread_bps:
            return GateResult.rejected(
                "live_spread",
                f"quoted spread {spread_bps:.1f}bps exceeds "
                f"{limits.max_spread_bps}bps")

        return GateResult.passed()


# --- loss limits with automatic halt ---------------------------------------------------


@dataclass
class LossLimitState:
    """Persisted across restarts — a breach must not be forgotten by a
    reboot, and the high-water mark is meaningless if it resets daily."""

    high_water_mark: float = 0.0
    day: str = ""            # ISO date the day anchor belongs to
    day_start_equity: float = 0.0
    week: str = ""           # ISO year-week
    week_start_equity: float = 0.0
    breached: str = ""       # non-empty = which limit tripped

    @classmethod
    def load(cls, path: Path) -> LossLimitState:
        import json

        try:
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return cls()
        except Exception:
            logger.warning("corrupt loss-limit state %s; starting fresh", path,
                           exc_info=True)
            return cls()

    def save(self, path: Path) -> None:
        from dataclasses import asdict

        from tradingagents.pro.persistence import atomic_write_json

        atomic_write_json(path, asdict(self))


class LossLimitMonitor:
    """Daily/weekly loss + drawdown-from-HWM against venue equity.

    ``evaluate`` runs on every fill and on a 1-minute timer. On breach it
    calls ``on_breach(reason)`` exactly once (the wiring cancels all
    orders, flattens, engages the kill switch, and alerts) and latches —
    only the manual re-arming ceremony clears it.
    """

    def __init__(self, limits: LiveRiskLimits, state_path: str | Path,
                 on_breach, alerts=None):
        self.limits = limits
        self._path = Path(state_path)
        self.state = LossLimitState.load(self._path)
        self._on_breach = on_breach
        self._alerts = alerts
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def breached(self) -> str:
        return self.state.breached

    def clear_breach(self, operator: str) -> None:
        """Only the arming ceremony calls this (Phase 4)."""
        if not operator:
            raise ValueError("operator identity required to clear a breach")
        with self._lock:
            self.state.breached = ""
            self.state.save(self._path)

    def evaluate(self, equity: float,
                 now: datetime | None = None) -> str | None:
        """Returns the breach reason when a limit trips (first time only)."""
        now = now or datetime.now(timezone.utc)
        with self._lock:
            state = self.state
            if state.breached:
                return None  # already latched; wiring already acted

            today = date(now.year, now.month, now.day).isoformat()
            week = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
            if state.day != today:
                state.day, state.day_start_equity = today, equity
            if state.week != week:
                state.week, state.week_start_equity = week, equity
            if equity > state.high_water_mark:
                state.high_water_mark = equity

            reason = self._check(equity, state)
            if reason:
                state.breached = reason
            state.save(self._path)
        if reason:
            logger.critical("loss limit breached: %s", reason)
            if self._alerts is not None:
                self._alerts.emit("critical", "loss_limit_breached", reason)
            self._on_breach(reason)
        return reason

    def _check(self, equity: float, state: LossLimitState) -> str | None:
        limits = self.limits
        if state.day_start_equity > 0:
            day_loss_pct = 100.0 * (state.day_start_equity - equity) \
                / state.day_start_equity
            if day_loss_pct >= limits.daily_loss_limit_pct:
                return (f"daily loss {day_loss_pct:.2f}% >= limit "
                        f"{limits.daily_loss_limit_pct}%")
        if state.week_start_equity > 0:
            week_loss_pct = 100.0 * (state.week_start_equity - equity) \
                / state.week_start_equity
            if week_loss_pct >= limits.weekly_loss_limit_pct:
                return (f"weekly loss {week_loss_pct:.2f}% >= limit "
                        f"{limits.weekly_loss_limit_pct}%")
        if state.high_water_mark > 0:
            drawdown_pct = 100.0 * (state.high_water_mark - equity) \
                / state.high_water_mark
            if drawdown_pct >= limits.max_drawdown_from_hwm_pct:
                return (f"drawdown {drawdown_pct:.2f}% from high-water mark "
                        f">= limit {limits.max_drawdown_from_hwm_pct}%")
        return None

    # --- timer ---------------------------------------------------------------------

    def start(self, equity_fn, interval: float = 60.0) -> None:
        if self._thread is not None:
            return
        self._stop.clear()

        def loop():
            while not self._stop.wait(interval):
                try:
                    self.evaluate(equity_fn())
                except Exception:
                    logger.exception("loss-limit tick failed; continuing")

        self._thread = threading.Thread(target=loop, daemon=True,
                                        name="loss-limit-monitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


def breach_response(oms, kill_switch, positions_fn, reference_prices):
    """Standard cancel-all + flatten-all + kill-switch response, shared by
    the loss monitor and the Phase-5 dead-man switch. ``reference_prices``
    maps symbol -> last known price for the reduce-only market closes."""

    def respond(reason: str) -> None:
        for order in list(oms.orders.values()):
            if order.sent and not order.state.terminal:
                try:
                    oms._apply(order,
                               oms.adapter.cancel_order(order.client_order_id))
                except Exception:
                    logger.exception("cancel during breach response failed")
        for position in positions_fn():
            try:
                oms.flatten_position(
                    symbol=position.symbol, quantity=position.quantity,
                    side=position.side,
                    reference_price=reference_prices.get(
                        position.symbol, position.avg_price),
                    reason=f"loss_limit:{reason}",
                )
            except Exception:
                logger.exception("flatten during breach response failed")
        kill_switch.engage(f"loss limit: {reason}")

    return respond
