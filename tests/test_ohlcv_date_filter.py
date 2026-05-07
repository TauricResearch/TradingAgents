"""Property-based and unit tests for OHLCV look-ahead bias date filter.

Feature: upstream-feature-adoption
Properties 1-3: OHLCV Date Filter Correctness, Idempotence, None Passthrough
Validates: Requirements 1.1, 1.4, 1.5, 1.6
"""

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tradingagents.dataflows.stockstats_utils import filter_ohlcv_by_date

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_DATE_RANGE = st.dates(
    min_value=pd.Timestamp("2010-01-01").date(),
    max_value=pd.Timestamp("2026-12-31").date(),
)


@st.composite
def ohlcv_dataframe(draw):
    """Generate a valid OHLCV DataFrame with a 'date' column."""
    n_rows = draw(st.integers(min_value=1, max_value=200))
    start = draw(_DATE_RANGE)
    dates = pd.date_range(start=start, periods=n_rows, freq="B")  # business days
    df = pd.DataFrame(
        {
            "date": dates,
            "open": draw(st.lists(st.floats(10, 1000), min_size=n_rows, max_size=n_rows)),
            "high": draw(st.lists(st.floats(10, 1000), min_size=n_rows, max_size=n_rows)),
            "low": draw(st.lists(st.floats(10, 1000), min_size=n_rows, max_size=n_rows)),
            "close": draw(st.lists(st.floats(10, 1000), min_size=n_rows, max_size=n_rows)),
            "volume": draw(
                st.lists(st.integers(1000, 10_000_000), min_size=n_rows, max_size=n_rows)
            ),
        }
    )
    return df


# ---------------------------------------------------------------------------
# Property 1: OHLCV Date Filter Correctness
# All rows in result have date <= curr_date
# ---------------------------------------------------------------------------


@given(df=ohlcv_dataframe(), curr_date=_DATE_RANGE)
@settings(max_examples=100)
def test_property_1_all_rows_on_or_before_curr_date(df, curr_date):
    """Property 1: After filtering, every row has date <= curr_date."""
    curr_date_str = curr_date.strftime("%Y-%m-%d")
    result = filter_ohlcv_by_date(df, curr_date_str)
    cutoff = pd.Timestamp(curr_date_str)
    if not result.empty and "date" in result.columns:
        assert (result["date"] <= cutoff).all()


# ---------------------------------------------------------------------------
# Property 2: OHLCV Date Filter Idempotence
# filter(filter(data, d2), d1) == filter(data, d1) for d1 <= d2
# ---------------------------------------------------------------------------


@given(df=ohlcv_dataframe(), d1=_DATE_RANGE, d2=_DATE_RANGE)
@settings(max_examples=100)
def test_property_2_idempotence(df, d1, d2):
    """Property 2: Filtering by d2 then d1 (where d1 <= d2) equals filtering by d1 alone."""
    if d1 > d2:
        d1, d2 = d2, d1  # ensure d1 <= d2
    d1_str = d1.strftime("%Y-%m-%d")
    d2_str = d2.strftime("%Y-%m-%d")

    result_direct = filter_ohlcv_by_date(df, d1_str)
    result_double = filter_ohlcv_by_date(filter_ohlcv_by_date(df, d2_str), d1_str)

    pd.testing.assert_frame_equal(
        result_direct.reset_index(drop=True), result_double.reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Property 3: OHLCV None Passthrough
# filter(data, None) returns identical DataFrame
# ---------------------------------------------------------------------------


@given(df=ohlcv_dataframe())
@settings(max_examples=100)
def test_property_3_none_passthrough(df):
    """Property 3: Passing None as curr_date returns the DataFrame unchanged."""
    result = filter_ohlcv_by_date(df, None)
    pd.testing.assert_frame_equal(result, df)


# ---------------------------------------------------------------------------
# Unit tests: edge cases
# ---------------------------------------------------------------------------


def test_empty_dataframe():
    """Empty DataFrame returns empty DataFrame."""
    df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    result = filter_ohlcv_by_date(df, "2025-01-01")
    assert result.empty


def test_curr_date_before_all_data():
    """curr_date before all data returns empty DataFrame."""
    dates = pd.date_range("2025-01-01", periods=10, freq="B")
    df = pd.DataFrame({"date": dates, "close": range(10)})
    result = filter_ohlcv_by_date(df, "2024-12-01")
    assert result.empty


def test_curr_date_after_all_data():
    """curr_date after all data returns full DataFrame."""
    dates = pd.date_range("2025-01-01", periods=10, freq="B")
    df = pd.DataFrame({"date": dates, "close": range(10)})
    result = filter_ohlcv_by_date(df, "2026-12-31")
    assert len(result) == 10


def test_invalid_curr_date_raises_valueerror():
    """Invalid curr_date string raises ValueError."""
    df = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=5), "close": range(5)})
    with pytest.raises(ValueError, match="cannot parse curr_date"):
        filter_ohlcv_by_date(df, "not-a-date")


def test_datetime_index_filtering():
    """Works with DatetimeIndex (after stockstats wrap sets date as index)."""
    dates = pd.date_range("2025-01-01", periods=20, freq="B")
    df = pd.DataFrame({"close": range(20)}, index=dates)
    df.index.name = "date"
    result = filter_ohlcv_by_date(df, "2025-01-15")
    assert (result.index <= pd.Timestamp("2025-01-15")).all()
    assert len(result) < 20
