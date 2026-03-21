import pandas as pd
import numpy as np
import pytest
from tradingagents.dataflows.stockstats_utils import _clean_dataframe

def test_clean_dataframe_valid_data():
    """Test _clean_dataframe with valid data where no rows should be dropped."""
    df = pd.DataFrame({
        "Date": ["2023-01-01", "2023-01-02", "2023-01-03"],
        "Open": [10.0, 11.0, 12.0],
        "High": [10.5, 11.5, 12.5],
        "Low": [9.5, 10.5, 11.5],
        "Close": [10.2, 11.2, 12.2],
        "Volume": [100, 200, 300]
    })

    cleaned_df = _clean_dataframe(df.copy())

    assert len(cleaned_df) == 3
    assert "date" in cleaned_df.columns
    assert pd.api.types.is_datetime64_any_dtype(cleaned_df["date"])

    # Check if price columns are correctly parsed as float/numeric
    for col in ["open", "high", "low", "close", "volume"]:
        assert pd.api.types.is_numeric_dtype(cleaned_df[col])
        assert (cleaned_df[col] == df[col.capitalize()]).all()

def test_clean_dataframe_invalid_dates():
    """Test _clean_dataframe drops rows with invalid or missing dates."""
    df = pd.DataFrame({
        "Date": ["2023-01-01", "invalid_date", None],
        "Open": [10.0, 11.0, 12.0],
        "Close": [10.2, 11.2, 12.2]
    })

    cleaned_df = _clean_dataframe(df.copy())

    assert len(cleaned_df) == 1
    assert cleaned_df.iloc[0]["date"] == pd.to_datetime("2023-01-01")

def test_clean_dataframe_missing_close():
    """Test _clean_dataframe drops rows where Close price is missing."""
    df = pd.DataFrame({
        "Date": ["2023-01-01", "2023-01-02", "2023-01-03"],
        "Open": [10.0, 11.0, 12.0],
        "Close": [10.2, np.nan, 12.2]
    })

    cleaned_df = _clean_dataframe(df.copy())

    assert len(cleaned_df) == 2
    assert cleaned_df.iloc[0]["date"] == pd.to_datetime("2023-01-01")
    assert cleaned_df.iloc[1]["date"] == pd.to_datetime("2023-01-03")

def test_clean_dataframe_numeric_coercion():
    """Test _clean_dataframe coerces non-numeric strings to NaN in price columns,
    but handles ffill/bfill for them."""
    df = pd.DataFrame({
        "Date": ["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04"],
        "Open": [10.0, "invalid", 12.0, 13.0],
        "Close": [10.2, 11.2, 12.2, 13.2]
    })

    cleaned_df = _clean_dataframe(df.copy())

    assert len(cleaned_df) == 4
    # "invalid" is coerced to NaN, then ffill will fill it with 10.0 (from previous row)
    assert cleaned_df.iloc[1]["open"] == 10.0

def test_clean_dataframe_ffill_bfill():
    """Test _clean_dataframe forward and backward fills missing values in price columns."""
    df = pd.DataFrame({
        "Date": ["2023-01-01", "2023-01-02", "2023-01-03"],
        "Open": [np.nan, 11.0, np.nan],
        "Close": [10.2, 11.2, 12.2]
    })

    cleaned_df = _clean_dataframe(df.copy())

    assert len(cleaned_df) == 3
    # The first row Open is NaN -> bfill uses the next valid value (11.0)
    assert cleaned_df.iloc[0]["open"] == 11.0
    # The last row Open is NaN -> ffill uses the previous valid value (11.0)
    assert cleaned_df.iloc[2]["open"] == 11.0

def test_clean_dataframe_empty():
    """Test _clean_dataframe with an empty DataFrame."""
    df = pd.DataFrame(columns=["Date", "Open", "Close"])

    cleaned_df = _clean_dataframe(df.copy())

    assert len(cleaned_df) == 0
    assert "date" in cleaned_df.columns
    assert "open" in cleaned_df.columns
    assert "close" in cleaned_df.columns

def test_clean_dataframe_missing_columns():
    """Test _clean_dataframe when some optional price columns are missing."""
    df = pd.DataFrame({
        "Date": ["2023-01-01", "2023-01-02"],
        "Close": [10.2, 11.2]
    })

    cleaned_df = _clean_dataframe(df.copy())

    assert len(cleaned_df) == 2
    assert "close" in cleaned_df.columns
    assert "open" not in cleaned_df.columns

def test_clean_dataframe_lowercase_columns():
    """Test _clean_dataframe successfully lowercases all column names."""
    # Given a DataFrame with mixed case and uppercase columns
    df = pd.DataFrame({
        "Date": ["2023-01-01"],
        "OPEN": [10.0],
        "High": [10.5],
        "loW": [9.5],
        "Close": [10.2],
        "Volume": [100]
    })

    # When _clean_dataframe is called
    cleaned_df = _clean_dataframe(df)

    # Then all columns should be lowercase
    expected_columns = ["date", "open", "high", "low", "close", "volume"]
    assert list(cleaned_df.columns) == expected_columns

    # And the original DataFrame should not be mutated
    assert list(df.columns) == ["Date", "OPEN", "High", "loW", "Close", "Volume"]

def test_clean_dataframe_non_string_columns():
    """Test _clean_dataframe successfully handles non-string column names by converting them to string then lowercase."""
    # Given a DataFrame with integer columns (which won't match Date or Close processing but will be lowercased)
    df = pd.DataFrame({
        "Date": ["2023-01-01"],
        "Close": [10.0],
        0: [100.0],
        1: [200.0]
    })

    # When _clean_dataframe is called
    cleaned_df = _clean_dataframe(df)

    # Then all columns should be strings and lowercase
    expected_columns = ["date", "close", "0", "1"]
    assert list(cleaned_df.columns) == expected_columns

def test_clean_dataframe_handles_no_date_or_close():
    """Test _clean_dataframe correctly formats column names if there's no date or close"""
    df = pd.DataFrame({
        1: [10.0, 11.0],
        "Open": [10.0, 11.0]
    })

    cleaned = _clean_dataframe(df)

    assert list(cleaned.columns) == ["1", "open"]
    assert len(cleaned) == 2
