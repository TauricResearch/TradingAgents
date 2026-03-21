import pandas as pd
from tradingagents.dataflows.stockstats_utils import _clean_dataframe

def test_clean_dataframe_lowercases_columns():
    df = pd.DataFrame({
        "Date": ["2023-01-01", "2023-01-02", "2023-01-03"],
        "Open": [10.0, 11.0, 12.0],
        "HIGH": [10.5, 11.5, 12.5],
        "low": [9.5, 10.5, 11.5],
        "ClOsE": [10.2, 11.2, 12.2],
        "Volume": [1000, 1100, 1200]
    })

    cleaned = _clean_dataframe(df)

    assert list(cleaned.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert len(cleaned) == 3

def test_clean_dataframe_handles_non_string_columns():
    df = pd.DataFrame({
        1: [10.0, 11.0],
        "Open": [10.0, 11.0]
    })

    cleaned = _clean_dataframe(df)

    assert list(cleaned.columns) == ["1", "open"]

def test_clean_dataframe_does_not_mutate_original():
    df = pd.DataFrame({
        "Date": ["2023-01-01", "2023-01-02", "2023-01-03"],
        "Open": [10.0, 11.0, 12.0]
    })

    _clean_dataframe(df)

    assert list(df.columns) == ["Date", "Open"]
