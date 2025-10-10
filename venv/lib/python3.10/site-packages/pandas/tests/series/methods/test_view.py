import numpy as np
import pytest

from pandas import (
    Index,
    Series,
    array,
    date_range,
)
import pandas._testing as tm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Series.view is deprecated and will be removed in a future version.:FutureWarning"  # noqa: E501
)


class TestView:
    def test_view_i8_to_datetimelike(self):
        dti = date_range("2000", periods=4, tz="US/Central")
        ser = Series(dti.asi8)

        result = ser.view(dti.dtype)
        tm.assert_datetime_array_equal(result._values, dti._data._with_freq(None))

        pi = dti.tz_localize(None).to_period("D")
        ser = Series(pi.asi8)
        result = ser.view(pi.dtype)
        tm.assert_period_array_equal(result._values, pi._data)

    def test_view_tz(self):
        # GH#24024
        ser = Series(date_range("2000", periods=4, tz="US/Central"))
        result = ser.view("i8")
        expected = Series(
            [
                946706400000000000,
                946792800000000000,
                946879200000000000,
                946965600000000000,
            ]
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "first", ["m8[ns]", "M8[ns]", "M8[ns, US/Central]", "period[D]"]
    )
    @pytest.mark.parametrize(
        "second", ["m8[ns]", "M8[ns]", "M8[ns, US/Central]", "period[D]"]
    )
    @pytest.mark.parametrize("box", [Series, Index, array])
    def test_view_between_datetimelike(self, first, second, box):
        dti = date_range("2016-01-01", periods=3)

        orig = box(dti)
        obj = orig.view(first)
        assert obj.dtype == first
        tm.assert_numpy_array_equal(np.asarray(obj.view("i8")), dti.asi8)

        res = obj.view(second)
        assert res.dtype == second
        tm.assert_numpy_array_equal(np.asarray(obj.view("i8")), dti.asi8)
