"""ExecutionRouter: the only sanctioned path from recommendation to venue.

Order of gates (each step audited):
validate -> kill switch -> circuit breaker -> idempotent submit with
bounded retries. Reconciliation compares the router's book against what
the adapter reports — drift is surfaced, never silently adopted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from tradingagents.contracts import RiskLimits, TradeRecommendation
from tradingagents.pro.execution.audit import AuditLog
from tradingagents.pro.execution.interface import (
    AdapterError,
    ExecutionAdapter,
    OrderRequest,
    OrderResult,
)
from tradingagents.pro.execution.safety import CircuitBreaker, KillSwitch
from tradingagents.pro.execution.validation import validate_recommendation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciliationReport:
    in_sync: bool
    missing_on_venue: tuple[str, ...] = ()
    unknown_on_venue: tuple[str, ...] = ()
    quantity_mismatches: tuple[str, ...] = ()


@dataclass
class ExecutionRouter:
    adapter: ExecutionAdapter
    limits: RiskLimits
    kill_switch: KillSwitch
    breaker: CircuitBreaker
    audit: AuditLog
    max_retries: int = 2
    local_book: dict[str, float] = field(default_factory=dict)  # symbol -> signed qty
    # go-live Phase 2: when an OrderManager is injected, submissions run
    # through the journaled OMS path (write-ahead, resolve-by-coid,
    # brackets). None = the original synchronous path, unchanged.
    oms = None
    protection_mode: str = "bar_close"  # "venue_bracket" for live wiring
    # go-live Phase 3: LiveGateChain when real capital is armed; None =
    # paper behavior unchanged.
    live_gates = None
    # go-live Phase 6 staged rollout: per-pair mode routing. ``arming``
    # decides the tier; ``live_oms`` (an OrderManager over the live venue
    # adapter) is where canary/live orders go; ``shadow_tracker`` records
    # would-have-been live fills for shadow-mode paper fills. All None =
    # every order stays on the paper venue, exactly as before.
    arming = None
    live_oms = None
    shadow_tracker = None

    def tier_for(self, symbol: str) -> str:
        if self.arming is None:
            return "paper"
        try:
            return self.arming.effective_tier(symbol)
        except Exception:
            return "paper"

    def omses(self) -> list:
        return [o for o in (self.oms, self.live_oms) if o is not None]

    def submit_recommendation(
        self, rec: TradeRecommendation | None, equity: float,
        spread_bps: float | None = None,
    ) -> OrderResult:
        tier = self.tier_for(getattr(rec, "symbol", ""))
        route_live = tier in ("canary", "live") and self.live_oms is not None
        self.audit.append("order_received", {
            "recommendation_id": getattr(rec, "id", None),
            "symbol": getattr(rec, "symbol", None),
            "action": getattr(rec, "action", None) and rec.action.value,
            "tier": tier,
            "route": "live" if route_live else "paper",
        })

        # a pair armed at a live tier with no live venue wired is REFUSED,
        # never silently paper-filled — the operator believes real capital
        # is working; pretending would be a lie (Phase 6)
        if tier in ("canary", "live") and self.live_oms is None:
            return self._refuse(
                rec, "live_route_unavailable",
                f"pair armed '{tier}' but no live venue is wired — refusing "
                "rather than silently filling on paper")

        # leading gate (OMS wiring only): a process that has not accounted
        # for its outstanding orders does not trade
        entry_oms = self.live_oms if route_live else self.oms
        if entry_oms is not None and not entry_oms.recovered:
            return self._refuse(rec, "oms_not_recovered",
                                "boot recovery has not completed")

        if route_live:
            # gates measure against the venue that will hold the risk
            try:
                equity = self.live_oms.adapter.account().equity
            except Exception as exc:
                return self._refuse(rec, "live_venue_unreachable", str(exc))
            if tier == "canary":
                # canary sizes to the venue minimum BEFORE validation —
                # the gates judge the order that will actually be placed
                sized = self._canary_sized(rec)
                if sized is None:
                    return self._refuse(
                        rec, "canary_sizing",
                        "venue minimum size unavailable for canary")
                rec = sized

        supported = (
            self.adapter.supported_symbols()
            if hasattr(self.adapter, "supported_symbols")
            else {getattr(rec, "symbol", "")}
        )
        check = validate_recommendation(rec, self.limits, equity, supported)
        if not check.ok:
            return self._refuse(rec, "validation_failed", "; ".join(check.reasons))

        if self.kill_switch.engaged:
            return self._refuse(rec, "kill_switch",
                                self.kill_switch.reason or "kill switch engaged")

        breaker = self.breaker.check()
        if breaker.tripped:
            return self._refuse(rec, "circuit_breaker", breaker.reason)

        if self.live_gates is not None:
            gate = self._check_live_gates(rec, equity, spread_bps)
            if not gate.ok:
                return self._refuse(rec, gate.gate, gate.reason)

        if route_live:
            return self._submit_via_oms(rec, oms=self.live_oms, tier=tier)

        if self.oms is not None:
            result = self._submit_via_oms(rec, oms=self.oms, tier=tier)
            self._maybe_shadow(rec, tier, result)
            return result

        order = OrderRequest(
            idempotency_key=rec.id,
            symbol=rec.symbol,
            side=rec.action.value,
            quantity=rec.position_size.quantity,
            reference_price=rec.entry_price,
            stop_loss=rec.stop_loss,
            take_profits=tuple(tp.price for tp in rec.take_profits),
        )
        result = self._submit_with_retries(order)
        self.audit.append("order_result", {
            "recommendation_id": rec.id,
            "status": result.status,
            "fill_price": result.fill_price,
            "filled_quantity": result.filled_quantity,
            "venue": result.venue,
            "reason": result.reason,
        })
        if result.status == "filled":
            sign = 1 if order.side == "BUY" else -1
            self.local_book[order.symbol] = (
                self.local_book.get(order.symbol, 0.0) + sign * result.filled_quantity
            )
        self._maybe_shadow(rec, tier, result)
        return result

    def _canary_sized(self, rec):
        """A copy of the recommendation resized to the live venue's minimum
        viable size — canary proves the pipe with the smallest real order."""
        try:
            info = self.live_oms.adapter.instruments.get(rec.symbol)
            quantity = min(rec.position_size.quantity,
                           info.to_quantity(info.min_contracts))
            if quantity <= 0:
                return None
            return rec.model_copy(update={
                "position_size": rec.position_size.model_copy(update={
                    "quantity": quantity,
                    "notional": quantity * rec.entry_price,
                }),
            })
        except Exception:
            logger.exception("canary sizing failed")
            return None

    def _maybe_shadow(self, rec, tier: str, result: OrderResult) -> None:
        """Shadow mode: after a PAPER fill, record the would-have-been live
        fill so paper-vs-live divergence is measured (Phase 6)."""
        if (tier != "shadow" or self.shadow_tracker is None
                or result.status != "filled"):
            return
        try:
            self.shadow_tracker.record(
                symbol=rec.symbol, side=rec.action.value,
                quantity=result.filled_quantity,
                paper_fill_price=result.fill_price,
            )
        except Exception:
            logger.exception("shadow fill recording failed; continuing")

    def record_close(self, symbol: str, pnl: float) -> None:
        """Called by the position manager when a trade closes; feeds the
        breaker and clears the local book entry."""
        self.local_book.pop(symbol, None)
        self.breaker.record_trade_result(pnl)
        self.audit.append("position_closed", {"symbol": symbol, "pnl": pnl})
        state = self.breaker.check()
        if state.tripped:
            self.audit.append("circuit_breaker_tripped", {"reason": state.reason})

    def reconcile(self) -> ReconciliationReport:
        # Phase 6: a symbol holds risk on exactly one venue at a time
        # (its tier decides), so the truth set is the union of venues
        venue_positions = {p.symbol: p for p in self.adapter.positions()}
        if self.live_oms is not None:
            try:
                for p in self.live_oms.adapter.positions():
                    venue_positions[p.symbol] = p
            except Exception:
                logger.warning("live venue unreachable during reconcile; "
                               "its positions are missing from this pass",
                               exc_info=True)
        missing, unknown, mismatched = [], [], []
        for symbol, local_quantity in self.local_book.items():
            venue_position = venue_positions.get(symbol)
            if venue_position is None:
                missing.append(symbol)
                continue
            venue_signed = (
                venue_position.quantity
                if venue_position.side == "BUY"
                else -venue_position.quantity
            )
            if abs(venue_signed - local_quantity) > 1e-9:
                mismatched.append(
                    f"{symbol}: local {local_quantity} vs venue {venue_signed}"
                )
        for symbol in venue_positions:
            if symbol not in self.local_book:
                unknown.append(symbol)
        report = ReconciliationReport(
            in_sync=not (missing or unknown or mismatched),
            missing_on_venue=tuple(missing),
            unknown_on_venue=tuple(unknown),
            quantity_mismatches=tuple(mismatched),
        )
        self.audit.append("reconciliation", {
            "in_sync": report.in_sync,
            "missing_on_venue": list(report.missing_on_venue),
            "unknown_on_venue": list(report.unknown_on_venue),
            "quantity_mismatches": list(report.quantity_mismatches),
        })
        return report

    # --- internals -----------------------------------------------------------

    def _check_live_gates(self, rec, equity: float, spread_bps: float | None):
        """Live-capital gates (Phase 3): account allocation, sizing, rate
        limits, error cooldowns — after the breaker, before any order."""
        notional = rec.position_size.quantity * rec.entry_price
        open_notional = sum(
            p.quantity * p.avg_price for p in self.adapter.positions()
        )
        risk_amount = (abs(rec.entry_price - rec.stop_loss)
                       * rec.position_size.quantity
                       if rec.stop_loss is not None else None)
        return self.live_gates.check_entry(
            notional=notional, equity=equity,
            open_notional=open_notional,
            open_positions=len(self.local_book),
            max_open_positions=self.limits.max_open_positions,
            risk_amount=risk_amount,
            max_risk_pct=self.limits.max_risk_per_trade_pct,
            spread_bps=spread_bps,
        )

    def _submit_via_oms(self, rec: TradeRecommendation, oms=None,
                        tier: str = "paper") -> OrderResult:
        """Phase-2 path: deterministic plan -> journaled OMS execution.
        Phase 6: ``oms`` selects the venue (paper vs live); canary clamps
        the quantity to the venue minimum and live tiers use venue-side
        bracket protection."""
        from tradingagents.pro.execution import ids
        from tradingagents.pro.execution.interface import BracketSpec, OrderState
        from tradingagents.pro.execution.orders import ExecutionPlan

        oms = oms if oms is not None else self.oms
        route_live = tier in ("canary", "live") and oms is self.live_oms
        quantity = rec.position_size.quantity  # canary already sized upstream

        bracket = None
        if rec.stop_loss is not None:
            bracket = BracketSpec(
                stop_loss_price=rec.stop_loss,
                take_profits=tuple((tp.price, tp.size_fraction)
                                   for tp in rec.take_profits),
            )
        order_type, limit_price = "market", None
        if self.live_gates is not None:
            limits = self.live_gates.limits
            notional = quantity * rec.entry_price
            if notional > limits.market_order_notional_cap:
                # Phase 3: big orders never cross the book unbounded —
                # limit at reference +/- max_cross_bps tolerance
                cross = limits.max_cross_bps / 10_000.0
                sign = 1 if rec.action.value == "BUY" else -1
                order_type = "limit"
                limit_price = rec.entry_price * (1 + sign * cross)
        plan = ExecutionPlan(
            run_id=rec.id,
            decision_hash=ids.decision_hash(rec),
            symbol=rec.symbol,
            side=rec.action.value,
            quantity=quantity,
            reference_price=rec.entry_price,
            bracket=bracket,
            protection_mode="venue_bracket" if route_live
            else self.protection_mode,
            order_type=order_type,
            limit_price=limit_price,
        )
        order = oms.execute(plan)
        if (self.live_gates is not None
                and order.state not in (OrderState.REJECTED,
                                        OrderState.ABANDONED)):
            self.live_gates.record_order()  # rate-limit accounting
        status = {
            OrderState.FILLED: "filled",
            OrderState.REJECTED: "rejected",
            OrderState.ABANDONED: "rejected",
            OrderState.CANCELED: "rejected",
        }.get(order.state, "submitted")
        result = OrderResult(
            status=status, idempotency_key=rec.id,
            venue=oms.adapter.name, venue_symbol=order.spec.venue_symbol,
            filled_quantity=order.filled_quantity,
            fill_price=order.avg_fill_price,
            commission=order.commission,
            reason=order.reason,
        )
        self.audit.append("order_result", {
            "recommendation_id": rec.id,
            "status": result.status,
            "fill_price": result.fill_price,
            "filled_quantity": result.filled_quantity,
            "venue": result.venue,
            "reason": result.reason,
        })
        if result.status == "filled":
            sign = 1 if rec.action.value == "BUY" else -1
            self.local_book[rec.symbol] = (
                self.local_book.get(rec.symbol, 0.0)
                + sign * result.filled_quantity
            )
        return result

    def apply_closed_trades(self) -> list:
        """Consume OMS-detected exits (venue-side stops/TPs/flattens) into
        the same book/breaker path bar-close exits use."""
        if self.oms is None:
            return []
        closed = self.oms.drain_closed()
        for trade in closed:
            self.record_close(trade.symbol, trade.pnl)
        return closed

    def _refuse(self, rec, stage: str, reason: str) -> OrderResult:
        self.audit.append(stage, {
            "recommendation_id": getattr(rec, "id", None), "reason": reason,
        })
        return OrderResult(
            status="rejected",
            idempotency_key=getattr(rec, "id", "n/a"),
            venue=self.adapter.name,
            reason=f"{stage}: {reason}",
        )

    def _submit_with_retries(self, order: OrderRequest) -> OrderResult:
        last_error: Exception | None = None
        for attempt in range(1 + self.max_retries):
            try:
                return self.adapter.submit(order)
            except AdapterError as exc:
                last_error = exc
                self.audit.append("submit_retry", {
                    "idempotency_key": order.idempotency_key,
                    "attempt": attempt + 1,
                    "error": str(exc),
                })
        return OrderResult(
            status="rejected", idempotency_key=order.idempotency_key,
            venue=self.adapter.name,
            reason=f"adapter failed after {1 + self.max_retries} attempts: {last_error}",
        )
