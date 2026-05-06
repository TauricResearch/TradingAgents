"""Property-based tests for commodity timeframe format compliance.

Feature: remaining-graph-hardening, Property 5: commodity timeframe format compliance

Validates: Requirements 6.1, 6.2, 6.3, 6.4
"""

from __future__ import annotations

import re
import string

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_os.backend.services.scanner_context import (
    format_commodity_line,
    validate_commodity_block,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_commodity_names = st.text(
    alphabet=string.ascii_letters,
    min_size=1,
    max_size=20,
).filter(lambda s: s.strip() != "")

_prices = st.floats(
    min_value=0.01,
    max_value=100000,
    allow_nan=False,
    allow_infinity=False,
)

_percentages = st.floats(
    min_value=-100,
    max_value=1000,
    allow_nan=False,
    allow_infinity=False,
)


# ---------------------------------------------------------------------------
# Property 5: Commodity timeframe format compliance
# ---------------------------------------------------------------------------


@given(
    name=_commodity_names,
    price=_prices,
    daily_change=_percentages,
    yoy_change=_percentages,
)
@settings(max_examples=100)
def test_property_commodity_timeframe_format_compliance(
    name: str,
    price: float,
    daily_change: float,
    yoy_change: float,
) -> None:
    """Property 5: Commodity timeframe format compliance.

    Feature: remaining-graph-hardening, Property 5: commodity timeframe format compliance

    For any commodity entry (name, price, daily_change_pct, yoy_change_pct),
    the formatted line matches "Name: $price (±X.XX% daily, ±Y.YY% YoY)"
    and contains no bare percentage without a timeframe label.

    **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
    """
    result = format_commodity_line(name, price, daily_change, yoy_change)

    # 1. Output matches the expected format pattern:
    #    "Name: $price (+X.XX% daily, +Y.YY% YoY)"
    pattern = re.compile(
        r"^.+: \$[\d.]+ \([+-][\d.]+% daily, [+-][\d.]+% YoY\)$"
    )
    assert pattern.match(result), (
        f"Output does not match expected format pattern.\n"
        f"Got: {result!r}\n"
        f"Expected pattern: 'Name: $price (±X.XX% daily, ±Y.YY% YoY)'"
    )

    # 2. Output contains no bare percentage without a timeframe label.
    #    A bare percentage is one that is NOT followed by " daily" or " YoY".
    bare_pct_pattern = re.compile(r"[+-]?\d+\.?\d*%(?!\s*(?:daily|YoY))")
    bare_matches = bare_pct_pattern.findall(result)
    assert not bare_matches, (
        f"Found bare percentage(s) without timeframe label: {bare_matches}\n"
        f"In output: {result!r}"
    )

    # 3. Output contains the commodity name, price, and both labeled percentages.
    assert name in result, f"Commodity name {name!r} not found in output: {result!r}"
    assert f"${price:.2f}" in result, (
        f"Price ${price:.2f} not found in output: {result!r}"
    )
    assert "daily" in result, f"'daily' label not found in output: {result!r}"
    assert "YoY" in result, f"'YoY' label not found in output: {result!r}"

    # 4. validate_commodity_block should accept this formatted line
    assert validate_commodity_block(result) is True, (
        f"validate_commodity_block rejected valid output: {result!r}"
    )


@given(
    name=_commodity_names,
    price=_prices,
    daily_change=_percentages,
    yoy_change=_percentages,
)
@settings(max_examples=100)
def test_property_validate_rejects_bare_percentages(
    name: str,
    price: float,
    daily_change: float,
    yoy_change: float,
) -> None:
    """Bare percentages without timeframe labels are rejected by the validator.

    Feature: remaining-graph-hardening, Property 5: commodity timeframe format compliance

    **Validates: Requirements 6.4**
    """
    # Construct a bare-percentage line (no timeframe label)
    bare_line = f"{name}: ${price:.2f} ({daily_change:+.2f}%)"
    assert validate_commodity_block(bare_line) is False, (
        f"validate_commodity_block should reject bare percentage line: {bare_line!r}"
    )
