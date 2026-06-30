"""End-to-end test of the default guarded paper-broker stack."""
from decimal import Decimal
import pytest
from ops.broker.base import OrderRejected
from ops.broker.guarded import GuardedBroker
from ops.broker.paper import PaperBroker
from ops.broker.types import Order, Side, OrderType, Position
from ops.config import OpsConfig
from ops.guardrails.engine import RuleEngine
from ops.guardrails.static_rules import (
    DenyListRule, NoMarginRule, NoOptionsRule, NoCryptoRule,
    LongOnlyRule, StopAttachedRule, FractionalSharesOnlyRule,
)
from ops.guardrails.sizing_rules import (
    PerPositionCapRule, PerTradeDollarFloorRule,
    MaxOpenPositionsRule, CashReserveRule,
)
from ops.guardrails.drawdown_rules import DailyDrawdownRule, WeeklyDrawdownRule
from ops.journal import Journal


def _default_stack(tmp_path, *, starting_cash="250", quotes=None,
                   start_day_equity="250", start_week_equity="250"):
    j = Journal(str(tmp_path / "j.sqlite"))
    quotes = quotes or {"AAPL": Decimal("200")}
    paper = PaperBroker(
        journal=j,
        quote_source=lambda s: quotes[s],
        starting_cash=Decimal(starting_cash),
    )
    cfg = OpsConfig()
    rules = [
        DenyListRule(),
        NoMarginRule(),
        NoOptionsRule(),
        NoCryptoRule(),
        LongOnlyRule(),
        StopAttachedRule(),
        FractionalSharesOnlyRule(),
        PerTradeDollarFloorRule(),
        PerPositionCapRule(),
        MaxOpenPositionsRule(),
        CashReserveRule(),
        DailyDrawdownRule(start_of_day_equity=lambda: Decimal(start_day_equity)),
        WeeklyDrawdownRule(start_of_week_equity=lambda: Decimal(start_week_equity)),
    ]
    return j, paper, GuardedBroker(inner=paper, engine=RuleEngine(rules), journal=j, config=cfg)


def _buy(symbol="AAPL", notional="25", stop="184", cid="c1") -> Order:
    return Order(
        client_order_id=cid, symbol=symbol, side=Side.BUY,
        notional_dollars=Decimal(notional), order_type=OrderType.MARKET,
        stop_loss_price=Decimal(stop) if stop else None,
    )


def test_happy_path_fills_and_journals(tmp_path):
    j, paper, guarded = _default_stack(tmp_path)
    fill = guarded.place_order(_buy())
    assert fill.quantity == Decimal("0.125")
    assert paper.get_positions()[0].symbol == "AAPL"
    # Journal: 1 order + 1 fill, no rejections
    assert len(j.read_orders()) == 1
    assert len(j.read_fills()) == 1
    assert [e for e in j.read_events() if e["kind"] == "order_rejected"] == []


@pytest.mark.parametrize("order,expected_rule", [
    (_buy(symbol="SPOT"), "DenyListRule"),
    (_buy(symbol="TQQQ"), "DenyListRule"),
    (_buy(symbol="MARGIN:AAPL"), "NoMarginRule"),
    (_buy(symbol="AAPL  260117C00200000"), "NoOptionsRule"),
    (_buy(symbol="BTC"), "NoCryptoRule"),
    (_buy(cid="SHORT-1"), "LongOnlyRule"),
    (_buy(stop=None), "StopAttachedRule"),
    (_buy(notional="4.99"), "PerTradeDollarFloorRule"),
    (_buy(notional="25.01"), "PerPositionCapRule"),
])
def test_rule_rejections(tmp_path, order, expected_rule):
    j, paper, guarded = _default_stack(tmp_path)
    with pytest.raises(OrderRejected) as exc:
        guarded.place_order(order)
    assert exc.value.rule_name == expected_rule
    # Inner broker untouched
    assert paper.get_positions() == []
    assert paper.get_cash() == Decimal("250")
    # Rejection journaled
    rejections = [e for e in j.read_events() if e["kind"] == "order_rejected"]
    assert len(rejections) == 1
    assert rejections[0]["payload"]["rule"] == expected_rule


def test_max_open_positions_rejection(tmp_path):
    # Fund the broker enough to hold 5 positions
    j = Journal(str(tmp_path / "j.sqlite"))
    quotes = {s: Decimal("200") for s in ("AAPL", "MSFT", "NVDA", "GOOG", "AMZN", "META")}
    paper = PaperBroker(journal=j, quote_source=lambda s: quotes[s],
                       starting_cash=Decimal("10000"))
    cfg = OpsConfig()
    rules = [
        DenyListRule(), NoMarginRule(), NoOptionsRule(), NoCryptoRule(),
        LongOnlyRule(), StopAttachedRule(), FractionalSharesOnlyRule(),
        PerTradeDollarFloorRule(), PerPositionCapRule(),
        MaxOpenPositionsRule(), CashReserveRule(),
        DailyDrawdownRule(start_of_day_equity=lambda: Decimal("10000")),
        WeeklyDrawdownRule(start_of_week_equity=lambda: Decimal("10000")),
    ]
    guarded = GuardedBroker(inner=paper, engine=RuleEngine(rules), journal=j, config=cfg)
    # Buy 5 different positions at $25 each
    for i, sym in enumerate(("AAPL", "MSFT", "NVDA", "GOOG", "AMZN")):
        guarded.place_order(_buy(symbol=sym, notional="25", cid=f"c{i}"))
    # 6th NEW symbol must be rejected
    with pytest.raises(OrderRejected) as exc:
        guarded.place_order(_buy(symbol="META", notional="25", cid="c6"))
    assert exc.value.rule_name == "MaxOpenPositionsRule"


def test_cash_reserve_rejection(tmp_path):
    # To isolate CashReserveRule, use a config with per_position_cap=1.0 (effectively disabled).
    j = Journal(str(tmp_path / "j.sqlite"))
    paper = PaperBroker(journal=j, quote_source=lambda s: Decimal("200"),
                       starting_cash=Decimal("60"))
    cfg = OpsConfig(per_position_cap_pct=Decimal("1.0"))
    rules = [
        DenyListRule(), NoMarginRule(), NoOptionsRule(), NoCryptoRule(),
        LongOnlyRule(), StopAttachedRule(), FractionalSharesOnlyRule(),
        PerTradeDollarFloorRule(), PerPositionCapRule(),
        MaxOpenPositionsRule(), CashReserveRule(),
        DailyDrawdownRule(start_of_day_equity=lambda: Decimal("60")),
        WeeklyDrawdownRule(start_of_week_equity=lambda: Decimal("60")),
    ]
    guarded = GuardedBroker(inner=paper, engine=RuleEngine(rules), journal=j, config=cfg)
    # Buy $50 — post-cash $10, floor 20% of $60 = $12 → reject
    with pytest.raises(OrderRejected) as exc:
        guarded.place_order(_buy(notional="50"))
    assert exc.value.rule_name == "CashReserveRule"


def test_daily_drawdown_rejection(tmp_path):
    # Equity $230 vs. start-of-day $250 → -8% (≤ -7% threshold) → reject
    j, paper, guarded = _default_stack(
        tmp_path, starting_cash="230", start_day_equity="250",
    )
    with pytest.raises(OrderRejected) as exc:
        guarded.place_order(_buy(notional="20"))
    assert exc.value.rule_name == "DailyDrawdownRule"


def test_weekly_drawdown_rejection(tmp_path):
    # Equity $200 vs. start-of-week $250 → -20% (≤ -15%) → reject
    # Set start_day = current so daily drawdown is 0% and only weekly trips.
    j, paper, guarded = _default_stack(
        tmp_path, starting_cash="200", start_day_equity="200", start_week_equity="250",
    )
    with pytest.raises(OrderRejected) as exc:
        guarded.place_order(_buy(notional="15"))
    assert exc.value.rule_name == "WeeklyDrawdownRule"
