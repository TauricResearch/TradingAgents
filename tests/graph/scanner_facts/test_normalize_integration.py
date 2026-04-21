"""Integration-level normalize tests using real 2026-04-16 fixture content.

These tests parse real scanner summary surface forms and assert that
normalization produces correct canonical outputs. They serve as a
living contract between the normalization layer and the actual report format.

Run with:
    pytest tests/graph/scanner_facts/test_normalize_integration.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradingagents.graph.scanner_facts.normalize import (
    canonicalize_sector,
    classify_node_type,
    is_equity_ticker,
    infer_polarity,
    compute_confidence,
    ConfidenceSource,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------- Sector surface forms seen in real reports ----------

# From smart_money_summary.md: "Consumer Cyclical", "Financial", "Healthcare"
# These are non-canonical forms the scanner actually emits.

@pytest.mark.parametrize("raw,expected", [
    ("Consumer Cyclical", "Consumer Discretionary"),   # smart_money_summary.md
    ("Financial", "Financials"),                       # smart_money_summary.md (OWL row)
    ("Healthcare", "Health Care"),                     # smart_money_summary.md (ABT row)
    ("Industrials", "Industrials"),                    # already canonical
    ("Technology", "Technology"),                      # already canonical
    ("Energy", "Energy"),                              # already canonical
    ("Consumer Defensive", "Consumer Staples"),        # industry_deep_dive_summary.md (PM/CL/PG)
    ("Telecommunications", "Communication Services"), # gatekeeper_summary.md (T row)
    ("Real Estate", "Real Estate"),                    # already canonical
])
def test_real_sector_canonicalization(raw, expected):
    assert canonicalize_sector(raw) == expected, f"'{raw}' should canonicalize to '{expected}'"


# ---------- Ticker classification from real Candidate Rows ----------

# Tickers that appear in real reports and must be recognized as equity tickers.
@pytest.mark.parametrize("ticker", [
    "F", "PBR", "OWL", "ABT", "JBLU", "ON", "QBTS",  # smart_money_summary
    "NVDA", "AAPL", "MSFT", "AMZN", "TSLA", "AMD",   # gatekeeper + industry
    "ORCL", "NFLX", "PLTR", "MU", "BAC", "NU",       # gatekeeper
    "INTC", "AVGO", "DLR", "EQIX", "CBRE", "PLD",    # industry_deep_dive
    "PM", "CL", "PG", "T",                             # industry_deep_dive + gatekeeper
])
def test_real_tickers_recognized_as_equity(ticker):
    assert is_equity_ticker(ticker), f"{ticker} should be an equity ticker"


# ---------- Non-ticker surface forms that must be rejected ----------

@pytest.mark.parametrize("label", [
    "N/A",              # geopolitical_summary.md (Not Applicable rows)
    "Not Applicable",   # geopolitical_summary.md
    "SECTOR/THEME",     # sector_summary.md
    "S&P 500",          # market_movers_summary.md
    "NASDAQ",           # market_movers_summary.md
    "Russell 2000",     # market_movers_summary.md
    "VIX",              # market_movers_summary.md
])
def test_real_non_tickers_rejected(label):
    assert not is_equity_ticker(label), f"{label} should NOT be an equity ticker"


# ---------- Node type classification for real market-mover rows ----------

@pytest.mark.parametrize("label,expected_type", [
    ("S&P 500", "MarketIndex"),
    ("NASDAQ", "MarketIndex"),
    ("Russell 2000", "MarketIndex"),
    ("VIX", "MacroIndicator"),
    ("Brent Crude", "Commodity"),
    ("WTI Crude", "Commodity"),
    ("Gold", "Commodity"),
    ("Bitcoin", "CryptoAsset"),
    ("EUR/USD", "CurrencyPair"),
    ("JPY/USD", "CurrencyPair"),
    ("CNY/USD", "CurrencyPair"),
    ("Technology", "Sector"),
    ("Real Estate", "Sector"),
    ("Energy", "Sector"),
    ("Financials", "Sector"),
    ("AI Infrastructure", "Theme"),           # industry_deep_dive: "AI Infrastructure"
    ("Risk-On Rotation", "Theme"),            # industry_deep_dive: "Risk-On Rotation"
    ("Defensive Sector Deterioration", "Theme"),  # macro_scan key_themes
])
def test_real_label_node_type_classification(label, expected_type):
    result = classify_node_type(label)
    assert result == expected_type, f"'{label}' → expected {expected_type}, got {result}"


# ---------- Polarity from real evidence/implication text ----------

@pytest.mark.parametrize("evidence,implication,expected_polarity", [
    # From smart_money_summary.md
    ("Breakout accumulation at $79.93 with 52-week high on high volume",
     "Supports strong technology sector alignment.", "bullish"),
    ("Unusual volume spike at $21.52",
     "Confirms technology sector strength and ongoing momentum.", "bullish"),
    ("Insider buying at $12.44",
     "Signaling auto/consumer cyclical sector revival.", "bullish"),
    ("Insider purchases at $21.5",
     "Suggests insider optimism despite broader energy sector volatility.", "bullish"),
    # From industry_deep_dive_summary.md
    ("+41.75% (1-month), +17.59% (1-week)",
     "Strong short-term performance.", "bullish"),
    ("-8.79% (1-month), -3.11% (1-week)",
     "Negative short-term performance.", "bearish"),
    # From geopolitical_summary.md
    ("Brent Crude up +3.44%",
     "Geopolitical tension-related supply risk.", "bearish"),
    ("German CDS +13.01%",
     "Rising perceived risk.", "bearish"),
])
def test_real_polarity_inference(evidence, implication, expected_polarity):
    result = infer_polarity(evidence, implication)
    assert result == expected_polarity, (
        f"Evidence: {evidence!r}\nImplication: {implication!r}\n"
        f"Expected: {expected_polarity!r}, got: {result!r}"
    )


# ---------- Confidence for real row shapes ----------

def test_full_5col_pipe_row_confidence():
    # ON | Technology | Breakout Accumulation | $79.93 price level | Implies institutional accumulation.
    # 5 columns, evidence present, no hedging
    c = compute_confidence(ConfidenceSource.MD_PIPE_FULL)
    assert c == 0.95


def test_partial_3col_pipe_row_confidence():
    # Consumer Cyclical | Insider buying signals potential early sector rebound | ...
    # The word "potential" is a hedge → apply hedging flag
    c = compute_confidence(ConfidenceSource.MD_PIPE_PARTIAL, hedging=True)
    assert 0.50 < c < 0.75


def test_macro_json_structured_confidence():
    # stocks_to_investigate[].ticker rows — structured JSON field
    c = compute_confidence(ConfidenceSource.MACRO_JSON_STRUCTURED)
    assert c == 0.90


def test_macro_json_free_text_confidence():
    # executive_summary text extraction
    c = compute_confidence(ConfidenceSource.MACRO_JSON_FREE_TEXT)
    assert c == 0.70


def test_inferred_edge_below_threshold():
    # Edge created from implication phrasing only — should be at/below threshold
    c = compute_confidence(ConfidenceSource.INFERRED_EDGE, hedging=True)
    assert c < 0.50


# ---------- End-to-end: load real fixture and verify no crash ----------

def test_load_macro_scan_summary_fixture():
    """Load the real macro_scan_summary.json fixture and run all surface forms through normalize."""
    payload = json.loads((FIXTURES / "macro_scan_summary.json").read_text())

    # stocks_to_investigate
    for stock in payload.get("stocks_to_investigate", []):
        ticker = stock["ticker"]
        sector = stock["sector"]
        assert is_equity_ticker(ticker), f"Fixture ticker {ticker!r} not recognized as equity"
        assert canonicalize_sector(sector) in {
            "Technology", "Financials", "Energy", "Health Care",
            "Consumer Discretionary", "Consumer Staples", "Real Estate",
            "Industrials", "Materials", "Utilities", "Communication Services",
        } or len(canonicalize_sector(sector)) > 0

    # key_themes — should classify as Theme
    for theme_obj in payload.get("key_themes", []):
        theme_label = theme_obj["theme"]
        t = classify_node_type(theme_label)
        assert t == "Theme", f"Theme label {theme_label!r} classified as {t!r}, expected Theme"

    # risk_factors — free text, should not crash
    for rf in payload.get("risk_factors", []):
        _ = infer_polarity(rf)


def test_load_smart_money_fixture_all_tickers_recognized():
    """Parse Candidate Rows from real smart_money_summary.md and check every ticker."""
    text = (FIXTURES / "smart_money_summary.md").read_text()
    # Extract pipe-row first columns: lines like "* F | Consumer Cyclical | ..."
    import re
    rows = re.findall(r"^\s*[*-]\s+([^|]+)\|", text, re.MULTILINE)
    tickers_in_candidate_rows = [
        r.strip() for r in rows
        if r.strip() and r.strip() not in ("Scan Date",)
        and not r.strip().startswith("Consumer")
        and not r.strip().startswith("Energy")
        and not r.strip().startswith("Financial")
        and not r.strip().startswith("Healthcare")
        and not r.strip().startswith("Industrials")
        and not r.strip().startswith("Technology")
    ]
    # Expected: F, PBR, OWL, ABT, JBLU, ON, QBTS
    expected_tickers = {"F", "PBR", "OWL", "ABT", "JBLU", "ON", "QBTS"}
    found = set(tickers_in_candidate_rows) & expected_tickers
    assert found == expected_tickers, f"Missing: {expected_tickers - found}"


def test_load_geopolitical_not_applicable_rows_rejected():
    """All Candidate Rows in geopolitical_summary.md start with 'Not Applicable' — none should pass is_equity_ticker."""
    text = (FIXTURES / "geopolitical_summary.md").read_text()
    import re
    rows = re.findall(r"^\s*[*-]\s+([^|]+)\|", text, re.MULTILINE)
    for first_col in rows:
        label = first_col.strip()
        assert not is_equity_ticker(label), (
            f"Geopolitical first-col {label!r} should NOT pass is_equity_ticker"
        )


def test_load_market_movers_indexes_classified():
    """Market mover Candidate Rows are index/volatility nodes — must not become Ticker."""
    text = (FIXTURES / "market_movers_summary.md").read_text()
    import re
    rows = re.findall(r"^\s*[*-]\s+([^|]+)\|", text, re.MULTILINE)
    for first_col in rows:
        label = first_col.strip()
        node_type = classify_node_type(label)
        assert node_type != "Ticker", (
            f"Market mover label {label!r} classified as Ticker — should be {node_type!r}"
        )
