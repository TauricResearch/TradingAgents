"""Property-based tests for research packet summary generation.

Feature: remaining-graph-hardening
Tests for `generate_research_packet_summary()` from
`tradingagents.graph._consistency_guard`.
"""

from __future__ import annotations

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from tradingagents.graph._consistency_guard import generate_research_packet_summary

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_RATINGS = st.sampled_from(["BUY", "SELL", "HOLD", "STRONG BUY", "STRONG SELL"])

_tickers = st.text(alphabet=string.ascii_uppercase, min_size=2, max_size=5).filter(
    lambda s: s.strip() != ""
)

_trade_dates = st.dates(
    min_value=__import__("datetime").date(2020, 1, 1),
    max_value=__import__("datetime").date(2030, 12, 31),
).map(lambda d: d.isoformat())

_confidence = st.one_of(
    st.floats(min_value=0.01, max_value=0.99, allow_nan=False).map(lambda f: f"{f:.2f}"),
    st.integers(min_value=1, max_value=99).map(lambda i: f"{i}%"),
)

_price = st.floats(min_value=1.0, max_value=9999.99, allow_nan=False, allow_infinity=False).map(
    lambda f: f"{f:.2f}"
)

# Generate short but meaningful point text (10-60 chars)
_point_text = st.text(
    alphabet=string.ascii_letters + string.digits + " ",
    min_size=10,
    max_size=60,
).filter(lambda s: s.strip() != "" and len(s.strip()) >= 10)

# Generate 1-4 bull/bear points
_bull_points = st.lists(_point_text, min_size=1, max_size=4)
_bear_points = st.lists(_point_text, min_size=1, max_size=4)


@st.composite
def valid_investment_plan(draw):
    """Generate a valid investment_plan text with all required fields."""
    rating = draw(_RATINGS)
    confidence = draw(_confidence)
    entry_price = draw(_price)
    target_price = draw(_price)
    bull_items = draw(_bull_points)
    bear_items = draw(_bear_points)

    # Build the investment plan text
    bull_section = "Bull Points:\n" + "\n".join(
        f"{i + 1}. {item.strip()}" for i, item in enumerate(bull_items)
    )
    bear_section = "Bear Points:\n" + "\n".join(
        f"{i + 1}. {item.strip()}" for i, item in enumerate(bear_items)
    )

    plan = (
        f"Rating: {rating}\n"
        f"Confidence: {confidence}\n"
        f"\n"
        f"{bull_section}\n"
        f"\n"
        f"{bear_section}\n"
        f"\n"
        f"Entry Price: ${entry_price}\n"
        f"Target Price: ${target_price}\n"
    )
    return plan


_fundamentals_report = st.text(
    alphabet=string.ascii_letters + string.digits + " .$%,\n",
    min_size=50,
    max_size=300,
).filter(lambda s: s.strip() != "")


# ---------------------------------------------------------------------------
# Property 6: Research packet summary field completeness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    ticker=_tickers,
    trade_date=_trade_dates,
    investment_plan=valid_investment_plan(),
    fundamentals_report=_fundamentals_report,
)
def test_property_summary_field_completeness(
    ticker: str,
    trade_date: str,
    investment_plan: str,
    fundamentals_report: str,
) -> None:
    """Property 6: Research packet summary field completeness.

    Feature: remaining-graph-hardening, Property 6: research packet summary field completeness

    **Validates: Requirements 7.2**

    For any valid research packet (non-empty investment_plan with rating,
    bull/bear points, entry/target price), output contains ticker, trade_date,
    at least one bull point, at least one bear point, rating, and price info.
    """
    result = generate_research_packet_summary(
        ticker=ticker,
        trade_date=trade_date,
        investment_plan=investment_plan,
        fundamentals_report=fundamentals_report,
    )

    # With valid inputs, result must be non-empty
    assert result != "", "Valid inputs should produce non-empty summary"

    # Must contain ticker
    assert ticker in result, f"Summary must contain ticker '{ticker}'"

    # Must contain trade_date
    assert trade_date in result, f"Summary must contain trade_date '{trade_date}'"

    # Must contain at least one bull point indicator
    assert "Bull:" in result, "Summary must contain 'Bull:' section"

    # Must contain at least one bear point indicator
    assert "Bear:" in result, "Summary must contain 'Bear:' section"

    # Must contain rating
    assert "Rating:" in result, "Summary must contain 'Rating:' label"

    # Must contain price info (Entry and Target)
    assert "Entry:" in result, "Summary must contain 'Entry:' price info"
    assert "Target:" in result, "Summary must contain 'Target:' price info"
    assert "$" in result, "Summary must contain '$' for price values"


# ---------------------------------------------------------------------------
# Property 7: Research packet summary length bounds
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    ticker=_tickers,
    trade_date=_trade_dates,
    investment_plan=valid_investment_plan(),
    fundamentals_report=_fundamentals_report,
)
def test_property_summary_length_bounds(
    ticker: str,
    trade_date: str,
    investment_plan: str,
    fundamentals_report: str,
) -> None:
    """Property 7: Research packet summary length bounds.

    Feature: remaining-graph-hardening, Property 7: research packet summary length bounds

    **Validates: Requirements 7.3**

    For any input producing a non-empty result, output length is between
    200 and 500 characters inclusive.
    """
    result = generate_research_packet_summary(
        ticker=ticker,
        trade_date=trade_date,
        investment_plan=investment_plan,
        fundamentals_report=fundamentals_report,
    )

    # Only check bounds for non-empty results
    if result:
        assert 200 <= len(result) <= 500, (
            f"Summary length {len(result)} is outside bounds [200, 500]. Summary: {result!r}"
        )
