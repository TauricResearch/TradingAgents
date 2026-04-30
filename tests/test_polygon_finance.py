"""Polygon vendor module tests.

Mocks :func:`tradingagents.dataflows.polygon_common._make_request` and
:func:`paginated_results` so no live network calls are made. Validates:

* PIT visibility rule (filing_date + period_of_report fallback)
* Strict TTM aggregation (returns None when any quarter missing)
* Statement-to-CSV shape (rows=concepts, columns=periods)
* End-to-end ``get_fundamentals`` integration with mocked endpoints
* Vendor router fallback when Polygon raises
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from tradingagents.dataflows import polygon_finance as pf
from tradingagents.dataflows.polygon_common import (
    PolygonError,
    PolygonNotFoundError,
    PolygonRateLimitError,
)


# ---------------------------------------------------------------------------
# _is_pit_visible
# ---------------------------------------------------------------------------


class TestIsPitVisible:
    """Filings with filing_date < curr_date are visible. Filings without
    filing_date fall back to a period_of_report + 90-day lag rule.
    """

    @staticmethod
    def _curr() -> datetime:
        return datetime(2024, 5, 10)

    def test_filing_date_strictly_before_curr_date_is_visible(self):
        entry = {"filing_date": "2024-05-09", "end_date": "2024-04-28"}
        assert pf._is_pit_visible(entry, self._curr()) is True

    def test_filing_date_equal_to_curr_date_is_not_visible(self):
        # Strictly less-than: a filing made today wasn't on the wire when the
        # market opened, so we exclude it from "visible at curr_date".
        entry = {"filing_date": "2024-05-10", "end_date": "2024-04-28"}
        assert pf._is_pit_visible(entry, self._curr()) is False

    def test_filing_date_after_curr_date_is_not_visible(self):
        entry = {"filing_date": "2024-05-29", "end_date": "2024-04-28"}
        assert pf._is_pit_visible(entry, self._curr()) is False

    def test_null_filing_date_with_old_period_is_visible_via_lag(self):
        # period_of_report + 90 days <= curr_date → assume the SEC filing
        # window has elapsed and the data is publicly available.
        entry = {"filing_date": None, "end_date": "2024-01-31"}  # +90d = 2024-04-30
        assert pf._is_pit_visible(entry, self._curr()) is True

    def test_null_filing_date_with_recent_period_is_not_visible(self):
        # period_of_report = curr_date - 30d → still inside the typical filing
        # window, no filing_date evidence, so we treat it as not yet public.
        entry = {"filing_date": None, "end_date": "2024-04-10"}
        assert pf._is_pit_visible(entry, self._curr()) is False

    def test_no_dates_at_all_is_not_visible(self):
        # Defensive: row with neither filing_date nor period_of_report is
        # excluded — better to drop than risk look-ahead.
        entry = {"filing_date": None, "end_date": None}
        assert pf._is_pit_visible(entry, self._curr()) is False


# ---------------------------------------------------------------------------
# _ttm_sum
# ---------------------------------------------------------------------------


def _quarter(value, concept="revenues", section="income_statement"):
    """Build a Polygon-shaped financials entry with a single concept value."""
    return {
        "timeframe": "quarterly",
        "financials": {
            section: {
                concept: {"value": value, "label": concept},
            }
        }
    }


class TestTtmSum:
    def test_strict_ttm_sums_four_quarters(self):
        quarters = [_quarter(100), _quarter(200), _quarter(150), _quarter(250)]
        assert pf._ttm_sum(quarters, "income_statement", "revenues") == 700

    def test_ttm_returns_none_when_fewer_than_four_quarters(self):
        quarters = [_quarter(100), _quarter(200), _quarter(150)]
        assert pf._ttm_sum(quarters, "income_statement", "revenues") is None

    def test_ttm_returns_none_when_any_quarter_missing_value(self):
        # All four entries present but one has no value for the concept.
        quarters = [
            _quarter(100),
            _quarter(200),
            {"timeframe": "quarterly", "financials": {"income_statement": {}}},  # missing concept
            _quarter(250),
        ]
        assert pf._ttm_sum(quarters, "income_statement", "revenues") is None

    def test_ttm_uses_only_first_four_quarters(self):
        # If 5 are passed, only the most recent 4 (caller's responsibility
        # to order) are summed.
        quarters = [_quarter(100), _quarter(200), _quarter(150), _quarter(250), _quarter(999)]
        assert pf._ttm_sum(quarters, "income_statement", "revenues") == 700


# ---------------------------------------------------------------------------
# _statement_to_csv
# ---------------------------------------------------------------------------


class TestStatementToCsv:
    def test_csv_shape_has_concepts_as_rows_and_periods_as_columns(self):
        entries = [
            {
                "end_date": "2024-04-28",
                "financials": {
                    "income_statement": {
                        "revenues": {"value": 26044000000.0, "label": "Revenue"},
                        "gross_profit": {"value": 20407000000.0, "label": "Gross Profit"},
                    }
                },
            },
            {
                "end_date": "2024-01-28",
                "financials": {
                    "income_statement": {
                        "revenues": {"value": 22103000000.0, "label": "Revenue"},
                        "gross_profit": {"value": 16791000000.0, "label": "Gross Profit"},
                    }
                },
            },
        ]
        csv = pf._statement_to_csv(entries, "income_statement")
        # Headers: concept column + each period
        assert "concept" in csv.lower() or "metric" in csv.lower() or "label" in csv.lower()
        assert "2024-04-28" in csv
        assert "2024-01-28" in csv
        # Both concepts represented
        assert "revenues" in csv.lower() or "revenue" in csv.lower()
        assert "gross_profit" in csv.lower() or "gross profit" in csv.lower()

    def test_csv_handles_empty_entries(self):
        csv = pf._statement_to_csv([], "income_statement")
        assert csv == "" or "no data" in csv.lower() or csv.startswith("concept") or csv.startswith("metric") or csv.startswith("label")


# ---------------------------------------------------------------------------
# get_fundamentals end-to-end (mocked HTTP)
# ---------------------------------------------------------------------------


_NVDA_TICKER_REF = {
    "results": {
        "name": "Nvidia Corp",
        "market_cap": 2247000000000.0,
        "share_class_shares_outstanding": 2500000000,
        "weighted_shares_outstanding": 2495000000,
        "sic_description": "SEMICONDUCTORS & RELATED DEVICES",
        "primary_exchange": "XNAS",
    }
}

_NVDA_BARS = {
    "results": [
        {"t": 1715040000000, "o": 89.48, "h": 91.19, "l": 89.42, "c": 90.41, "v": 325721020},
        {"t": 1715126400000, "o": 90.53, "h": 91.07, "l": 88.23, "c": 88.75, "v": 378012680},
        {"t": 1715212800000, "o": 90.30, "h": 91.40, "l": 89.23, "c": 89.88, "v": 335325410},
    ]
}


def _fin_quarter(end_date, filing_date, revenues, net_income=None, gross_profit=None):
    inc = {"revenues": {"value": revenues, "label": "Revenues"}}
    if gross_profit is not None:
        inc["gross_profit"] = {"value": gross_profit, "label": "Gross Profit"}
    if net_income is not None:
        inc["net_income_loss"] = {"value": net_income, "label": "Net Income"}
    return {
        "filing_date": filing_date,
        "end_date": end_date,
        "timeframe": "quarterly",
        "financials": {
            "income_statement": inc,
            "balance_sheet": {
                "assets": {"value": 65728000000.0, "label": "Total Assets"},
                "equity": {"value": 42978000000.0, "label": "Equity"},
                "long_term_debt": {"value": 9709000000.0, "label": "Long-Term Debt"},
            },
            "cash_flow_statement": {
                "net_cash_flow_from_operating_activities": {"value": 7000000000.0, "label": "OCF"},
            },
        },
    }


_NVDA_FINANCIALS = [
    _fin_quarter("2024-01-28", "2024-02-21", 22103000000, 12285000000, 16791000000),
    _fin_quarter("2023-10-29", "2023-11-21", 18120000000, 9243000000, 13400000000),
    _fin_quarter("2023-07-30", "2023-08-23", 13507000000, 6188000000, 9462000000),
    _fin_quarter("2023-04-30", "2023-05-24", 7192000000, 2043000000, 4648000000),
]


class TestGetFundamentalsIntegration:
    """Full get_fundamentals call with mocked Polygon endpoints."""

    def _route(self, endpoint, params=None):
        """Mock dispatcher: route calls based on URL prefix."""
        if endpoint.startswith("/v3/reference/tickers/"):
            return _NVDA_TICKER_REF
        if endpoint.startswith("/v2/aggs/ticker/"):
            return _NVDA_BARS
        raise AssertionError(f"Unexpected endpoint: {endpoint}")

    def test_get_fundamentals_returns_correct_market_cap_for_nvda(self):
        with patch.object(pf, "_make_request", side_effect=self._route), \
             patch.object(pf, "paginated_results", return_value=_NVDA_FINANCIALS):
            report = pf.get_fundamentals("NVDA", "2024-05-10")

        # Critical: market cap must be in trillions, not buggy $224B
        assert "$2.25T" in report or "$2.24T" in report
        assert "Nvidia" in report
        assert "SEMICONDUCTORS" in report.upper()
        # PIT date appears in header
        assert "2024-05-10" in report

    def test_get_fundamentals_filters_out_post_curr_date_filings(self):
        """A row with filing_date AFTER curr_date must not influence the
        report — this is the guarantee that yf_pit_derivations Path D failed."""
        leaked_future = _fin_quarter("2024-04-28", "2026-01-25", 99999999999)
        all_financials = [leaked_future] + _NVDA_FINANCIALS

        with patch.object(pf, "_make_request", side_effect=self._route), \
             patch.object(pf, "paginated_results", return_value=all_financials):
            report = pf.get_fundamentals("NVDA", "2024-05-10")

        # The leaked future-filed row's revenues (99,999,999,999) must not
        # appear; only the legitimate ~$60B TTM should.
        assert "99999999999" not in report
        assert "$99.9B" not in report

    def test_get_fundamentals_handles_no_visible_filings(self):
        """If every filing has filing_date >= curr_date, get_fundamentals
        must still return a useful response (degraded but not crashing)."""
        all_in_future = [
            _fin_quarter("2024-04-28", "2030-01-01", 22103000000),
        ]
        with patch.object(pf, "_make_request", side_effect=self._route), \
             patch.object(pf, "paginated_results", return_value=all_in_future):
            report = pf.get_fundamentals("NVDA", "2024-05-10")

        # Should still include the price-derived bits (close, 52w range)
        # and metadata even when no PIT financials are visible.
        assert "Nvidia" in report
        # No TTM revenue can be computed → label should reflect missing data
        # (we just want this to not raise)


# ---------------------------------------------------------------------------
# get_news / get_global_news / get_insider_transactions
# ---------------------------------------------------------------------------


class TestPolygonNews:
    def test_get_news_returns_formatted_string(self):
        sample = [
            {
                "published_utc": "2024-05-09T14:30:00Z",
                "title": "NVDA up on AI demand",
                "publisher": {"name": "Reuters"},
                "article_url": "https://example.com/1",
                "description": "NVIDIA shares rose ahead of earnings.",
            }
        ]
        from tradingagents.dataflows import polygon_news as pn
        with patch.object(pn, "paginated_results", return_value=sample):
            out = pn.get_news("NVDA", "2024-05-01", "2024-05-10")
        assert "NVDA up on AI demand" in out
        assert "Reuters" in out

    def test_get_news_handles_no_results(self):
        from tradingagents.dataflows import polygon_news as pn
        with patch.object(pn, "paginated_results", side_effect=PolygonNotFoundError("none")):
            out = pn.get_news("NVDA", "2024-05-01", "2024-05-10")
        assert "No news found" in out

    def test_get_insider_transactions_raises_to_trigger_fallback(self):
        """Polygon Stocks Starter doesn't include insider transactions —
        the function must raise PolygonError so route_to_vendor falls
        through to the next configured vendor."""
        from tradingagents.dataflows import polygon_news as pn
        with pytest.raises(PolygonError):
            pn.get_insider_transactions("NVDA")


# ---------------------------------------------------------------------------
# Vendor router fallback
# ---------------------------------------------------------------------------


class TestVendorRouterFallback:
    """Confirm route_to_vendor falls back from Polygon to yfinance on
    PolygonError, and from any vendor missing API key to the next."""

    def test_polygon_error_triggers_fallback_to_yfinance(self):
        from tradingagents.dataflows import interface

        def boom(*args, **kwargs):
            raise PolygonRateLimitError("simulated 429")

        sentinel = "FALLBACK_TO_YFINANCE_REPORT"
        # Patch the configured chain to be exactly polygon→yfinance so we
        # can reason about the fallback deterministically (avoids ordering
        # dependencies on alpha_vantage, which sits between them in the
        # registration order and would otherwise be tried second).
        with patch.object(interface, "get_vendor", return_value="polygon,yfinance"), \
             patch.dict(
                 interface.VENDOR_METHODS["get_fundamentals"],
                 {
                     "polygon": boom,
                     "yfinance": lambda *a, **kw: sentinel,
                 },
             ):
            result = interface.route_to_vendor(
                "get_fundamentals", "NVDA", "2024-05-10"
            )
            assert result == sentinel

    def test_missing_api_key_value_error_triggers_fallback(self):
        from tradingagents.dataflows import interface

        def missing_key(*args, **kwargs):
            raise ValueError("ALPHA_VANTAGE_API_KEY environment variable is not set.")

        sentinel = "FALLBACK_AFTER_MISSING_KEY"
        with patch.object(interface, "get_vendor", return_value="polygon,yfinance"), \
             patch.dict(
                 interface.VENDOR_METHODS["get_fundamentals"],
                 {
                     "polygon": missing_key,
                     "yfinance": lambda *a, **kw: sentinel,
                 },
             ):
            result = interface.route_to_vendor(
                "get_fundamentals", "NVDA", "2024-05-10"
            )
            assert result == sentinel

    def test_unrelated_value_error_does_not_swallow(self):
        """ValueError that isn't about API keys (e.g. bad input args) must
        propagate — we only fall through on missing-key signals."""
        from tradingagents.dataflows import interface

        def bad_input(*args, **kwargs):
            raise ValueError("ticker must be a non-empty string")

        with patch.object(interface, "get_vendor", return_value="polygon,yfinance,alpha_vantage"), \
             patch.dict(
                 interface.VENDOR_METHODS["get_fundamentals"],
                 {
                     "polygon": bad_input,
                     "yfinance": bad_input,
                     "alpha_vantage": bad_input,
                 },
             ):
            with pytest.raises(ValueError, match="non-empty string"):
                interface.route_to_vendor(
                    "get_fundamentals", "NVDA", "2024-05-10"
                )
