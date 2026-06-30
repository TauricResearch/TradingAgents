"""GuardedBroker — wraps any Broker and runs the rule chain on every order.

This is the only Broker callers ever see outside the broker package. The
inner broker is private to GuardedBroker; this is how we guarantee guardrails
cannot be bypassed."""
from __future__ import annotations

from decimal import Decimal

from ops.broker.base import Broker, OrderRejected
from ops.broker.types import Fill, Order, Position
from ops.config import OpsConfig
from ops.guardrails.base import RuleContext
from ops.guardrails.engine import RuleEngine
from ops.journal import Journal


class GuardedBroker(Broker):
    def __init__(self, *, inner: Broker, engine: RuleEngine, journal: Journal, config: OpsConfig):
        self._inner = inner
        self._engine = engine
        self._journal = journal
        self._config = config

    def get_cash(self) -> Decimal:
        return self._inner.get_cash()

    def get_equity(self) -> Decimal:
        return self._inner.get_equity()

    def get_positions(self) -> list[Position]:
        return self._inner.get_positions()

    def get_quote(self, symbol: str) -> Decimal:
        return self._inner.get_quote(symbol)

    def place_order(self, order: Order) -> Fill:
        ctx = RuleContext(order=order, broker=self._inner, config=self._config)
        result = self._engine.evaluate(ctx)
        if not result.allowed:
            self._journal.record_event(
                "order_rejected",
                {
                    "rule": result.failed_rule_name,
                    "reason": result.reason,
                    "client_order_id": order.client_order_id,
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "notional_dollars": str(order.notional_dollars),
                },
            )
            raise OrderRejected(result.failed_rule_name, result.reason)
        return self._inner.place_order(order)
