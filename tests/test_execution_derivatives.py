"""Unit tests for the derivatives executor (tradingagents/execution/derivatives.py).

The exchange is a fake injected through ``exchange_factory``; no real client
is built and no socket is opened (conftest ``_no_network`` would fail the test
anyway). The risk guard's clock is frozen. Every test pins the FR-D contract:
all three gate layers ship closed, and ANY default path (dry or live, with or
without confirm) is refused with an audit line and nothing sent.
"""

import json
from datetime import datetime, timezone

import ccxt
import pytest

import tradingagents.execution.risk as risk_module
from tradingagents.default_config import DEFAULT_CONFIG, _apply_env_overrides
from tradingagents.execution.derivatives import DerivativesExecutor
from tradingagents.portfolio import PortfolioContext

pytestmark = pytest.mark.unit

FROZEN_NOW = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)


class FakeDerivExchange:
    """Offline ccxt stand-in that also records set_leverage."""

    def __init__(self, *, api_key="test-key", secret="test-secret", price=50_000.0,
                 create_order_error=None):
        self.apiKey = api_key
        self.secret = secret
        self.price = price
        self.create_order_error = create_order_error
        self.calls = []
        self._markets_loaded = False

    def fetch_ticker(self, symbol):
        self.calls.append(("fetch_ticker", symbol))
        return {"last": self.price, "close": self.price}

    def load_markets(self):
        self.calls.append(("load_markets",))
        self._markets_loaded = True
        return {"BTC/USDT:USDT": {"limits": {"cost": {"min": 10.0}}}}

    def amount_to_precision(self, symbol, amount):
        if not self._markets_loaded:
            raise ccxt.ExchangeError("fake markets not loaded")
        self.calls.append(("amount_to_precision", symbol, amount))
        return f"{float(amount):.6f}"

    def set_leverage(self, leverage, symbol, params=None):
        self.calls.append(("set_leverage", leverage, symbol))

    def create_order(self, symbol, order_type, side, amount, price=None, params=None):
        self.calls.append(("create_order", symbol, order_type, side, amount))
        if self.create_order_error is not None:
            raise self.create_order_error
        return {"id": "deriv-123"}

    def fetch_balance(self):
        self.calls.append(("fetch_balance",))
        return {"total": {"USDT": 1_000.0}, "free": {"USDT": 1_000.0}}


def freeze(monkeypatch):
    monkeypatch.setattr(risk_module, "_utc_now", lambda: FROZEN_NOW)


def make_executor(tmp_path, monkeypatch, *, config=None, factory=None, env=None):
    """An executor with tmp audit log, frozen risk clock, scrubbed env."""
    monkeypatch.delenv("TRADINGAGENTS_EXEC_LIVE", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_EXEC_DERIVATIVES", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_EXEC_AUTO_CONFIRM", raising=False)
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_SECRET", raising=False)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)
    freeze(monkeypatch)
    merged = {"exec_log_path": str(tmp_path / "audit.jsonl")}
    merged.update(config or {})
    return DerivativesExecutor(config=merged, exchange_factory=factory)


def read_audit(tmp_path):
    path = tmp_path / "audit.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def gates_config(**extra):
    """Both derivatives gates armed in config (env stays a separate layer)."""
    return {"exec_derivatives": True, **extra}


def live_config(**extra):
    return gates_config(exec_live=True, **extra)


def live_env(**extra):
    return {"TRADINGAGENTS_EXEC_LIVE": "true", "TRADINGAGENTS_EXEC_DERIVATIVES": "true", **extra}


def test_every_default_path_is_refused(tmp_path, monkeypatch):
    """PRD requirement: with the gates at defaults, no path plans or sends."""
    book = PortfolioContext(cash=1_000.0)

    # dry plan, no gates: refused on the config layer
    executor = make_executor(tmp_path, monkeypatch)
    with pytest.raises(PermissionError, match="exec_derivatives"):
        executor.plan_order("BTC-USD", "Buy", book, price=50_000.0)
    assert read_audit(tmp_path)[-1]["action"] == "derivatives_denied"

    # live plan, env flag true but the config layer closed: refused again
    executor = make_executor(
        tmp_path, monkeypatch,
        config={"exec_live": True},
        env=live_env(),
    )
    with pytest.raises(PermissionError, match="exec_derivatives"):
        executor.plan_order("BTC-USD", "Buy", book, price=50_000.0)
    assert read_audit(tmp_path)[-1]["action"] == "derivatives_denied"

    # dry execute (crafted order, no confirm): refused on the confirm layer
    from tradingagents.execution.sizing import PlannedOrder

    executor = make_executor(
        tmp_path, monkeypatch,
        config=gates_config(risk_max_derivatives_exposure_pct=100.0),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    crafted = PlannedOrder(
        ticker="BTC-USD", ccxt_symbol="BTC/USDT:USDT", signal="Buy", side="buy",
        quantity=0.005, estimated_price=50_000.0, cost=250.0, market="derivatives",
    )
    with pytest.raises(PermissionError, match="confirm=True"):
        executor.execute_order(crafted, portfolio=PortfolioContext(cash=1_000.0))
    assert read_audit(tmp_path)[-1]["action"] == "derivatives_denied"

    # live execute with confirm but derivatives config gate closed: refused
    executor = make_executor(
        tmp_path, monkeypatch,
        config={"exec_live": True},
        env={"TRADINGAGENTS_EXEC_LIVE": "true", "TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    with pytest.raises(PermissionError, match="exec_derivatives"):
        executor.execute_order(crafted, confirm=True)
    assert read_audit(tmp_path)[-1]["action"] == "derivatives_denied"


def test_env_gate_read_fail_closed(tmp_path, monkeypatch):
    """Config armed but the env flag missing/garbage keeps everything closed."""
    book = PortfolioContext(cash=1_000.0)
    for env_value in (None, "false", "0", "garbage"):
        executor = make_executor(
            tmp_path, monkeypatch, config=gates_config(),
            env={"TRADINGAGENTS_EXEC_DERIVATIVES": env_value} if env_value else {},
        )
        with pytest.raises(PermissionError, match="TRADINGAGENTS_EXEC_DERIVATIVES"):
            executor.plan_order("BTC-USD", "Buy", book, price=50_000.0)


def test_config_gate_never_opens_on_truthy_strings(tmp_path, monkeypatch):
    """The config gate only opens on a real boolean, like exec_live."""
    book = PortfolioContext(cash=1_000.0)
    executor = make_executor(
        tmp_path, monkeypatch,
        config=gates_config(exec_derivatives="true"),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    with pytest.raises(PermissionError, match="exec_derivatives"):
        executor.plan_order("BTC-USD", "Buy", book, price=50_000.0)


def test_config_gate_env_var_is_not_a_config_override(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_EXEC_DERIVATIVES", "true")
    config = _apply_env_overrides(dict(DEFAULT_CONFIG))
    assert config["exec_derivatives"] is False


# --- plans once the gates are open -------------------------------------------


def test_gated_dry_plan_long(tmp_path, monkeypatch):
    executor = make_executor(
        tmp_path, monkeypatch,
        config=gates_config(risk_max_derivatives_exposure_pct=100.0),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    order = executor.plan_order(
        "BTC-USD", "Buy", PortfolioContext(cash=1_000.0), price=50_000.0
    )
    assert order.side == "buy"
    assert order.market == "derivatives"
    assert order.leverage == 1.0
    assert order.cost == pytest.approx(250.0)  # margin
    assert order.quantity == pytest.approx(250.0 / 50_000.0)  # notional/price at 1x
    assert order.ccxt_symbol == "BTC/USDT:USDT"


def test_gated_plan_sell_opens_a_short_without_holdings(tmp_path, monkeypatch):
    executor = make_executor(
        tmp_path, monkeypatch,
        config=gates_config(risk_max_derivatives_exposure_pct=100.0),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    order = executor.plan_order(
        "BTC-USD", "Sell", PortfolioContext(cash=1_000.0), price=50_000.0
    )
    assert order.side == "sell"  # short: no held position required
    assert order.cost == pytest.approx(250.0)


def test_gated_plan_leverage_scales_notional_not_margin(tmp_path, monkeypatch):
    executor = make_executor(
        tmp_path, monkeypatch,
        config=gates_config(
            risk_max_derivatives_leverage=5.0,
            risk_max_derivatives_exposure_pct=200.0,
            risk_max_total_exposure_pct=200.0,
            risk_max_position_pct_per_asset=200.0,  # per-asset sees notional 125%
        ),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    order = executor.plan_order(
        "BTC-USD", "Buy", PortfolioContext(cash=1_000.0), price=50_000.0, leverage=5.0
    )
    assert order.leverage == 5.0
    assert order.cost == pytest.approx(250.0)  # margin unchanged
    assert order.quantity == pytest.approx(1_250.0 / 50_000.0)  # 5x notional


def test_plan_hold_and_review_stay_no_orders(tmp_path, monkeypatch):
    executor = make_executor(
        tmp_path, monkeypatch, config=gates_config(),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    hold = executor.plan_order("BTC-USD", "Hold", PortfolioContext(cash=1_000.0), price=50_000.0)
    assert hold.side is None and hold.needs_review is False
    review = executor.plan_order("BTC-USD", "REVIEW", PortfolioContext(cash=1_000.0), price=50_000.0)
    assert review.needs_review is True


def test_plan_below_minimum_notional_is_refused(tmp_path, monkeypatch):
    executor = make_executor(
        tmp_path, monkeypatch, config=gates_config(),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    order = executor.plan_order(
        "BTC-USD", "Buy", PortfolioContext(cash=20.0), price=50_000.0
    )  # margin 5, notional 5 < floor 10
    assert order.side is None
    assert "minimum" in order.reason


def test_symbol_for_builds_unified_form_and_honors_overrides(tmp_path, monkeypatch):
    executor = make_executor(
        tmp_path, monkeypatch,
        config=gates_config(exec_symbol_overrides={"BTC-USD": "BTC/USDC:USDC"}),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    assert executor.symbol_for("BTC-USD") == "BTC/USDC:USDC"
    plain = make_executor(
        tmp_path, monkeypatch, config=gates_config(),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    assert plain.symbol_for("ETH-USD") == "ETH/USDT:USDT"


# --- risk caps on derivatives -------------------------------------------------


def test_plan_leverage_above_default_cap_returns_no_order_plan(tmp_path, monkeypatch):
    executor = make_executor(
        tmp_path, monkeypatch, config=gates_config(),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )  # default risk_max_derivatives_leverage = 1.0
    order = executor.plan_order(
        "BTC-USD", "Buy", PortfolioContext(cash=1_000.0), price=50_000.0, leverage=3.0
    )
    assert order.side is None
    assert "leverage" in order.reason
    assert read_audit(tmp_path)[-1]["action"] == "rejected_by_risk"


def test_plan_notional_above_zero_default_exposure_cap_is_rejected(tmp_path, monkeypatch):
    executor = make_executor(
        tmp_path, monkeypatch,
        config=gates_config(risk_max_derivatives_leverage=5.0),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )  # default risk_max_derivatives_exposure_pct = 0.0 blocks all notional
    order = executor.plan_order(
        "BTC-USD", "Buy", PortfolioContext(cash=1_000.0), price=50_000.0, leverage=3.0
    )
    assert order.side is None
    assert "derivatives notional" in order.reason


def test_plan_within_raised_caps_passes(tmp_path, monkeypatch):
    executor = make_executor(
        tmp_path, monkeypatch,
        config=gates_config(
            risk_max_derivatives_leverage=3.0,
            risk_max_derivatives_exposure_pct=80.0,
            # the per-asset cap reads the NOTIONAL for derivatives:
            # 750 = 75% of equity 1000, so it must be raised above 75%
            risk_max_position_pct_per_asset=100.0,
        ),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    order = executor.plan_order(
        "BTC-USD", "Buy", PortfolioContext(cash=1_000.0), price=50_000.0, leverage=3.0
    )
    # notional 750 = 75% per-asset (<= 100), 75% total exposure (<= 80) and
    # 75% derivatives exposure (<= 80)
    assert order.side == "buy"


# --- execution once the gates are open -----------------------------------------


def test_dry_execute_with_confirm_sends_nothing(tmp_path, monkeypatch):
    exchange = FakeDerivExchange()
    executor = make_executor(
        tmp_path, monkeypatch,
        config=gates_config(risk_max_derivatives_exposure_pct=100.0),
        factory=lambda: exchange,
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    book = PortfolioContext(cash=1_000.0)
    order = executor.plan_order("BTC-USD", "Buy", book, price=50_000.0)
    result = executor.execute_order(order, confirm=True, portfolio=book)
    assert result is None
    assert exchange.calls == []  # dry never touches the venue
    event = read_audit(tmp_path)[-1]
    assert event["action"] == "buy"
    assert event["phase"] == "execute"
    assert event["market"] == "derivatives"  # the matcher's short-recognition field
    assert event["leverage"] == 1.0


def test_live_execute_places_market_order(tmp_path, monkeypatch):
    exchange = FakeDerivExchange()
    executor = make_executor(
        tmp_path, monkeypatch,
        config=live_config(risk_max_derivatives_exposure_pct=100.0),
        factory=lambda: exchange, env=live_env(),
    )
    book = PortfolioContext(cash=1_000.0)
    order = executor.plan_order("BTC-USD", "Buy", book, price=50_000.0)
    order_id = executor.execute_order(order, confirm=True, portfolio=book)
    assert order_id == "deriv-123"
    assert ("create_order", "BTC/USDT:USDT", "market", "buy", "0.005000") in exchange.calls
    kinds = [call[0] for call in exchange.calls]
    assert kinds.index("load_markets") < kinds.index("amount_to_precision") < kinds.index("create_order")
    event = read_audit(tmp_path)[-1]
    assert event["order_id"] == "deriv-123"
    assert event["confirmed"] is True
    assert event["mode"] == "live"


def test_live_execute_sets_leverage_before_create_order(tmp_path, monkeypatch):
    exchange = FakeDerivExchange()
    executor = make_executor(
        tmp_path, monkeypatch,
        config=live_config(
            risk_max_derivatives_leverage=5.0,
            risk_max_derivatives_exposure_pct=200.0,
            risk_max_total_exposure_pct=200.0,
            risk_max_position_pct_per_asset=200.0,  # per-asset sees notional 125%
        ),
        factory=lambda: exchange, env=live_env(),
    )
    book = PortfolioContext(cash=1_000.0)
    order = executor.plan_order(
        "BTC-USD", "Buy", book, price=50_000.0, leverage=5.0
    )
    executor.execute_order(order, confirm=True, portfolio=book)
    leverage_calls = [call for call in exchange.calls if call[0] == "set_leverage"]
    assert leverage_calls == [("set_leverage", 5, "BTC/USDT:USDT")]
    kinds = [call[0] for call in exchange.calls]
    assert kinds.index("set_leverage") < kinds.index("create_order")


def test_live_execute_sets_leverage_even_at_one_x(tmp_path, monkeypatch):
    # 1x is still sent explicitly: without it the venue's per-symbol preset
    # would decide the real leverage.
    exchange = FakeDerivExchange()
    executor = make_executor(
        tmp_path, monkeypatch,
        config=live_config(risk_max_derivatives_exposure_pct=100.0),
        factory=lambda: exchange, env=live_env(),
    )
    book = PortfolioContext(cash=1_000.0)
    order = executor.plan_order("BTC-USD", "Buy", book, price=50_000.0)
    executor.execute_order(order, confirm=True, portfolio=book)
    assert ("set_leverage", 1, "BTC/USDT:USDT") in exchange.calls


def test_live_without_credentials_is_denied(tmp_path, monkeypatch):
    exchange = FakeDerivExchange(api_key="", secret="")
    executor = make_executor(
        tmp_path, monkeypatch,
        config=live_config(risk_max_derivatives_exposure_pct=100.0),
        factory=lambda: exchange, env=live_env(),
    )
    book = PortfolioContext(cash=1_000.0)
    order = executor.plan_order("BTC-USD", "Buy", book, price=50_000.0)
    with pytest.raises(RuntimeError, match="BINANCE_API_KEY"):
        executor.execute_order(order, confirm=True, portfolio=book)
    assert not any(call[0] == "create_order" for call in exchange.calls)


def test_exchange_error_is_audited_then_chained(tmp_path, monkeypatch):
    exchange = FakeDerivExchange(create_order_error=ccxt.NetworkError("connection reset"))
    executor = make_executor(
        tmp_path, monkeypatch,
        config=live_config(risk_max_derivatives_exposure_pct=100.0),
        factory=lambda: exchange, env=live_env(),
    )
    book = PortfolioContext(cash=1_000.0)
    order = executor.plan_order("BTC-USD", "Buy", book, price=50_000.0)
    with pytest.raises(RuntimeError) as excinfo:
        executor.execute_order(order, confirm=True, portfolio=book)
    assert isinstance(excinfo.value.__cause__, ccxt.NetworkError)
    assert read_audit(tmp_path)[-1]["action"] == "rejected_at_execute"


def test_execute_refuses_spot_orders(tmp_path, monkeypatch):
    from tradingagents.execution.sizing import PlannedOrder

    executor = make_executor(
        tmp_path, monkeypatch, config=gates_config(),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    spot = PlannedOrder(
        ticker="BTC-USD", ccxt_symbol="BTC/USDT", signal="Buy", side="buy",
        quantity=0.005, estimated_price=50_000.0, cost=250.0,
    )
    with pytest.raises(ValueError, match="derivatives orders only"):
        executor.execute_order(spot, confirm=True)


def test_execute_without_portfolio_is_refused_fail_closed(tmp_path, monkeypatch):
    # RiskGuard's percentage caps (leverage, derivatives notional) skip
    # fail-open without equity; on the derivatives path a None portfolio
    # must refuse BEFORE the guard runs, even with every gate open and
    # confirm given -- otherwise risk_max_derivatives_exposure_pct=0 is
    # silently disarmed.
    executor = make_executor(
        tmp_path, monkeypatch,
        config=gates_config(risk_max_derivatives_exposure_pct=100.0),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    book = PortfolioContext(cash=1_000.0)
    order = executor.plan_order("BTC-USD", "Buy", book, price=50_000.0)
    with pytest.raises(PermissionError, match="portfolio"):
        executor.execute_order(order, confirm=True)  # gates open + confirm, no portfolio
    assert read_audit(tmp_path)[-1]["action"] == "derivatives_denied"


def test_execute_with_unmarkable_portfolio_is_refused_fail_closed(tmp_path, monkeypatch):
    # Defense in depth: a portfolio that is present but yields no equity
    # (no cash, no positions) also makes the guard's percentage caps fail
    # open -- the derivatives path refuses it exactly like a None portfolio.
    executor = make_executor(
        tmp_path, monkeypatch,
        config=gates_config(risk_max_derivatives_exposure_pct=100.0),
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    book = PortfolioContext(cash=1_000.0)
    order = executor.plan_order("BTC-USD", "Buy", book, price=50_000.0)
    with pytest.raises(PermissionError, match="computable equity"):
        executor.execute_order(order, confirm=True, portfolio=PortfolioContext())
    assert read_audit(tmp_path)[-1]["action"] == "derivatives_denied"


def test_execute_fails_closed_when_audit_log_unreadable(tmp_path, monkeypatch):
    # Same rule as the spot execute re-check: an unreadable audit log hides
    # the halt/streak state a send decision needs, so it refuses even on the
    # dry path instead of passing fail-open.
    exchange = FakeDerivExchange()
    executor = make_executor(
        tmp_path, monkeypatch,
        config=gates_config(risk_max_derivatives_exposure_pct=100.0),
        factory=lambda: exchange,
        env={"TRADINGAGENTS_EXEC_DERIVATIVES": "true"},
    )
    book = PortfolioContext(cash=1_000.0)
    order = executor.plan_order("BTC-USD", "Buy", book, price=50_000.0)
    monkeypatch.setattr(risk_module, "_read_events", lambda path, *, fail_closed=False: None)
    with pytest.raises(PermissionError, match="unreadable"):
        executor.execute_order(order, confirm=True, portfolio=book)
    assert exchange.calls == []
    event = read_audit(tmp_path)[-1]
    assert event["action"] == "rejected_by_risk"
    assert "unreadable" in event["reason"]


def test_no_secrets_in_any_audit_line(tmp_path, monkeypatch):
    exchange = FakeDerivExchange(api_key="sentinel-key-123", secret="sentinel-secret-456")
    executor = make_executor(
        tmp_path, monkeypatch,
        config=live_config(risk_max_derivatives_exposure_pct=100.0),
        factory=lambda: exchange, env=live_env(),
    )
    book = PortfolioContext(cash=1_000.0)
    order = executor.plan_order("BTC-USD", "Buy", book, price=50_000.0)
    executor.execute_order(order, confirm=True, portfolio=book)
    text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "sentinel-key-123" not in text
    assert "sentinel-secret-456" not in text


def test_exports_expose_the_executor():
    import tradingagents.execution as execution_package

    assert execution_package.DerivativesExecutor is DerivativesExecutor
