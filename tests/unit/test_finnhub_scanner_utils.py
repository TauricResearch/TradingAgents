"""Unit tests for utility functions in finnhub_scanner.py."""

from tradingagents.dataflows.finnhub_scanner import _safe_fmt

def test_safe_fmt_none_returns_default_fallback():
    assert _safe_fmt(None) == "N/A"

def test_safe_fmt_none_returns_custom_fallback():
    assert _safe_fmt(None, fallback="Missing") == "Missing"

def test_safe_fmt_valid_float_returns_default_format():
    assert _safe_fmt(123.456) == "$123.46"

def test_safe_fmt_valid_int_returns_default_format():
    assert _safe_fmt(100) == "$100.00"

def test_safe_fmt_numeric_string_returns_default_format():
    assert _safe_fmt("45.678") == "$45.68"

def test_safe_fmt_custom_format():
    assert _safe_fmt(123.456, fmt="{:.3f}") == "123.456"

def test_safe_fmt_non_numeric_string_returns_original_string():
    # float("abc") raises ValueError, should return "abc"
    assert _safe_fmt("abc") == "abc"

def test_safe_fmt_unsupported_type_returns_str_representation():
    # float([]) raises TypeError, should return "[]"
    assert _safe_fmt([]) == "[]"

def test_safe_fmt_zero_returns_formatted_zero():
    assert _safe_fmt(0) == "$0.00"

def test_safe_fmt_negative_number():
    assert _safe_fmt(-1.23) == "$-1.23"
