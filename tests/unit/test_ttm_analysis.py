"""Tests for TTM (Trailing Twelve Months) analysis module."""

import pytest
import pandas as pd


# ---------------------------------------------------------------------------
# Fixtures — synthetic quarterly data
# ---------------------------------------------------------------------------

def _make_income_csv(n_quarters: int = 8) -> str:
    """Create synthetic income statement CSV (yfinance layout: rows=metrics, cols=dates)."""
    dates = [f"2023-0{i+1}-01" if i < 9 else f"2023-{i+1}-01" for i in range(n_quarters)]
    # Revenue grows 5% each quarter
    revenues = [10_000_000_000 * (1.05 ** i) for i in range(n_quarters)]
    # Gross profit = 40% of revenue
    gross_profits = [r * 0.40 for r in revenues]
    # Operating income = 20% of revenue
    op_incomes = [r * 0.20 for r in revenues]
    # Net income = 15% of revenue
    net_incomes = [r * 0.15 for r in revenues]

    data = {
        "Total Revenue": revenues,
        "Gross Profit": gross_profits,
        "Operating Income": op_incomes,
        "Net Income": net_incomes,
    }
    df = pd.DataFrame(data, index=pd.to_datetime(dates))
    return df.to_csv()


def _make_balance_csv(n_quarters: int = 8) -> str:
    dates = [f"2023-0{i+1}-01" if i < 9 else f"2023-{i+1}-01" for i in range(n_quarters)]
    data = {
        "Total Assets": [50_000_000_000] * n_quarters,
        "Total Debt": [10_000_000_000] * n_quarters,
        "Stockholders Equity": [20_000_000_000] * n_quarters,
    }
    df = pd.DataFrame(data, index=pd.to_datetime(dates))
    return df.to_csv()


def _make_cashflow_csv(n_quarters: int = 8) -> str:
    dates = [f"2023-0{i+1}-01" if i < 9 else f"2023-{i+1}-01" for i in range(n_quarters)]
    data = {
        "Free Cash Flow": [2_000_000_000] * n_quarters,
        "Operating Cash Flow": [3_000_000_000] * n_quarters,
    }
    df = pd.DataFrame(data, index=pd.to_datetime(dates))
    return df.to_csv()


# ---------------------------------------------------------------------------
# Unit tests for _find_col
# ---------------------------------------------------------------------------

class TestFindCol:
    def setup_method(self):
        from tradingagents.dataflows.ttm_analysis import _find_col
        self.find_col = _find_col

    def test_find_col_match(self):
        """Should return the matching column name."""
        df = pd.DataFrame({"Revenue": [1, 2, 3], "Cost": [4, 5, 6]})
        assert self.find_col(df, ["Revenue", "Total Revenue"]) == "Revenue"

    def test_find_col_no_match(self):
        """Should return None if no candidate matches."""
        df = pd.DataFrame({"Cost": [4, 5, 6], "Profit": [7, 8, 9]})
        assert self.find_col(df, ["Revenue", "Total Revenue"]) is None

    def test_find_col_empty_df(self):
        """Should return None for empty DataFrame."""
        df = pd.DataFrame()
        assert self.find_col(df, ["Revenue", "Total Revenue"]) is None


# ---------------------------------------------------------------------------
# Unit tests for compute_ttm_metrics
# ---------------------------------------------------------------------------

class TestComputeTTMMetrics:
    def setup_method(self):
        from tradingagents.dataflows.ttm_analysis import compute_ttm_metrics
        self.compute = compute_ttm_metrics

    def test_quarters_available_8(self):
        result = self.compute(
            _make_income_csv(8), _make_balance_csv(8), _make_cashflow_csv(8)
        )
        assert result["quarters_available"] == 8

    def test_quarters_available_4(self):
        """Gracefully handles <8 quarters."""
        result = self.compute(
            _make_income_csv(4), _make_balance_csv(4), _make_cashflow_csv(4)
        )
        assert result["quarters_available"] == 4

    def test_ttm_revenue_is_sum_of_last_4_quarters(self):
        result = self.compute(
            _make_income_csv(8), _make_balance_csv(8), _make_cashflow_csv(8)
        )
        # Last 4 quarters have indices 4,5,6,7 with revenues:
        # 10B * 1.05^4, ..., 10B * 1.05^7
        expected = sum(10_000_000_000 * (1.05 ** i) for i in range(4, 8))
        actual = result["ttm"]["revenue"]
        assert actual is not None
        assert abs(actual - expected) / expected < 0.001  # within 0.1%

    def test_ttm_net_income_is_sum_of_last_4_quarters(self):
        result = self.compute(
            _make_income_csv(8), _make_balance_csv(8), _make_cashflow_csv(8)
        )
        expected = sum(10_000_000_000 * (1.05 ** i) * 0.15 for i in range(4, 8))
        actual = result["ttm"]["net_income"]
        assert actual is not None
        assert abs(actual - expected) / expected < 0.001

    def test_ttm_gross_margin_approximately_40pct(self):
        result = self.compute(
            _make_income_csv(8), _make_balance_csv(8), _make_cashflow_csv(8)
        )
        gm = result["ttm"]["gross_margin_pct"]
        assert gm is not None
        assert abs(gm - 40.0) < 0.5

    def test_ttm_net_margin_approximately_15pct(self):
        result = self.compute(
            _make_income_csv(8), _make_balance_csv(8), _make_cashflow_csv(8)
        )
        nm = result["ttm"]["net_margin_pct"]
        assert nm is not None
        assert abs(nm - 15.0) < 0.5

    def test_ttm_roe_is_computed(self):
        result = self.compute(
            _make_income_csv(8), _make_balance_csv(8), _make_cashflow_csv(8)
        )
        roe = result["ttm"]["roe_pct"]
        assert roe is not None
        assert roe > 0

    def test_ttm_debt_to_equity(self):
        result = self.compute(
            _make_income_csv(8), _make_balance_csv(8), _make_cashflow_csv(8)
        )
        de = result["ttm"]["debt_to_equity"]
        assert de is not None
        # Debt=10B, Equity=20B → D/E = 0.5
        assert abs(de - 0.5) < 0.01

    def test_quarterly_count(self):
        result = self.compute(
            _make_income_csv(8), _make_balance_csv(8), _make_cashflow_csv(8)
        )
        assert len(result["quarterly"]) == 8

    def test_revenue_trend_fields(self):
        result = self.compute(
            _make_income_csv(8), _make_balance_csv(8), _make_cashflow_csv(8)
        )
        trends = result["trends"]
        assert "revenue_qoq_pct" in trends
        assert "revenue_yoy_pct" in trends
        # Revenue growing at 5% QoQ
        qoq = trends["revenue_qoq_pct"]
        assert qoq is not None
        assert abs(qoq - 5.0) < 0.5

    def test_revenue_yoy_is_four_quarters_back(self):
        """YoY growth must compare latest quarter to the quarter 4 periods earlier."""
        result = self.compute(
            _make_income_csv(8), _make_balance_csv(8), _make_cashflow_csv(8)
        )
        yoy = result["trends"]["revenue_yoy_pct"]
        assert yoy is not None
        # With 5% QoQ compounding, YoY = 1.05^4 - 1 ≈ 21.55%
        expected_yoy = ((1.05 ** 4) - 1) * 100
        assert abs(yoy - expected_yoy) < 0.5

    def test_revenue_yoy_with_exactly_5_quarters(self):
        """YoY is available when exactly 5 quarters exist (minimum for 4-quarter lookback)."""
        result = self.compute(
            _make_income_csv(5), _make_balance_csv(5), _make_cashflow_csv(5)
        )
        yoy = result["trends"]["revenue_yoy_pct"]
        assert yoy is not None
        # quarterly[-5] vs quarterly[-1] with 5% QoQ → 1.05^4 - 1 ≈ 21.55%
        expected_yoy = ((1.05 ** 4) - 1) * 100
        assert abs(yoy - expected_yoy) < 0.5

    def test_revenue_yoy_none_with_4_quarters(self):
        """YoY should be None when fewer than 5 quarters are available."""
        result = self.compute(
            _make_income_csv(4), _make_balance_csv(4), _make_cashflow_csv(4)
        )
        yoy = result["trends"]["revenue_yoy_pct"]
        assert yoy is None

    def test_margin_trend_expanding(self):
        """Expanding margin should be detected."""
        # Create data where net margin expands over time
        dates = [f"2023-0{i+1}-01" for i in range(5)]
        revenues = [10_000_000_000] * 5
        # Net margin goes from 10% to 20% linearly
        net_incomes = [10_000_000_000 * (0.10 + i * 0.025) for i in range(5)]
        data = {"Total Revenue": revenues, "Net Income": net_incomes}
        df = pd.DataFrame(data, index=pd.to_datetime(dates))
        income_csv = df.to_csv()

        result = self.compute(income_csv, _make_balance_csv(5), _make_cashflow_csv(5))
        assert result["trends"].get("net_margin_direction") == "expanding"

    def test_graceful_empty_income(self):
        result = self.compute("", _make_balance_csv(4), _make_cashflow_csv(4))
        assert result["quarters_available"] == 0
        assert "income statement parse failed" in result["metadata"]["parse_errors"]

    def test_graceful_partial_data(self):
        """Should work with just income data, returning None for balance/cashflow fields."""
        result = self.compute(_make_income_csv(4), "", "")
        assert result["quarters_available"] == 4
        assert result["ttm"]["revenue"] is not None
        assert result["ttm"]["total_debt"] is None


# ---------------------------------------------------------------------------
# Unit tests for format_ttm_report
# ---------------------------------------------------------------------------

class TestFormatTTMReport:
    def setup_method(self):
        from tradingagents.dataflows.ttm_analysis import compute_ttm_metrics, format_ttm_report
        self.compute = compute_ttm_metrics
        self.format = format_ttm_report

    def test_report_contains_ticker(self):
        metrics = self.compute(_make_income_csv(8), _make_balance_csv(8), _make_cashflow_csv(8))
        report = self.format(metrics, "AAPL")
        assert "AAPL" in report

    def test_report_contains_ttm_section(self):
        metrics = self.compute(_make_income_csv(8), _make_balance_csv(8), _make_cashflow_csv(8))
        report = self.format(metrics, "AAPL")
        assert "Trailing Twelve Months" in report

    def test_report_contains_quarterly_history(self):
        metrics = self.compute(_make_income_csv(8), _make_balance_csv(8), _make_cashflow_csv(8))
        report = self.format(metrics, "AAPL")
        assert "Quarter" in report

    def test_report_contains_trend_signals(self):
        metrics = self.compute(_make_income_csv(8), _make_balance_csv(8), _make_cashflow_csv(8))
        report = self.format(metrics, "AAPL")
        assert "Trend Signals" in report

    def test_empty_data_report(self):
        metrics = self.compute("", "", "")
        report = self.format(metrics, "AAPL")
        assert "No quarterly data available" in report


# ---------------------------------------------------------------------------
# Integration test — real ticker (requires network)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestTTMIntegration:
    def test_get_ttm_analysis_tool(self):
        """End-to-end: get_ttm_analysis tool returns a non-empty report."""
        from tradingagents.agents.utils.fundamental_data_tools import get_ttm_analysis
        result = get_ttm_analysis.invoke({"ticker": "AAPL", "curr_date": "2026-03-17"})
        assert isinstance(result, str)
        assert len(result) > 100
        assert "AAPL" in result.upper()
