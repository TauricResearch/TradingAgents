"""Unit tests for tradingagents.dataflows.symbols.

These functions are purely syntactic (no network calls) but carry subtle,
security-relevant rules: symbol canonicalization for Yahoo Finance and a
path-safe ticker validator that blocks directory traversal from
attacker-influenced (LLM/news) input. They previously had no unit coverage.
"""

import pytest

from tradingagents.dataflows.symbols import (
    crypto_base,
    normalize_symbol,
    safe_ticker_component,
)


# --- normalize_symbol: broker -> Yahoo canonical ---------------------------


def test_normalize_symbol_crypto_dashed_and_compact():
    assert normalize_symbol("BTCUSD") == "BTC-USD"
    assert normalize_symbol("BTC-USD") == "BTC-USD"
    assert normalize_symbol("ETHUSDT") == "ETH-USD"


def test_normalize_symbol_metal_alias():
    assert normalize_symbol("XAUUSD") == "GC=F"
    assert normalize_symbol("XAUUSD+") == "GC=F"  # broker CFD '+' stripped
    assert normalize_symbol("GOLD") == "GC=F"


def test_normalize_symbol_forex_gets_x_suffix():
    assert normalize_symbol("EURUSD") == "EURUSD=X"


def test_normalize_symbol_hk_zero_padding():
    assert normalize_symbol("09992.HK") == "9992.HK"
    assert normalize_symbol("700.HK") == "0700.HK"


def test_normalize_symbol_shanghai_becomes_ss():
    assert normalize_symbol("600519.SH") == "600519.SS"


def test_normalize_symbol_passthrough_for_plain_equities():
    assert normalize_symbol("AAPL") == "AAPL"
    assert normalize_symbol("^GSPC") == "^GSPC"  # Yahoo-native


def test_normalize_symbol_returns_raw_for_non_symbols():
    assert normalize_symbol("") == ""
    assert normalize_symbol(123) == 123


# --- crypto_base -----------------------------------------------------------


def test_crypto_base_known_bases():
    assert crypto_base("BTCUSD") == "BTC"
    assert crypto_base("ETHUSDT") == "ETH"
    assert crypto_base("SOL-USD") == "SOL"


def test_crypto_base_rejects_unknown_and_non_strings():
    assert crypto_base("AAPL") is None
    assert crypto_base(123) is None


# --- safe_ticker_component: path-traversal guard --------------------------


def test_safe_ticker_component_accepts_valid():
    assert safe_ticker_component("AAPL") == "AAPL"
    assert safe_ticker_component("^GSPC") == "^GSPC"
    assert safe_ticker_component("BTC-USD") == "BTC-USD"


def test_safe_ticker_component_rejects_traversal():
    with pytest.raises(ValueError):
        safe_ticker_component("../../../etc/passwd")


def test_safe_ticker_component_rejects_dots_only():
    with pytest.raises(ValueError):
        safe_ticker_component("..")


def test_safe_ticker_component_rejects_empty():
    with pytest.raises(ValueError):
        safe_ticker_component("")


def test_safe_ticker_component_rejects_overlong():
    with pytest.raises(ValueError):
        safe_ticker_component("A" * 40, max_len=32)
