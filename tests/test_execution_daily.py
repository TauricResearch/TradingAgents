"""Unit tests for the daily runner (tradingagents/execution/daily.py).

``TradingAgentsGraph`` is mocked wholesale (the real one would spend LLM
quota and touch vendors); the bridge's two network reads (balance sync and
price fetch) are stubbed at class level so no socket opens. The audit log
lives in tmp_path and the risk guard's clock is frozen.
"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import tradingagents.execution.daily as daily_module
import tradingagents.execution.risk as risk_module
from tradingagents.execution.daily import DailyResult, run_daily
from tradingagents.portfolio import PortfolioContext

pytestmark = pytest.mark.unit

FROZEN_NOW = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)


class FakeGraph:
    """Stand-in for TradingAgentsGraph: records construction and propagation."""

    signals: dict[str, str] = {}
    constructed: list = []
    propagated: list = []
    error_on: str | None = None

    def __init__(self, config=None, **kwargs):
        self.config = config
        FakeGraph.constructed.append(self)

    def propagate(self, coin, trade_date, asset_type="stock", portfolio=None):
        FakeGraph.propagated.append((coin, trade_date, asset_type))
        if self.error_on is not None and coin == self.error_on:
            raise RuntimeError("vendor outage")
        return (object(), FakeGraph.signals.get(coin, "Hold"))


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """Scrub env, freeze both clocks, stub the bridge's network reads."""
    monkeypatch.delenv("TRADINGAGENTS_EXEC_LIVE", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_EXEC_AUTO_CONFIRM", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_EXEC_DERIVATIVES", raising=False)
    monkeypatch.setattr(risk_module, "_utc_now", lambda: FROZEN_NOW)
    monkeypatch.setattr(daily_module, "_today_iso", lambda: "2026-09-28")
    from tradingagents.execution.bridge import ExchangeBridge

    monkeypatch.setattr(
        ExchangeBridge, "sync_portfolio",
        lambda self: PortfolioContext(cash=1_000.0),
    )
    monkeypatch.setattr(ExchangeBridge, "_fetch_price", lambda self, symbol: 50_000.0)
    # plan_order's network path builds the venue client for load_markets;
    # hand it an inert stand-in so no real ccxt client is ever constructed.
    monkeypatch.setattr(
        ExchangeBridge, "_exchange_or_raise",
        lambda self: SimpleNamespace(load_markets=lambda: {}),
    )
    FakeGraph.signals = {"BTC-USD": "Buy", "ETH-USD": "Sell", "SOL-USD": "Hold"}
    FakeGraph.constructed = []
    FakeGraph.propagated = []
    FakeGraph.error_on = None
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.TradingAgentsGraph", FakeGraph
    )
    yield


def make_config(tmp_path, **extra):
    merged = {"exec_log_path": str(tmp_path / "audit.jsonl")}
    merged.update(extra)
    return merged


def read_audit(tmp_path):
    path = tmp_path / "audit.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_missing_auto_confirm_falls_back_with_audit_reason(tmp_path):
    results = run_daily(["BTC-USD"], config=make_config(tmp_path))
    assert len(results) == 1
    result = results[0]
    assert result.signal == "Buy"
    assert result.plan.side == "buy"
    assert result.executed is False
    assert "awaiting approval" in result.reason
    events = read_audit(tmp_path)
    assert events[-1]["action"] == "awaiting_approval"
    assert "exec_auto_confirm" in events[-1]["reason"]


def test_env_auto_confirm_alone_never_arms(tmp_path, monkeypatch):
    # The env flag is only the second half; the config literal is required.
    monkeypatch.setenv("TRADINGAGENTS_EXEC_AUTO_CONFIRM", "true")
    results = run_daily(["BTC-USD"], config=make_config(tmp_path))
    assert results[0].executed is False
    assert "awaiting approval" in results[0].reason


def test_auto_confirm_dry_without_env_flag_falls_back(tmp_path):
    # FR-S2: the third gate needs BOTH halves even for a dry fill -- config
    # literal True alone must not arm unattended execution; the missing env
    # half falls back to waiting for approval, nothing executed.
    results = run_daily(
        ["BTC-USD"], config=make_config(tmp_path, exec_auto_confirm=True)
    )
    result = results[0]
    assert result.executed is False
    assert result.order_id is None
    assert "awaiting approval" in result.reason
    events = read_audit(tmp_path)
    assert events[-1]["action"] == "awaiting_approval"
    assert "TRADINGAGENTS_EXEC_AUTO_CONFIRM" in events[-1]["reason"]


def test_auto_confirm_dry_executes_when_both_gate_halves_open(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_EXEC_AUTO_CONFIRM", "true")
    monkeypatch.delenv("TRADINGAGENTS_EXEC_LIVE", raising=False)
    results = run_daily(
        ["BTC-USD"], config=make_config(tmp_path, exec_auto_confirm=True)
    )
    result = results[0]
    assert result.executed is True
    assert result.order_id is None  # dry fill
    events = read_audit(tmp_path)
    assert events[-1]["action"] == "buy"
    assert events[-1]["phase"] == "execute"
    assert events[-1]["mode"] == "dry"
    assert events[-1]["confirmed"] is True


def test_halt_blocks_execution(tmp_path, monkeypatch):
    from tradingagents.execution.audit import append_event

    config = make_config(tmp_path, exec_auto_confirm=True)
    append_event(
        config["exec_log_path"],
        {"event": "halt", "timestamp": "2026-09-28T10:00:00+00:00", "reason": "streak"},
    )
    results = run_daily(["BTC-USD"], config=config)
    result = results[0]
    assert result.executed is False
    assert result.plan is None  # plan_order refused before returning anything
    assert "halt" in result.reason
    assert read_audit(tmp_path)[-1]["action"] == "rejected_by_risk"


def test_live_auto_confirm_requires_both_live_gates(tmp_path, monkeypatch):
    # config auto-confirm on and exec_live armed, env EXEC_LIVE true -- but
    # the env AUTO_CONFIRM half missing: falls back to approval, nothing sent.
    monkeypatch.setenv("TRADINGAGENTS_EXEC_LIVE", "true")
    monkeypatch.delenv("TRADINGAGENTS_EXEC_AUTO_CONFIRM", raising=False)
    results = run_daily(
        ["BTC-USD"],
        config=make_config(tmp_path, exec_auto_confirm=True, exec_live=True),
    )
    result = results[0]
    assert result.executed is False
    assert "awaiting approval" in result.reason
    assert read_audit(tmp_path)[-1]["action"] == "awaiting_approval"


def test_live_auto_confirm_executes_when_all_gates_open(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_EXEC_LIVE", "true")
    monkeypatch.setenv("TRADINGAGENTS_EXEC_AUTO_CONFIRM", "true")
    from tradingagents.execution.bridge import ExchangeBridge

    sent = []

    def fake_live(self, order, confirm):
        sent.append(order)
        return "order-77"

    monkeypatch.setattr(ExchangeBridge, "_execute_live", fake_live)
    results = run_daily(
        ["BTC-USD"],
        config=make_config(tmp_path, exec_auto_confirm=True, exec_live=True),
    )
    assert results[0].executed is True
    assert results[0].order_id == "order-77"
    assert len(sent) == 1
    # the stubbed _execute_live writes no audit of its own; the last line is
    # the plan line, and the order itself was sent with confirm=True
    assert read_audit(tmp_path)[-1]["action"] == "buy"
    assert sent[0].side == "buy"


def test_coin_failure_is_isolated(tmp_path):
    FakeGraph.error_on = "ETH-USD"
    results = run_daily(["BTC-USD", "ETH-USD"], config=make_config(tmp_path))
    assert [r.ticker for r in results] == ["BTC-USD", "ETH-USD"]
    assert results[0].plan is not None  # first coin went through its policy
    assert results[1].plan is None
    assert "vendor outage" in results[1].reason
    assert len(FakeGraph.constructed) == 2  # a fresh graph per coin


def test_propagate_runs_the_crypto_pipeline_with_utc_today(tmp_path):
    run_daily(["BTC-USD"], config=make_config(tmp_path))
    assert FakeGraph.propagated == [("BTC-USD", "2026-09-28", "crypto")]


def test_watchlist_defaults_to_config(tmp_path):
    results = run_daily(config=make_config(tmp_path))
    assert [r.ticker for r in results] == ["BTC-USD", "ETH-USD"]  # exec_watchlist


def test_watchlist_string_argument_wraps_and_does_not_split(tmp_path):
    # A bare string is one coin, never list()-split into characters.
    results = run_daily("BTC-USD", config=make_config(tmp_path))
    assert [r.ticker for r in results] == ["BTC-USD"]


def test_watchlist_config_string_wraps_and_does_not_split(tmp_path):
    results = run_daily(config=make_config(tmp_path, exec_watchlist="BTC-USD"))
    assert [r.ticker for r in results] == ["BTC-USD"]


def test_watchlist_entries_stripped_empties_dropped_deduped_in_order(tmp_path):
    results = run_daily(
        ["  BTC-USD  ", "", "BTC-USD", "ETH-USD", "   "],
        config=make_config(tmp_path),
    )
    assert [r.ticker for r in results] == ["BTC-USD", "ETH-USD"]


def test_hold_coin_records_reason_without_execution(tmp_path):
    results = run_daily(["SOL-USD"], config=make_config(tmp_path, exec_auto_confirm=True))
    assert results[0].signal == "Hold"
    assert results[0].executed is False
    assert results[0].plan.side is None
    assert "Hold" in results[0].reason


def test_result_shape():
    result = DailyResult(ticker="BTC-USD")
    assert result.executed is False
    assert result.order_id is None
    assert result.signal is None
    assert result.plan is None
