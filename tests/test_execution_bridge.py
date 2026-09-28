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
from datetime import datetime, timezone

import ccxt
import pytest

import tradingagents.execution.risk as risk_module
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

# The risk guard's clock is frozen for the whole module so day-scoped checks
# (halt stickiness, daily P&L) are deterministic; injected control events use
# the same day. Bridge audit timestamps use the real clock and are unaffected.
FROZEN_NOW = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)


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


def make_bridge(tmp_path, monkeypatch, *, config=None, factory=None, env=None, risk_guard=None):
    """A bridge whose audit log lives in tmp_path, execution env scrubbed."""
    monkeypatch.delenv("TRADINGAGENTS_EXEC_LIVE", raising=False)
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_SECRET", raising=False)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(risk_module, "_utc_now", lambda: FROZEN_NOW)
    merged = {"exec_log_path": str(tmp_path / "audit.jsonl")}
    merged.update(config or {})
    return ExchangeBridge(config=merged, exchange_factory=factory, risk_guard=risk_guard)


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
        config={
            "exec_log_path": str(tmp_path / "audit.jsonl"),
            # the 50% buy_fraction would breach the default 25% per-asset cap
            "risk_max_position_pct_per_asset": 100.0,
            "risk_max_total_exposure_pct": 100.0,
        },
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
    # say the order exists -- otherwise a caller retry duplicates a real
    # order. The log path is broken mid-flight (inside the fake create_order)
    # so the fail-closed pre-send re-check still sees a healthy log and the
    # failure lands on the post-send success audit.
    exchange = FakeExchange()
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")  # audit log breaks post-plan
    real_create_order = exchange.create_order

    def create_order_and_break_log(symbol, order_type, side, amount, price=None, params=None):
        response = real_create_order(symbol, order_type, side, amount, price, params)
        bridge.config["exec_log_path"] = str(blocker / "audit.jsonl")
        return response

    monkeypatch.setattr(exchange, "create_order", create_order_and_break_log)
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


def test_execute_refuses_a_derivatives_plan_even_live_and_confirmed(tmp_path, monkeypatch):
    # FR-D: only DerivativesExecutor executes derivatives. The spot surface
    # must never route one -- exec_exchange_id is env-overridable, so a
    # "spot" bridge can point at a futures venue id; the market field, not
    # the venue, decides. Refusal fires before every gate, audit and send.
    exchange = FakeExchange()
    bridge = live_bridge(tmp_path, monkeypatch, exchange)  # both FR5 gates open
    crafted = PlannedOrder(
        ticker="BTC-USD", ccxt_symbol="BTC/USDT:USDT", signal="Sell", side="sell",
        quantity=0.005, estimated_price=50_000.0, cost=250.0,
        market="derivatives", leverage=50.0,
    )
    with pytest.raises(ValueError, match="DerivativesExecutor"):
        bridge.execute_order(crafted, confirm=True)
    assert not any(call[0] == "create_order" for call in exchange.calls)
    assert read_audit(tmp_path) == []  # refused before any audit line


def test_execute_refuses_a_derivatives_plan_in_dry(tmp_path, monkeypatch):
    # The dry branch is guarded too: a derivatives plan must not be able to
    # ride the no-confirm dry fill past the FR-D confirm requirement.
    exchange = FakeExchange()
    bridge = make_bridge(tmp_path, monkeypatch, factory=lambda: exchange)
    crafted = PlannedOrder(
        ticker="BTC-USD", ccxt_symbol="BTC/USDT:USDT", signal="Sell", side="sell",
        quantity=0.005, estimated_price=50_000.0, cost=250.0,
        market="derivatives", leverage=50.0,
    )
    with pytest.raises(ValueError, match="DerivativesExecutor"):
        bridge.execute_order(crafted, confirm=True)
    assert bridge._exchange is None  # nothing was ever built or sent


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

    class FakeBinance(ccxt.Exchange):
        def __init__(self, options):
            captured.update(options)
            self.apiKey = options["apiKey"]
            self.secret = options["secret"]

    monkeypatch.setattr(ccxt, "binance", FakeBinance)
    bridge_module._default_exchange_factory("binance")
    assert captured == {"apiKey": "env-key", "secret": "env-secret", "enableRateLimit": True}


def test_default_factory_selects_exchange_class_by_id(monkeypatch):
    # Two fake exchange ids: each resolves its own ccxt class and its own
    # {ID}_API_KEY / {ID}_SECRET env names (generalized from the L1 Binance
    # pair, which keeps working unchanged for id "binance").
    import tradingagents.execution.bridge as bridge_module

    built = []

    def make_fake(name):
        class FakeVenue(ccxt.Exchange):
            def __init__(self, options):
                built.append((name, options))

        return FakeVenue

    monkeypatch.setattr(ccxt, "okx", make_fake("okx"))
    monkeypatch.setattr(ccxt, "kraken", make_fake("kraken"))
    monkeypatch.setenv("OKX_API_KEY", "okx-key")
    monkeypatch.setenv("OKX_SECRET", "okx-secret")
    monkeypatch.setenv("KRAKEN_API_KEY", "kraken-key")
    monkeypatch.setenv("KRAKEN_SECRET", "kraken-secret")

    bridge_module._default_exchange_factory("okx")
    bridge_module._default_exchange_factory("kraken")
    assert built == [
        ("okx", {"apiKey": "okx-key", "secret": "okx-secret", "enableRateLimit": True}),
        ("kraken", {"apiKey": "kraken-key", "secret": "kraken-secret", "enableRateLimit": True}),
    ]


def test_default_factory_rejects_unknown_exchange_id():
    import tradingagents.execution.bridge as bridge_module

    with pytest.raises(ValueError, match="does not name a ccxt exchange class"):
        bridge_module._default_exchange_factory("nosuchexchange")


def test_default_factory_rejects_non_exchange_attribute(monkeypatch):
    import tradingagents.execution.bridge as bridge_module

    monkeypatch.setattr(ccxt, "impostor", object(), raising=False)  # not an Exchange subclass
    with pytest.raises(ValueError, match="does not name a ccxt exchange class"):
        bridge_module._default_exchange_factory("impostor")


def test_default_factory_rejects_plain_function(monkeypatch):
    # A callable that is not a ccxt.Exchange subclass must fail the factory
    # validation, not ride duck typing into the live path.
    import tradingagents.execution.bridge as bridge_module

    monkeypatch.setattr(ccxt, "impostor", lambda options: object(), raising=False)
    with pytest.raises(ValueError, match="does not name a ccxt exchange class"):
        bridge_module._default_exchange_factory("impostor")


def test_bridge_uses_exchange_id_override(tmp_path, monkeypatch):
    # The exchange_id constructor argument overrides exec_exchange_id and is
    # what the default factory receives.
    import tradingagents.execution.bridge as bridge_module

    seen = []

    def fake_factory(exchange_id):
        seen.append(exchange_id)
        return FakeExchange()

    monkeypatch.setattr(bridge_module, "_default_exchange_factory", fake_factory)
    bridge = ExchangeBridge(
        config={"exec_log_path": str(tmp_path / "audit.jsonl"), "exec_exchange_id": "binance"},
        exchange_id="kraken",
    )
    bridge._exchange_or_raise()
    assert seen == ["kraken"]


def test_bridge_defaults_exchange_id_from_config(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch, config={"exec_exchange_id": "okx"})
    assert bridge.exchange_id == "okx"


def test_bridge_rejects_empty_exchange_id(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="exec_exchange_id is empty"):
        make_bridge(tmp_path, monkeypatch, config={"exec_exchange_id": "  "})


# --- symbol overrides (L2) -------------------------------------------------


def test_symbol_for_uses_exec_symbol_overrides(tmp_path, monkeypatch):
    bridge = make_bridge(
        tmp_path, monkeypatch, config={"exec_symbol_overrides": {"BTC-USD": "BTC/USDC"}}
    )
    assert bridge.symbol_for("BTC-USD") == "BTC/USDC"


def test_symbol_override_allows_pairs_outside_the_closed_set(tmp_path, monkeypatch):
    bridge = make_bridge(
        tmp_path, monkeypatch, config={"exec_symbol_overrides": {"XYZ-USD": "XYZ/USDT"}}
    )
    assert bridge.symbol_for("XYZ-USD") == "XYZ/USDT"


def test_symbol_override_plans_end_to_end(tmp_path, monkeypatch):
    exchange = FakeExchange()
    bridge = make_bridge(
        tmp_path,
        monkeypatch,
        config={"exec_symbol_overrides": {"XYZ-USD": "XYZ/USDT"}},
        factory=lambda: exchange,
    )
    order = bridge.plan_order("XYZ-USD", "Buy", buy_book(), price=100.0)
    assert order.ccxt_symbol == "XYZ/USDT"
    assert order.side == "buy"


def test_symbol_override_unknown_ticker_without_entry_still_raises(tmp_path, monkeypatch):
    bridge = make_bridge(
        tmp_path, monkeypatch, config={"exec_symbol_overrides": {"BTC-USD": "BTC/USDC"}}
    )
    with pytest.raises(ValueError, match="not an executable crypto symbol"):
        bridge.symbol_for("XYZ-USD")


# --- risk guard integration (FR-K3) ----------------------------------------


def test_plan_buy_within_default_limits_passes(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    assert order.side == "buy"  # 25% of equity, exactly at the inclusive cap


def test_plan_beyond_per_asset_cap_returns_no_order_plan(tmp_path, monkeypatch):
    # cost 250 on equity 1000 = 25% > the tightened 10% cap: the contract is
    # a no-order plan, never an exception.
    bridge = make_bridge(
        tmp_path, monkeypatch, config={"risk_max_position_pct_per_asset": 10.0}
    )
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    assert order.side is None
    assert "per-asset" in order.reason
    event = read_audit(tmp_path)[-1]
    assert event["action"] == "rejected_by_risk"
    assert event["phase"] == "plan"


def test_plan_beyond_total_exposure_cap_returns_no_order_plan(tmp_path, monkeypatch):
    # The fake exchange prices every symbol at 50_000: the held ETH-USD
    # position marks at 50_000, equity is 51_000, and the 250 plan lifts
    # total exposure to ~98.5% > the tightened 80% cap.
    book = PortfolioContext(
        cash=1_000.0,
        positions=[Position(ticker="ETH-USD", quantity=1.0)],
    )
    bridge = make_bridge(
        tmp_path,
        monkeypatch,
        config={"risk_max_total_exposure_pct": 80.0},
        factory=lambda: FakeExchange(),
    )
    order = bridge.plan_order("BTC-USD", "Buy", book, price=50_000.0)
    assert order.side is None
    assert "total exposure" in order.reason


def test_plan_halted_raises_and_audits(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    append_event(
        bridge.config["exec_log_path"],
        {"event": "halt", "timestamp": "2026-09-28T10:00:00+00:00", "reason": "test"},
    )
    with pytest.raises(PermissionError, match="halt"):
        bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    event = read_audit(tmp_path)[-1]
    assert event["action"] == "rejected_by_risk"


def test_plan_rejection_is_never_double_counted_as_a_fill(tmp_path, monkeypatch):
    # The plan line carries phase="plan"; the risk replay must count only
    # executed lines, so planning + executing one order is one fill.
    exchange = FakeExchange()
    bridge = make_bridge(
        tmp_path, monkeypatch, config={"risk_max_position_pct_per_asset": 100.0},
        factory=lambda: exchange,
    )
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    bridge.execute_order(order)  # dry fill
    assert [e.get("phase") for e in read_audit(tmp_path)] == ["plan", "execute"]


def test_execute_halt_refuses_both_dry_and_live(tmp_path, monkeypatch):
    exchange = FakeExchange()
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    append_event(
        bridge.config["exec_log_path"],
        {"event": "halt", "timestamp": "2026-09-28T10:00:00+00:00", "reason": "mid-flight"},
    )
    with pytest.raises(PermissionError, match="halt"):
        bridge.execute_order(order)  # dry path guarded too
    with pytest.raises(PermissionError, match="halt"):
        bridge.execute_order(order, confirm=True)  # live path guarded too
    assert not any(call[0] == "create_order" for call in exchange.calls)
    assert read_audit(tmp_path)[-1]["action"] == "rejected_by_risk"
    assert read_audit(tmp_path)[-1]["phase"] == "execute"


def test_execute_risk_rejection_audits_before_refusing(tmp_path, monkeypatch):
    # A breach appearing between plan and execute (another process moved the
    # limits, or the portfolio changed) still refuses with an audit line.
    # The guard snapshots its limits at construction, so the test mutates the
    # guard itself -- document: bridge.config edits after construction do NOT
    # re-arm an existing guard; build a new bridge instead.
    exchange = FakeExchange()
    bridge = make_bridge(tmp_path, monkeypatch, factory=lambda: exchange)
    bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)  # passes at 25%
    bridge.risk_guard.limits.max_position_pct_per_asset = 5.0  # tightened afterwards
    with pytest.raises(PermissionError, match="per-asset"):
        bridge.execute_order(  # dry path: portfolio given so % limits re-run
            PlannedOrder(
                ticker="BTC-USD", ccxt_symbol="BTC/USDT", signal="Buy",
                side="buy", quantity=0.005, estimated_price=50_000.0, cost=250.0,
            ),
            portfolio=buy_book(),
        )
    assert not any(call[0] == "create_order" for call in exchange.calls)


def test_execute_fails_closed_when_audit_log_unreadable(tmp_path, monkeypatch):
    # The execute-time re-check reads the log fail-closed: an unreadable
    # audit log (locked by backup/AV, permissions) hides the halt and
    # loss-streak state, so the order is refused and audited as
    # rejected_by_risk -- never passed through.
    exchange = FakeExchange()
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    monkeypatch.setattr(risk_module, "_read_events", lambda path, *, fail_closed=False: None)
    with pytest.raises(PermissionError, match="unreadable"):
        bridge.execute_order(order, confirm=True)
    assert not any(call[0] == "create_order" for call in exchange.calls)
    event = read_audit(tmp_path)[-1]
    assert event["action"] == "rejected_by_risk"
    assert "unreadable" in event["reason"]


def test_reset_halt_unblocks_planning(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path, monkeypatch)
    guard = bridge.risk_guard
    append_event(
        bridge.config["exec_log_path"],
        {"event": "halt", "timestamp": "2026-09-28T10:00:00+00:00", "reason": "test"},
    )
    with pytest.raises(PermissionError):
        bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    guard.reset_halt(bridge.config["exec_log_path"])
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    assert order.side == "buy"


def test_injected_risk_guard_is_the_one_used(tmp_path, monkeypatch):
    from tradingagents.execution.risk import RiskDecision, RiskGuard

    class ScriptedGuard(RiskGuard):
        def check(self, order_plan, portfolio, audit_log):
            return RiskDecision(allowed=False, halted=False, reason="scripted refusal")

    bridge = make_bridge(tmp_path, monkeypatch, risk_guard=ScriptedGuard())
    order = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    assert order.side is None
    assert order.reason == "scripted refusal"


def test_consecutive_loss_halt_blocks_planning(tmp_path, monkeypatch):
    # Three losing sells in the audit (FIFO-matched): the next plan halts.
    bridge = make_bridge(tmp_path, monkeypatch)
    path = bridge.config["exec_log_path"]
    for hour, (qty, price) in enumerate(
        [(1.0, 100.0), (1.0, 90.0), (1.0, 100.0), (1.0, 80.0), (1.0, 100.0), (1.0, 70.0)], start=8
    ):
        append_event(path, {
            "timestamp": f"2026-09-28T{hour:02d}:00:00+00:00",
            "ticker": "BTC-USD",
            "action": "buy" if hour % 2 == 0 else "sell",
            "qty": qty,
            "price_est": price,
            "phase": "execute",
        })
    with pytest.raises(PermissionError, match="consecutive"):
        bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)


def test_no_secrets_in_risk_rejection_lines(tmp_path, monkeypatch):
    exchange = FakeExchange(api_key="sentinel-key-123", secret="sentinel-secret-456")
    bridge = live_bridge(tmp_path, monkeypatch, exchange)
    bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    bridge.risk_guard.limits.max_position_pct_per_asset = 0.0  # force a risk refusal
    rejected = bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    assert rejected.side is None  # a limit breach returns a plan; only a halt raises
    text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "sentinel-key-123" not in text
    assert "sentinel-secret-456" not in text


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


def test_audit_line_carries_market_and_leverage(tmp_path, monkeypatch):
    # The risk matcher replays these lines: market="derivatives" is what lets
    # it recognize a sell as a short opener; leverage documents the notional.
    bridge = make_bridge(tmp_path, monkeypatch)
    bridge.plan_order("BTC-USD", "Buy", buy_book(), price=50_000.0)
    event = read_audit(tmp_path)[-1]
    assert event["market"] == "spot"
    assert event["leverage"] == 1.0


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
