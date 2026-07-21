from decimal import Decimal
import pytest
from ops.broker.base import OrderRejected
from ops.broker.guarded import GuardedBroker
from ops.broker.paper import PaperBroker
from ops.broker.types import Order, Side, OrderType
from ops.config import OpsConfig
from ops.guardrails.base import Rule, RuleContext, RuleResult
from ops.guardrails.engine import RuleEngine
from ops.journal import Journal


class _RejectSymbol(Rule):
    def __init__(self, symbol): self._sym = symbol
    @property
    def name(self): return "RejectSymbol"
    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.symbol == self._sym:
            return RuleResult.reject(f"reject {self._sym}")
        return RuleResult.allow()


def _stack(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    paper = PaperBroker(journal=j, quote_source=lambda s: Decimal("200"),
                       starting_cash=Decimal("250"))
    engine = RuleEngine([_RejectSymbol("BANNED")])
    return j, paper, GuardedBroker(inner=paper, engine=engine, journal=j, config=OpsConfig())


def test_guarded_allows_passing_order(tmp_path):
    j, paper, guarded = _stack(tmp_path)
    fill = guarded.place_order(Order(
        client_order_id="c1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    ))
    assert fill.symbol == "AAPL"
    assert paper.get_positions()[0].symbol == "AAPL"


def test_guarded_rejects_and_journals_rejection(tmp_path):
    j, paper, guarded = _stack(tmp_path)
    with pytest.raises(OrderRejected) as exc:
        guarded.place_order(Order(
            client_order_id="c1", symbol="BANNED", side=Side.BUY,
            notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
            stop_loss_price=Decimal("184"),
        ))
    assert exc.value.rule_name == "RejectSymbol"
    # Inner broker was not touched
    assert paper.get_positions() == []
    assert paper.get_cash() == Decimal("250")
    # The rejection event is in the journal
    events = j.read_events()
    rejections = [e for e in events if e["kind"] == "order_rejected"]
    assert len(rejections) == 1
    assert rejections[0]["payload"]["rule"] == "RejectSymbol"
    assert rejections[0]["payload"]["symbol"] == "BANNED"


def test_guarded_passes_through_read_methods(tmp_path):
    _, paper, guarded = _stack(tmp_path)
    assert guarded.get_cash() == paper.get_cash()
    assert guarded.get_equity() == paper.get_equity()
    assert guarded.get_quote("AAPL") == paper.get_quote("AAPL")
