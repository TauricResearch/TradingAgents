"""Dead-man switch — layer (c) of the three-layer kill switch (Phase 5).

Layers (a) automated risk triggers and (b) the manual/file kill switch
already exist. This is the third: if the system can't confirm its own
health for ``timeout_seconds``, assume the operator is blind and the loop
may be wedged, and **cancel all resting orders** so nothing keeps working
unattended. Per the spec it does NOT flatten open positions — those keep
their venue-side protective stops; it removes only the un-triggered
resting orders that could fire while no one is watching.

Same lifecycle as ``BracketWatchdog``/``LossLimitMonitor``: a daemon
thread, or ``tick(now)`` synchronously in tests. Only started when a pair
is live-armed.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)


class DeadManSwitch:
    def __init__(self, health_fn, on_trip, timeout_seconds: float = 600.0,
                 alerts=None, now=time.time):
        self._health_fn = health_fn      # () -> HealthReport (has .ok)
        self._on_trip = on_trip          # (reason: str) -> None
        self.timeout = timeout_seconds
        self._alerts = alerts
        self._now = now
        self._last_ok = now()
        self._tripped = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def tripped(self) -> bool:
        return self._tripped

    def tick(self, now: float | None = None) -> bool:
        """One check. Refreshes the heartbeat on a healthy verdict; trips
        (once) when the heartbeat is older than the timeout. Returns True
        on the tick that trips."""
        now = now if now is not None else self._now()
        try:
            healthy = self._health_fn().ok
        except Exception:
            healthy = False  # can't confirm health = not healthy
        if healthy:
            self._last_ok = now
            return False
        if self._tripped:
            return False
        if now - self._last_ok < self.timeout:
            return False
        self._tripped = True
        reason = (f"health unconfirmed for {now - self._last_ok:.0f}s "
                  f"(timeout {self.timeout:.0f}s)")
        logger.critical("dead-man switch tripped: %s", reason)
        try:
            self._on_trip(reason)
        finally:
            if self._alerts is not None:
                self._alerts.emit("critical", "deadman_tripped",
                                  f"dead-man switch: {reason}; resting orders "
                                  "cancelled")
        return True

    def reset(self, now: float | None = None) -> None:
        self._tripped = False
        self._last_ok = now if now is not None else self._now()

    def start(self, interval: float = 30.0) -> None:
        if self._thread is not None:
            return
        self._stop.clear()

        def loop():
            while not self._stop.wait(interval):
                try:
                    self.tick()
                except Exception:
                    logger.exception("dead-man tick failed; continuing")

        self._thread = threading.Thread(target=loop, daemon=True,
                                        name="dead-man-switch")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


def cancel_resting_orders(router):
    """Cancel every resting (non-terminal) order without touching open
    positions — the dead-man's on_trip action. Reuses the OMS cancel path
    when present, else no-ops (paper adapter fills terminally)."""

    def respond(reason: str) -> None:
        oms = getattr(router, "oms", None)
        cancelled = []
        if oms is not None:
            for order in list(oms.orders.values()):
                if order.sent and not order.state.terminal:
                    try:
                        oms._apply(order, router.adapter.cancel_order(
                            order.client_order_id))
                        cancelled.append(order.client_order_id)
                    except Exception:
                        logger.exception("dead-man cancel failed")
        router.kill_switch.engage(f"dead-man: {reason}")
        router.audit.append("deadman_tripped",
                            {"reason": reason, "cancelled": cancelled})

    return respond
