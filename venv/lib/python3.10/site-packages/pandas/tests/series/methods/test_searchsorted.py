import numpy as np
import pytest

import pandas as pd
from pandas import (
    Series,
    Timestamp,
    date_range,
)
import pandas._testing as tm
from pandas.api.types import is_scalar


class TestSeriesSearchSorted:
    def test_searchsorted(self):
        ser = Series([1, 2, 3])

        result = ser.searchsorted(1, side="left")
        assert is_scalar(result)
        assert result == 0

        result = ser.searchsorted(1, side="right")
        assert is_scalar(result)
        assert result == 1

    def test_searchsorted_numeric_dtypes_scalar(self):
        ser = Series([1, 2, 90, 1000, 3e9])
        res = ser.searchsorted(30)
        assert is_scalar(res)
        assert res == 2

        res = ser.searchsorted([30])
        exp = np.array([2], dtype=np.intp)
        tm.assert_numpy_array_equal(res, exp)

    def test_searchsorted_numeric_dtypes_vector(self):
        ser = Series([1, 2, 90, 1000, 3e9])
        res = ser.searchsorted([91, 2e6])
        exp = np.array([3, 4], dtype=np.intp)
        tm.assert_numpy_array_equal(res, exp)

    def test_searchsorted_datetime64_scalar(self):
        ser = Series(date_range("20120101", periods=10, freq="2D"))
        val = Timestamp("20120102")
        res = ser.searchsorted(val)
        assert is_scalar(res)
        assert res == 1

    def test_searchsorted_datetime64_scalar_mixed_timezones(self):
        # GH 30086
        ser = Series(date_range("20120101", periods=10, freq="2D", tz="UTC"))
        val = Timestamp("20120102", tz="America/New_York")
        res = ser.searchsorted(val)
        assert is_scalar(res)
        assert res == 1

    def test_searchsorted_datetime64_list(self):
        ser = Series(date_range("20120101", periods=10, freq="2D"))
        vals = [Timestamp("20120102"), Timestamp("20120104")]
        res = ser.searchsorted(vals)
        exp = np.array([1, 2], dtype=np.intp)
        tm.assert_numpy_array_equal(res, exp)

    def test_searchsorted_sorter(self):
        # GH8490
        ser = Series([3, 1, 2])
        res = ser.searchsorted([0, 3], sorter=np.argsort(ser))
        exp = np.array([0, 2], dtype=np.intp)
        tm.assert_numpy_array_equal(res, exp)

    def test_searchsorted_dataframe_fail(self):
        # GH#49620
        ser = Series([1, 2, 3, 4, 5])
        vals = pd.DataFrame([[1, 2], [3, 4]])
        msg = "Value must be 1-D array-like or scalar, DataFrame is not supported"
        with pytest.raises(ValueError, match=msg):
            ser.searchsorted(vals)
