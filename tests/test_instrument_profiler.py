"""Instrument Profiler tests — one generic engine, four very different tickers.

BRK-B (US dual-class), AAPL and NVDA (US single-class), ENI.MI (Milan,
EUR) are the required test cases. Every expectation comes from the
*vendor payload* each case simulates — never from a per-ticker rule — so
the same engine must classify all four correctly from data alone. A fifth
family (GBp minor units, crypto, indices) proves the structural rules.
"""

from __future__ import annotations

import pytest

from tradingagents.dataflows.instrument_profiler import (
    DataQuality,
    InstrumentKind,
    profile_instrument,
)
from tradingagents.dataflows.validator import (
    check_ticker_identity,
    validate_currency_consistency,
)

# Vendor payloads as Yahoo serves them (fields the profiler reads).
BRK_B_INFO = {
    "quoteType": "EQUITY",
    "currency": "USD",
    "financialCurrency": "USD",
    "longName": "Berkshire Hathaway, Inc.",
    "exchange": "NYQ",
}
AAPL_INFO = {
    "quoteType": "EQUITY",
    "currency": "USD",
    "financialCurrency": "USD",
    "longName": "Apple Inc.",
    "exchange": "NMS",
}
NVDA_INFO = {
    "quoteType": "EQUITY",
    "currency": "USD",
    "financialCurrency": "USD",
    "longName": "NVIDIA Corporation",
    "exchange": "NMS",
}
ENI_MI_INFO = {
    "quoteType": "EQUITY",
    "currency": "EUR",
    "financialCurrency": "EUR",
    "longName": "ENI S.p.A.",
    "exchange": "MIL",
}
GBP_INFO = {
    "quoteType": "EQUITY",
    "currency": "GBp",           # London quotes in pence
    "financialCurrency": "GBP",  # financials in pounds
    "longName": "A London Listing",
    "exchange": "LSE",
}
BTC_INFO = {
    "quoteType": "CRYPTOCURRENCY",
    "currency": "USD",
    "longName": "Bitcoin USD",
}


# ---------------------------------------------------------------------------
# BRK-B: dual-class equity, detected structurally
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_brk_b_profile_detects_share_class_structurally():
    p = profile_instrument("BRK-B", BRK_B_INFO)
    assert p.kind is InstrumentKind.EQUITY
    assert p.share_class == "B"
    assert p.share_class_root == "BRK"
    assert p.has_share_class_siblings
    assert "BRK-A" in p.sibling_classes
    assert p.quote_currency == "USD"
    assert p.data_quality is DataQuality.COMPLETE


@pytest.mark.unit
def test_brk_b_sibling_serving_is_an_error_via_profile():
    """Asked for BRK-B, served BRK-A: the profiler's structural detection
    flags it — no hardcoded sibling table involved."""
    p = profile_instrument("BRK-B", BRK_B_INFO)
    result = check_ticker_identity("BRK-B", "BRK-A", profile=p)
    assert result.status == "QUARANTINED"
    assert any(i.code == "TICKER_SIBLING_CLASS" for i in result.issues)


@pytest.mark.unit
def test_brk_b_exact_match_passes():
    p = profile_instrument("BRK-B", BRK_B_INFO)
    assert check_ticker_identity("BRK-B", "BRK-B", profile=p).status == "OK"


# ---------------------------------------------------------------------------
# AAPL / NVDA: single-class US equities, no siblings invented
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("ticker,info", [("AAPL", AAPL_INFO), ("NVDA", NVDA_INFO)])
def test_single_class_us_equities_have_no_share_class(ticker, info):
    p = profile_instrument(ticker, info)
    assert p.kind is InstrumentKind.EQUITY
    assert p.share_class is None
    assert p.share_class_root is None
    assert not p.has_share_class_siblings
    assert p.quote_currency == "USD" == p.financial_currency
    assert not p.has_currency_mismatch


@pytest.mark.unit
def test_aapl_identity_mismatch_without_profile_is_only_a_warning():
    """Without a profile, a rewritten symbol is a warning: normalization
    legitimately rewrites symbols, so a bare mismatch is never an error."""
    result = check_ticker_identity("AAPL", "AAPL.VI")
    assert result.status == "UNVERIFIED"
    assert any(i.code == "TICKER_REWRITTEN" for i in result.issues)


# ---------------------------------------------------------------------------
# ENI.MI: Milan listing, EUR — same engine, foreign market
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_eni_mi_profile_is_an_eur_equity():
    p = profile_instrument("ENI.MI", ENI_MI_INFO)
    assert p.kind is InstrumentKind.EQUITY
    assert p.quote_currency == "EUR"
    assert p.financial_currency == "EUR"
    assert not p.has_currency_mismatch
    assert p.share_class is None  # ".MI" is an exchange suffix, not a class
    assert p.data_quality is DataQuality.COMPLETE


@pytest.mark.unit
def test_eni_mi_currency_consistency_passes():
    p = profile_instrument("ENI.MI", ENI_MI_INFO)
    result = validate_currency_consistency("EUR", "EUR", profile=p)
    assert result.status == "OK"


@pytest.mark.unit
def test_eni_mi_price_in_usd_against_eur_metrics_is_an_error():
    """A USD price against EUR financials: not comparable without conversion."""
    p = profile_instrument("ENI.MI", ENI_MI_INFO)
    result = validate_currency_consistency("USD", "EUR", profile=p)
    assert result.status == "QUARANTINED"
    assert any(i.code == "CURRENCY_MISMATCH" for i in result.issues)


# ---------------------------------------------------------------------------
# Minor units and structural kinds — the same rules, other families
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_gbp_minor_unit_quote_gets_a_conversion_factor():
    p = profile_instrument("HSBA.L", GBP_INFO)
    assert p.quote_currency == "GBp"
    assert p.financial_currency == "GBP"
    assert p.currency_conversion == pytest.approx(0.01)
    assert p.per_share_currency() == "GBP"
    assert p.has_currency_mismatch


@pytest.mark.unit
def test_gbp_minor_unit_mismatch_passes_with_the_profile():
    p = profile_instrument("HSBA.L", GBP_INFO)
    result = validate_currency_consistency("GBp", "GBP", profile=p)
    assert result.status == "UNVERIFIED"  # a warning: convert before ratios
    assert any(i.code == "CURRENCY_MINOR_UNIT" for i in result.issues)


@pytest.mark.unit
def test_gbp_minor_unit_mismatch_without_profile_is_an_error():
    result = validate_currency_consistency("GBp", "GBP")
    assert result.status == "QUARANTINED"
    assert any(i.code == "CURRENCY_MISMATCH" for i in result.issues)


@pytest.mark.unit
def test_unknown_currencies_are_unverified_not_errors():
    result = validate_currency_consistency(None, None)
    assert result.status == "UNVERIFIED"
    assert any(i.code == "CURRENCY_UNKNOWN" for i in result.issues)


@pytest.mark.unit
def test_crypto_and_index_kinds_are_structural():
    assert profile_instrument("BTC-USD", BTC_INFO).kind is InstrumentKind.CRYPTO
    assert profile_instrument("^GSPC", {"quoteType": "INDEX"}).kind is InstrumentKind.INDEX
    assert profile_instrument("EURUSD=X", {}).kind is InstrumentKind.FOREX


# ---------------------------------------------------------------------------
# Fail-closed: no vendor data, no guesses
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_vendor_data_yields_unknown_quality():
    p = profile_instrument("MYSTERY", {})
    assert p.kind is InstrumentKind.UNKNOWN
    assert p.data_quality is DataQuality.UNKNOWN
    assert p.quote_currency is None
    assert p.financial_currency is None


@pytest.mark.unit
def test_partial_vendor_data_is_labelled_partial():
    p = profile_instrument("SOME.CO", {"quoteType": "EQUITY"})
    assert p.kind is InstrumentKind.EQUITY
    assert p.data_quality is DataQuality.PARTIAL
    assert p.quote_currency is None
