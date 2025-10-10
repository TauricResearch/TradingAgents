import decimal

import numpy as np
import pytest

from pandas.core.dtypes.cast import maybe_downcast_to_dtype

from pandas import (
    Series,
    Timedelta,
)
import pandas._testing as tm


@pytest.mark.parametrize(
    "arr,dtype,expected",
    [
        (
            np.array([8.5, 8.6, 8.7, 8.8, 8.9999999999995]),
            "infer",
            np.array([8.5, 8.6, 8.7, 8.8, 8.9999999999995]),
        ),
        (
            np.array([8.0, 8.0, 8.0, 8.0, 8.9999999999995]),
            "infer",
            np.array([8, 8, 8, 8, 9], dtype=np.int64),
        ),
        (
            np.array([8.0, 8.0, 8.0, 8.0, 9.0000000000005]),
            "infer",
            np.array([8, 8, 8, 8, 9], dtype=np.int64),
        ),
        (
            # This is a judgement call, but we do _not_ downcast Decimal
            #  objects
            np.array([decimal.Decimal(0.0)]),
            "int64",
            np.array([decimal.Decimal(0.0)]),
        ),
        (
            # GH#45837
            np.array([Timedelta(days=1), Timedelta(days=2)], dtype=object),
            "infer",
            np.array([1, 2], dtype="m8[D]").astype("m8[ns]"),
        ),
        # TODO: similar for dt64, dt64tz, Period, Interval?
    ],
)
def test_downcast(arr, expected, dtype):
    result = maybe_downcast_to_dtype(arr, dtype)
    tm.assert_numpy_array_equal(result, expected)


def test_downcast_booleans():
    # see gh-16875: coercing of booleans.
    ser = Series([True, True, False])
    result = maybe_downcast_to_dtype(ser, np.dtype(np.float64))

    expected = ser.values
    tm.assert_numpy_array_equal(result, expected)


def test_downcast_conversion_no_nan(any_real_numpy_dtype):
    dtype = any_real_numpy_dtype
    expected = np.array([1, 2])
    arr = np.array([1.0, 2.0], dtype=dtype)

    result = maybe_downcast_to_dtype(arr, "infer")
    tm.assert_almost_equal(result, expected, check_dtype=False)


def test_downcast_conversion_nan(float_numpy_dtype):
    dtype = float_numpy_dtype
    data = [1.0, 2.0, np.nan]

    expected = np.array(data, dtype=dtype)
    arr = np.array(data, dtype=dtype)

    result = maybe_downcast_to_dtype(arr, "infer")
    tm.assert_almost_equal(result, expected)


def test_downcast_conversion_empty(any_real_numpy_dtype):
    dtype = any_real_numpy_dtype
    arr = np.array([], dtype=dtype)
    result = maybe_downcast_to_dtype(arr, np.dtype("int64"))
    tm.assert_numpy_array_equal(result, np.array([], dtype=np.int64))


@pytest.mark.parametrize("klass", [np.datetime64, np.timedelta64])
def test_datetime_likes_nan(klass):
    dtype = klass.__name__ + "[ns]"
    arr = np.array([1, 2, np.nan])

    exp = np.array([1, 2, klass("NaT")], dtype)
    res = maybe_downcast_to_dtype(arr, dtype)
    tm.assert_numpy_array_equal(res, exp)
