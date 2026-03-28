"""Live integration tests for the gatekeeper universe and Finviz gap subset.

These tests intentionally hit real yfinance and finvizfinance paths with no
mocks so the scanner foundation is validated before more graph changes land.
"""

import pytest


pytestmark = [pytest.mark.integration, pytest.mark.enable_socket()]


def test_yfinance_gatekeeper_query_data_path():
    import yfinance as yf
    from yfinance import EquityQuery

    query = EquityQuery(
        "and",
        [
            EquityQuery("is-in", ["exchange", "NMS", "NYQ", "ASE"]),
            EquityQuery("gte", ["intradaymarketcap", 2_000_000_000]),
            EquityQuery("gt", ["netincomemargin.lasttwelvemonths", 0]),
            EquityQuery("gt", ["avgdailyvol3m", 2_000_000]),
            EquityQuery("gt", ["intradayprice", 5]),
        ],
    )

    result = yf.screen(query, size=10, sortField="dayvolume", sortAsc=False)
    assert isinstance(result, dict)
    quotes = result.get("quotes", [])
    assert quotes, "Gatekeeper yfinance query returned no quotes"

    us_exchanges = {"NMS", "NYQ", "ASE"}
    for quote in quotes:
        assert quote.get("exchange") in us_exchanges
        assert float(quote.get("regularMarketPrice") or 0) > 5
        assert float(quote.get("averageDailyVolume3Month") or 0) > 2_000_000
        assert float(quote.get("marketCap") or 0) >= 2_000_000_000


def test_gatekeeper_universe_tool_live():
    from tradingagents.agents.utils.scanner_tools import get_gatekeeper_universe

    result = get_gatekeeper_universe.invoke({})
    assert isinstance(result, str)
    assert result.startswith("# Gatekeeper Universe") or result == "No stocks matched the gatekeeper universe today."


def test_finviz_gatekeeper_gap_filter_data_path():
    from finvizfinance.screener.overview import Overview

    overview = Overview()
    overview.set_filter(
        filters_dict={
            "Market Cap.": "+Mid (over $2bln)",
            "Net Profit Margin": "Positive (>0%)",
            "Average Volume": "Over 2M",
            "Price": "Over $5",
            "Gap": "Up 5%",
        }
    )
    df = overview.screener_view(limit=10, verbose=0)

    if df is None:
        pytest.skip("Finviz returned no page for the gatekeeper gap filter today")

    assert hasattr(df, "empty")
    if df.empty:
        pytest.skip("No Finviz stocks matched the gatekeeper gap filter today")

    assert "Ticker" in df.columns
    assert len(df) >= 1


def test_gap_candidates_tool_live():
    from tradingagents.agents.utils.scanner_tools import get_gap_candidates

    result = get_gap_candidates.invoke({})
    assert isinstance(result, str)
    assert (
        result.startswith("Top 5 stocks for gatekeeper_gap:")
        or result == "No stocks matched the gatekeeper_gap criteria today."
        or result.startswith("Smart money scan unavailable (Finviz error):")
    )
    assert "Invalid filter" not in result
