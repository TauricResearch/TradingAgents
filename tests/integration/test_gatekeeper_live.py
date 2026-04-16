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


# ── New tests for the retry + fallback redesign ───────────────────────────────

def test_gatekeeper_universe_yfinance_primary_path_live():
    """Primary path: custom EquityQuery returns real data with expected structure."""
    from tradingagents.dataflows.yfinance_scanner import get_gatekeeper_universe_yfinance

    result = get_gatekeeper_universe_yfinance(limit=10)

    assert isinstance(result, str), "Expected string output"
    assert len(result) > 100, "Result is unexpectedly short"

    # Header must be present (primary or fallback)
    assert "# Gatekeeper Universe" in result, f"Missing header in result: {result[:200]}"

    # Markdown table columns must be present
    assert "| Symbol |" in result, "Missing Symbol column"
    assert "| Market Cap |" in result, "Missing Market Cap column"

    # At least one data row beyond the header rows
    rows = [line for line in result.splitlines() if line.startswith("| ") and "Symbol" not in line and "---" not in line]
    assert len(rows) >= 1, f"No data rows found in result:\n{result[:500]}"

    # Every data row must have a real ticker (non-empty first cell)
    for row in rows:
        cells = [c.strip() for c in row.split("|") if c.strip()]
        symbol = cells[0] if cells else ""
        assert symbol and symbol != "N/A", f"Empty or N/A symbol in row: {row}"


def test_gatekeeper_universe_yfinance_numeric_evidence_live():
    """Validates that the returned report contains numeric price / market-cap evidence."""
    from tradingagents.dataflows.yfinance_scanner import get_gatekeeper_universe_yfinance
    from tradingagents.agents.utils.report_quality import assess_report_quality

    result = get_gatekeeper_universe_yfinance(limit=10)

    assessment = assess_report_quality(result, node_name="gatekeeper_scanner", requires_tools=True)
    assert assessment["quality"] in ("ok", "degraded"), (
        f"Expected ok/degraded quality but got '{assessment['quality']}'. "
        f"Issues: {assessment['issues']}. Evidence: {assessment['evidence_count']}"
    )
    assert assessment["evidence_count"] >= 5, (
        f"Too few numeric evidence tokens ({assessment['evidence_count']}); "
        "report may be hallucinated or empty."
    )


def test_gatekeeper_universe_yfinance_fallback_path_live():
    """Fallback path: when EquityQuery raises, the function falls back to MOST_ACTIVES
    screener using a real live network call (no mock for the fallback itself)."""
    import time
    from unittest.mock import patch
    import yfinance as yf
    from tradingagents.dataflows.yfinance_scanner import get_gatekeeper_universe_yfinance

    original_screen = yf.screen
    call_count = {"n": 0}

    def fail_equity_query(query_or_key, **kwargs):
        call_count["n"] += 1
        # EquityQuery objects have a body attribute; predefined keys are strings
        if not isinstance(query_or_key, str):
            raise Exception("Simulated 401 Unauthorized (EquityQuery path)")
        # Fallback call with string key goes to the real API
        return original_screen(query_or_key, **kwargs)

    with patch.object(yf, "screen", side_effect=fail_equity_query):
        with patch.object(time, "sleep", return_value=None):  # skip real backoff delays
            result = get_gatekeeper_universe_yfinance(limit=10)

    # 3 EquityQuery retries + 1 MOST_ACTIVES fallback = 4 calls
    assert call_count["n"] == 4, (
        f"Expected 4 screen calls (3 retries + 1 fallback), got {call_count['n']}"
    )

    assert isinstance(result, str)
    assert "# Gatekeeper Universe" in result, f"Missing header. Got: {result[:300]}"
    assert "fallback" in result, "Fallback header note missing from result"

    # The fallback still returns real data
    rows = [l for l in result.splitlines() if l.startswith("| ") and "Symbol" not in l and "---" not in l]
    assert len(rows) >= 1, "No data rows in fallback result"


def test_finviz_gatekeeper_gap_filter_data_path():
    finvizfinance = pytest.importorskip("finvizfinance.screener.overview")
    Overview = finvizfinance.Overview

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
        "# Gap Candidates" in result
        or "No stocks matched the gatekeeper gap criteria today." in result
        or "Smart money scan unavailable (Finviz error):" in result
    )
    assert "Invalid filter" not in result
