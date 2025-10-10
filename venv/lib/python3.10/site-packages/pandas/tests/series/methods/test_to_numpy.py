import numpy as np
import pytest

import pandas.util._test_decorators as td

from pandas import (
    NA,
    Series,
    Timedelta,
)
import pandas._testing as tm


@pytest.mark.parametrize("dtype", ["int64", "float64"])
def test_to_numpy_na_value(dtype):
    # GH#48951
    ser = Series([1, 2, NA, 4])
    result = ser.to_numpy(dtype=dtype, na_value=0)
    expected = np.array([1, 2, 0, 4], dtype=dtype)
    tm.assert_numpy_array_equal(result, expected)


def test_to_numpy_cast_before_setting_na():
    # GH#50600
    ser = Series([1])
    result = ser.to_numpy(dtype=np.float64, na_value=np.nan)
    expected = np.array([1.0])
    tm.assert_numpy_array_equal(result, expected)


@td.skip_if_no("pyarrow")
def test_to_numpy_arrow_dtype_given():
    # GH#57121
    ser = Series([1, NA], dtype="int64[pyarrow]")
    result = ser.to_numpy(dtype="float64")
    expected = np.array([1.0, np.nan])
    tm.assert_numpy_array_equal(result, expected)


def test_astype_ea_int_to_td_ts():
    # GH#57093
    ser = Series([1, None], dtype="Int64")
    result = ser.astype("m8[ns]")
    expected = Series([1, Timedelta("nat")], dtype="m8[ns]")
    tm.assert_series_equal(result, expected)

    result = ser.astype("M8[ns]")
    expected = Series([1, Timedelta("nat")], dtype="M8[ns]")
    tm.assert_series_equal(result, expected)
