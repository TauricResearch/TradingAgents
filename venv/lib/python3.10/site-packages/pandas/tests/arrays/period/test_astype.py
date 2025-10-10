import numpy as np
import pytest

from pandas.core.dtypes.dtypes import PeriodDtype

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays import period_array


@pytest.mark.parametrize("dtype", [int, np.int32, np.int64, "uint32", "uint64"])
def test_astype_int(dtype):
    # We choose to ignore the sign and size of integers for
    # Period/Datetime/Timedelta astype
    arr = period_array(["2000", "2001", None], freq="D")

    if np.dtype(dtype) != np.int64:
        with pytest.raises(TypeError, match=r"Do obj.astype\('int64'\)"):
            arr.astype(dtype)
        return

    result = arr.astype(dtype)
    expected = arr._ndarray.view("i8")
    tm.assert_numpy_array_equal(result, expected)


def test_astype_copies():
    arr = period_array(["2000", "2001", None], freq="D")
    result = arr.astype(np.int64, copy=False)

    # Add the `.base`, since we now use `.asi8` which returns a view.
    # We could maybe override it in PeriodArray to return ._ndarray directly.
    assert result.base is arr._ndarray

    result = arr.astype(np.int64, copy=True)
    assert result is not arr._ndarray
    tm.assert_numpy_array_equal(result, arr._ndarray.view("i8"))


def test_astype_categorical():
    arr = period_array(["2000", "2001", "2001", None], freq="D")
    result = arr.astype("category")
    categories = pd.PeriodIndex(["2000", "2001"], freq="D")
    expected = pd.Categorical.from_codes([0, 1, 1, -1], categories=categories)
    tm.assert_categorical_equal(result, expected)


def test_astype_period():
    arr = period_array(["2000", "2001", None], freq="D")
    result = arr.astype(PeriodDtype("M"))
    expected = period_array(["2000", "2001", None], freq="M")
    tm.assert_period_array_equal(result, expected)


@pytest.mark.parametrize("dtype", ["datetime64[ns]", "timedelta64[ns]"])
def test_astype_datetime(dtype):
    arr = period_array(["2000", "2001", None], freq="D")
    # slice off the [ns] so that the regex matches.
    if dtype == "timedelta64[ns]":
        with pytest.raises(TypeError, match=dtype[:-4]):
            arr.astype(dtype)

    else:
        # GH#45038 allow period->dt64 because we allow dt64->period
        result = arr.astype(dtype)
        expected = pd.DatetimeIndex(["2000", "2001", pd.NaT], dtype=dtype)._data
        tm.assert_datetime_array_equal(result, expected)
