import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    NaT,
    date_range,
)


@pytest.fixture
def datetime_frame() -> DataFrame:
    """
    Fixture for DataFrame of floats with DatetimeIndex

    Columns are ['A', 'B', 'C', 'D']
    """
    return DataFrame(
        np.random.default_rng(2).standard_normal((100, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=100, freq="B"),
    )


@pytest.fixture
def float_string_frame():
    """
    Fixture for DataFrame of floats and strings with index of unique strings

    Columns are ['A', 'B', 'C', 'D', 'foo'].
    """
    df = DataFrame(
        np.random.default_rng(2).standard_normal((30, 4)),
        index=Index([f"foo_{i}" for i in range(30)], dtype=object),
        columns=Index(list("ABCD")),
    )
    df["foo"] = "bar"
    return df


@pytest.fixture
def mixed_float_frame():
    """
    Fixture for DataFrame of different float types with index of unique strings

    Columns are ['A', 'B', 'C', 'D'].
    """
    df = DataFrame(
        {
            col: np.random.default_rng(2).random(30, dtype=dtype)
            for col, dtype in zip(
                list("ABCD"), ["float32", "float32", "float32", "float64"]
            )
        },
        index=Index([f"foo_{i}" for i in range(30)], dtype=object),
    )
    # not supported by numpy random
    df["C"] = df["C"].astype("float16")
    return df


@pytest.fixture
def mixed_int_frame():
    """
    Fixture for DataFrame of different int types with index of unique strings

    Columns are ['A', 'B', 'C', 'D'].
    """
    return DataFrame(
        {
            col: np.ones(30, dtype=dtype)
            for col, dtype in zip(list("ABCD"), ["int32", "uint64", "uint8", "int64"])
        },
        index=Index([f"foo_{i}" for i in range(30)], dtype=object),
    )


@pytest.fixture
def timezone_frame():
    """
    Fixture for DataFrame of date_range Series with different time zones

    Columns are ['A', 'B', 'C']; some entries are missing

               A                         B                         C
    0 2013-01-01 2013-01-01 00:00:00-05:00 2013-01-01 00:00:00+01:00
    1 2013-01-02                       NaT                       NaT
    2 2013-01-03 2013-01-03 00:00:00-05:00 2013-01-03 00:00:00+01:00
    """
    df = DataFrame(
        {
            "A": date_range("20130101", periods=3),
            "B": date_range("20130101", periods=3, tz="US/Eastern"),
            "C": date_range("20130101", periods=3, tz="CET"),
        }
    )
    df.iloc[1, 1] = NaT
    df.iloc[1, 2] = NaT
    return df
