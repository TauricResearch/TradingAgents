import numpy as np
import pytest

from pandas import (
    Series,
    TimedeltaIndex,
    date_range,
)
import pandas._testing as tm


class TestSeriesDiff:
    def test_diff_np(self):
        # TODO(__array_function__): could make np.diff return a Series
        #  matching ser.diff()

        ser = Series(np.arange(5))

        res = np.diff(ser)
        expected = np.array([1, 1, 1, 1])
        tm.assert_numpy_array_equal(res, expected)

    def test_diff_int(self):
        # int dtype
        a = 10000000000000000
        b = a + 1
        ser = Series([a, b])

        result = ser.diff()
        assert result[1] == 1

    def test_diff_tz(self):
        # Combined datetime diff, normal diff and boolean diff test
        ts = Series(
            np.arange(10, dtype=np.float64),
            index=date_range("2020-01-01", periods=10),
            name="ts",
        )
        ts.diff()

        # neg n
        result = ts.diff(-1)
        expected = ts - ts.shift(-1)
        tm.assert_series_equal(result, expected)

        # 0
        result = ts.diff(0)
        expected = ts - ts
        tm.assert_series_equal(result, expected)

    def test_diff_dt64(self):
        # datetime diff (GH#3100)
        ser = Series(date_range("20130102", periods=5))
        result = ser.diff()
        expected = ser - ser.shift(1)
        tm.assert_series_equal(result, expected)

        # timedelta diff
        result = result - result.shift(1)  # previous result
        expected = expected.diff()  # previously expected
        tm.assert_series_equal(result, expected)

    def test_diff_dt64tz(self):
        # with tz
        ser = Series(
            date_range("2000-01-01 09:00:00", periods=5, tz="US/Eastern"), name="foo"
        )
        result = ser.diff()
        expected = Series(TimedeltaIndex(["NaT"] + ["1 days"] * 4), name="foo")
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "input,output,diff",
        [([False, True, True, False, False], [np.nan, True, False, True, False], 1)],
    )
    def test_diff_bool(self, input, output, diff):
        # boolean series (test for fixing #17294)
        ser = Series(input)
        result = ser.diff()
        expected = Series(output)
        tm.assert_series_equal(result, expected)

    def test_diff_object_dtype(self):
        # object series
        ser = Series([False, True, 5.0, np.nan, True, False])
        result = ser.diff()
        expected = ser - ser.shift(1)
        tm.assert_series_equal(result, expected)
