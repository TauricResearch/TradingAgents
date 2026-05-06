"""Property-based tests for FundamentalsKeyMetrics extraction.

Feature: remaining-graph-hardening
Tests for `FundamentalsKeyMetrics.from_report_text()` from
`tradingagents.agents.utils.output_validation`.
"""

from __future__ import annotations

import math
import string

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from tradingagents.agents.utils.output_validation import FundamentalsKeyMetrics

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Metric value strategies
_pe_ratio_values = st.floats(min_value=0.01, max_value=9999.99, allow_nan=False, allow_infinity=False)
_de_ratio_values = st.floats(min_value=0.01, max_value=9999.99, allow_nan=False, allow_infinity=False)
_fcf_change_values = st.floats(min_value=-999.99, max_value=999.99, allow_nan=False, allow_infinity=False)
_operating_margin_values = st.floats(min_value=-999.99, max_value=999.99, allow_nan=False, allow_infinity=False)
_current_ratio_values = st.floats(min_value=0.01, max_value=99.99, allow_nan=False, allow_infinity=False)

_working_capital_examples = st.sampled_from([
    "$2.3B (negative)",
    "-$500M",
    "$1.2B",
    "$450M (positive)",
    "-$1.8B",
    "$3.5B (healthy)",
    "$100M",
    "-$200M (concerning)",
])

# Filler text that does NOT contain metric patterns
_filler_text = st.text(
    alphabet=string.ascii_lowercase + " \n",
    min_size=0,
    max_size=200,
).map(lambda s: s.replace("ratio", "").replace("margin", "").replace("change", "").replace("capital", ""))


# Strategy for PE ratio format variants
_pe_format = st.sampled_from(["P/E Ratio", "PE Ratio", "P/E ratio", "pe ratio"])

# Strategy for D/E ratio format variants
_de_format = st.sampled_from([
    "D/E Ratio", "Debt/Equity Ratio", "Debt-to-Equity", "D/E ratio",
    "Debt/Equity ratio", "Debt-to-Equity",
])

# Strategy for FCF change format variants
_fcf_format = st.sampled_from(["FCF Change", "Free Cash Flow Change", "fcf change"])

# Strategy for operating margin format variants
_om_format = st.sampled_from(["Operating Margin", "operating margin"])


def _format_pe_line(fmt: str, value: float) -> str:
    """Format a PE ratio line in mandated format."""
    return f"{fmt}: {value:.2f}"


def _format_de_line(fmt: str, value: float) -> str:
    """Format a D/E ratio line in mandated format."""
    return f"{fmt}: {value:.2f}"


def _format_fcf_line(fmt: str, value: float) -> str:
    """Format a FCF change line in mandated format."""
    return f"{fmt}: {value:.1f}%"


def _format_om_line(fmt: str, value: float) -> str:
    """Format an operating margin line in mandated format."""
    return f"{fmt}: {value:.1f}%"


def _format_cr_line(value: float) -> str:
    """Format a current ratio line in mandated format."""
    return f"Current Ratio: {value:.2f}"


def _format_wc_line(value: str) -> str:
    """Format a working capital line in mandated format."""
    return f"Working Capital: {value}"


# Strategy that generates a report text with a random subset of metrics
@st.composite
def _report_with_metrics(draw):
    """Generate a report text containing a random subset of metric lines."""
    lines = []
    expected = {}

    # Decide which metrics to include (at least one)
    include_pe = draw(st.booleans())
    include_de = draw(st.booleans())
    include_fcf = draw(st.booleans())
    include_om = draw(st.booleans())
    include_cr = draw(st.booleans())
    include_wc = draw(st.booleans())

    # Ensure at least one metric is included
    if not any([include_pe, include_de, include_fcf, include_om, include_cr, include_wc]):
        include_pe = True

    # Add filler before
    lines.append(draw(_filler_text))

    if include_pe:
        val = draw(_pe_ratio_values)
        fmt = draw(_pe_format)
        lines.append(_format_pe_line(fmt, val))
        expected["pe_ratio"] = round(val, 2)

    lines.append(draw(_filler_text))

    if include_de:
        val = draw(_de_ratio_values)
        fmt = draw(_de_format)
        lines.append(_format_de_line(fmt, val))
        expected["debt_equity_ratio"] = round(val, 2)

    lines.append(draw(_filler_text))

    if include_fcf:
        val = draw(_fcf_change_values)
        fmt = draw(_fcf_format)
        lines.append(_format_fcf_line(fmt, val))
        expected["fcf_change_pct"] = round(val, 1)

    lines.append(draw(_filler_text))

    if include_om:
        val = draw(_operating_margin_values)
        fmt = draw(_om_format)
        lines.append(_format_om_line(fmt, val))
        expected["operating_margin_pct"] = round(val, 1)

    lines.append(draw(_filler_text))

    if include_cr:
        val = draw(_current_ratio_values)
        lines.append(_format_cr_line(val))
        expected["current_ratio"] = round(val, 2)

    lines.append(draw(_filler_text))

    if include_wc:
        val = draw(_working_capital_examples)
        lines.append(_format_wc_line(val))
        expected["working_capital_str"] = val

    lines.append(draw(_filler_text))

    report_text = "\n".join(lines)
    return report_text, expected


# Strategy for round-trip: all numeric metrics present
@st.composite
def _all_numeric_metrics(draw):
    """Generate a complete set of numeric metric values for round-trip testing."""
    pe = draw(st.floats(min_value=0.1, max_value=999.99, allow_nan=False, allow_infinity=False))
    de = draw(st.floats(min_value=0.01, max_value=999.99, allow_nan=False, allow_infinity=False))
    fcf = draw(st.floats(min_value=-99.9, max_value=99.9, allow_nan=False, allow_infinity=False))
    om = draw(st.floats(min_value=-99.9, max_value=99.9, allow_nan=False, allow_infinity=False))
    cr = draw(st.floats(min_value=0.01, max_value=99.99, allow_nan=False, allow_infinity=False))
    wc = draw(_working_capital_examples)
    return {
        "pe_ratio": pe,
        "debt_equity_ratio": de,
        "fcf_change_pct": fcf,
        "operating_margin_pct": om,
        "current_ratio": cr,
        "working_capital_str": wc,
    }


# ---------------------------------------------------------------------------
# Property 8: Fundamentals metric extraction correctness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=_report_with_metrics())
def test_property_metric_extraction_correctness(data: tuple) -> None:
    """Property 8: Fundamentals metric extraction correctness.

    Feature: remaining-graph-hardening, Property 8: fundamentals metric extraction correctness

    **Validates: Requirements 8.1, 8.2, 8.3**

    For any report text containing mandated metric format lines,
    FundamentalsKeyMetrics.from_report_text() extracts each present metric
    into its typed field and sets absent metrics to None without raising.
    """
    report_text, expected = data

    # Should never raise
    result = FundamentalsKeyMetrics.from_report_text(report_text)

    # Check that present metrics are extracted correctly
    if "pe_ratio" in expected:
        assert result.pe_ratio is not None, "PE ratio should be extracted"
        assert abs(result.pe_ratio - expected["pe_ratio"]) < 0.01, (
            f"PE ratio mismatch: got {result.pe_ratio}, expected {expected['pe_ratio']}"
        )
    else:
        assert result.pe_ratio is None, "PE ratio should be None when not in report"

    if "debt_equity_ratio" in expected:
        assert result.debt_equity_ratio is not None, "D/E ratio should be extracted"
        assert abs(result.debt_equity_ratio - expected["debt_equity_ratio"]) < 0.01, (
            f"D/E ratio mismatch: got {result.debt_equity_ratio}, expected {expected['debt_equity_ratio']}"
        )
    else:
        assert result.debt_equity_ratio is None, "D/E ratio should be None when not in report"

    if "fcf_change_pct" in expected:
        assert result.fcf_change_pct is not None, "FCF change should be extracted"
        assert abs(result.fcf_change_pct - expected["fcf_change_pct"]) < 0.01, (
            f"FCF change mismatch: got {result.fcf_change_pct}, expected {expected['fcf_change_pct']}"
        )
    else:
        assert result.fcf_change_pct is None, "FCF change should be None when not in report"

    if "operating_margin_pct" in expected:
        assert result.operating_margin_pct is not None, "Operating margin should be extracted"
        assert abs(result.operating_margin_pct - expected["operating_margin_pct"]) < 0.01, (
            f"Operating margin mismatch: got {result.operating_margin_pct}, expected {expected['operating_margin_pct']}"
        )
    else:
        assert result.operating_margin_pct is None, "Operating margin should be None when not in report"

    if "current_ratio" in expected:
        assert result.current_ratio is not None, "Current ratio should be extracted"
        assert abs(result.current_ratio - expected["current_ratio"]) < 0.01, (
            f"Current ratio mismatch: got {result.current_ratio}, expected {expected['current_ratio']}"
        )
    else:
        assert result.current_ratio is None, "Current ratio should be None when not in report"

    if "working_capital_str" in expected:
        assert result.working_capital_str is not None, "Working capital should be extracted"
        assert result.working_capital_str == expected["working_capital_str"], (
            f"Working capital mismatch: got {result.working_capital_str!r}, expected {expected['working_capital_str']!r}"
        )
    else:
        assert result.working_capital_str is None, "Working capital should be None when not in report"


@settings(max_examples=100)
@given(report_text=st.text(min_size=0, max_size=500))
def test_property_metric_extraction_never_raises(report_text: str) -> None:
    """Property 8 (supplementary): from_report_text never raises on arbitrary input.

    Feature: remaining-graph-hardening, Property 8: fundamentals metric extraction correctness

    **Validates: Requirements 8.3**

    For any arbitrary text (including garbage), from_report_text() should
    never raise an exception — it sets absent metrics to None.
    """
    # Should never raise regardless of input
    result = FundamentalsKeyMetrics.from_report_text(report_text)

    # All fields should be either a valid value or None
    assert result.pe_ratio is None or isinstance(result.pe_ratio, float)
    assert result.debt_equity_ratio is None or isinstance(result.debt_equity_ratio, float)
    assert result.fcf_change_pct is None or isinstance(result.fcf_change_pct, float)
    assert result.operating_margin_pct is None or isinstance(result.operating_margin_pct, float)
    assert result.current_ratio is None or isinstance(result.current_ratio, float)
    assert result.working_capital_str is None or isinstance(result.working_capital_str, str)


# ---------------------------------------------------------------------------
# Property 9: Fundamentals metric round-trip preservation
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(metrics=_all_numeric_metrics())
def test_property_metric_round_trip_preservation(metrics: dict) -> None:
    """Property 9: Fundamentals metric round-trip preservation.

    Feature: remaining-graph-hardening, Property 9: fundamentals metric round-trip preservation

    **Validates: Requirements 8.6**

    For any set of valid metric values, formatting into mandated text then
    extracting via from_report_text() produces values equal to originals
    within tolerance (±0.01 for percentages, ±0.1 for ratios).
    """
    # Format metrics into mandated text (2 decimal places for all numerics)
    lines = [
        f"P/E Ratio: {metrics['pe_ratio']:.2f}",
        f"D/E Ratio: {metrics['debt_equity_ratio']:.2f}",
        f"FCF Change: {metrics['fcf_change_pct']:.2f}%",
        f"Operating Margin: {metrics['operating_margin_pct']:.2f}%",
        f"Current Ratio: {metrics['current_ratio']:.2f}",
        f"Working Capital: {metrics['working_capital_str']}",
    ]
    report_text = "\n".join(lines)

    # Extract via from_report_text
    result = FundamentalsKeyMetrics.from_report_text(report_text)

    # Verify round-trip within tolerance
    # ±0.1 for ratios (PE, D/E, Current Ratio)
    assert result.pe_ratio is not None, "PE ratio should be extracted in round-trip"
    assert abs(result.pe_ratio - metrics["pe_ratio"]) <= 0.1, (
        f"PE ratio round-trip failed: got {result.pe_ratio}, expected {metrics['pe_ratio']}"
    )

    assert result.debt_equity_ratio is not None, "D/E ratio should be extracted in round-trip"
    assert abs(result.debt_equity_ratio - metrics["debt_equity_ratio"]) <= 0.1, (
        f"D/E ratio round-trip failed: got {result.debt_equity_ratio}, expected {metrics['debt_equity_ratio']}"
    )

    assert result.current_ratio is not None, "Current ratio should be extracted in round-trip"
    assert abs(result.current_ratio - metrics["current_ratio"]) <= 0.1, (
        f"Current ratio round-trip failed: got {result.current_ratio}, expected {metrics['current_ratio']}"
    )

    # ±0.01 for percentages (FCF change, Operating Margin)
    assert result.fcf_change_pct is not None, "FCF change should be extracted in round-trip"
    assert abs(result.fcf_change_pct - metrics["fcf_change_pct"]) <= 0.01, (
        f"FCF change round-trip failed: got {result.fcf_change_pct}, expected {metrics['fcf_change_pct']}"
    )

    assert result.operating_margin_pct is not None, "Operating margin should be extracted in round-trip"
    assert abs(result.operating_margin_pct - metrics["operating_margin_pct"]) <= 0.01, (
        f"Operating margin round-trip failed: got {result.operating_margin_pct}, expected {metrics['operating_margin_pct']}"
    )

    # Working capital is a string — exact match
    assert result.working_capital_str == metrics["working_capital_str"], (
        f"Working capital round-trip failed: got {result.working_capital_str!r}, expected {metrics['working_capital_str']!r}"
    )
