# tests/agents/utils/test_historical_context.py
import json
from pathlib import Path

from tradingagents.agents.utils.historical_context import (
    find_latest_prior_analysis,
    find_latest_prior_pm_decision,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_find_latest_prior_analysis_returns_most_recent_before_target(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-04-25" / "RUN1" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "OLD plan"},
    )
    _write(
        base / "2026-04-28" / "RUN2" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "NEW plan"},
    )

    found = find_latest_prior_analysis(
        ticker="AAPL",
        as_of_date="2026-05-01",
        reports_root=base,
        lookback_days=30,
    )

    assert found is not None
    assert found["date"] == "2026-04-28"
    assert found["data"]["trader_investment_plan"] == "NEW plan"


def test_find_latest_prior_analysis_excludes_target_date(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-05-01" / "RUN1" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "TODAY"},
    )
    _write(
        base / "2026-04-28" / "RUN2" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "PRIOR"},
    )

    found = find_latest_prior_analysis(
        ticker="AAPL",
        as_of_date="2026-05-01",
        reports_root=base,
        lookback_days=30,
    )

    assert found is not None
    assert found["date"] == "2026-04-28"


def test_find_latest_prior_analysis_respects_lookback(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-01-01" / "RUN1" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "ANCIENT"},
    )

    found = find_latest_prior_analysis(
        ticker="AAPL",
        as_of_date="2026-05-01",
        reports_root=base,
        lookback_days=30,
    )

    assert found is None


def test_find_latest_prior_analysis_returns_none_when_missing(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    found = find_latest_prior_analysis(
        ticker="AAPL",
        as_of_date="2026-05-01",
        reports_root=base,
        lookback_days=30,
    )
    assert found is None


def test_find_latest_prior_pm_decision(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-04-28" / "RUN1" / "portfolio" / "report" / "00_default_pm_decision.json",
        {"decision": "BUY AAPL 100 shares"},
    )

    found = find_latest_prior_pm_decision(
        portfolio_id="default",
        as_of_date="2026-05-01",
        reports_root=base,
        lookback_days=30,
    )

    assert found is not None
    assert found["date"] == "2026-04-28"
    assert found["data"]["decision"] == "BUY AAPL 100 shares"


def test_find_latest_prior_analysis_picks_later_run_on_same_date(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-04-28" / "RUN_A" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "OLD_RUN"},
    )
    _write(
        base / "2026-04-28" / "RUN_B" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "NEW_RUN"},
    )
    found = find_latest_prior_analysis(
        ticker="AAPL",
        as_of_date="2026-05-01",
        reports_root=base,
        lookback_days=30,
    )
    assert found is not None
    assert found["data"]["trader_investment_plan"] == "NEW_RUN"
