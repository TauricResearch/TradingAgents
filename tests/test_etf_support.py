"""Unit tests for yfinance-backed ETF support.

Covers ETF detection, the yfinance ETF vendor functions, routing through
``interface.py``, the ``@etf_placeholder`` decorator behavior on
company-financial tools, ETF-aware ``build_instrument_context``, and a
smoke check confirming news tools do NOT route through ETF detection.

All network calls (yfinance) are mocked.
"""

from __future__ import annotations

import copy
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _reset_dataflows_config():
    """Reset dataflows config to defaults so each test sees predictable routing."""
    import copy
    import tradingagents.default_config as default_config
    from tradingagents.dataflows.config import set_config
    set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))


# ---------------------------------------------------------------------------
# ETF detection
# ---------------------------------------------------------------------------

@pytest.mark.unit
class IsEtfTickerTests(unittest.TestCase):
    def test_us_etf_via_yfinance_quote_type(self):
        from tradingagents.dataflows.etf_utils import is_etf_ticker

        with patch(
            "tradingagents.dataflows.etf_utils._yfinance_quote_type",
            return_value="ETF",
        ):
            self.assertTrue(is_etf_ticker("SPY"))

    def test_us_stock_via_yfinance_quote_type(self):
        from tradingagents.dataflows.etf_utils import is_etf_ticker

        with patch(
            "tradingagents.dataflows.etf_utils._yfinance_quote_type",
            return_value="EQUITY",
        ):
            self.assertFalse(is_etf_ticker("AAPL"))

    def test_hk_etf_via_yfinance_quote_type(self):
        from tradingagents.dataflows.etf_utils import is_etf_ticker

        with patch(
            "tradingagents.dataflows.etf_utils._yfinance_quote_type",
            return_value="ETF",
        ):
            self.assertTrue(is_etf_ticker("2800.HK"))

    def test_non_string_inputs(self):
        from tradingagents.dataflows.etf_utils import is_etf_ticker

        for bad in (None, 0, 123, [], {}, b"SPY"):
            self.assertFalse(is_etf_ticker(bad))

    def test_empty_string(self):
        from tradingagents.dataflows.etf_utils import is_etf_ticker

        self.assertFalse(is_etf_ticker(""))
        self.assertFalse(is_etf_ticker("   "))

    def test_quote_type_lookup_cached(self):
        """The lru_cache must prevent repeated yfinance ``.info`` calls."""
        from tradingagents.dataflows.etf_utils import _yfinance_quote_type

        mock_ticker = MagicMock()
        mock_ticker.info = {"quoteType": "ETF"}
        with patch("yfinance.Ticker", return_value=mock_ticker) as yt:
            _yfinance_quote_type("SPY")
            _yfinance_quote_type("SPY")
            _yfinance_quote_type("SPY")
        self.assertEqual(yt.call_count, 1)

    def test_quote_type_returns_none_on_network_error(self):
        from tradingagents.dataflows.etf_utils import _yfinance_quote_type

        with patch("yfinance.Ticker", side_effect=RuntimeError("network down")):
            self.assertIsNone(_yfinance_quote_type("WEIRD-TICKER-9999"))


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

@pytest.mark.unit
class EtfRoutingTests(unittest.TestCase):
    def test_get_etf_profile_routes_to_yfinance(self):
        from tradingagents.dataflows import interface

        sentinel = "YFIN_ETF_PROFILE_RESULT"
        with patch.dict(
            interface.VENDOR_METHODS["get_etf_profile"],
            {"yfinance": MagicMock(return_value=sentinel)},
        ):
            result = interface.route_to_vendor("get_etf_profile", "SPY")
        self.assertEqual(result, sentinel)

    def test_get_etf_holdings_routes_to_yfinance(self):
        from tradingagents.dataflows import interface

        sentinel = "YFIN_ETF_HOLDINGS_RESULT"
        with patch.dict(
            interface.VENDOR_METHODS["get_etf_holdings"],
            {"yfinance": MagicMock(return_value=sentinel)},
        ):
            result = interface.route_to_vendor("get_etf_holdings", "SPY", 5)
        self.assertEqual(result, sentinel)

    def test_route_falls_back_when_etf_data_key_missing_from_config(self):
        """Old user configs predate the etf_data category; route must still work."""
        from tradingagents.dataflows import interface
        from tradingagents.dataflows import config as df_config

        # Simulate a legacy config that has no etf_data key. Bypass set_config
        # because it merges-in rather than replaces, so we install the legacy
        # mapping directly into the module-level _config.
        legacy = copy.deepcopy(df_config._config)
        legacy["data_vendors"].pop("etf_data", None)
        df_config._config = legacy

        sentinel = "FALLBACK_OK"
        with patch.dict(
            interface.VENDOR_METHODS["get_etf_profile"],
            {"yfinance": MagicMock(return_value=sentinel)},
        ):
            # get_vendor returns "default" → not in VENDOR_METHODS → loop
            # then tries each registered vendor; yfinance hits.
            result = interface.route_to_vendor("get_etf_profile", "SPY")
        self.assertEqual(result, sentinel)

    def test_route_falls_back_when_configured_vendor_has_no_impl(self):
        """If the configured vendor is unregistered for this method, the
        fallback chain must keep trying other registered vendors."""
        from tradingagents.dataflows import interface
        from tradingagents.dataflows.config import set_config, get_config

        cfg = get_config()
        cfg["data_vendors"]["etf_data"] = "phantom_vendor_with_no_impl"
        set_config(cfg)

        sentinel = "FALLBACK_TO_YFIN"
        # Replace the whole impls dict so only yfinance is registered for
        # this method during the test.
        original = interface.VENDOR_METHODS["get_etf_profile"]
        interface.VENDOR_METHODS["get_etf_profile"] = {
            "yfinance": MagicMock(return_value=sentinel)
        }
        try:
            result = interface.route_to_vendor("get_etf_profile", "SPY")
        finally:
            interface.VENDOR_METHODS["get_etf_profile"] = original
        self.assertEqual(result, sentinel)


# ---------------------------------------------------------------------------
# yfinance ETF vendor rendering
# ---------------------------------------------------------------------------

@pytest.mark.unit
class YfinanceEtfVendorTests(unittest.TestCase):
    def _make_ticker_mock(self, info=None, funds_data=None):
        """Build a yfinance.Ticker mock with explicit ``info`` and ``funds_data``.

        Pass ``funds_data=None`` to simulate the common "no funds_data
        available" case (HK ETFs, new listings) — both vendor functions
        treat None as "skip / no holdings disclosed".
        """
        m = MagicMock()
        m.info = info or {}
        m.funds_data = funds_data
        return m

    def test_profile_renders_key_info_fields(self):
        from tradingagents.dataflows import yfinance_etf

        info = {
            "longName": "SPDR S&P 500 ETF Trust",
            "quoteType": "ETF",
            "category": "Large Blend",
            "fundFamily": "SPDR State Street Global Advisors",
            "totalAssets": 600_000_000_000,
            "navPrice": 580.12,
            "annualReportExpenseRatio": 0.0009,
            "yield": 0.013,
        }
        funds_data = MagicMock()
        funds_data.description = "Tracks the S&P 500 index."
        funds_data.asset_classes = {"stocks": 0.99, "cash": 0.01}
        funds_data.sector_weightings = {"Technology": 0.30, "Financials": 0.13}

        with patch.object(
            yfinance_etf.yf, "Ticker",
            return_value=self._make_ticker_mock(info=info, funds_data=funds_data),
        ):
            out = yfinance_etf.get_etf_profile("SPY")

        self.assertIn("SPDR S&P 500 ETF Trust", out)
        self.assertIn("Total Assets (AUM)", out)
        self.assertIn("## Strategy", out)
        self.assertIn("## Asset Class Breakdown", out)
        self.assertIn("## Sector Weightings", out)
        self.assertIn("Technology", out)

    def test_profile_degrades_when_funds_data_missing(self):
        """HK ETFs frequently expose .info but not funds_data — must not raise."""
        from tradingagents.dataflows import yfinance_etf

        info = {"longName": "Tracker Fund of Hong Kong ETF", "quoteType": "ETF"}
        with patch.object(
            yfinance_etf.yf, "Ticker",
            return_value=self._make_ticker_mock(info=info, funds_data=None),
        ):
            out = yfinance_etf.get_etf_profile("2800.HK")
        self.assertIn("Tracker Fund of Hong Kong ETF", out)
        self.assertNotIn("## Sector Weightings", out)
        self.assertNotIn("## Asset Class Breakdown", out)

    def test_profile_degrades_when_sector_weightings_empty(self):
        """funds_data exists but sector_weightings is empty — render basics, skip section."""
        from tradingagents.dataflows import yfinance_etf

        info = {"longName": "Some ETF", "quoteType": "ETF"}
        funds_data = MagicMock()
        funds_data.description = None
        funds_data.asset_classes = None
        funds_data.sector_weightings = {}

        with patch.object(
            yfinance_etf.yf, "Ticker",
            return_value=self._make_ticker_mock(info=info, funds_data=funds_data),
        ):
            out = yfinance_etf.get_etf_profile("XYZ")
        self.assertIn("Some ETF", out)
        self.assertNotIn("## Sector Weightings", out)

    def test_holdings_renders_top_n_with_weights(self):
        from tradingagents.dataflows import yfinance_etf

        holdings = pd.DataFrame(
            {
                "Name": ["Apple Inc.", "Microsoft Corp.", "Nvidia Corp."],
                "Holding Percent": [0.072, 0.065, 0.061],
            },
            index=["AAPL", "MSFT", "NVDA"],
        )
        funds_data = MagicMock()
        funds_data.top_holdings = holdings

        with patch.object(
            yfinance_etf.yf, "Ticker",
            return_value=self._make_ticker_mock(info={}, funds_data=funds_data),
        ):
            out = yfinance_etf.get_etf_holdings("SPY", top_n=2)
        self.assertIn("AAPL", out)
        self.assertIn("MSFT", out)
        # top_n=2 — NVDA must be filtered out
        self.assertNotIn("NVDA", out)
        # Weight column was converted from decimal to percent string.
        self.assertIn("7.2%", out)

    def test_holdings_degrades_when_funds_data_missing(self):
        from tradingagents.dataflows import yfinance_etf

        with patch.object(
            yfinance_etf.yf, "Ticker",
            return_value=self._make_ticker_mock(info={}, funds_data=None),
        ):
            out = yfinance_etf.get_etf_holdings("2800.HK")
        self.assertIn("No holdings disclosed", out)

    def test_holdings_degrades_when_top_holdings_none(self):
        from tradingagents.dataflows import yfinance_etf

        funds_data = MagicMock()
        funds_data.top_holdings = None
        with patch.object(
            yfinance_etf.yf, "Ticker",
            return_value=self._make_ticker_mock(info={}, funds_data=funds_data),
        ):
            out = yfinance_etf.get_etf_holdings("SPY")
        self.assertIn("No holdings disclosed", out)


# ---------------------------------------------------------------------------
# Alpha Vantage ETF vendor rendering
# ---------------------------------------------------------------------------

@pytest.mark.unit
class AlphaVantageEtfVendorTests(unittest.TestCase):
    """Mock the Alpha Vantage HTTP layer (``_make_api_request``) and verify
    ``alpha_vantage_etf`` renders the documented ``ETF_PROFILE`` payload."""

    _SAMPLE_PROFILE = {
        "symbol": "QQQ",
        "name": "Invesco QQQ Trust Series 1",
        "net_assets": "350000000000",
        "net_expense_ratio": "0.002",
        "portfolio_turnover": "0.06",
        "dividend_yield": "0.006",
        "inception_date": "1999-03-10",
        "leveraged": "NO",
        "asset_class": "EQUITY",
        "sectors": [
            {"sector": "Information Technology", "weight": "0.51"},
            {"sector": "Communication Services", "weight": "0.16"},
        ],
        "holdings": [
            {"symbol": "AAPL", "description": "Apple Inc", "weight": "0.092"},
            {"symbol": "MSFT", "description": "Microsoft Corp", "weight": "0.085"},
            {"symbol": "NVDA", "description": "Nvidia Corp", "weight": "0.064"},
        ],
    }

    def test_profile_renders_key_fields(self):
        from tradingagents.dataflows import alpha_vantage_etf

        with patch.object(
            alpha_vantage_etf, "_make_api_request",
            return_value=self._SAMPLE_PROFILE,
        ):
            out = alpha_vantage_etf.get_etf_profile("QQQ")
        self.assertIn("Invesco QQQ Trust", out)
        self.assertIn("Net Assets (AUM)", out)
        self.assertIn("Net Expense Ratio", out)
        self.assertIn("## Sector Weightings", out)
        self.assertIn("Information Technology", out)

    def test_profile_accepts_json_string_payload(self):
        """``_make_api_request`` may return raw text — must still parse."""
        import json
        from tradingagents.dataflows import alpha_vantage_etf

        with patch.object(
            alpha_vantage_etf, "_make_api_request",
            return_value=json.dumps(self._SAMPLE_PROFILE),
        ):
            out = alpha_vantage_etf.get_etf_profile("QQQ")
        self.assertIn("Invesco QQQ Trust", out)

    def test_profile_degrades_on_empty_response(self):
        from tradingagents.dataflows import alpha_vantage_etf

        with patch.object(alpha_vantage_etf, "_make_api_request", return_value={}):
            out = alpha_vantage_etf.get_etf_profile("WEIRD")
        self.assertIn("No ETF profile available", out)

    def test_holdings_renders_top_n(self):
        from tradingagents.dataflows import alpha_vantage_etf

        with patch.object(
            alpha_vantage_etf, "_make_api_request",
            return_value=self._SAMPLE_PROFILE,
        ):
            out = alpha_vantage_etf.get_etf_holdings("QQQ", top_n=2)
        self.assertIn("AAPL", out)
        self.assertIn("MSFT", out)
        # top_n=2 means NVDA must be cropped
        self.assertNotIn("NVDA", out)
        self.assertIn("Top 2 positions", out)

    def test_holdings_degrades_when_holdings_missing(self):
        from tradingagents.dataflows import alpha_vantage_etf

        with patch.object(
            alpha_vantage_etf, "_make_api_request",
            return_value={"symbol": "XYZ"},  # profile present, holdings missing
        ):
            out = alpha_vantage_etf.get_etf_holdings("XYZ")
        self.assertIn("No holdings disclosed", out)


# ---------------------------------------------------------------------------
# Alpha Vantage ETF routing
# ---------------------------------------------------------------------------

@pytest.mark.unit
class AlphaVantageEtfRoutingTests(unittest.TestCase):
    def test_etf_profile_routes_to_alpha_vantage_when_configured(self):
        from tradingagents.dataflows import interface
        from tradingagents.dataflows.config import get_config, set_config

        cfg = get_config()
        cfg["data_vendors"]["etf_data"] = "alpha_vantage"
        set_config(cfg)

        sentinel = "AV_ETF_PROFILE_RESULT"
        with patch.dict(
            interface.VENDOR_METHODS["get_etf_profile"],
            {"alpha_vantage": MagicMock(return_value=sentinel)},
        ):
            result = interface.route_to_vendor("get_etf_profile", "QQQ")
        self.assertEqual(result, sentinel)

    def test_etf_holdings_routes_to_alpha_vantage_when_configured(self):
        from tradingagents.dataflows import interface
        from tradingagents.dataflows.config import get_config, set_config

        cfg = get_config()
        cfg["data_vendors"]["etf_data"] = "alpha_vantage"
        set_config(cfg)

        sentinel = "AV_ETF_HOLDINGS_RESULT"
        with patch.dict(
            interface.VENDOR_METHODS["get_etf_holdings"],
            {"alpha_vantage": MagicMock(return_value=sentinel)},
        ):
            result = interface.route_to_vendor("get_etf_holdings", "QQQ", 5)
        self.assertEqual(result, sentinel)


# ---------------------------------------------------------------------------
# ETF placeholder applied at the dispatch layer (interface.route_to_vendor)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class EtfPlaceholderViaRoutingTests(unittest.TestCase):
    """ETF protection lives at the dispatch layer, so it applies uniformly
    across every registered vendor (yfinance, alpha_vantage, ...). These
    tests go through ``route_to_vendor`` — the way real callers reach
    these methods — rather than calling vendor functions directly.

    Direct calls to ``y_finance.get_fundamentals(...)`` intentionally
    bypass the placeholder; that's the cleaner separation (vendor
    modules stay vendor-pure)."""

    def _patch_etf(self, is_etf: bool):
        return patch(
            "tradingagents.dataflows.etf_utils._yfinance_quote_type",
            return_value="ETF" if is_etf else "EQUITY",
        )

    def test_fundamentals_returns_placeholder_for_etf_via_yfinance(self):
        from tradingagents.dataflows import interface

        with self._patch_etf(True):
            out = interface.route_to_vendor("get_fundamentals", "SPY", "2025-01-01")
        self.assertIn("SPY", out)
        self.assertIn("ETF", out)
        self.assertIn("get_etf_profile", out)
        self.assertIn("get_etf_holdings", out)

    def test_balance_sheet_returns_placeholder_for_etf(self):
        from tradingagents.dataflows import interface

        with self._patch_etf(True):
            out = interface.route_to_vendor("get_balance_sheet", "SPY")
        self.assertIn("balance sheet", out)
        self.assertIn("get_etf_profile", out)

    def test_cashflow_returns_placeholder_for_etf(self):
        from tradingagents.dataflows import interface

        with self._patch_etf(True):
            out = interface.route_to_vendor("get_cashflow", "SPY")
        self.assertIn("cash flow statement", out)

    def test_income_statement_returns_placeholder_for_etf(self):
        from tradingagents.dataflows import interface

        with self._patch_etf(True):
            out = interface.route_to_vendor("get_income_statement", "SPY")
        self.assertIn("income statement", out)

    def test_insider_transactions_returns_placeholder_for_etf(self):
        from tradingagents.dataflows import interface

        with self._patch_etf(True):
            out = interface.route_to_vendor("get_insider_transactions", "SPY")
        self.assertIn("insider transactions", out)

    def test_placeholder_also_applies_to_alpha_vantage_vendor(self):
        """The dispatch-layer decoration must protect every vendor, not just
        yfinance. Switch the configured vendor to alpha_vantage and confirm
        an ETF ticker still gets the placeholder — never a malformed
        Alpha Vantage OVERVIEW response."""
        from tradingagents.dataflows import interface
        from tradingagents.dataflows.config import get_config, set_config

        cfg = get_config()
        cfg["data_vendors"]["fundamental_data"] = "alpha_vantage"
        set_config(cfg)

        with self._patch_etf(True):
            out = interface.route_to_vendor("get_fundamentals", "SPY", "2025-01-01")
        self.assertIn("ETF", out)
        self.assertIn("get_etf_profile", out)

    def test_stock_ticker_passes_through_to_vendor_impl(self):
        """Non-ETF ticker must reach the underlying yfinance call."""
        from tradingagents.dataflows import interface, y_finance

        mock_ticker = MagicMock()
        mock_ticker.info = {"longName": "Apple Inc."}
        with self._patch_etf(False), \
             patch.object(y_finance.yf, "Ticker", return_value=mock_ticker) as yt:
            out = interface.route_to_vendor("get_fundamentals", "AAPL", "2025-01-01")
        yt.assert_called_once()
        self.assertIn("Apple Inc.", out)
        self.assertNotIn("get_etf_profile", out)

    def test_direct_vendor_call_bypasses_placeholder(self):
        """By design: y_finance.get_fundamentals stays a thin yfinance
        wrapper. Placeholder lives at the dispatch layer, not in vendors."""
        from tradingagents.dataflows import y_finance

        mock_ticker = MagicMock()
        mock_ticker.info = {"longName": "Some Fund"}
        with self._patch_etf(True), \
             patch.object(y_finance.yf, "Ticker", return_value=mock_ticker):
            out = y_finance.get_fundamentals("SPY")
        # Direct call returns yfinance data, not the placeholder.
        self.assertNotIn("get_etf_profile", out)
        self.assertIn("Some Fund", out)


# ---------------------------------------------------------------------------
# Smoke check: news tools are unaffected by ETF detection
# ---------------------------------------------------------------------------

@pytest.mark.unit
class EtfDoesNotLeakToNewsTests(unittest.TestCase):
    """ETF detection only sits on company-financial paths; news must flow
    through untouched even for ETF tickers."""

    def test_get_news_yfinance_does_not_return_etf_placeholder(self):
        from tradingagents.dataflows import yfinance_news

        mock_ticker = MagicMock()
        mock_ticker.get_news.return_value = []  # empty list; call must reach yfinance
        with patch(
            "tradingagents.dataflows.etf_utils._yfinance_quote_type",
            return_value="ETF",
        ), patch.object(yfinance_news.yf, "Ticker", return_value=mock_ticker) as yt:
            out = yfinance_news.get_news_yfinance("SPY", "2025-01-01", "2025-01-31")
        yt.assert_called()  # yfinance was reached — no ETF short-circuit
        # And the result is the regular news path (empty-news message), not
        # the ETF placeholder.
        self.assertNotIn("get_etf_profile", out)


# ---------------------------------------------------------------------------
# ETF-aware build_instrument_context
# ---------------------------------------------------------------------------

@pytest.mark.unit
class BuildInstrumentContextEtfTests(unittest.TestCase):
    def test_etf_ticker_gets_etf_block(self):
        from tradingagents.agents.utils.agent_utils import build_instrument_context

        with patch(
            "tradingagents.dataflows.etf_utils._yfinance_quote_type",
            return_value="ETF",
        ):
            ctx = build_instrument_context("SPY")
        self.assertIn("ETF", ctx)
        self.assertIn("get_etf_profile", ctx)
        self.assertIn("get_etf_holdings", ctx)
        # Redirects the LLM away from the company-financial tools that would
        # otherwise return placeholders.
        self.assertIn("get_fundamentals", ctx)

    def test_stock_ticker_unaffected(self):
        from tradingagents.agents.utils.agent_utils import build_instrument_context

        with patch(
            "tradingagents.dataflows.etf_utils._yfinance_quote_type",
            return_value="EQUITY",
        ):
            ctx = build_instrument_context("AAPL")
        self.assertNotIn("ETF", ctx)
        self.assertNotIn("get_etf_profile", ctx)

    def test_non_string_input_does_not_raise(self):
        """``state["company_of_interest"]`` should always be a string in
        practice, but the helper must not crash on a non-string sentinel."""
        from tradingagents.agents.utils.agent_utils import build_instrument_context

        # Should not raise; the f-string can format None / ints / etc.
        ctx = build_instrument_context(None)
        self.assertIn("None", ctx)
        self.assertNotIn("ETF", ctx)


# ---------------------------------------------------------------------------
# Analyst + ToolNode wiring
# ---------------------------------------------------------------------------

@pytest.mark.unit
class FundamentalsAnalystEtfToolsWiringTests(unittest.TestCase):
    def test_etf_tools_imported_into_agent_utils_namespace(self):
        """``from tradingagents.agents.utils.agent_utils import get_etf_profile``
        must resolve so the analyst and trading_graph can pull them from the
        same place as the other tools."""
        from tradingagents.agents.utils import agent_utils

        self.assertTrue(hasattr(agent_utils, "get_etf_profile"))
        self.assertTrue(hasattr(agent_utils, "get_etf_holdings"))

    def test_trading_graph_fundamentals_toolnode_registers_etf_tools(self):
        """ToolNode must list every tool the analyst can bind — otherwise the
        LLM's tool call fails with "not a valid tool" at runtime."""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        # _create_tool_nodes is an instance method but doesn't depend on
        # __init__ state; bind it through a lightweight proxy to avoid
        # construction cost.
        tg = TradingAgentsGraph.__new__(TradingAgentsGraph)
        nodes = TradingAgentsGraph._create_tool_nodes(tg)

        registered = {t.name for t in nodes["fundamentals"].tools_by_name.values()}
        self.assertIn("get_etf_profile", registered)
        self.assertIn("get_etf_holdings", registered)
        self.assertIn("get_etf_top_holdings_drilldown", registered)


# ---------------------------------------------------------------------------
# Top-holdings extractors — structured (vendor → list of tuples)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class YfinanceTopHoldingTickersTests(unittest.TestCase):
    def _ticker_with_top_holdings(self, df):
        m = MagicMock()
        funds_data = MagicMock()
        funds_data.top_holdings = df
        m.funds_data = funds_data
        return m

    def test_returns_normalized_tuples_with_percent_weights(self):
        from tradingagents.dataflows import yfinance_etf

        df = pd.DataFrame(
            {"Name": ["Apple Inc.", "Microsoft Corp."], "Holding Percent": [0.072, 0.065]},
            index=["AAPL", "MSFT"],
        )
        with patch.object(
            yfinance_etf.yf, "Ticker",
            return_value=self._ticker_with_top_holdings(df),
        ):
            out = yfinance_etf.get_top_holding_tickers("SPY", top_n=2)
        self.assertEqual(out[0][0], "AAPL")
        self.assertEqual(out[0][1], "Apple Inc.")
        # 0.072 decimal must be converted to 7.2 percent for downstream display.
        self.assertAlmostEqual(out[0][2], 7.2, places=2)
        self.assertEqual(out[1][0], "MSFT")

    def test_normalizes_bare_hk_codes_to_dot_hk(self):
        from tradingagents.dataflows import yfinance_etf

        df = pd.DataFrame(
            {"Name": ["Alibaba", "Tencent"], "Holding Percent": [0.10, 0.09]},
            index=["09988", "00700"],
        )
        with patch.object(
            yfinance_etf.yf, "Ticker",
            return_value=self._ticker_with_top_holdings(df),
        ):
            out = yfinance_etf.get_top_holding_tickers("2800.HK", top_n=2)
        # 5-digit numeric → ".HK" suffix appended
        self.assertEqual(out[0][0], "09988.HK")
        self.assertEqual(out[1][0], "00700.HK")

    def test_returns_empty_when_funds_data_missing(self):
        from tradingagents.dataflows import yfinance_etf

        m = MagicMock()
        m.funds_data = None
        with patch.object(yfinance_etf.yf, "Ticker", return_value=m):
            out = yfinance_etf.get_top_holding_tickers("WEIRD", top_n=3)
        self.assertEqual(out, [])

    def test_handles_yfinance_already_percent_weight(self):
        """yfinance is inconsistent: usually returns decimal but sometimes
        the value is already in percent form (e.g. 7.2). The 1.5 threshold
        treats >=1.5 as already-percent."""
        from tradingagents.dataflows import yfinance_etf

        df = pd.DataFrame(
            {"Name": ["X Co"], "Holding Percent": [7.2]},
            index=["XYZ"],
        )
        with patch.object(
            yfinance_etf.yf, "Ticker",
            return_value=self._ticker_with_top_holdings(df),
        ):
            out = yfinance_etf.get_top_holding_tickers("SOMEONE", top_n=1)
        self.assertAlmostEqual(out[0][2], 7.2, places=2)  # not 720


@pytest.mark.unit
class AlphaVantageTopHoldingTickersTests(unittest.TestCase):
    _SAMPLE = {
        "symbol": "QQQ",
        "holdings": [
            {"symbol": "AAPL", "description": "Apple Inc", "weight": "0.092"},
            {"symbol": "MSFT", "description": "Microsoft Corp", "weight": "0.085"},
            {"symbol": "NVDA", "description": "Nvidia Corp", "weight": "0.064"},
        ],
    }

    def test_returns_top_n_tuples_with_percent_weights(self):
        from tradingagents.dataflows import alpha_vantage_etf

        with patch.object(alpha_vantage_etf, "_make_api_request", return_value=self._SAMPLE):
            out = alpha_vantage_etf.get_top_holding_tickers("QQQ", top_n=2)
        self.assertEqual([t[0] for t in out], ["AAPL", "MSFT"])
        self.assertAlmostEqual(out[0][2], 9.2, places=2)  # 0.092 → 9.2%
        self.assertAlmostEqual(out[1][2], 8.5, places=2)

    def test_returns_empty_on_missing_holdings(self):
        from tradingagents.dataflows import alpha_vantage_etf

        with patch.object(alpha_vantage_etf, "_make_api_request", return_value={"symbol": "X"}):
            out = alpha_vantage_etf.get_top_holding_tickers("X", top_n=3)
        self.assertEqual(out, [])


# ---------------------------------------------------------------------------
# Drill-down orchestration
# ---------------------------------------------------------------------------

@pytest.mark.unit
class EtfDrilldownTests(unittest.TestCase):
    def _patch_etf_yes(self):
        return patch(
            "tradingagents.dataflows.etf_utils._yfinance_quote_type",
            return_value="ETF",
        )

    def test_non_etf_ticker_returns_redirect_message(self):
        """Drill-down should refuse non-ETF tickers without paying the
        constituent API calls."""
        from tradingagents.dataflows import etf_drilldown

        with patch(
            "tradingagents.dataflows.etf_utils._yfinance_quote_type",
            return_value="EQUITY",
        ):
            out = etf_drilldown.get_etf_top_holdings_drilldown(
                "AAPL", "2025-01-01", "2025-01-31"
            )
        self.assertIn("regular stock", out)
        self.assertIn("get_fundamentals", out)

    def test_renders_one_section_per_constituent(self):
        from tradingagents.dataflows import etf_drilldown, interface

        def fake_route(method, *args, **kwargs):
            if method == "get_top_holding_tickers":
                return [
                    ("AAPL", "Apple Inc.", 7.2),
                    ("MSFT", "Microsoft Corp.", 6.5),
                ]
            if method == "get_fundamentals":
                return f"FUNDAMENTALS_FOR_{args[0]}"
            if method == "get_news":
                return f"NEWS_FOR_{args[0]}"
            raise AssertionError(f"unexpected method {method}")

        with self._patch_etf_yes(), \
             patch.object(interface, "route_to_vendor", side_effect=fake_route):
            out = etf_drilldown.get_etf_top_holdings_drilldown(
                "SPY", "2025-01-01", "2025-01-31", top_n=2
            )
        self.assertIn("Top-2 holdings drill-down for ETF SPY", out)
        self.assertIn("## Apple Inc. (AAPL) — weight: 7.20%", out)
        self.assertIn("FUNDAMENTALS_FOR_AAPL", out)
        self.assertIn("NEWS_FOR_AAPL", out)
        self.assertIn("## Microsoft Corp. (MSFT) — weight: 6.50%", out)
        self.assertIn("FUNDAMENTALS_FOR_MSFT", out)
        self.assertIn("\n\n---\n\n", out)  # blocks separated by horizontal rule

    def test_empty_holdings_returns_friendly_message(self):
        from tradingagents.dataflows import etf_drilldown, interface

        with self._patch_etf_yes(), \
             patch.object(interface, "route_to_vendor", return_value=[]):
            out = etf_drilldown.get_etf_top_holdings_drilldown(
                "WEIRD", "2025-01-01", "2025-01-31"
            )
        self.assertIn("No top holdings could be resolved", out)

    def test_per_constituent_exception_does_not_kill_report(self):
        """If one constituent's fundamentals call blows up, the rest of
        the report must still render — surface the failure inline."""
        from tradingagents.dataflows import etf_drilldown, interface

        def fake_route(method, *args, **kwargs):
            if method == "get_top_holding_tickers":
                return [
                    ("BAD", "Bad Co", 5.0),
                    ("GOOD", "Good Co", 3.0),
                ]
            if method == "get_fundamentals" and args[0] == "BAD":
                raise RuntimeError("API exploded")
            if method == "get_fundamentals":
                return f"FUNDAMENTALS_FOR_{args[0]}"
            if method == "get_news":
                return f"NEWS_FOR_{args[0]}"

        with self._patch_etf_yes(), \
             patch.object(interface, "route_to_vendor", side_effect=fake_route):
            out = etf_drilldown.get_etf_top_holdings_drilldown(
                "SPY", "2025-01-01", "2025-01-31", top_n=2
            )
        self.assertIn("BAD", out)
        self.assertIn("API exploded", out)
        self.assertIn("FUNDAMENTALS_FOR_GOOD", out)
        self.assertIn("NEWS_FOR_GOOD", out)

    def test_truncates_long_fundamentals_and_news_blocks(self):
        """Each constituent section caps fundamentals at 1500 and news at
        1200 chars to keep the LLM's context window manageable."""
        from tradingagents.dataflows import etf_drilldown, interface

        big_fund = "F" * 5000
        big_news = "N" * 5000

        def fake_route(method, *args, **kwargs):
            if method == "get_top_holding_tickers":
                return [("AAPL", "Apple Inc.", 7.2)]
            if method == "get_fundamentals":
                return big_fund
            if method == "get_news":
                return big_news

        with self._patch_etf_yes(), \
             patch.object(interface, "route_to_vendor", side_effect=fake_route):
            out = etf_drilldown.get_etf_top_holdings_drilldown(
                "SPY", "2025-01-01", "2025-01-31", top_n=1
            )
        self.assertIn("…(truncated, full length 5000)", out)
        self.assertNotIn(big_fund, out)
        self.assertNotIn(big_news, out)


# ---------------------------------------------------------------------------
# Drill-down routing
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TopHoldingTickersRoutingTests(unittest.TestCase):
    def test_routes_to_yfinance_by_default(self):
        from tradingagents.dataflows import interface

        sentinel = [("AAPL", "Apple", 7.2)]
        with patch.dict(
            interface.VENDOR_METHODS["get_top_holding_tickers"],
            {"yfinance": MagicMock(return_value=sentinel)},
        ):
            out = interface.route_to_vendor("get_top_holding_tickers", "SPY", 3)
        self.assertEqual(out, sentinel)

    def test_routes_to_alpha_vantage_when_configured(self):
        from tradingagents.dataflows import interface
        from tradingagents.dataflows.config import get_config, set_config

        cfg = get_config()
        cfg["data_vendors"]["etf_data"] = "alpha_vantage"
        set_config(cfg)

        sentinel = [("AAPL", "Apple", 9.2)]
        with patch.dict(
            interface.VENDOR_METHODS["get_top_holding_tickers"],
            {"alpha_vantage": MagicMock(return_value=sentinel)},
        ):
            out = interface.route_to_vendor("get_top_holding_tickers", "QQQ", 3)
        self.assertEqual(out, sentinel)
