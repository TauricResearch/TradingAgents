import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    Series,
)
import pandas._testing as tm


@pytest.mark.parametrize(
    "in_vals, out_vals",
    [
        # Basics: strictly increasing (T), strictly decreasing (F),
        # abs val increasing (F), non-strictly increasing (T)
        ([1, 2, 5, 3, 2, 0, 4, 5, -6, 1, 1], [True, False, False, True]),
        # Test with inf vals
        (
            [1, 2.1, np.inf, 3, 2, np.inf, -np.inf, 5, 11, 1, -np.inf],
            [True, False, True, False],
        ),
        # Test with nan vals; should always be False
        (
            [1, 2, np.nan, 3, 2, np.nan, np.nan, 5, -np.inf, 1, np.nan],
            [False, False, False, False],
        ),
    ],
)
def test_is_monotonic_increasing(in_vals, out_vals):
    # GH 17015
    source_dict = {
        "A": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"],
        "B": ["a", "a", "a", "b", "b", "b", "c", "c", "c", "d", "d"],
        "C": in_vals,
    }
    df = DataFrame(source_dict)
    result = df.groupby("B").C.is_monotonic_increasing
    index = Index(list("abcd"), name="B")
    expected = Series(index=index, data=out_vals, name="C")
    tm.assert_series_equal(result, expected)

    # Also check result equal to manually taking x.is_monotonic_increasing.
    expected = df.groupby(["B"]).C.apply(lambda x: x.is_monotonic_increasing)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "in_vals, out_vals",
    [
        # Basics: strictly decreasing (T), strictly increasing (F),
        # abs val decreasing (F), non-strictly increasing (T)
        ([10, 9, 7, 3, 4, 5, -3, 2, 0, 1, 1], [True, False, False, True]),
        # Test with inf vals
        (
            [np.inf, 1, -np.inf, np.inf, 2, -3, -np.inf, 5, -3, -np.inf, -np.inf],
            [True, True, False, True],
        ),
        # Test with nan vals; should always be False
        (
            [1, 2, np.nan, 3, 2, np.nan, np.nan, 5, -np.inf, 1, np.nan],
            [False, False, False, False],
        ),
    ],
)
def test_is_monotonic_decreasing(in_vals, out_vals):
    # GH 17015
    source_dict = {
        "A": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"],
        "B": ["a", "a", "a", "b", "b", "b", "c", "c", "c", "d", "d"],
        "C": in_vals,
    }

    df = DataFrame(source_dict)
    result = df.groupby("B").C.is_monotonic_decreasing
    index = Index(list("abcd"), name="B")
    expected = Series(index=index, data=out_vals, name="C")
    tm.assert_series_equal(result, expected)
