"""Unit tests for the L1 ccxt execution bridge (tradingagents/execution/).

ccxt is mocked completely: every test injects a fake exchange through
``exchange_factory`` -- no real client is constructed and no socket is opened
(conftest ``_no_network`` would fail the test anyway). The audit log is
redirected into ``tmp_path`` so nothing ever touches ~/.tradingagents.

FakeExchange models the two real ccxt behaviors the bridge depends on:
amount_to_precision requires markets to be loaded first (ccxt 4.5.84 raises
ExchangeError("markets not loaded") otherwise), and precision TRUNCATES the
planned quantity (ccxt base/exchange.py), so validated-vs-sent drift is
testable.
"""

import json
from copy import deepcopy
from types import SimpleNamespace

import ccxt
import pytest

from tradingagents.default_config import DEFAULT_CONFIG, _apply_env_overrides
from tradingagents.execution import ExchangeBridge, PlannedOrder, SizingRules
from tradingagents.execution.audit import append_event
from tradingagents.execution.sizing import compute
from tradingagents.portfolio import PortfolioContext, Position

pytestmark = pytest.mark.unit

AUDIT_FIELDS = (
    "timestamp", "ticker", "ccxt_symbol", "signal", "action", "qty",
    "price_est", "mode", "confirmed", "order_id",
)


class FakeExchange:
    """Offline stand-in for ccxt.binance that records every call."""

    def __init__(self, *, api_key="test-key", secret="test-secret", price=50_000.0,
                 min_cost=10.0, balance=None, create_order_error=None):
        self.apiKey = api_key
        self.secret = secret
        self.price = price
        self.min_cost = min_cost
        self.balance = balance if balance is not None else {
            "total": {"BTC": 0.5, "ETH": 2.0, "USDT": 1_000.0},
            "free": {"BTC": 0.5, "ETH": 2.0, "USDT": 1_000.0},
        }
        self.create_order_error = create_order_error
        self.calls = []
        self._markets_loaded = False

    def fetch_ticker(self, symbol):
        self.calls.append(("fetch_ticker", symbol))
        return {"last": self.price, "close": self.price}

    def load_markets(self):
        self.calls.append(("load_markets",))
        self._markets_loaded = True
        return {"BTC/USDT": {"limits": {"cost": {"min": self.min_cost}}}}

    def amount_to_precision(self, symbol, amount):
        if not self._markets_loaded:
            raise ccxt.ExchangeError("fake markets not loaded")  # real ccxt precondition
        self.calls.append(("amount_to_precision", symbol, amount))
        scaled = int(float(amount) * 1_000_000) / 1_000_000  # ccxt TRUNCATES
        return f"{scaled:.6f}"

    def create_order(self, symbol, order_type, side, amount, price=None, params=None):
        self.calls.append(("create_order", symbol, order_type, side, amount))
        if self.create_order_error is not None:
            raise self.create_order_error
        return {"id": "order-123"}

    def fetch_balance(self):
        self.calls.append(("fetch_balance",))
        return self.balance


def make_bridge(tmp_path, monkeypatch, *, config=None, factory=None, env=None):
    """A bridge whose audit log lives in tmp_path, execution env scrubbed."""
    monkeypatch.delenv("TRADINGAGENTS_EXEC_LIVE", raising=False)
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_SECRET", raising=False)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)
    merged = {"exec_log_path": str(tmp_path / "audit.jsonl")}
    merged.update(config or {})
    return ExchangeBridge(config=merged, exchange_factory=factory)


def read_audit(tmp_path):
    path = tmp_path / "audit.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def live_bridge(tmp_path, monkeypatch, exchange, **kwargs):
    """A bridge with both gates open (config exec_live + env flag)."""
    return make_bridge(
        tmp_path, monkeypatch,
        config={"exec_live": True},
        factory=lambda: exchange,
        env={"TRADINGAGENTS_EXEC_LIVE": "true"},
        **kwargs,
    )


def buy_book():
    return PortfolioContext(cash=1_000.0)


# --- symbol mapping (FR1) -------------------------------------------------


def test_symbol_for_maps_yahoo_ticker_to_ccxt(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    assert bridge.symbol_for("BTC-USD") == "BTC/USDT"


def test_symbol_for_normalizes_quote_case(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch, config={"exec_quote_currency": "usdt"})
    assert bridge.symbol_for("ETH-USD") == "ETH/USDT"


def test_symbol_for_rejects_empty_quote(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch, config={"exec_quote_currency": "   "})
    with pytest.raises(ValueError, match="exec_quote_currency"):
        bridge.symbol_for("BTC-USD")


def test_symbol_for_rejects_non_crypto(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="not an executable crypto symbol"):
        bridge.symbol_for("AAPL")


def test_symbol_for_rejects_ccxt_form(tmp_path, monkeypatch):
    # crypto_base strips '-' but not '/', so the ccxt form must never be fed back in.
    bridge = make_bridge(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="not an executable crypto symbol"):
        bridge.symbol_for("BTC/USDT")


def test_symbol_for_rejects_base_outside_the_closed_set(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="not an executable crypto symbol"):
        bridge.symbol_for("BNB-USD")


# --- signal -> plan (FR2/FR3) ---------------------------------------------


def test_compute_always_returns_a_planned_order():
    order = compute(
        SizingRules(), signal="Hold", ticker="BTC-USD", ccxt_symbol="BTC/USDT",
        portfolio=buy_book(), price=50_000.0,
    )
    assert isinstance(order, PlannedOrder)


def test_plan_buy_sizes_from_cash(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    assert order.side == "buy"
    assert isinstance(order.quantity, float)
    assert order.quantity == pytest.approx(0.005)
    assert order.cost == pytest.approx(250.0)
    assert order.ccxt_symbol == "BTC/USDT"
    assert order.mode == "dry"
    assert order.needs_review is False
    assert read_audit(tmp_path)[0]["action"] == "buy"


def test_plan_overweight_adds_fraction(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    order = bridge.plan_order("BTC-USD", "Overweight", buy_book(), price=50_000.0)
    assert order.side == "buy"
    assert order.quantity == pytest.approx(0.002)


def test_plan_fetches_price_when_not_given(tmp_path, monkeypatch):
    exchange = FakeExchange(price=25_000.0)
    bridge = make_bridge(tmp_path, monkeypatch, factory=lambda: exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book())
    assert ("fetch_ticker", "BTC/USDT") in exchange.calls
    assert order.estimated_price == 25_000.0
    assert order.quantity == pytest.approx(0.010)


def test_plan_respects_exchange_min_cost_on_network_path(tmp_path, monkeypatch):
    exchange = FakeExchange(min_cost=1_000.0)  # plan budget 250 < market min 1000
    bridge = make_bridge(tmp_path, monkeypatch, factory=lambda: exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book())  # no price param: network plan
    assert order.side is None
    assert "minimum" in order.reason
    assert read_audit(tmp_path)[0]["action"] == "no_order"


def test_plan_offline_uses_rules_floor(tmp_path, monkeypatch):
    exchange = FakeExchange(min_cost=1_000.0)  # market limit unknowable offline
    bridge = make_bridge(tmp_path, monkeypatch, factory=lambda: exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    assert order.side == "buy"  # 250 >= rules floor 10; live execute re-checks fresh limits
    assert bridge._exchange is None  # an offline plan never builds the client


def test_plan_hold_is_a_no_order(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    order = bridge.plan_order("BTC-USD", "Hold", buy_book(), price=50_000.0)
    assert order.side is None
    assert order.quantity is None
    assert order.needs_review is False
    assert order.reason


def test_plan_review_needs_human(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    order = bridge.plan_order("BTC-USD", "REVIEW", buy_book(), price=50_000.0)
    assert order.side is None
    assert order.quantity is None
    assert order.needs_review is True
    assert read_audit(tmp_path)[0]["action"] == "no_order"


def test_plan_unrecognized_signal_is_case_sensitive(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    for signal in ("buy", "STRONG BUY"):
        order = bridge.plan_order("BTC-USD", signal, buy_book(), price=50_000.0)
        assert order.side is None
        assert order.needs_review is True


def test_plan_sell_without_position_is_rejected(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    for signal in ("Sell", "Underweight"):
        order = bridge.plan_order("BTC-USD", signal, buy_book(), price=50_000.0)
        assert order.side is None
        assert order.quantity is None  # never a zero-quantity order
        assert order.reason


def test_plan_sell_closes_position(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    book = PortfolioContext(cash=1_000.0, positions=[Position(ticker="BTC-USD", quantity=0.5)])
    order = bridge.plan_order("BTC-USD", "Sell", book, price=50_000.0)
    assert order.side == "sell"
    assert order.quantity == pytest.approx(0.5)


def test_plan_underweight_reduces_position(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    book = PortfolioContext(cash=1_000.0, positions=[Position(ticker="BTC-USD", quantity=0.5)])
    order = bridge.plan_order("BTC-USD", "Underweight", book, price=50_000.0)
    assert order.side == "sell"
    assert order.quantity == pytest.approx(0.05)


def test_plan_buy_without_cash_is_rejected(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    order = bridge.plan_order("BTC-USD", "Buy", PortfolioContext(cash=None), price=50_000.0)
    assert order.side is None
    assert order.quantity is None
    assert "cash" in order.reason


def test_plan_below_min_cost_is_rejected(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    order = bridge.plan_order("BTC-USD", "Buy", PortfolioContext(cash=20.0), price=50_000.0)
    assert order.side is None
    assert "minimum" in order.reason


def test_sizing_rules_are_configurable(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_EXEC_LIVE", raising=False)
    bridge = ExchangeBridge(
        config={"exec_log_path": str(tmp_path / "audit.jsonl")},
        rules=SizingRules(buy_fraction=0.5),
    )
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    assert order.quantity == pytest.approx(0.010)


# --- execution gate (FR4/FR5) ---------------------------------------------


def test_dry_run_needs_no_confirm_and_touches_no_endpoint(tmp_path, monkeypatch):
    exchange = FakeExchange()
    bridge = make_bridge(tmp_path, monkeypatch, factory=lambda: exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    result = bridge.execute_order(order)
    assert result is None
    assert exchange.calls == []  # plan took the price param; dry execute is simulated
    event = read_audit(tmp_path)[-1]
    assert event["action"] == "buy"
    assert event["mode"] == "dry"
    assert event["confirmed"] is False
    assert event["order_id"] is None


def test_live_without_confirm_is_denied(tmp_path, monkeypatch):
    exchange = FakeExchange()
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    with pytest.raises(PermissionError):
        bridge.execute_order(order)
    assert not any(call[0] == "create_order" for call in exchange.calls)
    event = read_audit(tmp_path)[-1]
    assert event["action"] == "execute_denied"
    assert event["mode"] == "live"


def test_live_with_confirm_places_market_order(tmp_path, monkeypatch):
    exchange = FakeExchange()
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    order_id = bridge.execute_order(order, confirm=True)
    assert order_id == "order-123"
    assert ("create_order", "BTC/USDT", "market", "buy", "0.005000") in exchange.calls
    kinds = [call[0] for call in exchange.calls]  # markets must load before precision
    assert kinds.index("load_markets") < kinds.index("amount_to_precision") < kinds.index("create_order")
    event = read_audit(tmp_path)[-1]
    assert event["action"] == "buy"
    assert event["order_id"] == "order-123"
    assert event["confirmed"] is True
    assert event["mode"] == "live"
    assert isinstance(event["qty"], float)
    assert isinstance(event["qty_precision"], str)


@pytest.mark.parametrize("value", ["false", "off", "0", "garbage", ""])
def test_env_flag_is_fail_closed(tmp_path, monkeypatch, value):
    exchange = FakeExchange()
    bridge = make_bridge(
        tmp_path, monkeypatch,
        config={"exec_live": True},
        factory=lambda: exchange,
        env={"TRADINGAGENTS_EXEC_LIVE": value},
    )
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    bridge.execute_order(order, confirm=True)  # must succeed as a dry run
    assert not any(call[0] == "create_order" for call in exchange.calls)
    assert read_audit(tmp_path)[-1]["mode"] == "dry"


def test_env_flag_alone_never_arms_live(tmp_path, monkeypatch):
    # The env flag is only one half: without config exec_live=True the bridge
    # stays dry even with confirm=True (pins the two-gate independence).
    exchange = FakeExchange()
    bridge = make_bridge(
        tmp_path, monkeypatch,
        factory=lambda: exchange,
        env={"TRADINGAGENTS_EXEC_LIVE": "true"},
    )
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    bridge.execute_order(order, confirm=True)
    assert not any(call[0] == "create_order" for call in exchange.calls)
    assert read_audit(tmp_path)[-1]["mode"] == "dry"


def test_exec_live_env_var_is_not_a_config_override(monkeypatch):
    # FR5 needs two independent gates: the env flag must never fold into
    # DEFAULT_CONFIG via _ENV_OVERRIDES, or one variable would arm both halves.
    monkeypatch.setenv("TRADINGAGENTS_EXEC_LIVE", "true")
    config = _apply_env_overrides(deepcopy(DEFAULT_CONFIG))
    assert config["exec_live"] is False


@pytest.mark.parametrize("bad", ["false", "0", "true", 1, None])
def test_config_gate_accepts_only_a_real_boolean(tmp_path, monkeypatch, bad):
    # A string in the config dict (hand-written or half-coerced) must fail
    # closed, never ride Python truthiness.
    exchange = FakeExchange()
    bridge = make_bridge(
        tmp_path, monkeypatch,
        config={"exec_live": bad},
        factory=lambda: exchange,
        env={"TRADINGAGENTS_EXEC_LIVE": "true"},
    )
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    bridge.execute_order(order, confirm=True)
    assert not any(call[0] == "create_order" for call in exchange.calls)


def test_planned_mode_is_informational_gate_is_decided_at_execute(tmp_path, monkeypatch):
    exchange = FakeExchange()
    bridge = make_bridge(
        tmp_path, monkeypatch,
        config={"exec_live": True},
        factory=lambda: exchange,
    )  # env gate closed at plan time
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    assert order.mode == "dry"
    monkeypatch.setenv("TRADINGAGENTS_EXEC_LIVE", "true")  # opened afterwards
    assert bridge.execute_order(order, confirm=True) == "order-123"


def test_live_without_credentials_is_denied(tmp_path, monkeypatch):
    exchange = FakeExchange(api_key="", secret="")
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    with pytest.raises(RuntimeError, match="BINANCE_API_KEY"):
        bridge.execute_order(order, confirm=True)
    assert not any(call[0] == "create_order" for call in exchange.calls)
    assert read_audit(tmp_path)[-1]["action"] == "execute_denied"


def test_live_min_cost_drift_rejects_at_execute(tmp_path, monkeypatch):
    exchange = FakeExchange(min_cost=1_000.0)  # plan-time floor is 10; market says 1000
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    with pytest.raises(RuntimeError, match="minimum"):
        bridge.execute_order(order, confirm=True)
    assert not any(call[0] == "create_order" for call in exchange.calls)
    assert read_audit(tmp_path)[-1]["action"] == "rejected_at_execute"


def test_live_rejects_when_truncated_amount_drops_below_min(tmp_path, monkeypatch):
    # ccxt truncates: planned 0.0052399 ($261.995) passes the $261.97 minimum,
    # the sent "0.005239" ($261.95) does not -- the check must use the wire amount.
    exchange = FakeExchange(min_cost=261.97)
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    order = PlannedOrder(
        ticker="BTC-USD", ccxt_symbol="BTC/USDT", signal="Buy",
        side="buy", quantity=0.0052399, estimated_price=50_000.0, cost=261.995,
    )
    with pytest.raises(RuntimeError, match="minimum"):
        bridge.execute_order(order, confirm=True)
    assert not any(call[0] == "create_order" for call in exchange.calls)
    assert read_audit(tmp_path)[-1]["action"] == "rejected_at_execute"


def test_live_exchange_error_is_audited_then_chained(tmp_path, monkeypatch):
    exchange = FakeExchange(create_order_error=ccxt.NetworkError("connection reset"))
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    with pytest.raises(RuntimeError) as excinfo:
        bridge.execute_order(order, confirm=True)
    assert isinstance(excinfo.value.__cause__, ccxt.NetworkError)
    assert read_audit(tmp_path)[-1]["action"] == "rejected_at_execute"


def test_unexpected_error_in_execute_is_audited(tmp_path, monkeypatch):
    # Safety #4: a non-ccxt exception (bad field, broken client) must still
    # leave an audit line before the raise, not escape silently.
    exchange = FakeExchange(create_order_error=ValueError("bad ticker field"))
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    with pytest.raises(RuntimeError) as excinfo:
        bridge.execute_order(order, confirm=True)
    assert isinstance(excinfo.value.__cause__, ValueError)
    event = read_audit(tmp_path)[-1]
    assert event["action"] == "rejected_at_execute"
    assert "unexpected error" in event["reason"]


def test_foreign_runtime_error_in_execute_is_audited(tmp_path, monkeypatch):
    # A RuntimeError from an injected client is NOT one of the audited
    # pre-trade rejections: it must fall through to the generic handler
    # (audited + wrapped), never ride the pass-through branch. Only
    # PreTradeRejection is trusted as "already audited".
    exchange = FakeExchange(create_order_error=RuntimeError("proxy timeout"))
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    with pytest.raises(RuntimeError, match="proxy timeout") as excinfo:
        bridge.execute_order(order, confirm=True)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    event = read_audit(tmp_path)[-1]
    assert event["action"] == "rejected_at_execute"
    assert "unexpected error" in event["reason"]


def test_success_audit_failure_reports_order_was_placed(tmp_path, monkeypatch):
    # If the audit write fails AFTER create_order succeeded, the raise must
    # say the order exists -- otherwise a caller retry duplicates a real order.
    exchange = FakeExchange()
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")  # audit log breaks post-plan
    bridge.config["exec_log_path"] = str(blocker / "audit.jsonl")
    with pytest.raises(RuntimeError, match="WAS placed") as excinfo:
        bridge.execute_order(order, confirm=True)
    assert "order-123" in str(excinfo.value)
    assert any(call[0] == "create_order" for call in exchange.calls)


@pytest.mark.parametrize(
    "signal,needs_review",
    [("REVIEW", False), ("garbage", False), ("Buy", True)],
)
def test_execute_refuses_non_tradeable_signals_even_if_crafted(
    tmp_path, monkeypatch, signal, needs_review
):
    # PlannedOrder is a public, mutable model: safety #3 must hold on the
    # execution surface, not only at plan time.
    bridge = make_bridge(tmp_path, monkeypatch)
    crafted = PlannedOrder(
        ticker="BTC-USD", ccxt_symbol="BTC/USDT", signal=signal,
        side="buy", quantity=0.005, estimated_price=50_000.0, cost=250.0,
        needs_review=needs_review,
    )
    with pytest.raises(ValueError, match="not a tradeable rating"):
        bridge.execute_order(crafted, confirm=True)


def test_execute_refuses_non_executable_plan(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    review = bridge.plan_order("BTC-USD", "REVIEW", price=50_000.0)
    with pytest.raises(ValueError):
        bridge.execute_order(review, confirm=True)


def test_partial_config_injection_keeps_defaults(tmp_path, monkeypatch):
    exchange = FakeExchange()
    bridge = make_bridge(tmp_path, monkeypatch, config={"exec_live": True}, factory=lambda: exchange)
    assert bridge.config["exec_quote_currency"] == "USDT"  # unspecified key survives
    assert bridge.symbol_for("BTC-USD") == "BTC/USDT"


def test_client_is_lazy_until_first_network_read(tmp_path, monkeypatch):
    built = []

    def factory():
        built.append(True)
        return FakeExchange()

    bridge = make_bridge(tmp_path, monkeypatch, factory=factory)
    bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    assert built == []  # price param given: no client, no call
    book = bridge.sync_portfolio()
    assert built == [True]
    assert book.position_in("BTC-USD") is not None


def test_custom_factory_client_is_the_one_used(tmp_path, monkeypatch):
    sentinel = FakeExchange()
    bridge = live_bridge(tmp_path, monkeypatch, sentinel)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    bridge.execute_order(order, confirm=True)
    assert sentinel.calls  # the injected fake served the live path


def test_default_factory_reads_credentials_from_env(monkeypatch):
    monkeypatch.setenv("BINANCE_API_KEY", "env-key")
    monkeypatch.setenv("BINANCE_SECRET", "env-secret")
    import tradingagents.execution.bridge as bridge_module

    captured = {}

    def fake_binance(options):
        captured.update(options)
        return SimpleNamespace(apiKey=options["apiKey"], secret=options["secret"])

    monkeypatch.setattr(ccxt, "binance", fake_binance)
    bridge_module._default_exchange_factory()
    assert captured == {"apiKey": "env-key", "secret": "env-secret", "enableRateLimit": True}


def test_config_never_carries_credentials(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    assert not any("api" in key.lower() or "secret" in key.lower() for key in bridge.config)


# --- portfolio sync (FR6) -------------------------------------------------


def test_sync_portfolio_maps_known_coins_and_skips_unknown(tmp_path, monkeypatch):
    exchange = FakeExchange(balance={
        "total": {"BTC": 0.5, "ETH": 2.0, "BNB": 10.0, "USDT": 1_000.0},
        "free": {"BTC": 0.5, "ETH": 2.0, "USDT": 1_000.0},
    })
    bridge = make_bridge(tmp_path, monkeypatch, factory=lambda: exchange)
    book = bridge.sync_portfolio()
    assert {p.ticker for p in book.positions} == {"BTC-USD", "ETH-USD"}
    assert book.cash == 1_000.0
    assert book.currency == "USDT"
    assert exchange.calls[0][0] == "fetch_balance"


def test_sync_portfolio_tickers_match_position_lookup(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch, factory=lambda: FakeExchange())
    book = bridge.sync_portfolio()
    assert book.position_in("BTC-USD") is not None  # Yahoo form, consistent with the pipeline
    assert book.position_in("BTC") is None  # bare base never matches


def test_sync_portfolio_skips_zero_balances(tmp_path, monkeypatch):
    exchange = FakeExchange(balance={"total": {"BTC": 0.0, "USDT": 50.0}, "free": {"USDT": 50.0}})
    bridge = make_bridge(tmp_path, monkeypatch, factory=lambda: exchange)
    book = bridge.sync_portfolio()
    assert book.positions == []
    assert book.cash == 50.0


# --- audit writer (FR7) ---------------------------------------------------


def test_plan_audit_line_carries_fr7_fields(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    event = read_audit(tmp_path)[0]
    for field in AUDIT_FIELDS:
        assert field in event
    assert event["ticker"] == "BTC-USD"
    assert event["ccxt_symbol"] == "BTC/USDT"
    assert event["timestamp"].endswith("+00:00")  # explicit UTC, TZ-safe under CI


def test_append_event_is_utf8_jsonl_with_parent_mkdir(tmp_path):
    path = tmp_path / "nested" / "execution" / "audit.jsonl"
    append_event(path, {"action": "no_order", "reason": "REVIEW — cần người duyệt"})
    append_event(path, {"action": "buy", "qty": 0.5})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["reason"] == "REVIEW — cần người duyệt"
    assert json.loads(lines[1])["qty"] == 0.5


def test_audit_never_contains_credentials_even_in_exchange_errors(tmp_path, monkeypatch):
    # Safety #5 at content level: an exchange exception whose text embeds the
    # API key must not carry it into the audit reason.
    exchange = FakeExchange(
        api_key="sentinel-key-123",
        secret="sentinel-secret-456",
        create_order_error=ccxt.ExchangeError("auth failed for sentinel-key-123"),
    )
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    with pytest.raises(RuntimeError):
        bridge.execute_order(order, confirm=True)
    text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "sentinel-key-123" not in text
    assert "sentinel-secret-456" not in text
    assert "[redacted]" in text


def test_audit_success_flow_never_leaks_credentials(tmp_path, monkeypatch):
    exchange = FakeExchange(api_key="sentinel-key-123", secret="sentinel-secret-456")
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    monkeypatch.setenv("BINANCE_API_KEY", "sentinel-key-123")
    monkeypatch.setenv("BINANCE_SECRET", "sentinel-secret-456")
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    bridge.execute_order(order, confirm=True)
    text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "sentinel-key-123" not in text
    assert "sentinel-secret-456" not in text


def test_planned_order_carries_no_precision_string():
    assert "qty_precision" not in PlannedOrder.model_fields
    order = PlannedOrder(ticker="BTC-USD", ccxt_symbol="BTC/USDT", signal="Buy")
    assert order.side is None
    assert order.needs_review is False
    assert order.mode == "dry"
