from datetime import datetime
import warnings

import dateutil
import numpy as np
import pytest
import pytz

from pandas._libs.tslibs.ccalendar import (
    DAYS,
    MONTHS,
)
from pandas._libs.tslibs.period import IncompatibleFrequency
from pandas.errors import InvalidIndexError

import pandas as pd
from pandas import (
    DataFrame,
    Series,
    Timestamp,
)
import pandas._testing as tm
from pandas.core.indexes.datetimes import date_range
from pandas.core.indexes.period import (
    Period,
    PeriodIndex,
    period_range,
)
from pandas.core.resample import _get_period_range_edges

from pandas.tseries import offsets


@pytest.fixture()
def _index_factory():
    return period_range


@pytest.fixture
def _series_name():
    return "pi"


@pytest.fixture
def simple_period_range_series():
    """
    Series with period range index and random data for test purposes.
    """

    def _simple_period_range_series(start, end, freq="D"):
        with warnings.catch_warnings():
            # suppress Period[B] deprecation warning
            msg = "|".join(["Period with BDay freq", r"PeriodDtype\[B\] is deprecated"])
            warnings.filterwarnings(
                "ignore",
                msg,
                category=FutureWarning,
            )
            rng = period_range(start, end, freq=freq)
        return Series(np.random.default_rng(2).standard_normal(len(rng)), index=rng)

    return _simple_period_range_series


class TestPeriodIndex:
    @pytest.mark.parametrize("freq", ["2D", "1h", "2h"])
    @pytest.mark.parametrize("kind", ["period", None, "timestamp"])
    def test_asfreq(self, series_and_frame, freq, kind):
        # GH 12884, 15944
        # make sure .asfreq() returns PeriodIndex (except kind='timestamp')

        obj = series_and_frame
        if kind == "timestamp":
            expected = obj.to_timestamp().resample(freq).asfreq()
        else:
            start = obj.index[0].to_timestamp(how="start")
            end = (obj.index[-1] + obj.index.freq).to_timestamp(how="start")
            new_index = date_range(start=start, end=end, freq=freq, inclusive="left")
            expected = obj.to_timestamp().reindex(new_index).to_period(freq)
        msg = "The 'kind' keyword in (Series|DataFrame).resample is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = obj.resample(freq, kind=kind).asfreq()
        tm.assert_almost_equal(result, expected)

    def test_asfreq_fill_value(self, series):
        # test for fill value during resampling, issue 3715

        s = series
        new_index = date_range(
            s.index[0].to_timestamp(how="start"),
            (s.index[-1]).to_timestamp(how="start"),
            freq="1h",
        )
        expected = s.to_timestamp().reindex(new_index, fill_value=4.0)
        msg = "The 'kind' keyword in Series.resample is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = s.resample("1h", kind="timestamp").asfreq(fill_value=4.0)
        tm.assert_series_equal(result, expected)

        frame = s.to_frame("value")
        new_index = date_range(
            frame.index[0].to_timestamp(how="start"),
            (frame.index[-1]).to_timestamp(how="start"),
            freq="1h",
        )
        expected = frame.to_timestamp().reindex(new_index, fill_value=3.0)
        msg = "The 'kind' keyword in DataFrame.resample is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = frame.resample("1h", kind="timestamp").asfreq(fill_value=3.0)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("freq", ["h", "12h", "2D", "W"])
    @pytest.mark.parametrize("kind", [None, "period", "timestamp"])
    @pytest.mark.parametrize("kwargs", [{"on": "date"}, {"level": "d"}])
    def test_selection(self, index, freq, kind, kwargs):
        # This is a bug, these should be implemented
        # GH 14008
        rng = np.arange(len(index), dtype=np.int64)
        df = DataFrame(
            {"date": index, "a": rng},
            index=pd.MultiIndex.from_arrays([rng, index], names=["v", "d"]),
        )
        msg = (
            "Resampling from level= or on= selection with a PeriodIndex is "
            r"not currently supported, use \.set_index\(\.\.\.\) to "
            "explicitly set index"
        )
        depr_msg = "The 'kind' keyword in DataFrame.resample is deprecated"
        with pytest.raises(NotImplementedError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=depr_msg):
                df.resample(freq, kind=kind, **kwargs)

    @pytest.mark.parametrize("month", MONTHS)
    @pytest.mark.parametrize("meth", ["ffill", "bfill"])
    @pytest.mark.parametrize("conv", ["start", "end"])
    @pytest.mark.parametrize(
        ("offset", "period"), [("D", "D"), ("B", "B"), ("ME", "M"), ("QE", "Q")]
    )
    def test_annual_upsample_cases(
        self, offset, period, conv, meth, month, simple_period_range_series
    ):
        ts = simple_period_range_series("1/1/1990", "12/31/1991", freq=f"Y-{month}")
        warn = FutureWarning if period == "B" else None
        msg = r"PeriodDtype\[B\] is deprecated"
        with tm.assert_produces_warning(warn, match=msg):
            result = getattr(ts.resample(period, convention=conv), meth)()
            expected = result.to_timestamp(period, how=conv)
            expected = expected.asfreq(offset, meth).to_period()
        tm.assert_series_equal(result, expected)

    def test_basic_downsample(self, simple_period_range_series):
        ts = simple_period_range_series("1/1/1990", "6/30/1995", freq="M")
        result = ts.resample("Y-DEC").mean()

        expected = ts.groupby(ts.index.year).mean()
        expected.index = period_range("1/1/1990", "6/30/1995", freq="Y-DEC")
        tm.assert_series_equal(result, expected)

        # this is ok
        tm.assert_series_equal(ts.resample("Y-DEC").mean(), result)
        tm.assert_series_equal(ts.resample("Y").mean(), result)

    @pytest.mark.parametrize(
        "rule,expected_error_msg",
        [
            ("Y-DEC", "<YearEnd: month=12>"),
            ("Q-MAR", "<QuarterEnd: startingMonth=3>"),
            ("M", "<MonthEnd>"),
            ("w-thu", "<Week: weekday=3>"),
        ],
    )
    def test_not_subperiod(self, simple_period_range_series, rule, expected_error_msg):
        # These are incompatible period rules for resampling
        ts = simple_period_range_series("1/1/1990", "6/30/1995", freq="w-wed")
        msg = (
            "Frequency <Week: weekday=2> cannot be resampled to "
            f"{expected_error_msg}, as they are not sub or super periods"
        )
        with pytest.raises(IncompatibleFrequency, match=msg):
            ts.resample(rule).mean()

    @pytest.mark.parametrize("freq", ["D", "2D"])
    def test_basic_upsample(self, freq, simple_period_range_series):
        ts = simple_period_range_series("1/1/1990", "6/30/1995", freq="M")
        result = ts.resample("Y-DEC").mean()

        resampled = result.resample(freq, convention="end").ffill()
        expected = result.to_timestamp(freq, how="end")
        expected = expected.asfreq(freq, "ffill").to_period(freq)
        tm.assert_series_equal(resampled, expected)

    def test_upsample_with_limit(self):
        rng = period_range("1/1/2000", periods=5, freq="Y")
        ts = Series(np.random.default_rng(2).standard_normal(len(rng)), rng)

        result = ts.resample("M", convention="end").ffill(limit=2)
        expected = ts.asfreq("M").reindex(result.index, method="ffill", limit=2)
        tm.assert_series_equal(result, expected)

    def test_annual_upsample(self, simple_period_range_series):
        ts = simple_period_range_series("1/1/1990", "12/31/1995", freq="Y-DEC")
        df = DataFrame({"a": ts})
        rdf = df.resample("D").ffill()
        exp = df["a"].resample("D").ffill()
        tm.assert_series_equal(rdf["a"], exp)

    def test_annual_upsample2(self):
        rng = period_range("2000", "2003", freq="Y-DEC")
        ts = Series([1, 2, 3, 4], index=rng)

        result = ts.resample("M").ffill()
        ex_index = period_range("2000-01", "2003-12", freq="M")

        expected = ts.asfreq("M", how="start").reindex(ex_index, method="ffill")
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("month", MONTHS)
    @pytest.mark.parametrize("convention", ["start", "end"])
    @pytest.mark.parametrize(
        ("offset", "period"), [("D", "D"), ("B", "B"), ("ME", "M")]
    )
    def test_quarterly_upsample(
        self, month, offset, period, convention, simple_period_range_series
    ):
        freq = f"Q-{month}"
        ts = simple_period_range_series("1/1/1990", "12/31/1995", freq=freq)
        warn = FutureWarning if period == "B" else None
        msg = r"PeriodDtype\[B\] is deprecated"
        with tm.assert_produces_warning(warn, match=msg):
            result = ts.resample(period, convention=convention).ffill()
            expected = result.to_timestamp(period, how=convention)
            expected = expected.asfreq(offset, "ffill").to_period()
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("target", ["D", "B"])
    @pytest.mark.parametrize("convention", ["start", "end"])
    def test_monthly_upsample(self, target, convention, simple_period_range_series):
        ts = simple_period_range_series("1/1/1990", "12/31/1995", freq="M")

        warn = None if target == "D" else FutureWarning
        msg = r"PeriodDtype\[B\] is deprecated"
        with tm.assert_produces_warning(warn, match=msg):
            result = ts.resample(target, convention=convention).ffill()
            expected = result.to_timestamp(target, how=convention)
            expected = expected.asfreq(target, "ffill").to_period()
        tm.assert_series_equal(result, expected)

    def test_resample_basic(self):
        # GH3609
        s = Series(
            range(100),
            index=date_range("20130101", freq="s", periods=100, name="idx"),
            dtype="float",
        )
        s[10:30] = np.nan
        index = PeriodIndex(
            [Period("2013-01-01 00:00", "min"), Period("2013-01-01 00:01", "min")],
            name="idx",
        )
        expected = Series([34.5, 79.5], index=index)
        msg = "The 'kind' keyword in Series.resample is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = s.to_period().resample("min", kind="period").mean()
        tm.assert_series_equal(result, expected)
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result2 = s.resample("min", kind="period").mean()
        tm.assert_series_equal(result2, expected)

    @pytest.mark.parametrize(
        "freq,expected_vals", [("M", [31, 29, 31, 9]), ("2M", [31 + 29, 31 + 9])]
    )
    def test_resample_count(self, freq, expected_vals):
        # GH12774
        series = Series(1, index=period_range(start="2000", periods=100))
        result = series.resample(freq).count()
        expected_index = period_range(
            start="2000", freq=freq, periods=len(expected_vals)
        )
        expected = Series(expected_vals, index=expected_index)
        tm.assert_series_equal(result, expected)

    def test_resample_same_freq(self, resample_method):
        # GH12770
        series = Series(range(3), index=period_range(start="2000", periods=3, freq="M"))
        expected = series

        result = getattr(series.resample("M"), resample_method)()
        tm.assert_series_equal(result, expected)

    def test_resample_incompat_freq(self):
        msg = (
            "Frequency <MonthEnd> cannot be resampled to <Week: weekday=6>, "
            "as they are not sub or super periods"
        )
        pi = period_range(start="2000", periods=3, freq="M")
        ser = Series(range(3), index=pi)
        rs = ser.resample("W")
        with pytest.raises(IncompatibleFrequency, match=msg):
            # TODO: should this raise at the resample call instead of at the mean call?
            rs.mean()

    @pytest.mark.parametrize(
        "tz",
        [
            pytz.timezone("America/Los_Angeles"),
            dateutil.tz.gettz("America/Los_Angeles"),
        ],
    )
    def test_with_local_timezone(self, tz):
        # see gh-5430
        local_timezone = tz

        start = datetime(year=2013, month=11, day=1, hour=0, minute=0, tzinfo=pytz.utc)
        # 1 day later
        end = datetime(year=2013, month=11, day=2, hour=0, minute=0, tzinfo=pytz.utc)

        index = date_range(start, end, freq="h", name="idx")

        series = Series(1, index=index)
        series = series.tz_convert(local_timezone)
        msg = "The 'kind' keyword in Series.resample is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = series.resample("D", kind="period").mean()

        # Create the expected series
        # Index is moved back a day with the timezone conversion from UTC to
        # Pacific
        expected_index = (
            period_range(start=start, end=end, freq="D", name="idx") - offsets.Day()
        )
        expected = Series(1.0, index=expected_index)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "tz",
        [
            pytz.timezone("America/Los_Angeles"),
            dateutil.tz.gettz("America/Los_Angeles"),
        ],
    )
    def test_resample_with_tz(self, tz, unit):
        # GH 13238
        dti = date_range("2017-01-01", periods=48, freq="h", tz=tz, unit=unit)
        ser = Series(2, index=dti)
        result = ser.resample("D").mean()
        exp_dti = pd.DatetimeIndex(
            ["2017-01-01", "2017-01-02"], tz=tz, freq="D"
        ).as_unit(unit)
        expected = Series(
            2.0,
            index=exp_dti,
        )
        tm.assert_series_equal(result, expected)
        # Especially assert that the timezone is LMT for pytz
        assert result.index.tz == tz

    def test_resample_nonexistent_time_bin_edge(self):
        # GH 19375
        index = date_range("2017-03-12", "2017-03-12 1:45:00", freq="15min")
        s = Series(np.zeros(len(index)), index=index)
        expected = s.tz_localize("US/Pacific")
        expected.index = pd.DatetimeIndex(expected.index, freq="900s")
        result = expected.resample("900s").mean()
        tm.assert_series_equal(result, expected)

    def test_resample_nonexistent_time_bin_edge2(self):
        # GH 23742
        index = date_range(start="2017-10-10", end="2017-10-20", freq="1h")
        index = index.tz_localize("UTC").tz_convert("America/Sao_Paulo")
        df = DataFrame(data=list(range(len(index))), index=index)
        result = df.groupby(pd.Grouper(freq="1D")).count()
        expected = date_range(
            start="2017-10-09",
            end="2017-10-20",
            freq="D",
            tz="America/Sao_Paulo",
            nonexistent="shift_forward",
            inclusive="left",
        )
        tm.assert_index_equal(result.index, expected)

    def test_resample_ambiguous_time_bin_edge(self):
        # GH 10117
        idx = date_range(
            "2014-10-25 22:00:00",
            "2014-10-26 00:30:00",
            freq="30min",
            tz="Europe/London",
        )
        expected = Series(np.zeros(len(idx)), index=idx)
        result = expected.resample("30min").mean()
        tm.assert_series_equal(result, expected)

    def test_fill_method_and_how_upsample(self):
        # GH2073
        s = Series(
            np.arange(9, dtype="int64"),
            index=date_range("2010-01-01", periods=9, freq="QE"),
        )
        last = s.resample("ME").ffill()
        both = s.resample("ME").ffill().resample("ME").last().astype("int64")
        tm.assert_series_equal(last, both)

    @pytest.mark.parametrize("day", DAYS)
    @pytest.mark.parametrize("target", ["D", "B"])
    @pytest.mark.parametrize("convention", ["start", "end"])
    def test_weekly_upsample(self, day, target, convention, simple_period_range_series):
        freq = f"W-{day}"
        ts = simple_period_range_series("1/1/1990", "12/31/1995", freq=freq)

        warn = None if target == "D" else FutureWarning
        msg = r"PeriodDtype\[B\] is deprecated"
        with tm.assert_produces_warning(warn, match=msg):
            result = ts.resample(target, convention=convention).ffill()
            expected = result.to_timestamp(target, how=convention)
            expected = expected.asfreq(target, "ffill").to_period()
        tm.assert_series_equal(result, expected)

    def test_resample_to_timestamps(self, simple_period_range_series):
        ts = simple_period_range_series("1/1/1990", "12/31/1995", freq="M")

        msg = "The 'kind' keyword in Series.resample is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = ts.resample("Y-DEC", kind="timestamp").mean()
        expected = ts.to_timestamp(how="start").resample("YE-DEC").mean()
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("month", MONTHS)
    def test_resample_to_quarterly(self, simple_period_range_series, month):
        ts = simple_period_range_series("1990", "1992", freq=f"Y-{month}")
        quar_ts = ts.resample(f"Q-{month}").ffill()

        stamps = ts.to_timestamp("D", how="start")
        qdates = period_range(
            ts.index[0].asfreq("D", "start"),
            ts.index[-1].asfreq("D", "end"),
            freq=f"Q-{month}",
        )

        expected = stamps.reindex(qdates.to_timestamp("D", "s"), method="ffill")
        expected.index = qdates

        tm.assert_series_equal(quar_ts, expected)

    @pytest.mark.parametrize("how", ["start", "end"])
    def test_resample_to_quarterly_start_end(self, simple_period_range_series, how):
        # conforms, but different month
        ts = simple_period_range_series("1990", "1992", freq="Y-JUN")
        result = ts.resample("Q-MAR", convention=how).ffill()
        expected = ts.asfreq("Q-MAR", how=how)
        expected = expected.reindex(result.index, method="ffill")

        # FIXME: don't leave commented-out
        # .to_timestamp('D')
        # expected = expected.resample('Q-MAR').ffill()

        tm.assert_series_equal(result, expected)

    def test_resample_fill_missing(self):
        rng = PeriodIndex([2000, 2005, 2007, 2009], freq="Y")

        s = Series(np.random.default_rng(2).standard_normal(4), index=rng)

        stamps = s.to_timestamp()
        filled = s.resample("Y").ffill()
        expected = stamps.resample("YE").ffill().to_period("Y")
        tm.assert_series_equal(filled, expected)

    def test_cant_fill_missing_dups(self):
        rng = PeriodIndex([2000, 2005, 2005, 2007, 2007], freq="Y")
        s = Series(np.random.default_rng(2).standard_normal(5), index=rng)
        msg = "Reindexing only valid with uniquely valued Index objects"
        with pytest.raises(InvalidIndexError, match=msg):
            s.resample("Y").ffill()

    @pytest.mark.parametrize("freq", ["5min"])
    @pytest.mark.parametrize("kind", ["period", None, "timestamp"])
    def test_resample_5minute(self, freq, kind):
        rng = period_range("1/1/2000", "1/5/2000", freq="min")
        ts = Series(np.random.default_rng(2).standard_normal(len(rng)), index=rng)
        expected = ts.to_timestamp().resample(freq).mean()
        if kind != "timestamp":
            expected = expected.to_period(freq)
        msg = "The 'kind' keyword in Series.resample is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = ts.resample(freq, kind=kind).mean()
        tm.assert_series_equal(result, expected)

    def test_upsample_daily_business_daily(self, simple_period_range_series):
        ts = simple_period_range_series("1/1/2000", "2/1/2000", freq="B")

        result = ts.resample("D").asfreq()
        expected = ts.asfreq("D").reindex(period_range("1/3/2000", "2/1/2000"))
        tm.assert_series_equal(result, expected)

        ts = simple_period_range_series("1/1/2000", "2/1/2000")
        result = ts.resample("h", convention="s").asfreq()
        exp_rng = period_range("1/1/2000", "2/1/2000 23:00", freq="h")
        expected = ts.asfreq("h", how="s").reindex(exp_rng)
        tm.assert_series_equal(result, expected)

    def test_resample_irregular_sparse(self):
        dr = date_range(start="1/1/2012", freq="5min", periods=1000)
        s = Series(np.array(100), index=dr)
        # subset the data.
        subset = s[:"2012-01-04 06:55"]

        result = subset.resample("10min").apply(len)
        expected = s.resample("10min").apply(len).loc[result.index]
        tm.assert_series_equal(result, expected)

    def test_resample_weekly_all_na(self):
        rng = date_range("1/1/2000", periods=10, freq="W-WED")
        ts = Series(np.random.default_rng(2).standard_normal(len(rng)), index=rng)

        result = ts.resample("W-THU").asfreq()

        assert result.isna().all()

        result = ts.resample("W-THU").asfreq().ffill()[:-1]
        expected = ts.asfreq("W-THU").ffill()
        tm.assert_series_equal(result, expected)

    def test_resample_tz_localized(self, unit):
        dr = date_range(start="2012-4-13", end="2012-5-1", unit=unit)
        ts = Series(range(len(dr)), index=dr)

        ts_utc = ts.tz_localize("UTC")
        ts_local = ts_utc.tz_convert("America/Los_Angeles")

        result = ts_local.resample("W").mean()

        ts_local_naive = ts_local.copy()
        ts_local_naive.index = ts_local_naive.index.tz_localize(None)

        exp = ts_local_naive.resample("W").mean().tz_localize("America/Los_Angeles")
        exp.index = pd.DatetimeIndex(exp.index, freq="W")

        tm.assert_series_equal(result, exp)

        # it works
        result = ts_local.resample("D").mean()

    def test_resample_tz_localized2(self):
        # #2245
        idx = date_range(
            "2001-09-20 15:59", "2001-09-20 16:00", freq="min", tz="Australia/Sydney"
        )
        s = Series([1, 2], index=idx)

        result = s.resample("D", closed="right", label="right").mean()
        ex_index = date_range("2001-09-21", periods=1, freq="D", tz="Australia/Sydney")
        expected = Series([1.5], index=ex_index)

        tm.assert_series_equal(result, expected)

        # for good measure
        msg = "The 'kind' keyword in Series.resample is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = s.resample("D", kind="period").mean()
        ex_index = period_range("2001-09-20", periods=1, freq="D")
        expected = Series([1.5], index=ex_index)
        tm.assert_series_equal(result, expected)

    def test_resample_tz_localized3(self):
        # GH 6397
        # comparing an offset that doesn't propagate tz's
        rng = date_range("1/1/2011", periods=20000, freq="h")
        rng = rng.tz_localize("EST")
        ts = DataFrame(index=rng)
        ts["first"] = np.random.default_rng(2).standard_normal(len(rng))
        ts["second"] = np.cumsum(np.random.default_rng(2).standard_normal(len(rng)))
        expected = DataFrame(
            {
                "first": ts.resample("YE").sum()["first"],
                "second": ts.resample("YE").mean()["second"],
            },
            columns=["first", "second"],
        )
        result = (
            ts.resample("YE")
            .agg({"first": "sum", "second": "mean"})
            .reindex(columns=["first", "second"])
        )
        tm.assert_frame_equal(result, expected)

    def test_closed_left_corner(self):
        # #1465
        s = Series(
            np.random.default_rng(2).standard_normal(21),
            index=date_range(start="1/1/2012 9:30", freq="1min", periods=21),
        )
        s.iloc[0] = np.nan

        result = s.resample("10min", closed="left", label="right").mean()
        exp = s[1:].resample("10min", closed="left", label="right").mean()
        tm.assert_series_equal(result, exp)

        result = s.resample("10min", closed="left", label="left").mean()
        exp = s[1:].resample("10min", closed="left", label="left").mean()

        ex_index = date_range(start="1/1/2012 9:30", freq="10min", periods=3)

        tm.assert_index_equal(result.index, ex_index)
        tm.assert_series_equal(result, exp)

    def test_quarterly_resampling(self):
        rng = period_range("2000Q1", periods=10, freq="Q-DEC")
        ts = Series(np.arange(10), index=rng)

        result = ts.resample("Y").mean()
        exp = ts.to_timestamp().resample("YE").mean().to_period()
        tm.assert_series_equal(result, exp)

    def test_resample_weekly_bug_1726(self):
        # 8/6/12 is a Monday
        ind = date_range(start="8/6/2012", end="8/26/2012", freq="D")
        n = len(ind)
        data = [[x] * 5 for x in range(n)]
        df = DataFrame(data, columns=["open", "high", "low", "close", "vol"], index=ind)

        # it works!
        df.resample("W-MON", closed="left", label="left").first()

    def test_resample_with_dst_time_change(self):
        # GH 15549
        index = (
            pd.DatetimeIndex([1457537600000000000, 1458059600000000000])
            .tz_localize("UTC")
            .tz_convert("America/Chicago")
        )
        df = DataFrame([1, 2], index=index)
        result = df.resample("12h", closed="right", label="right").last().ffill()

        expected_index_values = [
            "2016-03-09 12:00:00-06:00",
            "2016-03-10 00:00:00-06:00",
            "2016-03-10 12:00:00-06:00",
            "2016-03-11 00:00:00-06:00",
            "2016-03-11 12:00:00-06:00",
            "2016-03-12 00:00:00-06:00",
            "2016-03-12 12:00:00-06:00",
            "2016-03-13 00:00:00-06:00",
            "2016-03-13 13:00:00-05:00",
            "2016-03-14 01:00:00-05:00",
            "2016-03-14 13:00:00-05:00",
            "2016-03-15 01:00:00-05:00",
            "2016-03-15 13:00:00-05:00",
        ]
        index = (
            pd.to_datetime(expected_index_values, utc=True)
            .tz_convert("America/Chicago")
            .as_unit(index.unit)
        )
        index = pd.DatetimeIndex(index, freq="12h")
        expected = DataFrame(
            [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0],
            index=index,
        )
        tm.assert_frame_equal(result, expected)

    def test_resample_bms_2752(self):
        # GH2753
        timeseries = Series(
            index=pd.bdate_range("20000101", "20000201"), dtype=np.float64
        )
        res1 = timeseries.resample("BMS").mean()
        res2 = timeseries.resample("BMS").mean().resample("B").mean()
        assert res1.index[0] == Timestamp("20000103")
        assert res1.index[0] == res2.index[0]

    @pytest.mark.xfail(reason="Commented out for more than 3 years. Should this work?")
    def test_monthly_convention_span(self):
        rng = period_range("2000-01", periods=3, freq="ME")
        ts = Series(np.arange(3), index=rng)

        # hacky way to get same thing
        exp_index = period_range("2000-01-01", "2000-03-31", freq="D")
        expected = ts.asfreq("D", how="end").reindex(exp_index)
        expected = expected.fillna(method="bfill")

        result = ts.resample("D").mean()

        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "from_freq, to_freq", [("D", "ME"), ("QE", "YE"), ("ME", "QE"), ("D", "W")]
    )
    def test_default_right_closed_label(self, from_freq, to_freq):
        idx = date_range(start="8/15/2012", periods=100, freq=from_freq)
        df = DataFrame(np.random.default_rng(2).standard_normal((len(idx), 2)), idx)

        resampled = df.resample(to_freq).mean()
        tm.assert_frame_equal(
            resampled, df.resample(to_freq, closed="right", label="right").mean()
        )

    @pytest.mark.parametrize(
        "from_freq, to_freq",
        [("D", "MS"), ("QE", "YS"), ("ME", "QS"), ("h", "D"), ("min", "h")],
    )
    def test_default_left_closed_label(self, from_freq, to_freq):
        idx = date_range(start="8/15/2012", periods=100, freq=from_freq)
        df = DataFrame(np.random.default_rng(2).standard_normal((len(idx), 2)), idx)

        resampled = df.resample(to_freq).mean()
        tm.assert_frame_equal(
            resampled, df.resample(to_freq, closed="left", label="left").mean()
        )

    def test_all_values_single_bin(self):
        # GH#2070
        index = period_range(start="2012-01-01", end="2012-12-31", freq="M")
        ser = Series(np.random.default_rng(2).standard_normal(len(index)), index=index)

        result = ser.resample("Y").mean()
        tm.assert_almost_equal(result.iloc[0], ser.mean())

    def test_evenly_divisible_with_no_extra_bins(self):
        # GH#4076
        # when the frequency is evenly divisible, sometimes extra bins

        df = DataFrame(
            np.random.default_rng(2).standard_normal((9, 3)),
            index=date_range("2000-1-1", periods=9),
        )
        result = df.resample("5D").mean()
        expected = pd.concat([df.iloc[0:5].mean(), df.iloc[5:].mean()], axis=1).T
        expected.index = pd.DatetimeIndex(
            [Timestamp("2000-1-1"), Timestamp("2000-1-6")], dtype="M8[ns]", freq="5D"
        )
        tm.assert_frame_equal(result, expected)

    def test_evenly_divisible_with_no_extra_bins2(self):
        index = date_range(start="2001-5-4", periods=28)
        df = DataFrame(
            [
                {
                    "REST_KEY": 1,
                    "DLY_TRN_QT": 80,
                    "DLY_SLS_AMT": 90,
                    "COOP_DLY_TRN_QT": 30,
                    "COOP_DLY_SLS_AMT": 20,
                }
            ]
            * 28
            + [
                {
                    "REST_KEY": 2,
                    "DLY_TRN_QT": 70,
                    "DLY_SLS_AMT": 10,
                    "COOP_DLY_TRN_QT": 50,
                    "COOP_DLY_SLS_AMT": 20,
                }
            ]
            * 28,
            index=index.append(index),
        ).sort_index()

        index = date_range("2001-5-4", periods=4, freq="7D")
        expected = DataFrame(
            [
                {
                    "REST_KEY": 14,
                    "DLY_TRN_QT": 14,
                    "DLY_SLS_AMT": 14,
                    "COOP_DLY_TRN_QT": 14,
                    "COOP_DLY_SLS_AMT": 14,
                }
            ]
            * 4,
            index=index,
        )
        result = df.resample("7D").count()
        tm.assert_frame_equal(result, expected)

        expected = DataFrame(
            [
                {
                    "REST_KEY": 21,
                    "DLY_TRN_QT": 1050,
                    "DLY_SLS_AMT": 700,
                    "COOP_DLY_TRN_QT": 560,
                    "COOP_DLY_SLS_AMT": 280,
                }
            ]
            * 4,
            index=index,
        )
        result = df.resample("7D").sum()
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("freq, period_mult", [("h", 24), ("12h", 2)])
    @pytest.mark.parametrize("kind", [None, "period"])
    def test_upsampling_ohlc(self, freq, period_mult, kind):
        # GH 13083
        pi = period_range(start="2000", freq="D", periods=10)
        s = Series(range(len(pi)), index=pi)
        expected = s.to_timestamp().resample(freq).ohlc().to_period(freq)

        # timestamp-based resampling doesn't include all sub-periods
        # of the last original period, so extend accordingly:
        new_index = period_range(start="2000", freq=freq, periods=period_mult * len(pi))
        expected = expected.reindex(new_index)
        msg = "The 'kind' keyword in Series.resample is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = s.resample(freq, kind=kind).ohlc()
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "periods, values",
        [
            (
                [
                    pd.NaT,
                    "1970-01-01 00:00:00",
                    pd.NaT,
                    "1970-01-01 00:00:02",
                    "1970-01-01 00:00:03",
                ],
                [2, 3, 5, 7, 11],
            ),
            (
                [
                    pd.NaT,
                    pd.NaT,
                    "1970-01-01 00:00:00",
                    pd.NaT,
                    pd.NaT,
                    pd.NaT,
                    "1970-01-01 00:00:02",
                    "1970-01-01 00:00:03",
                    pd.NaT,
                    pd.NaT,
                ],
                [1, 2, 3, 5, 6, 8, 7, 11, 12, 13],
            ),
        ],
    )
    @pytest.mark.parametrize(
        "freq, expected_values",
        [
            ("1s", [3, np.nan, 7, 11]),
            ("2s", [3, (7 + 11) / 2]),
            ("3s", [(3 + 7) / 2, 11]),
        ],
    )
    def test_resample_with_nat(self, periods, values, freq, expected_values):
        # GH 13224
        index = PeriodIndex(periods, freq="s")
        frame = DataFrame(values, index=index)

        expected_index = period_range(
            "1970-01-01 00:00:00", periods=len(expected_values), freq=freq
        )
        expected = DataFrame(expected_values, index=expected_index)
        result = frame.resample(freq).mean()
        tm.assert_frame_equal(result, expected)

    def test_resample_with_only_nat(self):
        # GH 13224
        pi = PeriodIndex([pd.NaT] * 3, freq="s")
        frame = DataFrame([2, 3, 5], index=pi, columns=["a"])
        expected_index = PeriodIndex(data=[], freq=pi.freq)
        expected = DataFrame(index=expected_index, columns=["a"], dtype="float64")
        result = frame.resample("1s").mean()
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "start,end,start_freq,end_freq,offset",
        [
            ("19910905", "19910909 03:00", "h", "24h", "10h"),
            ("19910905", "19910909 12:00", "h", "24h", "10h"),
            ("19910905", "19910909 23:00", "h", "24h", "10h"),
            ("19910905 10:00", "19910909", "h", "24h", "10h"),
            ("19910905 10:00", "19910909 10:00", "h", "24h", "10h"),
            ("19910905", "19910909 10:00", "h", "24h", "10h"),
            ("19910905 12:00", "19910909", "h", "24h", "10h"),
            ("19910905 12:00", "19910909 03:00", "h", "24h", "10h"),
            ("19910905 12:00", "19910909 12:00", "h", "24h", "10h"),
            ("19910905 12:00", "19910909 12:00", "h", "24h", "34h"),
            ("19910905 12:00", "19910909 12:00", "h", "17h", "10h"),
            ("19910905 12:00", "19910909 12:00", "h", "17h", "3h"),
            ("19910905", "19910913 06:00", "2h", "24h", "10h"),
            ("19910905", "19910905 01:39", "Min", "5Min", "3Min"),
            ("19910905", "19910905 03:18", "2Min", "5Min", "3Min"),
        ],
    )
    def test_resample_with_offset(self, start, end, start_freq, end_freq, offset):
        # GH 23882 & 31809
        pi = period_range(start, end, freq=start_freq)
        ser = Series(np.arange(len(pi)), index=pi)
        result = ser.resample(end_freq, offset=offset).mean()
        result = result.to_timestamp(end_freq)

        expected = ser.to_timestamp().resample(end_freq, offset=offset).mean()
        tm.assert_series_equal(result, expected)

    def test_resample_with_offset_month(self):
        # GH 23882 & 31809
        pi = period_range("19910905 12:00", "19910909 1:00", freq="h")
        ser = Series(np.arange(len(pi)), index=pi)
        result = ser.resample("M", offset="3h").mean()
        result = result.to_timestamp("M")
        expected = ser.to_timestamp().resample("ME", offset="3h").mean()
        # TODO: is non-tick the relevant characteristic? (GH 33815)
        expected.index = expected.index._with_freq(None)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "first,last,freq,freq_to_offset,exp_first,exp_last",
        [
            ("19910905", "19920406", "D", "D", "19910905", "19920406"),
            ("19910905 00:00", "19920406 06:00", "D", "D", "19910905", "19920406"),
            (
                "19910905 06:00",
                "19920406 06:00",
                "h",
                "h",
                "19910905 06:00",
                "19920406 06:00",
            ),
            ("19910906", "19920406", "M", "ME", "1991-09", "1992-04"),
            ("19910831", "19920430", "M", "ME", "1991-08", "1992-04"),
            ("1991-08", "1992-04", "M", "ME", "1991-08", "1992-04"),
        ],
    )
    def test_get_period_range_edges(
        self, first, last, freq, freq_to_offset, exp_first, exp_last
    ):
        first = Period(first)
        last = Period(last)

        exp_first = Period(exp_first, freq=freq)
        exp_last = Period(exp_last, freq=freq)

        freq = pd.tseries.frequencies.to_offset(freq_to_offset)
        result = _get_period_range_edges(first, last, freq)
        expected = (exp_first, exp_last)
        assert result == expected

    def test_sum_min_count(self):
        # GH 19974
        index = date_range(start="2018", freq="ME", periods=6)
        data = np.ones(6)
        data[3:6] = np.nan
        s = Series(data, index).to_period()
        result = s.resample("Q").sum(min_count=1)
        expected = Series(
            [3.0, np.nan], index=PeriodIndex(["2018Q1", "2018Q2"], freq="Q-DEC")
        )
        tm.assert_series_equal(result, expected)

    def test_resample_t_l_deprecated(self):
        # GH#52536
        msg_t = "'T' is deprecated and will be removed in a future version."
        msg_l = "'L' is deprecated and will be removed in a future version."

        with tm.assert_produces_warning(FutureWarning, match=msg_l):
            rng_l = period_range(
                "2020-01-01 00:00:00 00:00", "2020-01-01 00:00:00 00:01", freq="L"
            )
        ser = Series(np.arange(len(rng_l)), index=rng_l)

        rng = period_range(
            "2020-01-01 00:00:00 00:00", "2020-01-01 00:00:00 00:01", freq="min"
        )
        expected = Series([29999.5, 60000.0], index=rng)
        with tm.assert_produces_warning(FutureWarning, match=msg_t):
            result = ser.resample("T").mean()
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "freq, freq_depr, freq_res, freq_depr_res, data",
        [
            ("2Q", "2q", "2Y", "2y", [0.5]),
            ("2M", "2m", "2Q", "2q", [1.0, 3.0]),
        ],
    )
    def test_resample_lowercase_frequency_deprecated(
        self, freq, freq_depr, freq_res, freq_depr_res, data
    ):
        depr_msg = f"'{freq_depr[1:]}' is deprecated and will be removed in a "
        f"future version. Please use '{freq[1:]}' instead."
        depr_msg_res = f"'{freq_depr_res[1:]}' is deprecated and will be removed in a "
        f"future version. Please use '{freq_res[1:]}' instead."

        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            rng_l = period_range("2020-01-01", "2020-08-01", freq=freq_depr)
        ser = Series(np.arange(len(rng_l)), index=rng_l)

        rng = period_range("2020-01-01", "2020-08-01", freq=freq_res)
        expected = Series(data=data, index=rng)

        with tm.assert_produces_warning(FutureWarning, match=depr_msg_res):
            result = ser.resample(freq_depr_res).mean()
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "offset",
        [
            offsets.MonthBegin(),
            offsets.BYearBegin(2),
            offsets.BusinessHour(2),
        ],
    )
    def test_asfreq_invalid_period_offset(self, offset, series_and_frame):
        # GH#55785
        msg = f"Invalid offset: '{offset.base}' for converting time series "

        df = series_and_frame
        with pytest.raises(ValueError, match=msg):
            df.asfreq(freq=offset)


@pytest.mark.parametrize(
    "freq,freq_depr",
    [
        ("2M", "2ME"),
        ("2Q", "2QE"),
        ("2Q-FEB", "2QE-FEB"),
        ("2Y", "2YE"),
        ("2Y-MAR", "2YE-MAR"),
        ("2M", "2me"),
        ("2Q", "2qe"),
        ("2Y-MAR", "2ye-mar"),
    ],
)
def test_resample_frequency_ME_QE_YE_error_message(series_and_frame, freq, freq_depr):
    # GH#9586
    msg = f"for Period, please use '{freq[1:]}' instead of '{freq_depr[1:]}'"

    obj = series_and_frame
    with pytest.raises(ValueError, match=msg):
        obj.resample(freq_depr)


def test_corner_cases_period(simple_period_range_series):
    # miscellaneous test coverage
    len0pts = simple_period_range_series("2007-01", "2010-05", freq="M")[:0]
    # it works
    result = len0pts.resample("Y-DEC").mean()
    assert len(result) == 0


@pytest.mark.parametrize(
    "freq_depr",
    [
        "2BME",
        "2CBME",
        "2SME",
        "2BQE-FEB",
        "2BYE-MAR",
    ],
)
def test_resample_frequency_invalid_freq(series_and_frame, freq_depr):
    # GH#9586
    msg = f"Invalid frequency: {freq_depr[1:]}"

    obj = series_and_frame
    with pytest.raises(ValueError, match=msg):
        obj.resample(freq_depr)
