"""Offline R4 examples for trading-cost math and configuration."""

import pandas as pd
import pytest

from tradingagents.default_config import build_default_config
from tradingagents.memory import TradingMemoryLog, settlement
from tradingagents.memory.reflection import Reflector
from tradingagents.memory.settlement import apply_trading_costs


def test_round_trip_cost_example():
    net_raw, net_alpha = apply_trading_costs(0.05, 0.037531, cost_bps=10)
    assert net_raw == pytest.approx(0.04790105)
    assert net_alpha == pytest.approx(0.03543205)
    assert net_raw < 0.05 and net_alpha < 0.037531


def test_r4_default_cost_policy(monkeypatch):
    for name in (
        "TRADINGAGENTS_HOLDING_DAYS",
        "TRADINGAGENTS_USE_COST_ADJUSTED_RETURNS",
        "TRADINGAGENTS_TRADING_COST_BPS",
        "TRADINGAGENTS_MIN_COMMISSION",
        "TRADINGAGENTS_ASSUMED_TRADE_NOTIONAL",
    ):
        monkeypatch.delenv(name, raising=False)
    config = build_default_config()
    assert config["holding_period_days"] == 5
    assert config["use_cost_adjusted_returns"] is True
    assert config["trading_cost_bps"] == 10.0
    assert config["min_commission"] == 0.0
    assert config["assumed_trade_notional"] == 10_000.0


def test_zero_cost_preserves_gross_exactly():
    assert apply_trading_costs(0.05, 0.02, cost_bps=0) == (0.05, 0.02)


def test_minimum_commission_uses_assumed_notional_per_side():
    net_raw, net_alpha = apply_trading_costs(
        0.05, 0.03, cost_bps=10, min_commission=5, trade_notional=2_000,
    )
    assert net_raw == pytest.approx(1.05 * (1 - 0.0025) ** 2 - 1)
    assert net_alpha == pytest.approx(0.03 - (0.05 - net_raw))


def test_negative_return_and_total_loss():
    net_raw, net_alpha = apply_trading_costs(-0.1, -0.12, cost_bps=10)
    assert net_raw == pytest.approx(0.9 * 0.999 ** 2 - 1)
    assert net_alpha < -0.12
    assert apply_trading_costs(-1.0, -1.02, cost_bps=10) == (-1.0, -1.02)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"gross_raw": float("nan")},
        {"gross_alpha": float("inf")},
        {"gross_raw": -1.01},
        {"cost_bps": -1},
        {"cost_bps": float("inf")},
        {"cost_bps": 10_000},
        {"min_commission": -1},
        {"min_commission": 5, "trade_notional": 0},
        {"min_commission": 5, "trade_notional": float("nan")},
    ],
)
def test_invalid_cost_inputs_fail(kwargs):
    args = {"gross_raw": 0.05, "gross_alpha": 0.03, "cost_bps": 10}
    with pytest.raises(ValueError):
        apply_trading_costs(**(args | kwargs))


def test_cost_and_holding_env_overrides(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_HOLDING_DAYS", "21")
    monkeypatch.setenv("TRADINGAGENTS_USE_COST_ADJUSTED_RETURNS", "false")
    monkeypatch.setenv("TRADINGAGENTS_TRADING_COST_BPS", "12.5")
    monkeypatch.setenv("TRADINGAGENTS_MIN_COMMISSION", "5")
    monkeypatch.setenv("TRADINGAGENTS_ASSUMED_TRADE_NOTIONAL", "2000")
    config = build_default_config()
    assert config["holding_period_days"] == 21
    assert config["use_cost_adjusted_returns"] is False
    assert config["trading_cost_bps"] == 12.5
    assert config["min_commission"] == 5.0
    assert config["assumed_trade_notional"] == 2000.0


@pytest.mark.parametrize(
    "name,value",
    [("TRADINGAGENTS_HOLDING_DAYS", "21days"),
     ("TRADINGAGENTS_HOLDING_DAYS", "0"),
     ("TRADINGAGENTS_HOLDING_DAYS", "-1"),
     ("TRADINGAGENTS_USE_COST_ADJUSTED_RETURNS", "maybe")],
)
def test_invalid_env_override_fails(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        build_default_config()


def _price_data(monkeypatch, stock_prices=None):
    dates = pd.bdate_range("2026-01-05", periods=7)
    stock = pd.Series(stock_prices or [99, 100, 101, 102, 103, 104, 105], index=dates[:len(stock_prices)] if stock_prices else dates)
    spy = pd.Series([400, 401, 402, 403, 404, 405, 406], index=dates)
    prices = {"NVDA": stock, "SPY": spy}

    def fake_get_closes(symbol, start_date, end_date):
        series = prices[symbol]
        return series[(series.index >= start_date) & (series.index < end_date)]

    monkeypatch.setattr(settlement, "get_closes", fake_get_closes)


def _pending_log(tmp_path):
    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "memory.md")})
    log.store_decision("NVDA", "2026-01-05", "**Rating**: Buy\n\nThesis")
    return log


class _CaptureReflector:
    def __init__(self):
        self.calls = []

    def reflect_on_final_decision(self, **kwargs):
        self.calls.append(kwargs)
        return "Cost-aware lesson."


def test_cost_adjusted_settlement_passes_both_values_and_writes_net(tmp_path, monkeypatch):
    _price_data(monkeypatch)
    log, reflector = _pending_log(tmp_path), _CaptureReflector()
    config = {"holding_period_days": 5, "use_cost_adjusted_returns": True,
              "trading_cost_bps": 10.0, "min_commission": 0.0,
              "assumed_trade_notional": 10_000.0}

    result = settlement.settle_pending("NVDA", log, reflector, config)

    assert result.settled == [("NVDA", "2026-01-05")]
    assert result.failed == []
    gross_alpha = 0.05 - (406 / 401 - 1)
    assert reflector.calls[0]["gross_raw_return"] == pytest.approx(0.05)
    assert reflector.calls[0]["gross_alpha_return"] == pytest.approx(gross_alpha)
    assert reflector.calls[0]["raw_return"] == pytest.approx(0.04790105)
    assert reflector.calls[0]["alpha_return"] == pytest.approx(gross_alpha - 0.00209895)
    entry = log.load_entries()[0]
    assert (entry["raw"], entry["alpha"], entry["holding"]) == ("+4.8%", "+3.5%", "5d")
    assert entry["resolved"] == "2026-01-13"
    assert settlement.settle_pending("NVDA", log, reflector, config).settled == []
    assert len(reflector.calls) == 1


def test_switch_off_preserves_gross_settlement(tmp_path, monkeypatch):
    _price_data(monkeypatch)
    log, reflector = _pending_log(tmp_path), _CaptureReflector()

    result = settlement.settle_pending(
        "NVDA", log, reflector,
        {"holding_period_days": 5, "use_cost_adjusted_returns": False},
    )

    assert result.settled == [("NVDA", "2026-01-05")]
    assert "gross_raw_return" not in reflector.calls[0]
    assert reflector.calls[0]["raw_return"] == pytest.approx(0.05)
    assert log.load_entries()[0]["raw"] == "+5.0%"


def test_incomplete_window_stays_pending_without_reflection(tmp_path, monkeypatch):
    _price_data(monkeypatch, [100, 101, 102])
    log, reflector = _pending_log(tmp_path), _CaptureReflector()

    result = settlement.settle_pending(
        "NVDA", log, reflector,
        {"holding_period_days": 5, "use_cost_adjusted_returns": True, "trading_cost_bps": 10},
    )

    assert result.settled == result.failed == reflector.calls == []
    assert log.load_entries()[0]["pending"] is True


def test_invalid_cost_config_and_reflection_failure_stay_pending(tmp_path, monkeypatch):
    _price_data(monkeypatch)
    log, reflector = _pending_log(tmp_path), _CaptureReflector()
    config = {"holding_period_days": 5, "use_cost_adjusted_returns": True,
              "trading_cost_bps": -1}

    result = settlement.settle_pending("NVDA", log, reflector, config)
    assert result.settled == []
    assert "invalid cost config" in result.failed[0][2]
    assert reflector.calls == [] and log.load_entries()[0]["pending"] is True

    class _FailingReflector:
        def reflect_on_final_decision(self, **kwargs):
            raise RuntimeError("provider down")

    config["trading_cost_bps"] = 10
    result = settlement.settle_pending("NVDA", log, _FailingReflector(), config)
    assert result.settled == []
    assert "reflection failed" in result.failed[0][2]
    assert log.load_entries()[0]["pending"] is True


class _FakeLLM:
    def __init__(self):
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return type("Response", (), {"content": "Lesson."})()


def test_reflection_shows_gross_and_net_with_regional_benchmark():
    llm = _FakeLLM()
    result = Reflector(llm).reflect_on_final_decision(
        "Buy thesis", raw_return=0.04790105, alpha_return=0.03543205,
        benchmark_name="^N225", holding_days=5,
        gross_raw_return=0.05, gross_alpha_return=0.037531,
    )
    system, human = (content for _, content in llm.messages)
    assert result == "Lesson."
    assert "Gross return over 5 trading days: +5.0%" in human
    assert "Net return after round-trip trading costs: +4.8%" in human
    assert "Gross alpha vs ^N225: +3.8%" in human
    assert "Net alpha vs ^N225: +3.5%" in human
    assert "Use net alpha" in system


def test_reflection_without_gross_values_keeps_legacy_prompt():
    llm = _FakeLLM()
    Reflector(llm).reflect_on_final_decision("Buy thesis", 0.05, 0.02)
    system, human = (content for _, content in llm.messages)
    assert "Raw return over 5 trading days: +5.0%" in human
    assert "Alpha vs SPY: +2.0%" in human
    assert "Gross return" not in human
    assert "round-trip trading costs" not in system


def test_reflection_rejects_half_of_gross_pair():
    llm = _FakeLLM()
    with pytest.raises(ValueError, match="both gross returns"):
        Reflector(llm).reflect_on_final_decision(
            "Buy thesis", 0.04, 0.02, gross_raw_return=0.05,
        )
    assert llm.messages is None
