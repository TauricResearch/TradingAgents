"""Tests for the public factory and the privacy/concurrency hardening
that prevent guardrails from being bypassed."""
from __future__ import annotations

import threading
from decimal import Decimal

import pytest

from ops import build_default_rule_chain, build_guarded_paper_broker
from ops.broker.base import OrderRejected
from ops.broker.guarded import GuardedBroker
from ops.broker.types import Order, OrderType, Side
from ops.config import OpsConfig
from ops.journal import Journal


def _factory(tmp_path, *, starting_cash="250", quotes=None):
    journal = Journal(str(tmp_path / "j.sqlite"))
    quotes = quotes or {"AAPL": Decimal("200")}
    cfg = OpsConfig()
    guarded = build_guarded_paper_broker(
        config=cfg,
        journal=journal,
        quote_source=lambda s: quotes[s],
        starting_cash=Decimal(starting_cash),
        start_of_day_equity=lambda: Decimal(starting_cash),
        start_of_week_equity=lambda: Decimal(starting_cash),
    )
    return journal, guarded


def _buy(symbol="AAPL", notional="25", stop="184", cid="c1") -> Order:
    return Order(
        client_order_id=cid, symbol=symbol, side=Side.BUY,
        notional_dollars=Decimal(notional), order_type=OrderType.MARKET,
        stop_loss_price=Decimal(stop) if stop else None,
    )


def test_factory_returns_guarded_broker(tmp_path):
    _, guarded = _factory(tmp_path)
    assert isinstance(guarded, GuardedBroker)


def test_factory_default_chain_rejects_spot(tmp_path):
    _, guarded = _factory(tmp_path)
    with pytest.raises(OrderRejected) as exc:
        guarded.place_order(_buy(symbol="SPOT"))
    assert exc.value.rule_name == "DenyListRule"


def test_factory_default_chain_allows_normal_order(tmp_path):
    _, guarded = _factory(tmp_path)
    fill = guarded.place_order(_buy())
    assert fill.symbol == "AAPL"


def test_inner_broker_is_name_mangled(tmp_path):
    """A naive bypass attempt via the conventional `_inner` name fails."""
    _, guarded = _factory(tmp_path)
    with pytest.raises(AttributeError):
        guarded._inner  # noqa: B018 — intentional access for the test


def test_default_rule_chain_has_all_thirteen_rules():
    rules = build_default_rule_chain(
        start_of_day_equity=lambda: Decimal("250"),
        start_of_week_equity=lambda: Decimal("250"),
    )
    names = [type(r).__name__ for r in rules]
    expected = [
        "DenyListRule", "NoMarginRule", "NoOptionsRule", "NoCryptoRule",
        "LongOnlyRule", "StopAttachedRule", "FractionalSharesOnlyRule",
        "PerTradeDollarFloorRule", "PerPositionCapRule",
        "MaxOpenPositionsRule", "CashReserveRule",
        "DailyDrawdownRule", "WeeklyDrawdownRule",
    ]
    assert names == expected


def test_broker_layer_exception_is_journaled(tmp_path):
    """If the inner broker rejects after guardrails pass (e.g. InsufficientFunds
    in a degenerate scenario), the rejection must still land in the journal."""
    # Engineer a stack where guardrails pass but the inner broker rejects.
    # We start with $250 cash. We disable CashReserveRule to let the BUY past,
    # then SELL a position we don't have — inner raises NoSuchPosition.
    journal = Journal(str(tmp_path / "j.sqlite"))
    cfg = OpsConfig()  # default; we'll use a non-guarded path
    guarded = build_guarded_paper_broker(
        config=cfg, journal=journal,
        quote_source=lambda s: Decimal("200"),
        starting_cash=Decimal("250"),
        start_of_day_equity=lambda: Decimal("250"),
        start_of_week_equity=lambda: Decimal("250"),
    )
    sell = Order(
        client_order_id="cS", symbol="AAPL", side=Side.SELL,
        notional_dollars=Decimal("0"), order_type=OrderType.MARKET,
    )
    with pytest.raises(Exception):
        guarded.place_order(sell)
    broker_rejections = [
        e for e in journal.read_events()
        if e["kind"] == "order_rejected" and e["payload"]["rule"] == "broker"
    ]
    assert len(broker_rejections) == 1
    assert "NoSuchPosition" in broker_rejections[0]["payload"]["reason"]


def test_concurrent_buys_respect_max_open_positions(tmp_path):
    """Two concurrent BUYs against the cap should not both succeed.
    Without the lock, both threads would read the same pre-trade state,
    both pass MaxOpenPositionsRule, and both fill — breaching the cap."""
    journal = Journal(str(tmp_path / "j.sqlite"))
    cfg = OpsConfig(max_open_positions=1)
    quotes = {s: Decimal("200") for s in ("AAPL", "MSFT")}
    guarded = build_guarded_paper_broker(
        config=cfg, journal=journal,
        quote_source=lambda s: quotes[s],
        starting_cash=Decimal("10000"),
        start_of_day_equity=lambda: Decimal("10000"),
        start_of_week_equity=lambda: Decimal("10000"),
    )
    results: list[Exception | None] = [None, None]

    def buy(idx: int, symbol: str) -> None:
        try:
            guarded.place_order(_buy(symbol=symbol, notional="25", cid=f"c{idx}"))
        except OrderRejected as exc:
            results[idx] = exc

    t1 = threading.Thread(target=buy, args=(0, "AAPL"))
    t2 = threading.Thread(target=buy, args=(1, "MSFT"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one position should exist; exactly one OrderRejected should have fired.
    assert len(guarded.get_positions()) == 1
    rejections = [r for r in results if isinstance(r, OrderRejected)]
    assert len(rejections) == 1
    assert rejections[0].rule_name == "MaxOpenPositionsRule"


def test_config_rejects_positive_drawdown():
    with pytest.raises(ValueError, match="daily_drawdown_pct"):
        OpsConfig(daily_drawdown_pct=Decimal("0.07"))


def test_config_rejects_positive_weekly_drawdown():
    with pytest.raises(ValueError, match="weekly_drawdown_pct"):
        OpsConfig(weekly_drawdown_pct=Decimal("0.15"))


def test_config_rejects_positive_per_position_stop():
    with pytest.raises(ValueError, match="per_position_stop_pct"):
        OpsConfig(per_position_stop_pct=Decimal("0.08"))


def test_config_rejects_out_of_range_cap():
    with pytest.raises(ValueError, match="per_position_cap_pct"):
        OpsConfig(per_position_cap_pct=Decimal("1.5"))
    with pytest.raises(ValueError, match="per_position_cap_pct"):
        OpsConfig(per_position_cap_pct=Decimal("-0.1"))


def test_config_rejects_zero_or_negative_max_positions():
    with pytest.raises(ValueError, match="max_open_positions"):
        OpsConfig(max_open_positions=0)


def test_config_rejects_unknown_broker_mode():
    with pytest.raises(ValueError, match="broker_mode"):
        OpsConfig(broker_mode="schwab")


def test_config_defaults_still_valid():
    # Default construction must still succeed.
    cfg = OpsConfig()
    assert cfg.broker_mode == "paper"
