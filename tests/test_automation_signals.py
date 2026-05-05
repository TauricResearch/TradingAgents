from pathlib import Path

import pytest

from automation.signals import MarketSnapshot, build_signal


def _state(rating: str, trader: str = ""):
    return {
        "final_trade_decision": f"**Rating**: {rating}\n\n**Executive Summary**: test",
        "trader_investment_plan": trader,
    }


@pytest.mark.unit
def test_buy_signal_uses_atr_levels_when_llm_levels_absent(tmp_path: Path):
    signal = build_signal(
        ticker="CFISP500.SN",
        analysis_date="2026-05-04",
        final_state=_state("Buy"),
        report_path=tmp_path / "complete_report.md",
        risk_config={"stop_atr_multiple": 1.5, "take_profit_atr_multiple": 2.5, "min_reward_risk": 1.5},
        snapshot=MarketSnapshot("CFISP500.SN", close=100.0, atr=2.0),
    )

    assert signal.action == "BUY"
    assert signal.entry_price == 100.0
    assert signal.stop_loss == 97.0
    assert signal.take_profit == 105.0
    assert signal.risk_reward == 1.67


@pytest.mark.unit
def test_hold_signal_does_not_emit_entry(tmp_path: Path):
    signal = build_signal(
        ticker="CFIETFIPSA.SN",
        analysis_date="2026-05-04",
        final_state=_state("Hold"),
        report_path=tmp_path / "complete_report.md",
        risk_config={},
        snapshot=MarketSnapshot("CFIETFIPSA.SN", close=50.0, atr=1.0),
    )

    assert signal.action == "HOLD"
    assert signal.entry_price is None
    assert signal.position_bias == "watchlist"


@pytest.mark.unit
def test_overweight_degrades_when_llm_target_has_bad_reward_risk(tmp_path: Path):
    signal = build_signal(
        ticker="CFISP500.SN",
        analysis_date="2026-05-04",
        final_state={
            "final_trade_decision": "**Rating**: Overweight\n\n**Price Target**: 101",
            "trader_investment_plan": "",
        },
        report_path=tmp_path / "complete_report.md",
        risk_config={"min_reward_risk": 1.5},
        snapshot=MarketSnapshot("CFISP500.SN", close=100.0, atr=2.0),
    )

    assert signal.action == "HOLD"
    assert signal.position_bias == "watchlist"


@pytest.mark.unit
def test_markdown_llm_levels_are_used(tmp_path: Path):
    signal = build_signal(
        ticker="CFISP500.SN",
        analysis_date="2026-05-04",
        final_state={
            "final_trade_decision": "**Rating**: Buy\n\n**Price Target**: 112",
            "trader_investment_plan": "**Entry Price**: 101\n\n**Stop Loss**: 96",
        },
        report_path=tmp_path / "complete_report.md",
        risk_config={"min_reward_risk": 1.5},
        snapshot=MarketSnapshot("CFISP500.SN", close=100.0, atr=2.0),
    )

    assert signal.action == "BUY"
    assert signal.entry_price == 101.0
    assert signal.stop_loss == 96.0
    assert signal.take_profit == 112.0


@pytest.mark.unit
def test_market_symbol_override_keeps_public_ticker(tmp_path: Path, monkeypatch):
    captured = {}

    def fake_snapshot(symbol, *, atr_period=14):
        captured["symbol"] = symbol
        return MarketSnapshot(symbol, close=100.0, atr=2.0)

    monkeypatch.setattr("automation.signals.fetch_market_snapshot", fake_snapshot)
    signal = build_signal(
        ticker="CFIETFIPSA.SN",
        analysis_date="2026-05-04",
        final_state=_state("Buy"),
        report_path=tmp_path / "complete_report.md",
        risk_config={},
        market_symbol="CFIIPSA.SN",
    )

    assert captured["symbol"] == "CFIIPSA.SN"
    assert signal.ticker == "CFIETFIPSA.SN"
