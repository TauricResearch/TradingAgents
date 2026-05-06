"""Property-based and unit tests for yfinance financial statements look-ahead bias filter.

Feature: upstream-feature-adoption
Properties 6-7: YFinance Column Date Filter, None Passthrough
Validates: Requirements 3.1, 3.2, 3.3
"""

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from tradingagents.dataflows.y_finance import _filter_financials_by_date

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_DATE_RANGE = st.dates(
    min_value=pd.Timestamp("2015-01-01").date(),
    max_value=pd.Timestamp("2026-12-31").date(),
)


@st.composite
def financial_statement_df(draw):
    """Generate a DataFrame mimicking yfinance financial statements.

    yfinance returns financial statements with Timestamp column headers
    (fiscal period end dates) and row index of line items.
    """
    n_periods = draw(st.integers(min_value=1, max_value=12))
    n_items = draw(st.integers(min_value=1, max_value=10))

    # Generate fiscal period end dates as columns
    base_date = draw(_DATE_RANGE)
    col_dates = pd.date_range(start=base_date, periods=n_periods, freq="QE")

    # Line items as row index
    items = [f"LineItem_{i}" for i in range(n_items)]

    data = {
        col: draw(st.lists(st.floats(-1e9, 1e9), min_size=n_items, max_size=n_items))
        for col in col_dates
    }
    df = pd.DataFrame(data, index=items)
    return df


# ---------------------------------------------------------------------------
# Property 6: YFinance Column Date Filter
# All remaining column headers represent dates <= curr_date
# ---------------------------------------------------------------------------


@given(df=financial_statement_df(), curr_date=_DATE_RANGE)
@settings(max_examples=100)
def test_property_6_all_columns_on_or_before_curr_date(df, curr_date):
    """Property 6: After filtering, every column date header is <= curr_date."""
    curr_date_str = curr_date.strftime("%Y-%m-%d")
    result = _filter_financials_by_date(df, curr_date_str)

    if isinstance(result, str):
        # All columns were filtered out — that's valid
        return

    cutoff = pd.Timestamp(curr_date_str)
    for col in result.columns:
        col_ts = pd.Timestamp(col)
        assert col_ts <= cutoff, f"Column {col} is after cutoff {cutoff}"


# ---------------------------------------------------------------------------
# Property 7: YFinance None Passthrough
# filter(data, None) returns identical DataFrame
# ---------------------------------------------------------------------------


@given(df=financial_statement_df())
@settings(max_examples=100)
def test_property_7_none_passthrough(df):
    """Property 7: Passing None as curr_date returns the DataFrame unchanged."""
    result = _filter_financials_by_date(df, None)
    pd.testing.assert_frame_equal(result, df)


# ---------------------------------------------------------------------------
# Unit tests: edge cases
# ---------------------------------------------------------------------------


def test_empty_dataframe():
    """Empty DataFrame returns empty DataFrame."""
    df = pd.DataFrame()
    result = _filter_financials_by_date(df, "2025-01-01")
    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_all_columns_after_curr_date():
    """All columns after curr_date returns message string."""
    dates = pd.date_range("2026-01-01", periods=4, freq="QE")
    df = pd.DataFrame(
        {d: [100, 200, 300] for d in dates},
        index=["Revenue", "COGS", "NetIncome"],
    )
    result = _filter_financials_by_date(df, "2025-06-01")
    assert isinstance(result, str)
    assert "No financial data available" in result


def test_partial_filtering():
    """Only columns after curr_date are removed."""
    dates = pd.date_range("2024-01-01", periods=4, freq="QE")
    df = pd.DataFrame(
        {d: [100 * (i + 1)] for i, d in enumerate(dates)},
        index=["Revenue"],
    )
    # curr_date between 2nd and 3rd quarter
    result = _filter_financials_by_date(df, "2024-07-15")
    assert isinstance(result, pd.DataFrame)
    # Should keep Q1 (2024-03-31) and Q2 (2024-06-30), drop Q3 (2024-09-30) and Q4 (2024-12-31)
    assert len(result.columns) == 2


def test_none_curr_date_returns_unchanged():
    """None curr_date returns DataFrame unchanged."""
    dates = pd.date_range("2024-01-01", periods=4, freq="QE")
    df = pd.DataFrame(
        {d: [100] for d in dates},
        index=["Revenue"],
    )
    result = _filter_financials_by_date(df, None)
    pd.testing.assert_frame_equal(result, df)
