import pytest

from tradingagents.dataflows.india.symbols import (
    IndiaSymbolError,
    is_indian_equity_symbol,
    normalize_india_symbol,
    safe_india_ticker_component,
    validate_india_symbol_or_raise,
)


@pytest.mark.unit
def test_reliance_normalizes_to_nse():
    assert normalize_india_symbol("RELIANCE") == "RELIANCE.NS"


@pytest.mark.unit
def test_lowercase_nse_normalizes():
    assert normalize_india_symbol("reliance.ns") == "RELIANCE.NS"


@pytest.mark.unit
def test_bse_symbol_accepted():
    assert normalize_india_symbol("RELIANCE.BO") == "RELIANCE.BO"
    assert is_indian_equity_symbol("RELIANCE.BO")


@pytest.mark.unit
def test_nifty_index_accepted():
    assert normalize_india_symbol("^NSEI") == "^NSEI"
    assert is_indian_equity_symbol("^NSEI")


@pytest.mark.unit
@pytest.mark.parametrize("symbol", ["AAPL", "SPY", "BTC-USD"])
def test_non_india_symbols_rejected(symbol):
    with pytest.raises(IndiaSymbolError):
        validate_india_symbol_or_raise(symbol, {"allow_non_india_tickers": False})


@pytest.mark.unit
def test_legacy_escape_hatch_allows_non_india_but_still_cleans_input():
    assert (
        validate_india_symbol_or_raise("aapl", {"allow_non_india_tickers": True})
        == "AAPL"
    )
    with pytest.raises(IndiaSymbolError):
        validate_india_symbol_or_raise("../AAPL", {"allow_non_india_tickers": True})


@pytest.mark.unit
@pytest.mark.parametrize("symbol", ["../RELIANCE", "", "RELIANCE/NS"])
def test_path_traversal_and_empty_rejected(symbol):
    with pytest.raises(IndiaSymbolError):
        normalize_india_symbol(symbol)


@pytest.mark.unit
def test_safe_india_ticker_component():
    assert safe_india_ticker_component("RELIANCE") == "RELIANCE.NS"


@pytest.mark.unit
def test_default_suffix_controls_bare_symbol_normalization():
    assert (
        validate_india_symbol_or_raise(
            "RELIANCE",
            {"allow_non_india_tickers": False, "default_india_suffix": ".BO"},
        )
        == "RELIANCE.BO"
    )
