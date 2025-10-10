"""
Note: includes tests for `last`
"""
import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    bdate_range,
    date_range,
)
import pandas._testing as tm

deprecated_msg = "first is deprecated"
last_deprecated_msg = "last is deprecated"


class TestFirst:
    def test_first_subset(self, frame_or_series):
        ts = DataFrame(
            np.random.default_rng(2).standard_normal((100, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=100, freq="12h"),
        )
        ts = tm.get_obj(ts, frame_or_series)
        with tm.assert_produces_warning(FutureWarning, match=deprecated_msg):
            result = ts.first("10d")
            assert len(result) == 20

        ts = DataFrame(
            np.random.default_rng(2).standard_normal((100, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=100, freq="D"),
        )
        ts = tm.get_obj(ts, frame_or_series)
        with tm.assert_produces_warning(FutureWarning, match=deprecated_msg):
            result = ts.first("10d")
            assert len(result) == 10

        with tm.assert_produces_warning(FutureWarning, match=deprecated_msg):
            result = ts.first("3ME")
            expected = ts[:"3/31/2000"]
            tm.assert_equal(result, expected)

        with tm.assert_produces_warning(FutureWarning, match=deprecated_msg):
            result = ts.first("21D")
            expected = ts[:21]
            tm.assert_equal(result, expected)

        with tm.assert_produces_warning(FutureWarning, match=deprecated_msg):
            result = ts[:0].first("3ME")
            tm.assert_equal(result, ts[:0])

    def test_first_last_raises(self, frame_or_series):
        # GH#20725
        obj = DataFrame([[1, 2, 3], [4, 5, 6]])
        obj = tm.get_obj(obj, frame_or_series)

        msg = "'first' only supports a DatetimeIndex index"
        with tm.assert_produces_warning(
            FutureWarning, match=deprecated_msg
        ), pytest.raises(
            TypeError, match=msg
        ):  # index is not a DatetimeIndex
            obj.first("1D")

        msg = "'last' only supports a DatetimeIndex index"
        with tm.assert_produces_warning(
            FutureWarning, match=last_deprecated_msg
        ), pytest.raises(
            TypeError, match=msg
        ):  # index is not a DatetimeIndex
            obj.last("1D")

    def test_last_subset(self, frame_or_series):
        ts = DataFrame(
            np.random.default_rng(2).standard_normal((100, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=100, freq="12h"),
        )
        ts = tm.get_obj(ts, frame_or_series)
        with tm.assert_produces_warning(FutureWarning, match=last_deprecated_msg):
            result = ts.last("10d")
        assert len(result) == 20

        ts = DataFrame(
            np.random.default_rng(2).standard_normal((30, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=30, freq="D"),
        )
        ts = tm.get_obj(ts, frame_or_series)
        with tm.assert_produces_warning(FutureWarning, match=last_deprecated_msg):
            result = ts.last("10d")
        assert len(result) == 10

        with tm.assert_produces_warning(FutureWarning, match=last_deprecated_msg):
            result = ts.last("21D")
        expected = ts["2000-01-10":]
        tm.assert_equal(result, expected)

        with tm.assert_produces_warning(FutureWarning, match=last_deprecated_msg):
            result = ts.last("21D")
        expected = ts[-21:]
        tm.assert_equal(result, expected)

        with tm.assert_produces_warning(FutureWarning, match=last_deprecated_msg):
            result = ts[:0].last("3ME")
        tm.assert_equal(result, ts[:0])

    @pytest.mark.parametrize("start, periods", [("2010-03-31", 1), ("2010-03-30", 2)])
    def test_first_with_first_day_last_of_month(self, frame_or_series, start, periods):
        # GH#29623
        x = frame_or_series([1] * 100, index=bdate_range(start, periods=100))
        with tm.assert_produces_warning(FutureWarning, match=deprecated_msg):
            result = x.first("1ME")
        expected = frame_or_series(
            [1] * periods, index=bdate_range(start, periods=periods)
        )
        tm.assert_equal(result, expected)

    def test_first_with_first_day_end_of_frq_n_greater_one(self, frame_or_series):
        # GH#29623
        x = frame_or_series([1] * 100, index=bdate_range("2010-03-31", periods=100))
        with tm.assert_produces_warning(FutureWarning, match=deprecated_msg):
            result = x.first("2ME")
        expected = frame_or_series(
            [1] * 23, index=bdate_range("2010-03-31", "2010-04-30")
        )
        tm.assert_equal(result, expected)

    def test_empty_not_input(self):
        # GH#51032
        df = DataFrame(index=pd.DatetimeIndex([]))
        with tm.assert_produces_warning(FutureWarning, match=last_deprecated_msg):
            result = df.last(offset=1)

        with tm.assert_produces_warning(FutureWarning, match=deprecated_msg):
            result = df.first(offset=1)

        tm.assert_frame_equal(df, result)
        assert df is not result
