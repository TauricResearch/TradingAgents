from datetime import datetime

import numpy as np

import pandas as pd
from pandas import (
    Period,
    Series,
    date_range,
    period_range,
    to_datetime,
)
import pandas._testing as tm


class TestCombineFirst:
    def test_combine_first_period_datetime(self):
        # GH#3367
        didx = date_range(start="1950-01-31", end="1950-07-31", freq="ME")
        pidx = period_range(start=Period("1950-1"), end=Period("1950-7"), freq="M")
        # check to be consistent with DatetimeIndex
        for idx in [didx, pidx]:
            a = Series([1, np.nan, np.nan, 4, 5, np.nan, 7], index=idx)
            b = Series([9, 9, 9, 9, 9, 9, 9], index=idx)

            result = a.combine_first(b)
            expected = Series([1, 9, 9, 4, 5, 9, 7], index=idx, dtype=np.float64)
            tm.assert_series_equal(result, expected)

    def test_combine_first_name(self, datetime_series):
        result = datetime_series.combine_first(datetime_series[:5])
        assert result.name == datetime_series.name

    def test_combine_first(self, using_infer_string):
        values = np.arange(20, dtype=np.float64)
        series = Series(values, index=np.arange(20, dtype=np.int64))

        series_copy = series * 2
        series_copy[::2] = np.nan

        # nothing used from the input
        combined = series.combine_first(series_copy)

        tm.assert_series_equal(combined, series)

        # Holes filled from input
        combined = series_copy.combine_first(series)
        assert np.isfinite(combined).all()

        tm.assert_series_equal(combined[::2], series[::2])
        tm.assert_series_equal(combined[1::2], series_copy[1::2])

        # mixed types
        index = pd.Index([str(i) for i in range(20)])
        floats = Series(np.random.default_rng(2).standard_normal(20), index=index)
        strings = Series([str(i) for i in range(10)], index=index[::2], dtype=object)

        combined = strings.combine_first(floats)

        tm.assert_series_equal(strings, combined.loc[index[::2]])
        tm.assert_series_equal(floats[1::2].astype(object), combined.loc[index[1::2]])

        # corner case
        ser = Series([1.0, 2, 3], index=[0, 1, 2])
        empty = Series([], index=[], dtype=object)
        msg = "The behavior of array concatenation with empty entries is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = ser.combine_first(empty)
        if not using_infer_string:
            ser.index = ser.index.astype("O")
        tm.assert_series_equal(ser, result)

    def test_combine_first_dt64(self, unit):
        s0 = to_datetime(Series(["2010", np.nan])).dt.as_unit(unit)
        s1 = to_datetime(Series([np.nan, "2011"])).dt.as_unit(unit)
        rs = s0.combine_first(s1)
        xp = to_datetime(Series(["2010", "2011"])).dt.as_unit(unit)
        tm.assert_series_equal(rs, xp)

        s0 = to_datetime(Series(["2010", np.nan])).dt.as_unit(unit)
        s1 = Series([np.nan, "2011"])
        rs = s0.combine_first(s1)

        xp = Series([datetime(2010, 1, 1), "2011"], dtype="datetime64[ns]")

        tm.assert_series_equal(rs, xp)

    def test_combine_first_dt_tz_values(self, tz_naive_fixture):
        ser1 = Series(
            pd.DatetimeIndex(["20150101", "20150102", "20150103"], tz=tz_naive_fixture),
            name="ser1",
        )
        ser2 = Series(
            pd.DatetimeIndex(["20160514", "20160515", "20160516"], tz=tz_naive_fixture),
            index=[2, 3, 4],
            name="ser2",
        )
        result = ser1.combine_first(ser2)
        exp_vals = pd.DatetimeIndex(
            ["20150101", "20150102", "20150103", "20160515", "20160516"],
            tz=tz_naive_fixture,
        )
        exp = Series(exp_vals, name="ser1")
        tm.assert_series_equal(exp, result)

    def test_combine_first_timezone_series_with_empty_series(self):
        # GH 41800
        time_index = date_range(
            datetime(2021, 1, 1, 1),
            datetime(2021, 1, 1, 10),
            freq="h",
            tz="Europe/Rome",
        )
        s1 = Series(range(10), index=time_index)
        s2 = Series(index=time_index)
        msg = "The behavior of array concatenation with empty entries is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = s1.combine_first(s2)
        tm.assert_series_equal(result, s1)

    def test_combine_first_preserves_dtype(self):
        # GH51764
        s1 = Series([1666880195890293744, 1666880195890293837])
        s2 = Series([1, 2, 3])
        result = s1.combine_first(s2)
        expected = Series([1666880195890293744, 1666880195890293837, 3])
        tm.assert_series_equal(result, expected)

    def test_combine_mixed_timezone(self):
        # GH 26283
        uniform_tz = Series({pd.Timestamp("2019-05-01", tz="UTC"): 1.0})
        multi_tz = Series(
            {
                pd.Timestamp("2019-05-01 01:00:00+0100", tz="Europe/London"): 2.0,
                pd.Timestamp("2019-05-02", tz="UTC"): 3.0,
            }
        )

        result = uniform_tz.combine_first(multi_tz)
        expected = Series(
            [1.0, 3.0],
            index=pd.Index(
                [
                    pd.Timestamp("2019-05-01 00:00:00+00:00", tz="UTC"),
                    pd.Timestamp("2019-05-02 00:00:00+00:00", tz="UTC"),
                ],
                dtype="object",
            ),
        )
        tm.assert_series_equal(result, expected)
