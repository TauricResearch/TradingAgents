import os
import plistlib
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from scripts.paper_trading_report import format_report

NOW = datetime(2026, 9, 4, 14, tzinfo=timezone.utc)
PROJECT_DIR = Path(__file__).resolve().parents[1]


def test_report_displays_wheel_positions_intents_and_risk_without_credentials(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "private-api-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "private-secret-key")
    account = SimpleNamespace(status="ACTIVE", cash="100000", portfolio_value="120000")
    positions = [
        SimpleNamespace(
            symbol="AAPL261002P00300000",
            asset_class="us_option",
            side="short",
            qty="1",
            market_value="-250",
        )
    ]
    option_intents = [
        (
            "2026-09-04T14:00:00+00:00",
            "AAPL261002P00300000",
            "AAPL",
            "sell_to_open",
            "1",
            "3.10",
            "planned",
        )
    ]
    risk = {
        "wheel_collateral": Decimal("30000"),
        "covered_shares": {"META": Decimal("100")},
        "option_delta_exposure": {"AAPL": Decimal("6400")},
        "combined_forecast_volatility": Decimal("0.149"),
        "gross_leverage": Decimal("1.42"),
        "suppression_reasons": ("earnings blackout: NVDA",),
    }

    report = format_report(account, positions, [], [], option_intents, risk, NOW)

    assert "Option positions" in report
    assert "AAPL261002P00300000" in report
    assert "Option order intents" in report
    assert "Reserved collateral: $30000" in report
    assert "Covered shares: META 100" in report
    assert "Option delta exposure: AAPL $6400" in report
    assert "Combined forecast volatility: 14.90%" in report
    assert "Gross leverage: 1.42x" in report
    assert "Suppression reasons: earnings blackout: NVDA" in report
    assert os.environ["ALPACA_API_KEY"] not in report
    assert os.environ["ALPACA_SECRET_KEY"] not in report
    assert "ALPACA_SECRET_KEY" not in report


def test_report_shows_empty_option_sections_and_unsuppressed_state():
    account = SimpleNamespace(status="ACTIVE", cash="100000", portfolio_value="120000")

    report = format_report(account, [], [], [], [], {}, NOW)

    assert "## Option positions\n- None" in report
    assert "## Option order intents in the last 24 hours\n- None" in report
    assert "Suppression reasons: None" in report


def test_earnings_refresh_plist_is_disabled_and_scheduled_for_weekdays():
    plist_path = PROJECT_DIR / "deploy/com.tradingagents.earnings-refresh.plist.example"
    with plist_path.open("rb") as stream:
        config = plistlib.load(stream)

    assert config["Disabled"] is True
    assert config["RunAtLoad"] is False
    assert config["EnvironmentVariables"]["TZ"] == "America/New_York"
    assert config["ProgramArguments"] == [
        str(PROJECT_DIR / ".venv/bin/python"),
        str(PROJECT_DIR / "scripts/refresh_earnings.py"),
    ]
    assert config["StartCalendarInterval"] == [
        {"Weekday": weekday, "Hour": 8, "Minute": 30}
        for weekday in range(1, 6)
    ]
