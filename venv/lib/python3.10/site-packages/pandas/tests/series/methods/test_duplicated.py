import numpy as np
import pytest

from pandas import (
    NA,
    Categorical,
    Series,
)
import pandas._testing as tm


@pytest.mark.parametrize(
    "keep, expected",
    [
        ("first", Series([False, False, True, False, True], name="name")),
        ("last", Series([True, True, False, False, False], name="name")),
        (False, Series([True, True, True, False, True], name="name")),
    ],
)
def test_duplicated_keep(keep, expected):
    ser = Series(["a", "b", "b", "c", "a"], name="name")

    result = ser.duplicated(keep=keep)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "keep, expected",
    [
        ("first", Series([False, False, True, False, True])),
        ("last", Series([True, True, False, False, False])),
        (False, Series([True, True, True, False, True])),
    ],
)
def test_duplicated_nan_none(keep, expected):
    ser = Series([np.nan, 3, 3, None, np.nan], dtype=object)

    result = ser.duplicated(keep=keep)
    tm.assert_series_equal(result, expected)


def test_duplicated_categorical_bool_na(nulls_fixture):
    # GH#44351
    ser = Series(
        Categorical(
            [True, False, True, False, nulls_fixture],
            categories=[True, False],
            ordered=True,
        )
    )
    result = ser.duplicated()
    expected = Series([False, False, True, True, False])
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "keep, vals",
    [
        ("last", [True, True, False]),
        ("first", [False, True, True]),
        (False, [True, True, True]),
    ],
)
def test_duplicated_mask(keep, vals):
    # GH#48150
    ser = Series([1, 2, NA, NA, NA], dtype="Int64")
    result = ser.duplicated(keep=keep)
    expected = Series([False, False] + vals)
    tm.assert_series_equal(result, expected)


def test_duplicated_mask_no_duplicated_na(keep):
    # GH#48150
    ser = Series([1, 2, NA], dtype="Int64")
    result = ser.duplicated(keep=keep)
    expected = Series([False, False, False])
    tm.assert_series_equal(result, expected)
