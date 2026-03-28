"""Live integration test for the real gap-detection data path.

This test intentionally exercises the raw yfinance path with no mocks before
the scanner tool is relied upon by the agent layer.
"""

import pytest


pytestmark = pytest.mark.integration


@pytest.mark.integration
def test_yfinance_gap_detection_data_path():
    import yfinance as yf

    screen = yf.screen("MOST_ACTIVES", count=10)
    assert isinstance(screen, dict)
    quotes = screen.get("quotes", [])
    assert quotes, "MOST_ACTIVES returned no quotes"

    symbols = []
    for quote in quotes:
        symbol = quote.get("symbol")
        if symbol and symbol not in symbols:
            symbols.append(symbol)
        if len(symbols) == 5:
            break

    assert symbols, "No symbols extracted from screen results"

    hist = yf.download(
        symbols,
        period="5d",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=True,
    )
    assert not hist.empty, "download returned no OHLC data"

    gap_rows = []
    for symbol in symbols:
        try:
            opens = hist["Open"][symbol].dropna()
            closes = hist["Close"][symbol].dropna()
        except KeyError:
            continue

        if len(opens) < 1 or len(closes) < 2:
            continue

        today_open = float(opens.iloc[-1])
        prev_close = float(closes.iloc[-2])
        if prev_close == 0:
            continue

        gap_pct = (today_open - prev_close) / prev_close * 100
        gap_rows.append((symbol, gap_pct))

    assert gap_rows, "Could not compute any real gap percentages from live OHLC data"
    assert all(isinstance(symbol, str) and isinstance(gap_pct, float) for symbol, gap_pct in gap_rows)


@pytest.mark.integration
def test_gap_candidates_tool_live():
    from tradingagents.agents.utils.scanner_tools import get_gap_candidates

    result = get_gap_candidates.invoke({})
    assert isinstance(result, str)
    assert (
        "# Gap Candidates" in result
        or "No stocks matched the live gap criteria today." in result
        or "No stocks matched the live gap universe today." in result
    )
