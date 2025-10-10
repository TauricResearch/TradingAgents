import re
import sys

import numpy as np
import pytest

from pandas import (
    DataFrame,
    Series,
    date_range,
)
import pandas._testing as tm


@pytest.mark.parametrize("subset", ["a", ["a"], ["a", "B"]])
def test_duplicated_with_misspelled_column_name(subset):
    # GH 19730
    df = DataFrame({"A": [0, 0, 1], "B": [0, 0, 1], "C": [0, 0, 1]})
    msg = re.escape("Index(['a'], dtype=")

    with pytest.raises(KeyError, match=msg):
        df.duplicated(subset)


def test_duplicated_implemented_no_recursion():
    # gh-21524
    # Ensure duplicated isn't implemented using recursion that
    # can fail on wide frames
    df = DataFrame(np.random.default_rng(2).integers(0, 1000, (10, 1000)))
    rec_limit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(100)
        result = df.duplicated()
    finally:
        sys.setrecursionlimit(rec_limit)

    # Then duplicates produce the bool Series as a result and don't fail during
    # calculation. Actual values doesn't matter here, though usually it's all
    # False in this case
    assert isinstance(result, Series)
    assert result.dtype == np.bool_


@pytest.mark.parametrize(
    "keep, expected",
    [
        ("first", Series([False, False, True, False, True])),
        ("last", Series([True, True, False, False, False])),
        (False, Series([True, True, True, False, True])),
    ],
)
def test_duplicated_keep(keep, expected):
    df = DataFrame({"A": [0, 1, 1, 2, 0], "B": ["a", "b", "b", "c", "a"]})

    result = df.duplicated(keep=keep)
    tm.assert_series_equal(result, expected)


@pytest.mark.xfail(reason="GH#21720; nan/None falsely considered equal")
@pytest.mark.parametrize(
    "keep, expected",
    [
        ("first", Series([False, False, True, False, True])),
        ("last", Series([True, True, False, False, False])),
        (False, Series([True, True, True, False, True])),
    ],
)
def test_duplicated_nan_none(keep, expected):
    df = DataFrame({"C": [np.nan, 3, 3, None, np.nan], "x": 1}, dtype=object)

    result = df.duplicated(keep=keep)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("subset", [None, ["A", "B"], "A"])
def test_duplicated_subset(subset, keep):
    df = DataFrame(
        {
            "A": [0, 1, 1, 2, 0],
            "B": ["a", "b", "b", "c", "a"],
            "C": [np.nan, 3, 3, None, np.nan],
        }
    )

    if subset is None:
        subset = list(df.columns)
    elif isinstance(subset, str):
        # need to have a DataFrame, not a Series
        # -> select columns with singleton list, not string
        subset = [subset]

    expected = df[subset].duplicated(keep=keep)
    result = df.duplicated(keep=keep, subset=subset)
    tm.assert_series_equal(result, expected)


def test_duplicated_on_empty_frame():
    # GH 25184

    df = DataFrame(columns=["a", "b"])
    dupes = df.duplicated("a")

    result = df[dupes]
    expected = df.copy()
    tm.assert_frame_equal(result, expected)


def test_frame_datetime64_duplicated():
    dates = date_range("2010-07-01", end="2010-08-05")

    tst = DataFrame({"symbol": "AAA", "date": dates})
    result = tst.duplicated(["date", "symbol"])
    assert (-result).all()

    tst = DataFrame({"date": dates})
    result = tst.date.duplicated()
    assert (-result).all()
