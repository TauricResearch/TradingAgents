from datetime import datetime

import pytest

import pandas as pd
from pandas import (
    Series,
    date_range,
)
import pandas._testing as tm


class TestTruncate:
    def test_truncate_datetimeindex_tz(self):
        # GH 9243
        idx = date_range("4/1/2005", "4/30/2005", freq="D", tz="US/Pacific")
        s = Series(range(len(idx)), index=idx)
        with pytest.raises(TypeError, match="Cannot compare tz-naive"):
            # GH#36148 as of 2.0 we require tzawareness compat
            s.truncate(datetime(2005, 4, 2), datetime(2005, 4, 4))

        lb = idx[1]
        ub = idx[3]
        result = s.truncate(lb.to_pydatetime(), ub.to_pydatetime())
        expected = Series([1, 2, 3], index=idx[1:4])
        tm.assert_series_equal(result, expected)

    def test_truncate_periodindex(self):
        # GH 17717
        idx1 = pd.PeriodIndex(
            [pd.Period("2017-09-02"), pd.Period("2017-09-02"), pd.Period("2017-09-03")]
        )
        series1 = Series([1, 2, 3], index=idx1)
        result1 = series1.truncate(after="2017-09-02")

        expected_idx1 = pd.PeriodIndex(
            [pd.Period("2017-09-02"), pd.Period("2017-09-02")]
        )
        tm.assert_series_equal(result1, Series([1, 2], index=expected_idx1))

        idx2 = pd.PeriodIndex(
            [pd.Period("2017-09-03"), pd.Period("2017-09-02"), pd.Period("2017-09-03")]
        )
        series2 = Series([1, 2, 3], index=idx2)
        result2 = series2.sort_index().truncate(after="2017-09-02")

        expected_idx2 = pd.PeriodIndex([pd.Period("2017-09-02")])
        tm.assert_series_equal(result2, Series([2], index=expected_idx2))

    def test_truncate_one_element_series(self):
        # GH 35544
        series = Series([0.1], index=pd.DatetimeIndex(["2020-08-04"]))
        before = pd.Timestamp("2020-08-02")
        after = pd.Timestamp("2020-08-04")

        result = series.truncate(before=before, after=after)

        # the input Series and the expected Series are the same
        tm.assert_series_equal(result, series)

    def test_truncate_index_only_one_unique_value(self):
        # GH 42365
        obj = Series(0, index=date_range("2021-06-30", "2021-06-30")).repeat(5)

        truncated = obj.truncate("2021-06-28", "2021-07-01")

        tm.assert_series_equal(truncated, obj)
