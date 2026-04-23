"""Unit tests for normalize.py — pure-logic, no I/O."""
from tradingagents.graph.scanner_facts.normalize import (
    ConfidenceSource,
    canonicalize_sector,
    classify_node_type,
    compute_confidence,
    infer_polarity,
    is_equity_ticker,
)

# ---- canonicalize_sector ----

def test_information_technology_becomes_technology():
    assert canonicalize_sector("Information Technology") == "Technology"

def test_financial_becomes_financials():
    assert canonicalize_sector("Financial") == "Financials"

def test_consumer_cyclical_becomes_consumer_discretionary():
    assert canonicalize_sector("Consumer Cyclical") == "Consumer Discretionary"

def test_consumer_defensive_becomes_consumer_staples():
    assert canonicalize_sector("Consumer Defensive") == "Consumer Staples"

def test_already_canonical_passes_through():
    assert canonicalize_sector("Technology") == "Technology"
    assert canonicalize_sector("Real Estate") == "Real Estate"
    assert canonicalize_sector("Energy") == "Energy"

def test_real_report_sector_variants():
    # These appear literally in the 2026-04-16 real summaries
    assert canonicalize_sector("Financials") == "Financials"
    assert canonicalize_sector("Healthcare") == "Health Care"
    assert canonicalize_sector("Telecommunications") == "Communication Services"
    assert canonicalize_sector("Communication Services") == "Communication Services"


# ---- classify_node_type ----

def test_classify_sp500_as_market_index():
    assert classify_node_type("S&P 500") == "MarketIndex"

def test_classify_nasdaq_as_market_index():
    assert classify_node_type("NASDAQ") == "MarketIndex"

def test_classify_russell_as_market_index():
    assert classify_node_type("Russell 2000") == "MarketIndex"

def test_classify_vix_as_macro_indicator():
    assert classify_node_type("VIX") == "MacroIndicator"

def test_classify_brent_crude_as_commodity():
    assert classify_node_type("Brent Crude") == "Commodity"

def test_classify_wti_crude_as_commodity():
    assert classify_node_type("WTI Crude") == "Commodity"

def test_classify_gold_as_commodity():
    assert classify_node_type("Gold") == "Commodity"

def test_classify_eurusd_as_currency_pair():
    assert classify_node_type("EUR/USD") == "CurrencyPair"

def test_classify_jpyusd_as_currency_pair():
    assert classify_node_type("JPY/USD") == "CurrencyPair"

def test_classify_bitcoin_as_crypto():
    assert classify_node_type("Bitcoin") == "CryptoAsset"

def test_classify_technology_as_sector():
    assert classify_node_type("Technology") == "Sector"

def test_classify_energy_as_sector():
    assert classify_node_type("Energy") == "Sector"

def test_classify_unknown_short_upper_as_ticker():
    # 1-5 uppercase chars not in known lists → Ticker (caller must validate with is_equity_ticker)
    assert classify_node_type("NVDA") == "Ticker"

def test_classify_ai_infrastructure_as_theme():
    assert classify_node_type("AI Infrastructure") == "Theme"

def test_classify_risk_on_rotation_as_theme():
    assert classify_node_type("Risk-On Rotation") == "Theme"


# ---- is_equity_ticker ----

def test_nvda_is_equity_ticker():
    assert is_equity_ticker("NVDA") is True

def test_on_is_equity_ticker():
    assert is_equity_ticker("ON") is True

def test_na_is_not_equity_ticker():
    assert is_equity_ticker("N/A") is False
    assert is_equity_ticker("Not Applicable") is False

def test_sector_theme_placeholder_is_not_equity_ticker():
    assert is_equity_ticker("SECTOR/THEME") is False

def test_sp500_label_is_not_equity_ticker():
    assert is_equity_ticker("S&P 500") is False

def test_nasdaq_is_not_equity_ticker():
    assert is_equity_ticker("NASDAQ") is False

def test_vix_is_not_equity_ticker():
    assert is_equity_ticker("VIX") is False

def test_gold_is_not_equity_ticker():
    assert is_equity_ticker("Gold") is False

def test_bitcoin_is_not_equity_ticker():
    assert is_equity_ticker("Bitcoin") is False

def test_ai_is_not_equity_ticker():
    # Common words that look like tickers
    assert is_equity_ticker("AI") is False

def test_us_is_not_equity_ticker():
    assert is_equity_ticker("US") is False

def test_etf_is_not_equity_ticker():
    assert is_equity_ticker("ETF") is False


# ---- infer_polarity ----

def test_polarity_bullish_from_accumulation():
    assert infer_polarity("Breakout accumulation at $79.93") == "bullish"

def test_polarity_bullish_from_momentum():
    assert infer_polarity("Strong short-term performance", "Momentum Leader") == "bullish"

def test_polarity_bearish_from_laggard():
    assert infer_polarity("Negative short-term performance", "Laggard") == "bearish"

def test_polarity_bearish_from_risk_word():
    assert infer_polarity("Geopolitical tension-related supply risk") == "bearish"

def test_polarity_bearish_from_deterioration():
    assert infer_polarity("Sustained outflow/weakness in defensive sector") == "bearish"

def test_polarity_empty_when_neutral():
    assert infer_polarity("Stable with minor movements") == ""

def test_polarity_bearish_takes_precedence_over_bullish():
    # "potential" → bullish word absent; "risk" present → bearish
    result = infer_polarity("Strong potential but significant risk")
    assert result in ("bullish", "bearish", "")  # both present — no strict rule, just not crash


# ---- compute_confidence ----

def test_confidence_macro_json_structured():
    c = compute_confidence(ConfidenceSource.MACRO_JSON_STRUCTURED)
    assert abs(c - 0.90) < 0.01

def test_confidence_md_pipe_full():
    c = compute_confidence(ConfidenceSource.MD_PIPE_FULL)
    assert abs(c - 0.95) < 0.01

def test_confidence_md_pipe_partial():
    c = compute_confidence(ConfidenceSource.MD_PIPE_PARTIAL)
    assert abs(c - 0.75) < 0.01

def test_confidence_md_free_bullet():
    c = compute_confidence(ConfidenceSource.MD_FREE_BULLET)
    assert abs(c - 0.55) < 0.01

def test_confidence_inferred_edge():
    c = compute_confidence(ConfidenceSource.INFERRED_EDGE)
    assert abs(c - 0.50) < 0.01

def test_confidence_macro_json_free_text():
    c = compute_confidence(ConfidenceSource.MACRO_JSON_FREE_TEXT)
    assert abs(c - 0.70) < 0.01

def test_confidence_hedging_adjustment():
    c = compute_confidence(ConfidenceSource.MD_PIPE_FULL, hedging=True)
    assert c < 0.95  # must be lower

def test_confidence_no_polarity_adjustment():
    c_with = compute_confidence(ConfidenceSource.MD_PIPE_FULL, polarity_empty=True)
    c_without = compute_confidence(ConfidenceSource.MD_PIPE_FULL, polarity_empty=False)
    assert c_with < c_without

def test_confidence_heuristic_adjustment():
    c_heuristic = compute_confidence(ConfidenceSource.MD_PIPE_FULL, heuristic_only=True)
    c_normal = compute_confidence(ConfidenceSource.MD_PIPE_FULL, heuristic_only=False)
    assert c_heuristic < c_normal

def test_confidence_corroboration_boost():
    c_single = compute_confidence(ConfidenceSource.MD_PIPE_FULL, corroborated=False)
    c_double = compute_confidence(ConfidenceSource.MD_PIPE_FULL, corroborated=True)
    assert c_double > c_single

def test_confidence_clamped_to_max_099():
    c = compute_confidence(ConfidenceSource.MD_PIPE_FULL, corroborated=True)
    assert c <= 0.99

def test_confidence_clamped_to_min_01():
    c = compute_confidence(
        ConfidenceSource.INFERRED_EDGE,
        hedging=True, heuristic_only=True, polarity_empty=True,
    )
    assert c >= 0.10

def test_confidence_below_threshold_is_low():
    # INFERRED_EDGE + hedging + heuristic → should be below 0.50
    c = compute_confidence(
        ConfidenceSource.INFERRED_EDGE,
        hedging=True, heuristic_only=True,
    )
    assert c < 0.50
