"""
Tests for np.foo applied to Series, not necessarily ufuncs.
"""

import numpy as np
import pytest

import pandas.util._test_decorators as td

from pandas import Series
import pandas._testing as tm


class TestPtp:
    def test_ptp(self):
        # GH#21614
        N = 1000
        arr = np.random.default_rng(2).standard_normal(N)
        ser = Series(arr)
        assert np.ptp(ser) == np.ptp(arr)


def test_numpy_unique(datetime_series):
    # it works!
    np.unique(datetime_series)


@pytest.mark.parametrize("index", [["a", "b", "c", "d", "e"], None])
def test_numpy_argwhere(index):
    # GH#35331

    s = Series(range(5), index=index, dtype=np.int64)

    result = np.argwhere(s > 2).astype(np.int64)
    expected = np.array([[3], [4]], dtype=np.int64)

    tm.assert_numpy_array_equal(result, expected)


@td.skip_if_no("pyarrow")
def test_log_arrow_backed_missing_value():
    # GH#56285
    ser = Series([1, 2, None], dtype="float64[pyarrow]")
    result = np.log(ser)
    expected = np.log(Series([1, 2, None], dtype="float64"))
    tm.assert_series_equal(result, expected)
