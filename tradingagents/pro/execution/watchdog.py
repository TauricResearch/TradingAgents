"""Bracket watchdog: no naked positions (go-live Phase 2).

Enforces one invariant from two directions (the other is boot recovery's
protection check): a filled entry whose protective stop is not confirmed
within the deadline gets flattened immediately. Also emulates OCO for
synthetic brackets — a filled stop cancels the TPs and vice versa.

Deterministic in tests: call ``tick(now)`` directly. In live mode a
daemon thread ticks every second.
"""

from __future__ import annotations

import logging
import threading
import time

from tradingagents.pro.execution import ids
from tradingagents.pro.execution.interface import OrderState
from tradingagents.pro.execution.oms import OrderManager
from tradingagents.pro.execution.orders import ManagedOrder

logger = logging.getLogger(__name__)


class BracketWatchdog:
    def __init__(self, oms: OrderManager, alerts=None):
        self.oms = oms
        self.alerts = alerts
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # --- lifecycle -------------------------------------------------------------

    def start(self, interval: float = 1.0) -> None:
        if self._thread is not None:
            return
        self._stop.clear()

        def loop():
            while not self._stop.wait(interval):
                try:
                    self.tick(time.time())
                except Exception:
                    logger.exception("watchdog tick failed; continuing")

        self._thread = threading.Thread(target=loop, daemon=True,
                                        name="bracket-watchdog")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # --- the invariant -----------------------------------------------------------

    def tick(self, now: float) -> None:
        self.oms.poll()
        self._enforce_protection_deadlines(now)
        self._emulate_oco()

    def _enforce_protection_deadlines(self, now: float) -> None:
        for entry_coid, info in list(self.oms.pending_protection.items()):
            deadline = info["deadline"]
            entry = self.oms.orders.get(entry_coid)
            if entry is None or entry.state in (OrderState.REJECTED,
                                                OrderState.CANCELED,
                                                OrderState.ABANDONED):
                self.oms.pending_protection.pop(entry_coid, None)
                continue
            if self.oms.has_venue_protection(entry.spec.symbol):
                self.oms._confirm_protection(entry_coid)
                continue
            if now < deadline:
                continue
            if entry.filled_quantity <= 0:
                # nothing filled yet: no exposure, keep waiting one cycle
                info["deadline"] = now + 5.0
                continue
            logger.critical("stop not confirmed within deadline for %s — "
                            "flattening", entry_coid)
            # cancel any resting siblings (e.g. the TP) so nothing orphaned
            # stays working after the position is gone
            for sibling in list(self.oms.orders.values()):
                if (sibling.bracket_group == entry.bracket_group
                        and sibling.leg != ids.ENTRY
                        and sibling.sent and not sibling.state.terminal):
                    self.oms._apply(sibling, self.oms.adapter.cancel_order(
                        sibling.client_order_id))
            self.oms.flatten_position(
                symbol=entry.spec.symbol,
                quantity=entry.filled_quantity,
                side=entry.spec.side,
                reference_price=entry.avg_fill_price or entry.spec.reference_price,
                reason="watchdog:protection_deadline",
            )
            self.oms.pending_protection.pop(entry_coid, None)
            self.oms._audit("watchdog_flattened", {"entry": entry_coid})
            if self.alerts is not None:
                self.alerts.emit(
                    "critical", "watchdog_flattened",
                    f"protective stop unconfirmed for {entry.spec.symbol}; "
                    "position flattened", symbol=entry.spec.symbol,
                )

    def _emulate_oco(self) -> None:
        groups: dict[str, list[ManagedOrder]] = {}
        for order in self.oms.orders.values():
            if order.bracket_group:
                groups.setdefault(order.bracket_group, []).append(order)
        for members in groups.values():
            protections = [o for o in members if o.leg != ids.ENTRY]
            filled_exit = next(
                (o for o in protections if o.state is OrderState.FILLED), None)
            if filled_exit is None:
                continue
            for sibling in protections:
                if sibling is filled_exit or sibling.state.terminal:
                    continue
                update = self.oms.adapter.cancel_order(
                    sibling.client_order_id)
                self.oms._apply(sibling, update)
