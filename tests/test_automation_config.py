from pathlib import Path

import pytest

from tradingagents.automation import AutomationSettings, partition_watchlist


def _config(**overrides):
    base = {
        "watchlist": "AAPL,MSFT,NVDA,AMZN,META,GOOG,TSLA",
        "batch_size": 3,
        "analysis_interval_minutes": 30,
        "position_interval_minutes": 30,
        "max_cash_allocation": 0.30,
        "decision_max_age_minutes": 120,
        "rebalance_threshold_usd": 10.0,
        "automation_state_path": "/tmp/tradingagents-state.db",
        "auto_execute": False,
        "alpaca_mode": "paper",
        "live_trading_ack": "",
    }
    base.update(overrides)
    return base


def test_settings_require_exactly_seven_unique_symbols():
    with pytest.raises(ValueError, match="exactly 7 unique symbols"):
        AutomationSettings.from_config(_config(watchlist="AAPL,AAPL,MSFT"))


def test_settings_normalize_watchlist_and_keep_hard_cap():
    settings = AutomationSettings.from_config(
        _config(watchlist=" aapl, msft,nvda,amzn,meta,goog,tsla ")
    )
    assert settings.watchlist == ("AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG", "TSLA")
    assert settings.max_cash_allocation == 0.30
    assert settings.state_path == Path("/tmp/tradingagents-state.db")


def test_settings_reject_allocation_above_thirty_percent():
    with pytest.raises(ValueError, match="no greater than 0.30"):
        AutomationSettings.from_config(_config(max_cash_allocation=0.31))


def test_partition_patterns_cover_every_symbol_once():
    symbols = ("A", "B", "C", "D", "E", "F", "G")
    assert partition_watchlist(symbols, 3) == (("A", "B", "C"), ("D", "E"), ("F", "G"))
    assert partition_watchlist(symbols, 2) == (("A", "B"), ("C", "D"), ("E", "F", "G"))
