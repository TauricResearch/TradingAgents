from pathlib import Path

import pytest

from tradingagents.automation import AutomationSettings, partition_watchlist
from tradingagents.default_config import _ENV_OVERRIDES


def _config(**overrides):
    base = {
        "watchlist": "AAPL,MSFT,NVDA,AMZN,META,GOOG,TSLA",
        "batch_size": 3,
        "analysis_interval_minutes": 30,
        "position_interval_minutes": 30,
        "max_cash_allocation": 0.30,
        "target_volatility": 0.15,
        "max_volatility": 0.20,
        "max_gross_leverage": 2.0,
        "decision_max_age_minutes": 120,
        "rebalance_threshold_usd": 10.0,
        "automation_state_path": "/tmp/tradingagents-state.db",
        "auto_execute": False,
        "alpaca_mode": "paper",
        "live_trading_ack": "",
        "options_enabled": False,
        "options_auto_execute": False,
        "options_max_equity_fraction": 0.20,
        "options_entry_time_et": "10:00",
        "options_earnings_path": "/tmp/earnings.json",
        "live_options_ack": "",
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


def test_settings_accept_volatility_policy():
    settings = AutomationSettings.from_config(
        _config(
            target_volatility=0.15,
            max_volatility=0.20,
            max_gross_leverage=2.0,
        )
    )
    assert settings.target_volatility == 0.15
    assert settings.max_volatility == 0.20
    assert settings.max_gross_leverage == 2.0


def test_options_defaults_are_safe():
    settings = AutomationSettings.from_config(
        _config(
            options_enabled=False,
            options_auto_execute=False,
            options_max_equity_fraction=0.20,
            options_entry_time_et="10:00",
            options_earnings_path="/tmp/earnings.json",
            live_options_ack="",
        )
    )
    assert not settings.options_enabled
    assert not settings.options_auto_execute
    assert settings.options_max_equity_fraction == 0.20


def test_options_fraction_cannot_exceed_twenty_percent():
    with pytest.raises(ValueError, match="no greater than 0.20"):
        AutomationSettings.from_config(_config(options_max_equity_fraction=0.21))


@pytest.mark.parametrize(
    "values",
    [
        {"target_volatility": 0},
        {"target_volatility": 0.21, "max_volatility": 0.20},
        {"max_volatility": 0.21},
        {"max_gross_leverage": 2.01},
    ],
)
def test_settings_reject_invalid_volatility_policy(values):
    with pytest.raises(ValueError):
        AutomationSettings.from_config(_config(**values))


def test_settings_reject_allocation_above_thirty_percent():
    with pytest.raises(ValueError, match="no greater than 0.30"):
        AutomationSettings.from_config(_config(max_cash_allocation=0.31))


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"batch_size": 4}, "batch_size must be 2 or 3"),
        ({"alpaca_mode": "sandbox"}, "alpaca_mode must be paper or live"),
        ({"analysis_interval_minutes": 0}, "intervals and decision age must be positive"),
        ({"position_interval_minutes": 0}, "intervals and decision age must be positive"),
        ({"decision_max_age_minutes": 0}, "intervals and decision age must be positive"),
        ({"max_cash_allocation": 0}, "max_cash_allocation must be greater than 0"),
        ({"rebalance_threshold_usd": -1}, "rebalance_threshold_usd must be non-negative"),
    ],
)
def test_settings_reject_other_invalid_automation_values(override, message):
    with pytest.raises(ValueError, match=message):
        AutomationSettings.from_config(_config(**override))


def test_partition_patterns_cover_every_symbol_once():
    symbols = ("A", "B", "C", "D", "E", "F", "G")
    assert partition_watchlist(symbols, 3) == (("A", "B", "C"), ("D", "E"), ("F", "G"))
    assert partition_watchlist(symbols, 2) == (("A", "B"), ("C", "D"), ("E", "F", "G"))


def test_env_example_documents_every_automation_override():
    text = Path(".env.example").read_text()
    automation_vars = {
        name
        for name, key in _ENV_OVERRIDES.items()
        if key
        in {
            "watchlist",
            "batch_size",
            "analysis_interval_minutes",
            "position_interval_minutes",
            "max_cash_allocation",
            "decision_max_age_minutes",
            "rebalance_threshold_usd",
            "automation_state_path",
            "auto_execute",
            "alpaca_mode",
            "live_trading_ack",
        }
    }
    assert automation_vars
    assert all(name in text for name in automation_vars)


def test_env_example_documents_every_option_and_risk_override():
    text = Path(".env.example").read_text()
    required = {
        "TRADINGAGENTS_TARGET_VOLATILITY",
        "TRADINGAGENTS_MAX_VOLATILITY",
        "TRADINGAGENTS_MAX_GROSS_LEVERAGE",
        "TRADINGAGENTS_OPTIONS_ENABLED",
        "TRADINGAGENTS_OPTIONS_AUTO_EXECUTE",
        "TRADINGAGENTS_OPTIONS_MAX_EQUITY_FRACTION",
        "TRADINGAGENTS_OPTIONS_ENTRY_TIME_ET",
        "TRADINGAGENTS_OPTIONS_EARNINGS_PATH",
        "TRADINGAGENTS_LIVE_OPTIONS_ACK",
    }
    assert all(name in text for name in required)
