import os
import plistlib
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from scripts import paper_trading_report as paper_report
from scripts.paper_trading_report import build_report, format_report
from tradingagents.automation_state import AutomationState
from tradingagents.execution import AccountSnapshot
from tradingagents.options import EquityPosition, OptionContract, OptionOpenOrder, OptionPosition

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


def test_build_report_computes_current_normalized_wheel_risk(monkeypatch, tmp_path):
    state_path = tmp_path / "state.db"
    with AutomationState(state_path) as state:
        for task, reason in (
            ("analysis", "waiting for fresh decisions"),
            ("options", "earnings blackout: NVDA"),
        ):
            assert state.try_acquire_lease(task, "report-test", NOW, 60)
            assert state.complete_task_run(
                task,
                "report-test",
                NOW,
                NOW,
                suppression_reason=reason,
            )

    symbols = ("AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG", "TSLA")

    class Client:
        def get_account(self):
            return SimpleNamespace(status="ACTIVE", cash="70000", portfolio_value="100000")

        def get_all_positions(self):
            return []

        def get_orders(self, filter):
            return []

    class Broker:
        def account(self):
            return AccountSnapshot(
                Decimal("70000"),
                Decimal("200000"),
                False,
                "ACTIVE",
                Decimal("100000"),
                Decimal("70000"),
            )

        def wheel_positions_and_orders(self):
            return (
                (
                    EquityPosition("AAPL", Decimal("100"), Decimal("90"), Decimal("100")),
                    EquityPosition("META", Decimal("100"), Decimal("90"), Decimal("100")),
                ),
                (
                    OptionPosition(
                        "AAPL261002P00090000",
                        "AAPL",
                        "put",
                        Decimal("-1"),
                        Decimal("3"),
                        Decimal("-0.20"),
                    ),
                    OptionPosition(
                        "META261002C00110000",
                        "META",
                        "call",
                        Decimal("-1"),
                        Decimal("3"),
                        Decimal("0.20"),
                    ),
                ),
                (
                    OptionOpenOrder(
                        "GOOG261002P00090000",
                        "GOOG",
                        "put",
                        "sell_to_open",
                        Decimal("1"),
                        Decimal("0.25"),
                        Decimal("90"),
                    ),
                ),
            )

        def latest_price(self, symbol):
            return Decimal("100")

        def daily_closes(self, requested):
            assert requested == symbols
            start = date(2026, 7, 1)
            result = {}
            for offset, symbol in enumerate(symbols, start=1):
                price = Decimal("100")
                rows = [(start, price)]
                for index in range(40):
                    change = Decimal("0.001") * offset * (1 if index % 2 == 0 else -1)
                    price *= Decimal("1") + change
                    rows.append((start + timedelta(days=index + 1), price))
                result[symbol] = tuple(rows)
            return result

        def option_contract(self, symbol, now):
            assert symbol == "GOOG261002P00090000"
            assert now == NOW
            return OptionContract(
                symbol,
                "GOOG",
                "put",
                Decimal("90"),
                date(2026, 10, 2),
                Decimal("-0.25"),
                Decimal("3.00"),
                Decimal("3.10"),
                Decimal("500"),
                NOW - timedelta(seconds=30),
            )

    client = Client()
    broker = Broker()
    monkeypatch.setenv("TRADINGAGENTS_ALPACA_MODE", "paper")
    monkeypatch.setenv("ALPACA_API_KEY", "private-api-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "private-secret-key")
    monkeypatch.setenv("TRADINGAGENTS_AUTOMATION_STATE_PATH", str(state_path))
    monkeypatch.setattr(paper_report, "TradingClient", lambda *args, **kwargs: client)
    monkeypatch.setattr(paper_report, "AlpacaBroker", lambda *args, **kwargs: broker)

    report = build_report(NOW)

    assert "Reserved collateral: $15750.00" in report
    assert "Covered shares: META 100" in report
    assert "Option delta exposure: AAPL $2000.00, GOOG $1875.0000, META $-2000.00" in report
    assert "Combined forecast volatility: Unavailable" not in report
    assert "Gross leverage: 0.25875x" in report
    assert f"analysis as of {NOW.isoformat()}: waiting for fresh decisions" in report
    assert f"options as of {NOW.isoformat()}: earnings blackout: NVDA" in report
    assert "private-api-key" not in report
    assert "private-secret-key" not in report


def test_current_risk_fails_closed_when_pending_order_contract_quote_is_invalid():
    order = OptionOpenOrder(
        "GOOG261002P00090000",
        "GOOG",
        "put",
        "sell_to_open",
        Decimal("1"),
        Decimal("0"),
        Decimal("90"),
    )
    valid_contract = OptionContract(
        order.symbol,
        order.underlying,
        order.kind,
        order.strike,
        date(2026, 10, 2),
        Decimal("-0.25"),
        Decimal("3.00"),
        Decimal("3.10"),
        Decimal("500"),
        NOW - timedelta(seconds=30),
    )

    class Broker:
        def account(self):
            return SimpleNamespace(equity=Decimal("100000"))

        def wheel_positions_and_orders(self):
            return (), (), (order,)

        def latest_price(self, symbol):
            return Decimal("100")

        def option_contract(self, symbol, now):
            return replace(valid_contract, bid=Decimal("-1"))

    summary = paper_report._current_risk_summary(
        Broker(),
        ("AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG", "TSLA"),
        (),
        NOW,
    )

    assert "combined_forecast_volatility" not in summary
    assert summary["suppression_reasons"] == (
        "risk: Unavailable (current broker data invalid)",
    )


def test_suppression_outcomes_render_fresh_as_of_and_stale_state(tmp_path):
    state_path = tmp_path / "state.db"
    analysis_time = NOW - timedelta(minutes=31)
    options_time = NOW - timedelta(minutes=15)
    with AutomationState(state_path) as state:
        for task, ran_at, reason in (
            ("analysis", analysis_time, "analysis delayed"),
            ("options", options_time, None),
        ):
            assert state.try_acquire_lease(task, "outcome-test", ran_at, 60)
            assert state.complete_task_run(
                task,
                "outcome-test",
                ran_at,
                ran_at,
                suppression_reason=reason,
            )

    assert paper_report._suppression_outcomes(state_path, NOW, 30) == (
        f"analysis: Unavailable (stale; as of {analysis_time.isoformat()})",
        f"options as of {options_time.isoformat()}: None",
    )


def test_earnings_refresh_plist_is_disabled_and_periodic():
    plist_path = PROJECT_DIR / "deploy/com.tradingagents.earnings-refresh.plist.example"
    with plist_path.open("rb") as stream:
        config = plistlib.load(stream)

    assert config["Disabled"] is True
    assert config["RunAtLoad"] is False
    assert config["WorkingDirectory"] == str(PROJECT_DIR)
    assert config["ProgramArguments"] == [
        str(PROJECT_DIR / ".venv/bin/python"),
        str(PROJECT_DIR / "scripts/refresh_earnings.py"),
        "--scheduled",
    ]
    assert config["StartInterval"] == 60
    assert "StartCalendarInterval" not in config
