"""Order Management System (go-live Phase 2).

Sits between the router's deterministic gates and the venue adapter.
Owns: write-ahead journaling, the order state machine, resolve-by-coid
for UNKNOWN outcomes, bracket orchestration (native or synthetic +
watchdog), blocking reconcile-on-boot, and realized-exit detection.

The OMS never sees LLM output — only ``ExecutionPlan`` objects the router
built from an already-gated recommendation. Paper and live run the SAME
code path: the paper adapter simply goes terminal inside ``place_order``,
so every paper test run exercises the recovery machinery too.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tradingagents.pro.execution import ids
from tradingagents.pro.execution.interface import (
    AdapterError,
    BracketSpec,
    OrderSpec,
    OrderState,
    OrderUpdate,
)
from tradingagents.pro.execution.journal import OrderJournal
from tradingagents.pro.execution.orders import (
    ClosedTrade,
    ExecutionPlan,
    IllegalTransition,
    ManagedOrder,
)

logger = logging.getLogger(__name__)


class RecoveryFailed(Exception):
    """Boot recovery could not account for every order — trading refused."""


class OrderManager:
    def __init__(self, adapter, journal: OrderJournal | None = None,
                 journal_path: str | Path | None = None,
                 audit=None, max_resolve_retries: int = 2,
                 protection_deadline_seconds: float = 10.0):
        self.adapter = adapter
        self.journal = journal or OrderJournal(journal_path)
        self.audit = audit
        self.max_resolve_retries = max_resolve_retries
        self.protection_deadline = protection_deadline_seconds
        self.orders: dict[str, ManagedOrder] = {}
        # entry coid -> {"deadline": ts, "plan": serialized ExecutionPlan}
        self.pending_protection: dict[str, dict] = {}
        self._closed: list[ClosedTrade] = []
        self.recovered = False

    # --- helpers ---------------------------------------------------------------

    def _audit(self, event: str, payload: dict) -> None:
        if self.audit is not None:
            self.audit.append(event, payload)

    def _apply(self, order: ManagedOrder, update: OrderUpdate) -> None:
        before = order.state
        try:
            changed = order.apply(update)
        except IllegalTransition as exc:
            self._audit("oms_illegal_transition", {"error": str(exc)})
            logger.error("illegal transition ignored: %s", exc)
            return
        if changed and order.state != before:
            self.journal.transition(order, before)

    def _terminal_result_reason(self, order: ManagedOrder) -> str:
        return order.reason or order.state.value

    # --- submit path -------------------------------------------------------------

    def execute(self, plan: ExecutionPlan) -> ManagedOrder:
        """Place the entry (with native bracket when supported). Returns the
        entry ManagedOrder in its furthest known state."""
        if not self.recovered:
            raise RecoveryFailed("OMS has not completed boot recovery")
        capabilities = self.adapter.capabilities()
        use_native = (plan.bracket is not None
                      and plan.protection_mode == "venue_bracket"
                      and capabilities.native_bracket)
        coid = ids.client_order_id(plan.run_id, plan.decision_hash, ids.ENTRY)
        existing = self.orders.get(coid)
        if existing is not None:
            return existing  # deterministic id: same decision = same order
        spec = OrderSpec(
            client_order_id=coid, symbol=plan.symbol, venue_symbol="",
            side=plan.side, quantity=plan.quantity,
            reference_price=plan.reference_price,
        )
        order = ManagedOrder(spec=spec, leg=ids.ENTRY,
                             bracket_group=plan.decision_hash[:16])
        self.orders[coid] = order
        self.journal.intent(order)                       # WAL point 1 (fsync)
        self.journal.submitting(coid)
        order.sent = True
        update = self._place_with_resolve(
            spec, plan.bracket if use_native else None)
        self._apply(order, update)

        if (plan.bracket is not None and not use_native
                and plan.protection_mode == "venue_bracket"):
            # synthetic bracket: protection must exist within the deadline
            deadline = time.time() + self.protection_deadline
            self.pending_protection[coid] = {"deadline": deadline,
                                             "plan": _plan_to_json(plan)}
            self.journal.protection_pending(coid, deadline,
                                            plan=_plan_to_json(plan))
            if order.filled_quantity > 0:
                self._place_protection(order, plan)
        return order

    def _place_with_resolve(self, spec: OrderSpec,
                            bracket: BracketSpec | None) -> OrderUpdate:
        """One send; on transport uncertainty, resolve by coid (venue-side
        dedupe makes same-coid resubmits safe)."""
        for attempt in range(1 + self.max_resolve_retries):
            try:
                return self.adapter.place_order(spec, bracket)
            except AdapterError as exc:
                self._audit("submit_retry", {
                    "idempotency_key": spec.client_order_id,
                    "attempt": attempt + 1, "error": str(exc),
                })
                resolved = self._lookup(spec.client_order_id)
                if resolved is not None:
                    return resolved  # the send actually landed
                # provably not on the venue -> safe to resend same coid
        return OrderUpdate(client_order_id=spec.client_order_id,
                           state=OrderState.REJECTED,
                           reason="unresolvable after retry budget")

    def _lookup(self, coid: str) -> OrderUpdate | None:
        try:
            return self.adapter.get_order(coid)
        except AdapterError:
            return None

    # --- synthetic protection ------------------------------------------------------

    def _place_protection(self, entry: ManagedOrder, plan: ExecutionPlan) -> None:
        assert plan.bracket is not None
        exit_side = "SELL" if plan.side == "BUY" else "BUY"
        stop_coid = ids.client_order_id(plan.run_id, plan.decision_hash,
                                        ids.STOP)
        if stop_coid not in self.orders:
            stop_spec = OrderSpec(
                client_order_id=stop_coid, symbol=plan.symbol,
                venue_symbol="", side=exit_side,
                quantity=entry.filled_quantity or plan.quantity,
                order_type="limit",
                limit_price=plan.bracket.stop_loss_price,
                reduce_only=True,
                reference_price=plan.bracket.stop_loss_price,
            )
            stop = ManagedOrder(spec=stop_spec, leg=ids.STOP,
                                bracket_group=entry.bracket_group)
            self.orders[stop_coid] = stop
            self.journal.intent(stop)
            self.journal.submitting(stop_coid)
            stop.sent = True
            self._apply(stop, self._place_with_resolve(stop_spec, None))
            if stop.state in (OrderState.ACKED, OrderState.SUBMITTED,
                              OrderState.FILLED):
                self._confirm_protection(entry.client_order_id)
            elif stop.state is OrderState.REJECTED:
                logger.error("protective stop REJECTED for %s: %s",
                             entry.client_order_id, stop.reason)

        # final take-profit (same exit semantics as the paper engine: one
        # exit at the FINAL target); OCO emulation cancels the sibling
        if plan.bracket.take_profits:
            tp_price = plan.bracket.take_profits[-1][0]
            tp_coid = ids.client_order_id(plan.run_id, plan.decision_hash,
                                          ids.take_profit_leg(0))
            if tp_coid not in self.orders:
                tp_spec = OrderSpec(
                    client_order_id=tp_coid, symbol=plan.symbol,
                    venue_symbol="", side=exit_side,
                    quantity=entry.filled_quantity or plan.quantity,
                    order_type="limit", limit_price=tp_price,
                    reduce_only=True, reference_price=tp_price,
                )
                tp = ManagedOrder(spec=tp_spec, leg=ids.take_profit_leg(0),
                                  bracket_group=entry.bracket_group)
                self.orders[tp_coid] = tp
                self.journal.intent(tp)
                self.journal.submitting(tp_coid)
                tp.sent = True
                self._apply(tp, self._place_with_resolve(tp_spec, None))

    def _confirm_protection(self, entry_coid: str) -> None:
        if entry_coid in self.pending_protection:
            del self.pending_protection[entry_coid]
            self.journal.protection_confirmed(entry_coid)
            self._audit("protection_confirmed", {"entry": entry_coid})

    def has_venue_protection(self, symbol: str) -> bool:
        """True when this symbol's open position is protected venue-side
        (native bracket or a working synthetic stop)."""
        for order in self.orders.values():
            if (order.leg == ids.STOP and order.spec.symbol == symbol
                    and not order.state.terminal):
                return True
        return False

    # --- flatten ---------------------------------------------------------------------

    def flatten_position(self, symbol: str, quantity: float, side: str,
                         reference_price: float, reason: str) -> ManagedOrder:
        """Reduce-only market close, journaled like everything else."""
        exit_side = "SELL" if side == "BUY" else "BUY"
        coid = ids.client_order_id("flatten", f"{symbol}-{time.time():.0f}",
                                   ids.FLATTEN)
        spec = OrderSpec(client_order_id=coid, symbol=symbol, venue_symbol="",
                         side=exit_side, quantity=quantity, reduce_only=True,
                         reference_price=reference_price)
        order = ManagedOrder(spec=spec, leg=ids.FLATTEN, reason=reason)
        self.orders[coid] = order
        self.journal.intent(order)
        self.journal.submitting(coid)
        order.sent = True
        self._apply(order, self._place_with_resolve(spec, None))
        self._audit("oms_flatten", {"symbol": symbol, "reason": reason,
                                    "state": order.state.value})
        return order

    # --- polling / exits ---------------------------------------------------------------

    def poll(self) -> None:
        """Absorb venue updates for every non-terminal order."""
        open_orders = [o for o in self.orders.values()
                       if o.sent and not o.state.terminal]
        if not open_orders:
            return
        since = min(o.spec.created_at for o in open_orders) - timedelta(minutes=1)
        try:
            updates = {u.client_order_id: u
                       for u in self.adapter.poll_updates(since)}
        except AdapterError as exc:
            logger.warning("poll failed: %s", exc)
            return
        for order in open_orders:
            update = updates.get(order.client_order_id)
            if update is not None:
                self._apply(order, update)
                if order.state is OrderState.FILLED and order.leg != ids.ENTRY:
                    self._record_exit(order)
        self._ensure_protection()

    def _ensure_protection(self) -> None:
        """Entries that filled asynchronously get their synthetic protection
        placed here (execute() only covers synchronous fills)."""
        for entry_coid, info in list(self.pending_protection.items()):
            entry = self.orders.get(entry_coid)
            if entry is None or entry.filled_quantity <= 0:
                continue
            plan = _plan_from_json(info.get("plan", {}))
            if plan is not None:
                self._place_protection(entry, plan)

    def _record_exit(self, order: ManagedOrder) -> None:
        entry = next(
            (o for o in self.orders.values()
             if o.bracket_group == order.bracket_group and o.leg == ids.ENTRY),
            None,
        )
        entry_price = entry.avg_fill_price if entry else 0.0
        sign = 1 if (entry and entry.spec.side == "BUY") else -1
        pnl = sign * (order.avg_fill_price - entry_price) * order.filled_quantity
        self._closed.append(ClosedTrade(
            symbol=order.spec.symbol, quantity=order.filled_quantity,
            entry_price=entry_price, exit_price=order.avg_fill_price,
            pnl=pnl - order.commission - (entry.commission if entry else 0.0),
            commission=order.commission,
            reason={"sl": "stop_loss", "flatten": "flatten"}.get(
                order.leg, "take_profit"),
            client_order_id=order.client_order_id,
        ))

    def drain_closed(self) -> list[ClosedTrade]:
        closed, self._closed = self._closed, []
        return closed

    # --- boot recovery --------------------------------------------------------------

    def recover(self, max_attempts: int = 3) -> None:
        """Mandatory, blocking: resolve every non-terminal journaled order
        against the venue before anything may trade. Venue unreachable =
        startup fails — a process that cannot account for its orders does
        not trade."""
        self.orders, self.pending_protection = self.journal.replay()
        unresolved = [o for o in self.orders.values() if not o.state.terminal]
        for order in unresolved:
            if not order.sent:
                # journaled intent, provably never sent
                before = order.state
                order.state = OrderState.ABANDONED
                order.reason = "intent journaled but never sent"
                self.journal.transition(order, before)
                self._audit("oms_abandoned", {"coid": order.client_order_id})
                continue
            resolved: OrderUpdate | None = None
            last_error: Exception | None = None
            for _ in range(max_attempts):
                try:
                    resolved = self.adapter.get_order(order.client_order_id)
                    last_error = None
                    break
                except AdapterError as exc:
                    last_error = exc
                    time.sleep(0.2)
            if last_error is not None:
                raise RecoveryFailed(
                    f"venue unreachable while resolving "
                    f"{order.client_order_id}: {last_error}"
                )
            before = order.state
            if resolved is None:
                order.state = OrderState.REJECTED
                order.reason = "not found on venue after submit"
                self.journal.transition(order, before)
            else:
                self._apply(order, resolved)
                if order.state is OrderState.FILLED and order.leg != ids.ENTRY:
                    self._record_exit(order)
        # protection invariant: every pending_protection entry either has a
        # working stop now, or the watchdog flattens on its next tick
        self.recovered = True
        self._audit("oms_recovered", {
            "orders": len(self.orders),
            "pending_protection": len(self.pending_protection),
        })

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


def _plan_to_json(plan: ExecutionPlan) -> dict:
    from dataclasses import asdict

    return asdict(plan)


def _plan_from_json(data: dict) -> ExecutionPlan | None:
    if not data:
        return None
    payload = dict(data)
    bracket = payload.get("bracket")
    if bracket is not None:
        payload["bracket"] = BracketSpec(
            stop_loss_price=bracket["stop_loss_price"],
            take_profits=tuple(tuple(tp) for tp in bracket["take_profits"]),
            stop_trigger=bracket.get("stop_trigger", "mark"),
        )
    return ExecutionPlan(**payload)
