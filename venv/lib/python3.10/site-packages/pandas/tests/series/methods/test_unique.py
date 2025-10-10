import numpy as np

from pandas import (
    Categorical,
    IntervalIndex,
    Series,
    date_range,
)
import pandas._testing as tm


class TestUnique:
    def test_unique_uint64(self):
        ser = Series([1, 2, 2**63, 2**63], dtype=np.uint64)
        res = ser.unique()
        exp = np.array([1, 2, 2**63], dtype=np.uint64)
        tm.assert_numpy_array_equal(res, exp)

    def test_unique_data_ownership(self):
        # it works! GH#1807
        Series(Series(["a", "c", "b"]).unique()).sort_values()

    def test_unique(self):
        # GH#714 also, dtype=float
        ser = Series([1.2345] * 100)
        ser[::2] = np.nan
        result = ser.unique()
        assert len(result) == 2

        # explicit f4 dtype
        ser = Series([1.2345] * 100, dtype="f4")
        ser[::2] = np.nan
        result = ser.unique()
        assert len(result) == 2

    def test_unique_nan_object_dtype(self):
        # NAs in object arrays GH#714
        ser = Series(["foo"] * 100, dtype="O")
        ser[::2] = np.nan
        result = ser.unique()
        assert len(result) == 2

    def test_unique_none(self):
        # decision about None
        ser = Series([1, 2, 3, None, None, None], dtype=object)
        result = ser.unique()
        expected = np.array([1, 2, 3, None], dtype=object)
        tm.assert_numpy_array_equal(result, expected)

    def test_unique_categorical(self):
        # GH#18051
        cat = Categorical([])
        ser = Series(cat)
        result = ser.unique()
        tm.assert_categorical_equal(result, cat)

        cat = Categorical([np.nan])
        ser = Series(cat)
        result = ser.unique()
        tm.assert_categorical_equal(result, cat)

    def test_tz_unique(self):
        # GH 46128
        dti1 = date_range("2016-01-01", periods=3)
        ii1 = IntervalIndex.from_breaks(dti1)
        ser1 = Series(ii1)
        uni1 = ser1.unique()
        tm.assert_interval_array_equal(ser1.array, uni1)

        dti2 = date_range("2016-01-01", periods=3, tz="US/Eastern")
        ii2 = IntervalIndex.from_breaks(dti2)
        ser2 = Series(ii2)
        uni2 = ser2.unique()
        tm.assert_interval_array_equal(ser2.array, uni2)

        assert uni1.dtype != uni2.dtype
