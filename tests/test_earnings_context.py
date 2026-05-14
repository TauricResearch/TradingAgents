"""Tests for the earnings-context tool (issue #561).

The tool synthesises four yfinance surfaces (calendar, earnings_estimate,
revenue_estimate, earnings_history, recommendations_summary) into a single
markdown string for the Fundamentals Analyst. These tests mock yf.Ticker so
the suite stays offline and verify:

- All four sections render with realistic synthetic data
- The surprise-history section is look-ahead-safe (filtered <= curr_date)
- "Next earnings event" picks the first scheduled date >= curr_date
- The near-earnings flag flips correctly at the window boundary
- Each yfinance attribute can fail independently without nuking the report
- Empty / missing data degrades to "(unavailable)" instead of raising
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows.y_finance import get_earnings_context


def _eps_estimate_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "avg": [2.31, 2.55, 9.10, 10.20],
            "low": [2.10, 2.30, 8.75, 9.50],
            "high": [2.50, 2.80, 9.45, 10.90],
            "numberOfAnalysts": [28, 27, 30, 25],
            "growth": [0.12, 0.14, 0.10, 0.12],
        },
        index=["0q", "+1q", "0y", "+1y"],
    )


def _revenue_estimate_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "avg": [95_200_000_000, 102_500_000_000, 410_000_000_000, 450_000_000_000],
            "low": [92_000_000_000, 99_000_000_000, 400_000_000_000, 440_000_000_000],
            "high": [98_500_000_000, 105_000_000_000, 420_000_000_000, 462_000_000_000],
            "numberOfAnalysts": [28, 27, 30, 25],
            "growth": [0.08, 0.09, 0.07, 0.10],
        },
        index=["0q", "+1q", "0y", "+1y"],
    )


def _earnings_history_df() -> pd.DataFrame:
    """Five quarters; only four end on/before 2026-01-15 (the look-ahead cutoff)."""
    return pd.DataFrame(
        {
            "epsEstimate": [1.20, 1.30, 1.40, 1.45, 1.60],
            "epsActual":   [1.25, 1.32, 1.41, 1.52, 1.55],
            "surprisePercent": [0.0417, 0.0154, 0.0071, 0.0483, -0.0313],
        },
        index=pd.to_datetime([
            "2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30", "2026-03-31",
        ]),
    )


def _recommendations_summary_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "period": ["0m", "-1m", "-2m", "-3m"],
            "strongBuy": [12, 11, 10, 9],
            "buy": [18, 19, 17, 18],
            "hold": [6, 7, 8, 9],
            "sell": [1, 1, 2, 2],
            "strongSell": [0, 0, 1, 1],
        }
    )


def _build_mock_ticker(**overrides) -> MagicMock:
    """Build a MagicMock with realistic yfinance attribute defaults; overrides win."""
    defaults = {
        "calendar": {"Earnings Date": [pd.Timestamp("2026-01-30")]},
        "earnings_estimate": _eps_estimate_df(),
        "revenue_estimate": _revenue_estimate_df(),
        "earnings_history": _earnings_history_df(),
        "recommendations_summary": _recommendations_summary_df(),
        "recommendations": None,
    }
    defaults.update(overrides)
    m = MagicMock()
    for attr, value in defaults.items():
        setattr(m, attr, value)
    return m


@pytest.mark.unit
class TestEarningsContext:
    def test_full_render_contains_all_sections(self):
        mock_ticker = _build_mock_ticker()
        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            out = get_earnings_context("AAPL", "2026-01-15", 5)

        assert "# Earnings Context for AAPL (as of 2026-01-15)" in out
        assert "## Next Earnings Event" in out
        assert "## Consensus Estimates (upcoming periods)" in out
        assert "### EPS" in out
        assert "### Revenue" in out
        assert "## Earnings Surprise History" in out
        assert "## Analyst Recommendations Snapshot" in out

    def test_ticker_uppercased_for_yfinance(self):
        mock_ticker = _build_mock_ticker()
        with patch(
            "tradingagents.dataflows.y_finance.yf.Ticker",
            return_value=mock_ticker,
        ) as cls:
            get_earnings_context("aapl", "2026-01-15")
        cls.assert_called_once_with("AAPL")

    def test_surprise_history_excludes_dates_after_curr_date(self):
        """Quarter ending 2026-03-31 is after curr_date 2026-01-15 — must be omitted."""
        mock_ticker = _build_mock_ticker()
        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            out = get_earnings_context("AAPL", "2026-01-15", 5)
        assert "2026-03-31" not in out
        # All four eligible periods are present.
        for ts in ("2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30"):
            assert ts in out

    def test_next_earnings_picks_first_date_on_or_after_curr_date(self):
        """Past dates in the calendar list are skipped; first future date wins."""
        mock_ticker = _build_mock_ticker(
            calendar={"Earnings Date": [
                pd.Timestamp("2025-10-30"),  # past — skip
                pd.Timestamp("2026-04-25"),  # second future
                pd.Timestamp("2026-01-30"),  # first future
            ]},
        )
        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            out = get_earnings_context("AAPL", "2026-01-15", 5)
        assert "Date: 2026-01-30" in out
        assert "Date: 2026-04-25" not in out

    def test_near_earnings_flag_yes_inside_window(self):
        mock_ticker = _build_mock_ticker(
            calendar={"Earnings Date": [pd.Timestamp("2026-01-20")]},  # 3 business days from Jan 15 (Thu)
        )
        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            out = get_earnings_context("AAPL", "2026-01-15", 5)
        assert "Near earnings (within 5 trading days): YES" in out

    def test_near_earnings_flag_no_outside_window(self):
        mock_ticker = _build_mock_ticker(
            calendar={"Earnings Date": [pd.Timestamp("2026-02-15")]},  # ~22 business days out
        )
        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            out = get_earnings_context("AAPL", "2026-01-15", 5)
        assert "Near earnings (within 5 trading days): NO" in out

    def test_no_upcoming_earnings_handled(self):
        mock_ticker = _build_mock_ticker(
            calendar={"Earnings Date": [pd.Timestamp("2024-01-01")]},  # only a past date
        )
        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            out = get_earnings_context("AAPL", "2026-01-15", 5)
        assert "No upcoming earnings date scheduled." in out

    def test_empty_calendar_dict_handled(self):
        mock_ticker = _build_mock_ticker(calendar={})
        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            out = get_earnings_context("AAPL", "2026-01-15", 5)
        assert "No upcoming earnings date scheduled." in out

    def test_section_failure_is_isolated(self):
        """If a single yfinance surface raises, only its section degrades."""
        class _Raiser:
            def __getattr__(self, name):
                raise RuntimeError(f"yfinance exploded on {name}")

        m = _build_mock_ticker()
        # Use a property-like raiser only for earnings_history; other sections must still render.
        type(m).earnings_history = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=m):
            out = get_earnings_context("AAPL", "2026-01-15", 5)

        # Surprise history section degraded
        assert "## Earnings Surprise History" in out
        assert "(unavailable)" in out
        # But the other three sections still rendered
        assert "Date: 2026-01-30" in out
        assert "### EPS" in out
        assert "## Analyst Recommendations Snapshot" in out
        assert "| 0m |" in out

    def test_recommendations_fallback_to_recommendations_when_summary_empty(self):
        mock_ticker = _build_mock_ticker(
            recommendations_summary=pd.DataFrame(),
            recommendations=_recommendations_summary_df(),
        )
        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            out = get_earnings_context("AAPL", "2026-01-15", 5)
        assert "## Analyst Recommendations Snapshot" in out
        assert "| 0m |" in out

    def test_returns_string_always(self):
        mock_ticker = _build_mock_ticker()
        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            out = get_earnings_context("AAPL", "2026-01-15", 5)
        assert isinstance(out, str)

    def test_curr_date_defaults_to_today_when_none(self):
        mock_ticker = _build_mock_ticker()
        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            out = get_earnings_context("AAPL", None)
        # Header is well-formed and dated; we don't assert the exact date to keep
        # the test stable across days.
        assert out.startswith("# Earnings Context for AAPL (as of ")
