import pytest

import pandas as pd
from pandas import Series
import pandas._testing as tm


def test_take_validate_axis():
    # GH#51022
    ser = Series([-1, 5, 6, 2, 4])

    msg = "No axis named foo for object type Series"
    with pytest.raises(ValueError, match=msg):
        ser.take([1, 2], axis="foo")


def test_take():
    ser = Series([-1, 5, 6, 2, 4])

    actual = ser.take([1, 3, 4])
    expected = Series([5, 2, 4], index=[1, 3, 4])
    tm.assert_series_equal(actual, expected)

    actual = ser.take([-1, 3, 4])
    expected = Series([4, 2, 4], index=[4, 3, 4])
    tm.assert_series_equal(actual, expected)

    msg = "indices are out-of-bounds"
    with pytest.raises(IndexError, match=msg):
        ser.take([1, 10])
    with pytest.raises(IndexError, match=msg):
        ser.take([2, 5])


def test_take_categorical():
    # https://github.com/pandas-dev/pandas/issues/20664
    ser = Series(pd.Categorical(["a", "b", "c"]))
    result = ser.take([-2, -2, 0])
    expected = Series(
        pd.Categorical(["b", "b", "a"], categories=["a", "b", "c"]), index=[1, 1, 0]
    )
    tm.assert_series_equal(result, expected)


def test_take_slice_raises():
    ser = Series([-1, 5, 6, 2, 4])

    msg = "Series.take requires a sequence of integers, not slice"
    with pytest.raises(TypeError, match=msg):
        ser.take(slice(0, 3, 1))
