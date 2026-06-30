from decimal import Decimal
from unittest.mock import MagicMock
from ops.broker.types import Order, Side, OrderType
from ops.config import OpsConfig
from ops.guardrails.base import Rule, RuleContext, RuleResult
from ops.guardrails.engine import RuleEngine


class _AlwaysAllow(Rule):
    def check(self, ctx): return RuleResult.allow()


class _AlwaysReject(Rule):
    def __init__(self, label: str): self._label = label
    @property
    def name(self): return f"Reject_{self._label}"
    def check(self, ctx): return RuleResult.reject(f"rejected by {self._label}")


def _ctx() -> RuleContext:
    o = Order(
        client_order_id="c", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    )
    return RuleContext(order=o, broker=MagicMock(), config=OpsConfig())


def test_engine_passes_when_all_allow():
    eng = RuleEngine([_AlwaysAllow(), _AlwaysAllow()])
    result = eng.evaluate(_ctx())
    assert result.allowed is True


def test_engine_short_circuits_on_first_failure():
    second = _AlwaysReject("B")
    eng = RuleEngine([_AlwaysAllow(), _AlwaysReject("A"), second])
    result = eng.evaluate(_ctx())
    assert result.allowed is False
    assert "rejected by A" in result.reason
    assert result.failed_rule_name == "Reject_A"
