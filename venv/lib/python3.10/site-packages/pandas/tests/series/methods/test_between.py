import numpy as np
import pytest

from pandas import (
    Series,
    bdate_range,
    date_range,
    period_range,
)
import pandas._testing as tm


class TestBetween:
    def test_between(self):
        series = Series(date_range("1/1/2000", periods=10))
        left, right = series[[2, 7]]

        result = series.between(left, right)
        expected = (series >= left) & (series <= right)
        tm.assert_series_equal(result, expected)

    def test_between_datetime_object_dtype(self):
        ser = Series(bdate_range("1/1/2000", periods=20), dtype=object)
        ser[::2] = np.nan

        result = ser[ser.between(ser[3], ser[17])]
        expected = ser[3:18].dropna()
        tm.assert_series_equal(result, expected)

        result = ser[ser.between(ser[3], ser[17], inclusive="neither")]
        expected = ser[5:16].dropna()
        tm.assert_series_equal(result, expected)

    def test_between_period_values(self):
        ser = Series(period_range("2000-01-01", periods=10, freq="D"))
        left, right = ser[[2, 7]]
        result = ser.between(left, right)
        expected = (ser >= left) & (ser <= right)
        tm.assert_series_equal(result, expected)

    def test_between_inclusive_string(self):
        # GH 40628
        series = Series(date_range("1/1/2000", periods=10))
        left, right = series[[2, 7]]

        result = series.between(left, right, inclusive="both")
        expected = (series >= left) & (series <= right)
        tm.assert_series_equal(result, expected)

        result = series.between(left, right, inclusive="left")
        expected = (series >= left) & (series < right)
        tm.assert_series_equal(result, expected)

        result = series.between(left, right, inclusive="right")
        expected = (series > left) & (series <= right)
        tm.assert_series_equal(result, expected)

        result = series.between(left, right, inclusive="neither")
        expected = (series > left) & (series < right)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("inclusive", ["yes", True, False])
    def test_between_error_args(self, inclusive):
        # GH 40628
        series = Series(date_range("1/1/2000", periods=10))
        left, right = series[[2, 7]]

        value_error_msg = (
            "Inclusive has to be either string of 'both',"
            "'left', 'right', or 'neither'."
        )

        with pytest.raises(ValueError, match=value_error_msg):
            series = Series(date_range("1/1/2000", periods=10))
            series.between(left, right, inclusive=inclusive)
