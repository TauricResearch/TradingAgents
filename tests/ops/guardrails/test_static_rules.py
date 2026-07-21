from decimal import Decimal
import pytest
from ops.broker.types import Order, Side, OrderType
from ops.config import OpsConfig
from ops.guardrails.base import RuleContext
from ops.guardrails.static_rules import (
    DenyListRule, NoMarginRule, NoOptionsRule, NoCryptoRule,
    LongOnlyRule, StopAttachedRule, FractionalSharesOnlyRule,
)


def _ctx(order: Order, cfg: OpsConfig | None = None) -> RuleContext:
    return RuleContext(order=order, broker=None, config=cfg or OpsConfig())  # type: ignore[arg-type]


def _buy(symbol: str = "AAPL", **kwargs) -> Order:
    defaults = dict(
        client_order_id="c", symbol=symbol, side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    )
    defaults.update(kwargs)
    return Order(**defaults)


def test_deny_list_blocks_spot():
    assert DenyListRule().check(_ctx(_buy("SPOT"))).allowed is False

def test_deny_list_blocks_leveraged_etf():
    assert DenyListRule().check(_ctx(_buy("TQQQ"))).allowed is False

def test_deny_list_allows_normal_ticker():
    assert DenyListRule().check(_ctx(_buy("AAPL"))).allowed is True

def test_no_margin_blocks_explicit_margin_symbol_format():
    o = _buy("MARGIN:AAPL")
    assert NoMarginRule().check(_ctx(o)).allowed is False

def test_no_margin_allows_regular_symbol():
    assert NoMarginRule().check(_ctx(_buy("AAPL"))).allowed is True

def test_no_options_blocks_occ_symbol():
    o = _buy("AAPL  260117C00200000")
    assert NoOptionsRule().check(_ctx(o)).allowed is False

def test_no_options_allows_equity():
    assert NoOptionsRule().check(_ctx(_buy("AAPL"))).allowed is True

def test_no_crypto_blocks_known_crypto_symbols():
    for sym in ("BTC", "ETH", "DOGE", "SHIB", "BTC-USD"):
        assert NoCryptoRule().check(_ctx(_buy(sym))).allowed is False, sym

def test_no_crypto_allows_equity():
    assert NoCryptoRule().check(_ctx(_buy("AAPL"))).allowed is True

def test_long_only_blocks_short_marker_in_client_order_id():
    o = _buy(client_order_id="SHORT-1")
    assert LongOnlyRule().check(_ctx(o)).allowed is False

def test_long_only_allows_buy_and_sell():
    assert LongOnlyRule().check(_ctx(_buy())).allowed is True
    sell = Order(
        client_order_id="c", symbol="AAPL", side=Side.SELL,
        notional_dollars=Decimal("0"), order_type=OrderType.MARKET,
    )
    assert LongOnlyRule().check(_ctx(sell)).allowed is True

def test_stop_attached_requires_stop_on_buy():
    o = Order(
        client_order_id="c", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=None,
    )
    assert StopAttachedRule().check(_ctx(o)).allowed is False

def test_stop_attached_allows_sell_without_stop():
    sell = Order(
        client_order_id="c", symbol="AAPL", side=Side.SELL,
        notional_dollars=Decimal("0"), order_type=OrderType.MARKET,
    )
    assert StopAttachedRule().check(_ctx(sell)).allowed is True

def test_fractional_only_blocks_whole_share_order_marker():
    assert FractionalSharesOnlyRule().check(_ctx(_buy())).allowed is True
