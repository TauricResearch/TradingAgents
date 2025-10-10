import numpy as np
import pytest

from pandas._libs.tslibs import IncompatibleFrequency

from pandas import (
    DatetimeIndex,
    PeriodIndex,
    Series,
    Timestamp,
    date_range,
    isna,
    notna,
    offsets,
    period_range,
)
import pandas._testing as tm


class TestSeriesAsof:
    def test_asof_nanosecond_index_access(self):
        ts = Timestamp("20130101").as_unit("ns")._value
        dti = DatetimeIndex([ts + 50 + i for i in range(100)])
        ser = Series(np.random.default_rng(2).standard_normal(100), index=dti)

        first_value = ser.asof(ser.index[0])

        # GH#46903 previously incorrectly was "day"
        assert dti.resolution == "nanosecond"

        # this used to not work bc parsing was done by dateutil that didn't
        #  handle nanoseconds
        assert first_value == ser["2013-01-01 00:00:00.000000050"]

        expected_ts = np.datetime64("2013-01-01 00:00:00.000000050", "ns")
        assert first_value == ser[Timestamp(expected_ts)]

    def test_basic(self):
        # array or list or dates
        N = 50
        rng = date_range("1/1/1990", periods=N, freq="53s")
        ts = Series(np.random.default_rng(2).standard_normal(N), index=rng)
        ts.iloc[15:30] = np.nan
        dates = date_range("1/1/1990", periods=N * 3, freq="25s")

        result = ts.asof(dates)
        assert notna(result).all()
        lb = ts.index[14]
        ub = ts.index[30]

        result = ts.asof(list(dates))
        assert notna(result).all()
        lb = ts.index[14]
        ub = ts.index[30]

        mask = (result.index >= lb) & (result.index < ub)
        rs = result[mask]
        assert (rs == ts[lb]).all()

        val = result[result.index[result.index >= ub][0]]
        assert ts[ub] == val

    def test_scalar(self):
        N = 30
        rng = date_range("1/1/1990", periods=N, freq="53s")
        # Explicit cast to float avoid implicit cast when setting nan
        ts = Series(np.arange(N), index=rng, dtype="float")
        ts.iloc[5:10] = np.nan
        ts.iloc[15:20] = np.nan

        val1 = ts.asof(ts.index[7])
        val2 = ts.asof(ts.index[19])

        assert val1 == ts.iloc[4]
        assert val2 == ts.iloc[14]

        # accepts strings
        val1 = ts.asof(str(ts.index[7]))
        assert val1 == ts.iloc[4]

        # in there
        result = ts.asof(ts.index[3])
        assert result == ts.iloc[3]

        # no as of value
        d = ts.index[0] - offsets.BDay()
        assert np.isnan(ts.asof(d))

    def test_with_nan(self):
        # basic asof test
        rng = date_range("1/1/2000", "1/2/2000", freq="4h")
        s = Series(np.arange(len(rng)), index=rng)
        r = s.resample("2h").mean()

        result = r.asof(r.index)
        expected = Series(
            [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6.0],
            index=date_range("1/1/2000", "1/2/2000", freq="2h"),
        )
        tm.assert_series_equal(result, expected)

        r.iloc[3:5] = np.nan
        result = r.asof(r.index)
        expected = Series(
            [0, 0, 1, 1, 1, 1, 3, 3, 4, 4, 5, 5, 6.0],
            index=date_range("1/1/2000", "1/2/2000", freq="2h"),
        )
        tm.assert_series_equal(result, expected)

        r.iloc[-3:] = np.nan
        result = r.asof(r.index)
        expected = Series(
            [0, 0, 1, 1, 1, 1, 3, 3, 4, 4, 4, 4, 4.0],
            index=date_range("1/1/2000", "1/2/2000", freq="2h"),
        )
        tm.assert_series_equal(result, expected)

    def test_periodindex(self):
        # array or list or dates
        N = 50
        rng = period_range("1/1/1990", periods=N, freq="h")
        ts = Series(np.random.default_rng(2).standard_normal(N), index=rng)
        ts.iloc[15:30] = np.nan
        dates = date_range("1/1/1990", periods=N * 3, freq="37min")

        result = ts.asof(dates)
        assert notna(result).all()
        lb = ts.index[14]
        ub = ts.index[30]

        result = ts.asof(list(dates))
        assert notna(result).all()
        lb = ts.index[14]
        ub = ts.index[30]

        pix = PeriodIndex(result.index.values, freq="h")
        mask = (pix >= lb) & (pix < ub)
        rs = result[mask]
        assert (rs == ts[lb]).all()

        ts.iloc[5:10] = np.nan
        ts.iloc[15:20] = np.nan

        val1 = ts.asof(ts.index[7])
        val2 = ts.asof(ts.index[19])

        assert val1 == ts.iloc[4]
        assert val2 == ts.iloc[14]

        # accepts strings
        val1 = ts.asof(str(ts.index[7]))
        assert val1 == ts.iloc[4]

        # in there
        assert ts.asof(ts.index[3]) == ts.iloc[3]

        # no as of value
        d = ts.index[0].to_timestamp() - offsets.BDay()
        assert isna(ts.asof(d))

        # Mismatched freq
        msg = "Input has different freq"
        with pytest.raises(IncompatibleFrequency, match=msg):
            ts.asof(rng.asfreq("D"))

    def test_errors(self):
        s = Series(
            [1, 2, 3],
            index=[Timestamp("20130101"), Timestamp("20130103"), Timestamp("20130102")],
        )

        # non-monotonic
        assert not s.index.is_monotonic_increasing
        with pytest.raises(ValueError, match="requires a sorted index"):
            s.asof(s.index[0])

        # subset with Series
        N = 10
        rng = date_range("1/1/1990", periods=N, freq="53s")
        s = Series(np.random.default_rng(2).standard_normal(N), index=rng)
        with pytest.raises(ValueError, match="not valid for Series"):
            s.asof(s.index[0], subset="foo")

    def test_all_nans(self):
        # GH 15713
        # series is all nans

        # testing non-default indexes
        N = 50
        rng = date_range("1/1/1990", periods=N, freq="53s")

        dates = date_range("1/1/1990", periods=N * 3, freq="25s")
        result = Series(np.nan, index=rng).asof(dates)
        expected = Series(np.nan, index=dates)
        tm.assert_series_equal(result, expected)

        # testing scalar input
        date = date_range("1/1/1990", periods=N * 3, freq="25s")[0]
        result = Series(np.nan, index=rng).asof(date)
        assert isna(result)

        # test name is propagated
        result = Series(np.nan, index=[1, 2, 3, 4], name="test").asof([4, 5])
        expected = Series(np.nan, index=[4, 5], name="test")
        tm.assert_series_equal(result, expected)
