"""Tests for tradingagents/agents/utils/portfolio_tools.py.

All tests use in-memory / temporary-filesystem data — no Supabase DB required.

Coverage:
- get_enriched_holdings: happy path, missing price, invalid JSON, empty list
- compute_portfolio_risk_metrics: happy path, insufficient data, invalid JSON
- load_portfolio_risk_metrics: file present, file missing, invalid JSON input
- load_portfolio_decision: file present, file missing

Run::

    pytest tests/unit/test_portfolio_tools.py -v
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tradingagents.agents.utils.portfolio_tools import (
    compute_portfolio_risk_metrics,
    get_enriched_holdings,
    load_portfolio_decision,
    load_portfolio_risk_metrics,
)
from tradingagents.portfolio.models import Holding, Portfolio, PortfolioSnapshot
from tradingagents.portfolio.report_store import ReportStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


PORTFOLIO_ID = "aaaa1111-0000-0000-0000-000000000001"
DATE = "2026-03-20"


@pytest.fixture
def sample_holdings_list() -> list[dict]:
    return [
        {
            "holding_id": "h1",
            "portfolio_id": PORTFOLIO_ID,
            "ticker": "AAPL",
            "shares": 100.0,
            "avg_cost": 150.0,
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "created_at": "",
            "updated_at": "",
        },
        {
            "holding_id": "h2",
            "portfolio_id": PORTFOLIO_ID,
            "ticker": "MSFT",
            "shares": 50.0,
            "avg_cost": 300.0,
            "sector": "Technology",
            "industry": "Software",
            "created_at": "",
            "updated_at": "",
        },
    ]


@pytest.fixture
def sample_prices() -> dict[str, float]:
    return {"AAPL": 182.50, "MSFT": 420.00}


@pytest.fixture
def sample_snapshots() -> list[dict]:
    """30 snapshot dicts for risk metrics computation."""
    navs = [100_000.0 * (1.001 ** i) for i in range(30)]
    return [
        {
            "snapshot_id": f"snap-{i}",
            "portfolio_id": PORTFOLIO_ID,
            "snapshot_date": f"2026-02-{i + 1:02d}",
            "total_value": v,
            "cash": 0.0,
            "equity_value": v,
            "num_positions": 2,
            "holdings_snapshot": [],
            "metadata": {},
        }
        for i, v in enumerate(navs)
    ]


@pytest.fixture
def tmp_reports(tmp_path: Path) -> Path:
    """Temporary reports directory backed by pytest tmp_path."""
    d = tmp_path / "reports"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Tests: get_enriched_holdings
# ---------------------------------------------------------------------------


class TestGetEnrichedHoldings:
    def test_happy_path_returns_enriched_data(
        self, sample_holdings_list, sample_prices
    ):
        result_str = get_enriched_holdings.invoke(
            {
                "holdings_json": json.dumps(sample_holdings_list),
                "prices_json": json.dumps(sample_prices),
                "portfolio_cash": 10_000.0,
            }
        )
        result = json.loads(result_str)

        assert "holdings" in result
        assert "portfolio_summary" in result
        assert len(result["holdings"]) == 2

        aapl = next(h for h in result["holdings"] if h["ticker"] == "AAPL")
        assert aapl["current_price"] == pytest.approx(182.50)
        assert aapl["current_value"] == pytest.approx(182.50 * 100.0)
        assert aapl["cost_basis"] == pytest.approx(150.0 * 100.0)
        assert aapl["unrealized_pnl"] == pytest.approx((182.50 - 150.0) * 100.0)

        summary = result["portfolio_summary"]
        equity = 182.50 * 100 + 420.0 * 50
        total = 10_000.0 + equity
        assert summary["total_value"] == pytest.approx(total)
        assert summary["cash"] == pytest.approx(10_000.0)
        assert summary["cash_pct"] == pytest.approx(10_000.0 / total)

    def test_holding_with_missing_price_has_none_enrichment(
        self, sample_holdings_list
    ):
        # Only AAPL price provided — MSFT enrichment should remain None
        prices = {"AAPL": 182.50}
        result_str = get_enriched_holdings.invoke(
            {
                "holdings_json": json.dumps(sample_holdings_list),
                "prices_json": json.dumps(prices),
                "portfolio_cash": 0.0,
            }
        )
        result = json.loads(result_str)
        msft = next(h for h in result["holdings"] if h["ticker"] == "MSFT")
        assert msft["current_price"] is None

    def test_empty_holdings_returns_zero_equity(self, sample_prices):
        result_str = get_enriched_holdings.invoke(
            {
                "holdings_json": "[]",
                "prices_json": json.dumps(sample_prices),
                "portfolio_cash": 50_000.0,
            }
        )
        result = json.loads(result_str)
        assert result["holdings"] == []
        assert result["portfolio_summary"]["equity_value"] == pytest.approx(0.0)
        assert result["portfolio_summary"]["total_value"] == pytest.approx(50_000.0)

    def test_invalid_holdings_json_returns_error(self, sample_prices):
        result_str = get_enriched_holdings.invoke(
            {
                "holdings_json": "not-json",
                "prices_json": json.dumps(sample_prices),
                "portfolio_cash": 0.0,
            }
        )
        result = json.loads(result_str)
        assert "error" in result

    def test_invalid_prices_json_returns_error(self, sample_holdings_list):
        result_str = get_enriched_holdings.invoke(
            {
                "holdings_json": json.dumps(sample_holdings_list),
                "prices_json": "{bad json}",
                "portfolio_cash": 0.0,
            }
        )
        result = json.loads(result_str)
        assert "error" in result

    def test_weight_sums_to_equity_fraction(
        self, sample_holdings_list, sample_prices
    ):
        result_str = get_enriched_holdings.invoke(
            {
                "holdings_json": json.dumps(sample_holdings_list),
                "prices_json": json.dumps(sample_prices),
                "portfolio_cash": 0.0,
            }
        )
        result = json.loads(result_str)
        total_weight = sum(
            h["weight"] for h in result["holdings"] if h["weight"] is not None
        )
        assert total_weight == pytest.approx(1.0, rel=1e-4)

    def test_zero_cash_with_holdings(self, sample_holdings_list, sample_prices):
        result_str = get_enriched_holdings.invoke(
            {
                "holdings_json": json.dumps(sample_holdings_list),
                "prices_json": json.dumps(sample_prices),
                "portfolio_cash": 0.0,
            }
        )
        result = json.loads(result_str)
        summary = result["portfolio_summary"]
        assert summary["cash_pct"] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Tests: compute_portfolio_risk_metrics
# ---------------------------------------------------------------------------


class TestComputePortfolioRiskMetrics:
    def test_happy_path_30_snapshots(self, sample_snapshots):
        result_str = compute_portfolio_risk_metrics.invoke(
            {
                "nav_history_json": json.dumps(sample_snapshots),
                "benchmark_returns_json": "[]",
            }
        )
        result = json.loads(result_str)
        assert "sharpe" in result
        assert "sortino" in result
        assert "var_95" in result
        assert "max_drawdown" in result
        assert "return_stats" in result
        assert result["return_stats"]["n_days"] == 29

    def test_single_snapshot_returns_none_metrics(self):
        snap = {
            "snapshot_id": "s1",
            "portfolio_id": PORTFOLIO_ID,
            "snapshot_date": "2026-01-01",
            "total_value": 100_000.0,
            "cash": 0.0,
            "equity_value": 100_000.0,
            "num_positions": 0,
        }
        result_str = compute_portfolio_risk_metrics.invoke(
            {
                "nav_history_json": json.dumps([snap]),
                "benchmark_returns_json": "[]",
            }
        )
        result = json.loads(result_str)
        assert result["sharpe"] is None
        assert result["var_95"] is None

    def test_invalid_nav_json_returns_error(self):
        result_str = compute_portfolio_risk_metrics.invoke(
            {
                "nav_history_json": "not-json",
                "benchmark_returns_json": "[]",
            }
        )
        result = json.loads(result_str)
        assert "error" in result

    def test_invalid_snapshot_record_returns_error(self):
        bad_snap = {"total_value": 100.0}  # missing required fields
        result_str = compute_portfolio_risk_metrics.invoke(
            {
                "nav_history_json": json.dumps([bad_snap]),
                "benchmark_returns_json": "[]",
            }
        )
        result = json.loads(result_str)
        assert "error" in result

    def test_with_benchmark_returns_beta(self, sample_snapshots):
        # Use a non-constant benchmark so variance > 0 and beta is computed
        bench = [0.001 * (1 + 0.1 * (i % 5 - 2)) for i in range(29)]
        result_str = compute_portfolio_risk_metrics.invoke(
            {
                "nav_history_json": json.dumps(sample_snapshots),
                "benchmark_returns_json": json.dumps(bench),
            }
        )
        result = json.loads(result_str)
        assert result["beta"] is not None

    def test_empty_list_returns_null_metrics(self):
        result_str = compute_portfolio_risk_metrics.invoke(
            {
                "nav_history_json": "[]",
                "benchmark_returns_json": "[]",
            }
        )
        result = json.loads(result_str)
        assert result["sharpe"] is None
        assert result["return_stats"]["n_days"] == 0


# ---------------------------------------------------------------------------
# Tests: load_portfolio_risk_metrics
# ---------------------------------------------------------------------------


class TestLoadPortfolioRiskMetrics:
    def test_returns_metrics_when_file_exists(self, tmp_reports):
        store = ReportStore(base_dir=tmp_reports)
        metrics = {"sharpe": 1.23, "sortino": 1.87, "var_95": 0.018}
        store.save_risk_metrics(DATE, PORTFOLIO_ID, metrics)

        result_str = load_portfolio_risk_metrics.invoke(
            {
                "portfolio_id": PORTFOLIO_ID,
                "date": DATE,
                "reports_dir": str(tmp_reports),
            }
        )
        result = json.loads(result_str)
        assert result["sharpe"] == pytest.approx(1.23)
        assert result["sortino"] == pytest.approx(1.87)

    def test_returns_error_when_file_missing(self, tmp_reports):
        result_str = load_portfolio_risk_metrics.invoke(
            {
                "portfolio_id": "nonexistent-id",
                "date": DATE,
                "reports_dir": str(tmp_reports),
            }
        )
        result = json.loads(result_str)
        assert "error" in result
        assert "nonexistent-id" in result["error"]

    def test_loaded_metrics_match_saved(self, tmp_reports):
        store = ReportStore(base_dir=tmp_reports)
        full_metrics = {
            "sharpe": 0.85,
            "sortino": 1.10,
            "var_95": 0.025,
            "max_drawdown": -0.12,
            "beta": 0.93,
            "sector_concentration": {"Technology": 40.0, "Healthcare": 20.0},
            "return_stats": {"mean_daily": 0.0003, "std_daily": 0.009, "n_days": 60},
        }
        store.save_risk_metrics(DATE, PORTFOLIO_ID, full_metrics)

        result_str = load_portfolio_risk_metrics.invoke(
            {
                "portfolio_id": PORTFOLIO_ID,
                "date": DATE,
                "reports_dir": str(tmp_reports),
            }
        )
        result = json.loads(result_str)
        assert result["beta"] == pytest.approx(0.93)
        assert result["sector_concentration"]["Technology"] == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# Tests: load_portfolio_decision
# ---------------------------------------------------------------------------


class TestLoadPortfolioDecision:
    def test_returns_decision_when_file_exists(self, tmp_reports):
        store = ReportStore(base_dir=tmp_reports)
        decision = {
            "sells": [{"ticker": "XYZ", "shares": 50, "rationale": "Stop loss triggered"}],
            "buys": [{"ticker": "AAPL", "shares": 10, "rationale": "Strong momentum"}],
            "holds": ["MSFT", "GOOGL"],
            "target_cash_pct": 0.05,
        }
        store.save_pm_decision(DATE, PORTFOLIO_ID, decision)

        result_str = load_portfolio_decision.invoke(
            {
                "portfolio_id": PORTFOLIO_ID,
                "date": DATE,
                "reports_dir": str(tmp_reports),
            }
        )
        result = json.loads(result_str)
        assert result["sells"][0]["ticker"] == "XYZ"
        assert result["buys"][0]["ticker"] == "AAPL"
        assert "MSFT" in result["holds"]

    def test_returns_error_when_file_missing(self, tmp_reports):
        result_str = load_portfolio_decision.invoke(
            {
                "portfolio_id": "no-such-portfolio",
                "date": DATE,
                "reports_dir": str(tmp_reports),
            }
        )
        result = json.loads(result_str)
        assert "error" in result
        assert "no-such-portfolio" in result["error"]

    def test_decision_fields_preserved(self, tmp_reports):
        store = ReportStore(base_dir=tmp_reports)
        decision = {
            "sells": [],
            "buys": [],
            "holds": ["AAPL"],
            "target_cash_pct": 0.10,
            "rationale": "Market uncertainty — staying defensive.",
        }
        store.save_pm_decision(DATE, PORTFOLIO_ID, decision)

        result_str = load_portfolio_decision.invoke(
            {
                "portfolio_id": PORTFOLIO_ID,
                "date": DATE,
                "reports_dir": str(tmp_reports),
            }
        )
        result = json.loads(result_str)
        assert result["rationale"] == "Market uncertainty — staying defensive."
        assert result["target_cash_pct"] == pytest.approx(0.10)
