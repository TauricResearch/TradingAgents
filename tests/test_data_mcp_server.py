"""Tests for the TradingAgents data MCP server.

These tests are network-free: the underlying ``route_to_vendor`` dispatch and
``yfinance`` are mocked. They verify (1) the expected tool surface is exposed,
(2) each MCP tool delegates to the existing data implementation with the right
arguments, and (3) the realized-return / benchmark math behaves correctly.
"""

import asyncio
import json
from unittest import mock

import pytest

from tradingagents.mcp import _returns, data_server

# --------------------------------------------------------------------------- #
# Tool surface
# --------------------------------------------------------------------------- #
EXPECTED_TOOLS = {
    "get_stock_price_data",
    "get_technical_indicators",
    "get_market_snapshot",
    "get_ticker_news",
    "get_macro_news",
    "get_company_insider_transactions",
    "get_stocktwits_messages",
    "get_reddit_posts",
    "get_macro_indicator",
    "get_event_prediction_markets",
    "get_company_fundamentals",
    "get_company_balance_sheet",
    "get_company_cashflow",
    "get_company_income_statement",
    "resolve_instrument",
    "get_realized_return",
}


@pytest.mark.unit
def test_server_exposes_expected_tools():
    tools = asyncio.run(data_server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS


@pytest.mark.unit
def test_every_tool_has_description_and_schema():
    tools = asyncio.run(data_server.mcp.list_tools())
    for t in tools:
        assert t.description, f"{t.name} is missing a description"
        assert t.inputSchema.get("type") == "object"


# --------------------------------------------------------------------------- #
# Delegation: each data tool calls the underlying route_to_vendor correctly.
# We patch route_to_vendor in the interface module (where the @tool wrappers
# import it from) so we assert the exact method name + args reach the dispatch.
# --------------------------------------------------------------------------- #
# The @tool wrappers do ``from ...interface import route_to_vendor`` at import
# time, binding the name in each tool module's namespace — so patch it there,
# not on the interface module.
@pytest.mark.unit
def test_get_stock_price_data_delegates():
    with mock.patch(
        "tradingagents.agents.utils.core_stock_tools.route_to_vendor",
        return_value="OHLCV",
    ) as rv:
        out = data_server.get_stock_price_data("AAPL", "2026-01-01", "2026-01-10")
    assert out == "OHLCV"
    rv.assert_called_once_with("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")


@pytest.mark.unit
def test_get_ticker_news_delegates():
    with mock.patch(
        "tradingagents.agents.utils.news_data_tools.route_to_vendor",
        return_value="NEWS",
    ) as rv:
        out = data_server.get_ticker_news("TSLA", "2026-01-01", "2026-01-10")
    assert out == "NEWS"
    rv.assert_called_once_with("get_news", "TSLA", "2026-01-01", "2026-01-10")


@pytest.mark.unit
def test_get_company_fundamentals_delegates():
    with mock.patch(
        "tradingagents.agents.utils.fundamental_data_tools.route_to_vendor",
        return_value="FUND",
    ) as rv:
        out = data_server.get_company_fundamentals("MSFT", "2026-01-10")
    assert out == "FUND"
    rv.assert_called_once_with("get_fundamentals", "MSFT", "2026-01-10")


@pytest.mark.unit
def test_get_macro_indicator_passes_optional_lookback():
    with mock.patch(
        "tradingagents.agents.utils.macro_data_tools.route_to_vendor",
        return_value="MACRO",
    ) as rv:
        out = data_server.get_macro_indicator("cpi", "2026-01-10", 90)
    assert out == "MACRO"
    rv.assert_called_once_with("get_macro_indicators", "cpi", "2026-01-10", 90)


@pytest.mark.unit
def test_balance_sheet_default_frequency():
    with mock.patch(
        "tradingagents.agents.utils.fundamental_data_tools.route_to_vendor",
        return_value="BS",
    ) as rv:
        data_server.get_company_balance_sheet("AAPL", curr_date="2026-01-10")
    rv.assert_called_once_with("get_balance_sheet", "AAPL", "quarterly", "2026-01-10")


@pytest.mark.unit
def test_market_snapshot_delegates_to_validator():
    with mock.patch(
        "tradingagents.agents.utils.market_data_validation_tools."
        "build_verified_market_snapshot",
        return_value="SNAP",
    ) as bv:
        out = data_server.get_market_snapshot("AAPL", "2026-01-10", 20)
    assert out == "SNAP"
    bv.assert_called_once_with("AAPL", "2026-01-10", 20)


# --------------------------------------------------------------------------- #
# resolve_instrument: anchoring context built from resolved identity.
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_resolve_instrument_builds_context_with_identity():
    with mock.patch(
        "tradingagents.mcp.data_server.resolve_instrument_identity",
        return_value={"company_name": "Apple Inc.", "sector": "Technology"},
    ):
        ctx = data_server.resolve_instrument("AAPL")
    assert "AAPL" in ctx
    assert "Apple Inc." in ctx


@pytest.mark.unit
def test_resolve_instrument_crypto_falls_back_without_identity():
    with mock.patch(
        "tradingagents.mcp.data_server.resolve_instrument_identity",
        return_value={},
    ):
        ctx = data_server.resolve_instrument("BTC-USD", asset_type="crypto")
    assert "BTC-USD" in ctx
    assert "crypto asset" in ctx


# --------------------------------------------------------------------------- #
# Realized return / benchmark math (pure, yfinance mocked).
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_resolve_benchmark_uses_suffix_map():
    assert _returns.resolve_benchmark("7203.T") == "^N225"
    assert _returns.resolve_benchmark("0700.HK") == "^HSI"
    # US ticker with no recognised suffix -> SPY default.
    assert _returns.resolve_benchmark("AAPL") == "SPY"


@pytest.mark.unit
def test_resolve_benchmark_explicit_override(monkeypatch):
    from tradingagents.dataflows import config as cfg

    cfg.set_config({"benchmark_ticker": "QQQ"})
    assert _returns.resolve_benchmark("7203.T") == "QQQ"


class _FakeHistory:
    """Minimal stand-in for a yfinance history DataFrame."""

    def __init__(self, closes):
        self._closes = closes

    def __len__(self):
        return len(self._closes)

    def __getitem__(self, key):
        assert key == "Close"
        return _FakeCol(self._closes)


class _FakeCol:
    def __init__(self, values):
        self.iloc = values


@pytest.mark.unit
def test_fetch_realized_return_computes_alpha():
    stock = _FakeHistory([100.0, 101, 102, 103, 104, 110.0])  # +10% over 5 days
    bench = _FakeHistory([400.0, 401, 402, 403, 404, 408.0])  # +2% over 5 days

    def fake_ticker(sym):
        m = mock.Mock()
        m.history.return_value = stock if sym != "SPY" else bench
        return m

    with mock.patch("tradingagents.mcp._returns.yf.Ticker", side_effect=fake_ticker):
        out = _returns.fetch_realized_return("AAPL", "2026-01-05", holding_days=5)

    assert out["available"] is True
    assert out["benchmark"] == "SPY"
    assert out["raw_return"] == pytest.approx(0.10, abs=1e-9)
    assert out["benchmark_return"] == pytest.approx(0.02, abs=1e-9)
    assert out["alpha_return"] == pytest.approx(0.08, abs=1e-9)


@pytest.mark.unit
def test_fetch_realized_return_unavailable_when_too_recent():
    short = _FakeHistory([100.0])  # < 2 rows -> not enough data

    def fake_ticker(sym):
        m = mock.Mock()
        m.history.return_value = short
        return m

    with mock.patch("tradingagents.mcp._returns.yf.Ticker", side_effect=fake_ticker):
        out = _returns.fetch_realized_return("AAPL", "2026-06-14")

    assert out["available"] is False
    assert "reason" in out


@pytest.mark.unit
def test_get_realized_return_tool_returns_json_serialisable_dict():
    with mock.patch(
        "tradingagents.mcp.data_server.fetch_realized_return",
        return_value={"ticker": "AAPL", "available": False, "reason": "x"},
    ):
        out = data_server.get_realized_return("AAPL", "2026-06-14")
    # The tool returns a dict; it must round-trip through JSON for MCP transport.
    assert json.loads(json.dumps(out))["ticker"] == "AAPL"
