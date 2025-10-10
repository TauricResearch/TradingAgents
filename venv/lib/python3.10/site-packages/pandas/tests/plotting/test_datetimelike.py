""" Test cases for time series specific (freq conversion, etc) """
from datetime import (
    date,
    datetime,
    time,
    timedelta,
)
import pickle

import numpy as np
import pytest

from pandas._libs.tslibs import (
    BaseOffset,
    to_offset,
)
from pandas._libs.tslibs.dtypes import freq_to_period_freqstr

from pandas import (
    DataFrame,
    Index,
    NaT,
    Series,
    concat,
    isna,
    to_datetime,
)
import pandas._testing as tm
from pandas.core.indexes.datetimes import (
    DatetimeIndex,
    bdate_range,
    date_range,
)
from pandas.core.indexes.period import (
    Period,
    PeriodIndex,
    period_range,
)
from pandas.core.indexes.timedeltas import timedelta_range
from pandas.tests.plotting.common import _check_ticks_props

from pandas.tseries.offsets import WeekOfMonth

mpl = pytest.importorskip("matplotlib")


class TestTSPlot:
    @pytest.mark.filterwarnings("ignore::UserWarning")
    def test_ts_plot_with_tz(self, tz_aware_fixture):
        # GH2877, GH17173, GH31205, GH31580
        tz = tz_aware_fixture
        index = date_range("1/1/2011", periods=2, freq="h", tz=tz)
        ts = Series([188.5, 328.25], index=index)
        _check_plot_works(ts.plot)
        ax = ts.plot()
        xdata = next(iter(ax.get_lines())).get_xdata()
        # Check first and last points' labels are correct
        assert (xdata[0].hour, xdata[0].minute) == (0, 0)
        assert (xdata[-1].hour, xdata[-1].minute) == (1, 0)

    def test_fontsize_set_correctly(self):
        # For issue #8765
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 9)), index=range(10)
        )
        _, ax = mpl.pyplot.subplots()
        df.plot(fontsize=2, ax=ax)
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            assert label.get_fontsize() == 2

    def test_frame_inferred(self):
        # inferred freq
        idx = date_range("1/1/1987", freq="MS", periods=100)
        idx = DatetimeIndex(idx.values, freq=None)

        df = DataFrame(
            np.random.default_rng(2).standard_normal((len(idx), 3)), index=idx
        )
        _check_plot_works(df.plot)

        # axes freq
        idx = idx[0:40].union(idx[45:99])
        df2 = DataFrame(
            np.random.default_rng(2).standard_normal((len(idx), 3)), index=idx
        )
        _check_plot_works(df2.plot)

    def test_frame_inferred_n_gt_1(self):
        # N > 1
        idx = date_range("2008-1-1 00:15:00", freq="15min", periods=10)
        idx = DatetimeIndex(idx.values, freq=None)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((len(idx), 3)), index=idx
        )
        _check_plot_works(df.plot)

    def test_is_error_nozeroindex(self):
        # GH11858
        i = np.array([1, 2, 3])
        a = DataFrame(i, index=i)
        _check_plot_works(a.plot, xerr=a)
        _check_plot_works(a.plot, yerr=a)

    def test_nonnumeric_exclude(self):
        idx = date_range("1/1/1987", freq="YE", periods=3)
        df = DataFrame({"A": ["x", "y", "z"], "B": [1, 2, 3]}, idx)

        fig, ax = mpl.pyplot.subplots()
        df.plot(ax=ax)  # it works
        assert len(ax.get_lines()) == 1  # B was plotted
        mpl.pyplot.close(fig)

    def test_nonnumeric_exclude_error(self):
        idx = date_range("1/1/1987", freq="YE", periods=3)
        df = DataFrame({"A": ["x", "y", "z"], "B": [1, 2, 3]}, idx)
        msg = "no numeric data to plot"
        with pytest.raises(TypeError, match=msg):
            df["A"].plot()

    @pytest.mark.parametrize("freq", ["s", "min", "h", "D", "W", "M", "Q", "Y"])
    def test_tsplot_period(self, freq):
        idx = period_range("12/31/1999", freq=freq, periods=100)
        ser = Series(np.random.default_rng(2).standard_normal(len(idx)), idx)
        _, ax = mpl.pyplot.subplots()
        _check_plot_works(ser.plot, ax=ax)

    @pytest.mark.parametrize(
        "freq", ["s", "min", "h", "D", "W", "ME", "QE-DEC", "YE", "1B30Min"]
    )
    def test_tsplot_datetime(self, freq):
        idx = date_range("12/31/1999", freq=freq, periods=100)
        ser = Series(np.random.default_rng(2).standard_normal(len(idx)), idx)
        _, ax = mpl.pyplot.subplots()
        _check_plot_works(ser.plot, ax=ax)

    def test_tsplot(self):
        ts = Series(
            np.arange(10, dtype=np.float64), index=date_range("2020-01-01", periods=10)
        )
        _, ax = mpl.pyplot.subplots()
        ts.plot(style="k", ax=ax)
        color = (0.0, 0.0, 0.0, 1)
        assert color == ax.get_lines()[0].get_color()

    def test_both_style_and_color(self):
        ts = Series(
            np.arange(10, dtype=np.float64), index=date_range("2020-01-01", periods=10)
        )
        msg = (
            "Cannot pass 'style' string with a color symbol and 'color' "
            "keyword argument. Please use one or the other or pass 'style' "
            "without a color symbol"
        )
        with pytest.raises(ValueError, match=msg):
            ts.plot(style="b-", color="#000099")

        s = ts.reset_index(drop=True)
        with pytest.raises(ValueError, match=msg):
            s.plot(style="b-", color="#000099")

    @pytest.mark.parametrize("freq", ["ms", "us"])
    def test_high_freq(self, freq):
        _, ax = mpl.pyplot.subplots()
        rng = date_range("1/1/2012", periods=100, freq=freq)
        ser = Series(np.random.default_rng(2).standard_normal(len(rng)), rng)
        _check_plot_works(ser.plot, ax=ax)

    def test_get_datevalue(self):
        from pandas.plotting._matplotlib.converter import get_datevalue

        assert get_datevalue(None, "D") is None
        assert get_datevalue(1987, "Y") == 1987
        assert get_datevalue(Period(1987, "Y"), "M") == Period("1987-12", "M").ordinal
        assert get_datevalue("1/1/1987", "D") == Period("1987-1-1", "D").ordinal

    def test_ts_plot_format_coord(self):
        def check_format_of_first_point(ax, expected_string):
            first_line = ax.get_lines()[0]
            first_x = first_line.get_xdata()[0].ordinal
            first_y = first_line.get_ydata()[0]
            assert expected_string == ax.format_coord(first_x, first_y)

        annual = Series(1, index=date_range("2014-01-01", periods=3, freq="YE-DEC"))
        _, ax = mpl.pyplot.subplots()
        annual.plot(ax=ax)
        check_format_of_first_point(ax, "t = 2014  y = 1.000000")

        # note this is added to the annual plot already in existence, and
        # changes its freq field
        daily = Series(1, index=date_range("2014-01-01", periods=3, freq="D"))
        daily.plot(ax=ax)
        check_format_of_first_point(ax, "t = 2014-01-01  y = 1.000000")

    @pytest.mark.parametrize("freq", ["s", "min", "h", "D", "W", "M", "Q", "Y"])
    def test_line_plot_period_series(self, freq):
        idx = period_range("12/31/1999", freq=freq, periods=100)
        ser = Series(np.random.default_rng(2).standard_normal(len(idx)), idx)
        _check_plot_works(ser.plot, ser.index.freq)

    @pytest.mark.parametrize(
        "frqncy", ["1s", "3s", "5min", "7h", "4D", "8W", "11M", "3Y"]
    )
    def test_line_plot_period_mlt_series(self, frqncy):
        # test period index line plot for series with multiples (`mlt`) of the
        # frequency (`frqncy`) rule code. tests resolution of issue #14763
        idx = period_range("12/31/1999", freq=frqncy, periods=100)
        s = Series(np.random.default_rng(2).standard_normal(len(idx)), idx)
        _check_plot_works(s.plot, s.index.freq.rule_code)

    @pytest.mark.parametrize(
        "freq", ["s", "min", "h", "D", "W", "ME", "QE-DEC", "YE", "1B30Min"]
    )
    def test_line_plot_datetime_series(self, freq):
        idx = date_range("12/31/1999", freq=freq, periods=100)
        ser = Series(np.random.default_rng(2).standard_normal(len(idx)), idx)
        _check_plot_works(ser.plot, ser.index.freq.rule_code)

    @pytest.mark.parametrize("freq", ["s", "min", "h", "D", "W", "ME", "QE", "YE"])
    def test_line_plot_period_frame(self, freq):
        idx = date_range("12/31/1999", freq=freq, periods=100)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((len(idx), 3)),
            index=idx,
            columns=["A", "B", "C"],
        )
        _check_plot_works(df.plot, df.index.freq)

    @pytest.mark.parametrize(
        "frqncy", ["1s", "3s", "5min", "7h", "4D", "8W", "11M", "3Y"]
    )
    def test_line_plot_period_mlt_frame(self, frqncy):
        # test period index line plot for DataFrames with multiples (`mlt`)
        # of the frequency (`frqncy`) rule code. tests resolution of issue
        # #14763
        idx = period_range("12/31/1999", freq=frqncy, periods=100)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((len(idx), 3)),
            index=idx,
            columns=["A", "B", "C"],
        )
        freq = freq_to_period_freqstr(1, df.index.freq.rule_code)
        freq = df.index.asfreq(freq).freq
        _check_plot_works(df.plot, freq)

    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    @pytest.mark.parametrize(
        "freq", ["s", "min", "h", "D", "W", "ME", "QE-DEC", "YE", "1B30Min"]
    )
    def test_line_plot_datetime_frame(self, freq):
        idx = date_range("12/31/1999", freq=freq, periods=100)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((len(idx), 3)),
            index=idx,
            columns=["A", "B", "C"],
        )
        freq = freq_to_period_freqstr(1, df.index.freq.rule_code)
        freq = df.index.to_period(freq).freq
        _check_plot_works(df.plot, freq)

    @pytest.mark.parametrize(
        "freq", ["s", "min", "h", "D", "W", "ME", "QE-DEC", "YE", "1B30Min"]
    )
    def test_line_plot_inferred_freq(self, freq):
        idx = date_range("12/31/1999", freq=freq, periods=100)
        ser = Series(np.random.default_rng(2).standard_normal(len(idx)), idx)
        ser = Series(ser.values, Index(np.asarray(ser.index)))
        _check_plot_works(ser.plot, ser.index.inferred_freq)

        ser = ser.iloc[[0, 3, 5, 6]]
        _check_plot_works(ser.plot)

    def test_fake_inferred_business(self):
        _, ax = mpl.pyplot.subplots()
        rng = date_range("2001-1-1", "2001-1-10")
        ts = Series(range(len(rng)), index=rng)
        ts = concat([ts[:3], ts[5:]])
        ts.plot(ax=ax)
        assert not hasattr(ax, "freq")

    def test_plot_offset_freq(self):
        ser = Series(
            np.arange(10, dtype=np.float64), index=date_range("2020-01-01", periods=10)
        )
        _check_plot_works(ser.plot)

    def test_plot_offset_freq_business(self):
        dr = date_range("2023-01-01", freq="BQS", periods=10)
        ser = Series(np.random.default_rng(2).standard_normal(len(dr)), index=dr)
        _check_plot_works(ser.plot)

    def test_plot_multiple_inferred_freq(self):
        dr = Index([datetime(2000, 1, 1), datetime(2000, 1, 6), datetime(2000, 1, 11)])
        ser = Series(np.random.default_rng(2).standard_normal(len(dr)), index=dr)
        _check_plot_works(ser.plot)

    @pytest.mark.xfail(reason="Api changed in 3.6.0")
    def test_uhf(self):
        import pandas.plotting._matplotlib.converter as conv

        idx = date_range("2012-6-22 21:59:51.960928", freq="ms", periods=500)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((len(idx), 2)), index=idx
        )

        _, ax = mpl.pyplot.subplots()
        df.plot(ax=ax)
        axis = ax.get_xaxis()

        tlocs = axis.get_ticklocs()
        tlabels = axis.get_ticklabels()
        for loc, label in zip(tlocs, tlabels):
            xp = conv._from_ordinal(loc).strftime("%H:%M:%S.%f")
            rs = str(label.get_text())
            if len(rs):
                assert xp == rs

    def test_irreg_hf(self):
        idx = date_range("2012-6-22 21:59:51", freq="s", periods=10)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((len(idx), 2)), index=idx
        )

        irreg = df.iloc[[0, 1, 3, 4]]
        _, ax = mpl.pyplot.subplots()
        irreg.plot(ax=ax)
        diffs = Series(ax.get_lines()[0].get_xydata()[:, 0]).diff()

        sec = 1.0 / 24 / 60 / 60
        assert (np.fabs(diffs[1:] - [sec, sec * 2, sec]) < 1e-8).all()

    def test_irreg_hf_object(self):
        idx = date_range("2012-6-22 21:59:51", freq="s", periods=10)
        df2 = DataFrame(
            np.random.default_rng(2).standard_normal((len(idx), 2)), index=idx
        )
        _, ax = mpl.pyplot.subplots()
        df2.index = df2.index.astype(object)
        df2.plot(ax=ax)
        diffs = Series(ax.get_lines()[0].get_xydata()[:, 0]).diff()
        sec = 1.0 / 24 / 60 / 60
        assert (np.fabs(diffs[1:] - sec) < 1e-8).all()

    def test_irregular_datetime64_repr_bug(self):
        ser = Series(
            np.arange(10, dtype=np.float64), index=date_range("2020-01-01", periods=10)
        )
        ser = ser.iloc[[0, 1, 2, 7]]

        _, ax = mpl.pyplot.subplots()

        ret = ser.plot(ax=ax)
        assert ret is not None

        for rs, xp in zip(ax.get_lines()[0].get_xdata(), ser.index):
            assert rs == xp

    def test_business_freq(self):
        bts = Series(range(5), period_range("2020-01-01", periods=5))
        msg = r"PeriodDtype\[B\] is deprecated"
        dt = bts.index[0].to_timestamp()
        with tm.assert_produces_warning(FutureWarning, match=msg):
            bts.index = period_range(start=dt, periods=len(bts), freq="B")
        _, ax = mpl.pyplot.subplots()
        bts.plot(ax=ax)
        assert ax.get_lines()[0].get_xydata()[0, 0] == bts.index[0].ordinal
        idx = ax.get_lines()[0].get_xdata()
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert PeriodIndex(data=idx).freqstr == "B"

    def test_business_freq_convert(self):
        bts = Series(
            np.arange(300, dtype=np.float64),
            index=date_range("2020-01-01", periods=300, freq="B"),
        ).asfreq("BME")
        ts = bts.to_period("M")
        _, ax = mpl.pyplot.subplots()
        bts.plot(ax=ax)
        assert ax.get_lines()[0].get_xydata()[0, 0] == ts.index[0].ordinal
        idx = ax.get_lines()[0].get_xdata()
        assert PeriodIndex(data=idx).freqstr == "M"

    def test_freq_with_no_period_alias(self):
        # GH34487
        freq = WeekOfMonth()
        bts = Series(
            np.arange(10, dtype=np.float64), index=date_range("2020-01-01", periods=10)
        ).asfreq(freq)
        _, ax = mpl.pyplot.subplots()
        bts.plot(ax=ax)

        idx = ax.get_lines()[0].get_xdata()
        msg = "freq not specified and cannot be inferred"
        with pytest.raises(ValueError, match=msg):
            PeriodIndex(data=idx)

    def test_nonzero_base(self):
        # GH2571
        idx = date_range("2012-12-20", periods=24, freq="h") + timedelta(minutes=30)
        df = DataFrame(np.arange(24), index=idx)
        _, ax = mpl.pyplot.subplots()
        df.plot(ax=ax)
        rs = ax.get_lines()[0].get_xdata()
        assert not Index(rs).is_normalized

    def test_dataframe(self):
        bts = DataFrame(
            {
                "a": Series(
                    np.arange(10, dtype=np.float64),
                    index=date_range("2020-01-01", periods=10),
                )
            }
        )
        _, ax = mpl.pyplot.subplots()
        bts.plot(ax=ax)
        idx = ax.get_lines()[0].get_xdata()
        tm.assert_index_equal(bts.index.to_period(), PeriodIndex(idx))

    @pytest.mark.filterwarnings(
        "ignore:Period with BDay freq is deprecated:FutureWarning"
    )
    @pytest.mark.parametrize(
        "obj",
        [
            Series(
                np.arange(10, dtype=np.float64),
                index=date_range("2020-01-01", periods=10),
            ),
            DataFrame(
                {
                    "a": Series(
                        np.arange(10, dtype=np.float64),
                        index=date_range("2020-01-01", periods=10),
                    ),
                    "b": Series(
                        np.arange(10, dtype=np.float64),
                        index=date_range("2020-01-01", periods=10),
                    )
                    + 1,
                }
            ),
        ],
    )
    def test_axis_limits(self, obj):
        _, ax = mpl.pyplot.subplots()
        obj.plot(ax=ax)
        xlim = ax.get_xlim()
        ax.set_xlim(xlim[0] - 5, xlim[1] + 10)
        result = ax.get_xlim()
        assert result[0] == xlim[0] - 5
        assert result[1] == xlim[1] + 10

        # string
        expected = (Period("1/1/2000", ax.freq), Period("4/1/2000", ax.freq))
        ax.set_xlim("1/1/2000", "4/1/2000")
        result = ax.get_xlim()
        assert int(result[0]) == expected[0].ordinal
        assert int(result[1]) == expected[1].ordinal

        # datetime
        expected = (Period("1/1/2000", ax.freq), Period("4/1/2000", ax.freq))
        ax.set_xlim(datetime(2000, 1, 1), datetime(2000, 4, 1))
        result = ax.get_xlim()
        assert int(result[0]) == expected[0].ordinal
        assert int(result[1]) == expected[1].ordinal
        fig = ax.get_figure()
        mpl.pyplot.close(fig)

    def test_get_finder(self):
        import pandas.plotting._matplotlib.converter as conv

        assert conv.get_finder(to_offset("B")) == conv._daily_finder
        assert conv.get_finder(to_offset("D")) == conv._daily_finder
        assert conv.get_finder(to_offset("ME")) == conv._monthly_finder
        assert conv.get_finder(to_offset("QE")) == conv._quarterly_finder
        assert conv.get_finder(to_offset("YE")) == conv._annual_finder
        assert conv.get_finder(to_offset("W")) == conv._daily_finder

    def test_finder_daily(self):
        day_lst = [10, 40, 252, 400, 950, 2750, 10000]

        msg = "Period with BDay freq is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            xpl1 = xpl2 = [Period("1999-1-1", freq="B").ordinal] * len(day_lst)
        rs1 = []
        rs2 = []
        for n in day_lst:
            rng = bdate_range("1999-1-1", periods=n)
            ser = Series(np.random.default_rng(2).standard_normal(len(rng)), rng)
            _, ax = mpl.pyplot.subplots()
            ser.plot(ax=ax)
            xaxis = ax.get_xaxis()
            rs1.append(xaxis.get_majorticklocs()[0])

            vmin, vmax = ax.get_xlim()
            ax.set_xlim(vmin + 0.9, vmax)
            rs2.append(xaxis.get_majorticklocs()[0])
            mpl.pyplot.close(ax.get_figure())

        assert rs1 == xpl1
        assert rs2 == xpl2

    def test_finder_quarterly(self):
        yrs = [3.5, 11]

        xpl1 = xpl2 = [Period("1988Q1").ordinal] * len(yrs)
        rs1 = []
        rs2 = []
        for n in yrs:
            rng = period_range("1987Q2", periods=int(n * 4), freq="Q")
            ser = Series(np.random.default_rng(2).standard_normal(len(rng)), rng)
            _, ax = mpl.pyplot.subplots()
            ser.plot(ax=ax)
            xaxis = ax.get_xaxis()
            rs1.append(xaxis.get_majorticklocs()[0])

            (vmin, vmax) = ax.get_xlim()
            ax.set_xlim(vmin + 0.9, vmax)
            rs2.append(xaxis.get_majorticklocs()[0])
            mpl.pyplot.close(ax.get_figure())

        assert rs1 == xpl1
        assert rs2 == xpl2

    def test_finder_monthly(self):
        yrs = [1.15, 2.5, 4, 11]

        xpl1 = xpl2 = [Period("Jan 1988").ordinal] * len(yrs)
        rs1 = []
        rs2 = []
        for n in yrs:
            rng = period_range("1987Q2", periods=int(n * 12), freq="M")
            ser = Series(np.random.default_rng(2).standard_normal(len(rng)), rng)
            _, ax = mpl.pyplot.subplots()
            ser.plot(ax=ax)
            xaxis = ax.get_xaxis()
            rs1.append(xaxis.get_majorticklocs()[0])

            vmin, vmax = ax.get_xlim()
            ax.set_xlim(vmin + 0.9, vmax)
            rs2.append(xaxis.get_majorticklocs()[0])
            mpl.pyplot.close(ax.get_figure())

        assert rs1 == xpl1
        assert rs2 == xpl2

    def test_finder_monthly_long(self):
        rng = period_range("1988Q1", periods=24 * 12, freq="M")
        ser = Series(np.random.default_rng(2).standard_normal(len(rng)), rng)
        _, ax = mpl.pyplot.subplots()
        ser.plot(ax=ax)
        xaxis = ax.get_xaxis()
        rs = xaxis.get_majorticklocs()[0]
        xp = Period("1989Q1", "M").ordinal
        assert rs == xp

    def test_finder_annual(self):
        xp = [1987, 1988, 1990, 1990, 1995, 2020, 2070, 2170]
        xp = [Period(x, freq="Y").ordinal for x in xp]
        rs = []
        for nyears in [5, 10, 19, 49, 99, 199, 599, 1001]:
            rng = period_range("1987", periods=nyears, freq="Y")
            ser = Series(np.random.default_rng(2).standard_normal(len(rng)), rng)
            _, ax = mpl.pyplot.subplots()
            ser.plot(ax=ax)
            xaxis = ax.get_xaxis()
            rs.append(xaxis.get_majorticklocs()[0])
            mpl.pyplot.close(ax.get_figure())

        assert rs == xp

    @pytest.mark.slow
    def test_finder_minutely(self):
        nminutes = 50 * 24 * 60
        rng = date_range("1/1/1999", freq="Min", periods=nminutes)
        ser = Series(np.random.default_rng(2).standard_normal(len(rng)), rng)
        _, ax = mpl.pyplot.subplots()
        ser.plot(ax=ax)
        xaxis = ax.get_xaxis()
        rs = xaxis.get_majorticklocs()[0]
        xp = Period("1/1/1999", freq="Min").ordinal

        assert rs == xp

    def test_finder_hourly(self):
        nhours = 23
        rng = date_range("1/1/1999", freq="h", periods=nhours)
        ser = Series(np.random.default_rng(2).standard_normal(len(rng)), rng)
        _, ax = mpl.pyplot.subplots()
        ser.plot(ax=ax)
        xaxis = ax.get_xaxis()
        rs = xaxis.get_majorticklocs()[0]
        xp = Period("1/1/1999", freq="h").ordinal

        assert rs == xp

    def test_gaps(self):
        ts = Series(
            np.arange(30, dtype=np.float64), index=date_range("2020-01-01", periods=30)
        )
        ts.iloc[5:25] = np.nan
        _, ax = mpl.pyplot.subplots()
        ts.plot(ax=ax)
        lines = ax.get_lines()
        assert len(lines) == 1
        line = lines[0]
        data = line.get_xydata()

        data = np.ma.MaskedArray(data, mask=isna(data), fill_value=np.nan)

        assert isinstance(data, np.ma.core.MaskedArray)
        mask = data.mask
        assert mask[5:25, 1].all()
        mpl.pyplot.close(ax.get_figure())

    def test_gaps_irregular(self):
        # irregular
        ts = Series(
            np.arange(30, dtype=np.float64), index=date_range("2020-01-01", periods=30)
        )
        ts = ts.iloc[[0, 1, 2, 5, 7, 9, 12, 15, 20]]
        ts.iloc[2:5] = np.nan
        _, ax = mpl.pyplot.subplots()
        ax = ts.plot(ax=ax)
        lines = ax.get_lines()
        assert len(lines) == 1
        line = lines[0]
        data = line.get_xydata()

        data = np.ma.MaskedArray(data, mask=isna(data), fill_value=np.nan)

        assert isinstance(data, np.ma.core.MaskedArray)
        mask = data.mask
        assert mask[2:5, 1].all()
        mpl.pyplot.close(ax.get_figure())

    def test_gaps_non_ts(self):
        # non-ts
        idx = [0, 1, 2, 5, 7, 9, 12, 15, 20]
        ser = Series(np.random.default_rng(2).standard_normal(len(idx)), idx)
        ser.iloc[2:5] = np.nan
        _, ax = mpl.pyplot.subplots()
        ser.plot(ax=ax)
        lines = ax.get_lines()
        assert len(lines) == 1
        line = lines[0]
        data = line.get_xydata()
        data = np.ma.MaskedArray(data, mask=isna(data), fill_value=np.nan)

        assert isinstance(data, np.ma.core.MaskedArray)
        mask = data.mask
        assert mask[2:5, 1].all()

    def test_gap_upsample(self):
        low = Series(
            np.arange(30, dtype=np.float64), index=date_range("2020-01-01", periods=30)
        )
        low.iloc[5:25] = np.nan
        _, ax = mpl.pyplot.subplots()
        low.plot(ax=ax)

        idxh = date_range(low.index[0], low.index[-1], freq="12h")
        s = Series(np.random.default_rng(2).standard_normal(len(idxh)), idxh)
        s.plot(secondary_y=True)
        lines = ax.get_lines()
        assert len(lines) == 1
        assert len(ax.right_ax.get_lines()) == 1

        line = lines[0]
        data = line.get_xydata()
        data = np.ma.MaskedArray(data, mask=isna(data), fill_value=np.nan)

        assert isinstance(data, np.ma.core.MaskedArray)
        mask = data.mask
        assert mask[5:25, 1].all()

    def test_secondary_y(self):
        ser = Series(np.random.default_rng(2).standard_normal(10))
        fig, _ = mpl.pyplot.subplots()
        ax = ser.plot(secondary_y=True)
        assert hasattr(ax, "left_ax")
        assert not hasattr(ax, "right_ax")
        axes = fig.get_axes()
        line = ax.get_lines()[0]
        xp = Series(line.get_ydata(), line.get_xdata())
        tm.assert_series_equal(ser, xp)
        assert ax.get_yaxis().get_ticks_position() == "right"
        assert not axes[0].get_yaxis().get_visible()
        mpl.pyplot.close(fig)

    def test_secondary_y_yaxis(self):
        Series(np.random.default_rng(2).standard_normal(10))
        ser2 = Series(np.random.default_rng(2).standard_normal(10))
        _, ax2 = mpl.pyplot.subplots()
        ser2.plot(ax=ax2)
        assert ax2.get_yaxis().get_ticks_position() == "left"
        mpl.pyplot.close(ax2.get_figure())

    def test_secondary_both(self):
        ser = Series(np.random.default_rng(2).standard_normal(10))
        ser2 = Series(np.random.default_rng(2).standard_normal(10))
        ax = ser2.plot()
        ax2 = ser.plot(secondary_y=True)
        assert ax.get_yaxis().get_visible()
        assert not hasattr(ax, "left_ax")
        assert hasattr(ax, "right_ax")
        assert hasattr(ax2, "left_ax")
        assert not hasattr(ax2, "right_ax")

    def test_secondary_y_ts(self):
        idx = date_range("1/1/2000", periods=10)
        ser = Series(np.random.default_rng(2).standard_normal(10), idx)
        fig, _ = mpl.pyplot.subplots()
        ax = ser.plot(secondary_y=True)
        assert hasattr(ax, "left_ax")
        assert not hasattr(ax, "right_ax")
        axes = fig.get_axes()
        line = ax.get_lines()[0]
        xp = Series(line.get_ydata(), line.get_xdata()).to_timestamp()
        tm.assert_series_equal(ser, xp)
        assert ax.get_yaxis().get_ticks_position() == "right"
        assert not axes[0].get_yaxis().get_visible()
        mpl.pyplot.close(fig)

    def test_secondary_y_ts_yaxis(self):
        idx = date_range("1/1/2000", periods=10)
        ser2 = Series(np.random.default_rng(2).standard_normal(10), idx)
        _, ax2 = mpl.pyplot.subplots()
        ser2.plot(ax=ax2)
        assert ax2.get_yaxis().get_ticks_position() == "left"
        mpl.pyplot.close(ax2.get_figure())

    def test_secondary_y_ts_visible(self):
        idx = date_range("1/1/2000", periods=10)
        ser2 = Series(np.random.default_rng(2).standard_normal(10), idx)
        ax = ser2.plot()
        assert ax.get_yaxis().get_visible()

    def test_secondary_kde(self):
        pytest.importorskip("scipy")
        ser = Series(np.random.default_rng(2).standard_normal(10))
        fig, ax = mpl.pyplot.subplots()
        ax = ser.plot(secondary_y=True, kind="density", ax=ax)
        assert hasattr(ax, "left_ax")
        assert not hasattr(ax, "right_ax")
        axes = fig.get_axes()
        assert axes[1].get_yaxis().get_ticks_position() == "right"

    def test_secondary_bar(self):
        ser = Series(np.random.default_rng(2).standard_normal(10))
        fig, ax = mpl.pyplot.subplots()
        ser.plot(secondary_y=True, kind="bar", ax=ax)
        axes = fig.get_axes()
        assert axes[1].get_yaxis().get_ticks_position() == "right"

    def test_secondary_frame(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 3)), columns=["a", "b", "c"]
        )
        axes = df.plot(secondary_y=["a", "c"], subplots=True)
        assert axes[0].get_yaxis().get_ticks_position() == "right"
        assert axes[1].get_yaxis().get_ticks_position() == "left"
        assert axes[2].get_yaxis().get_ticks_position() == "right"

    def test_secondary_bar_frame(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 3)), columns=["a", "b", "c"]
        )
        axes = df.plot(kind="bar", secondary_y=["a", "c"], subplots=True)
        assert axes[0].get_yaxis().get_ticks_position() == "right"
        assert axes[1].get_yaxis().get_ticks_position() == "left"
        assert axes[2].get_yaxis().get_ticks_position() == "right"

    def test_mixed_freq_regular_first(self):
        # TODO
        s1 = Series(
            np.arange(20, dtype=np.float64),
            index=date_range("2020-01-01", periods=20, freq="B"),
        )
        s2 = s1.iloc[[0, 5, 10, 11, 12, 13, 14, 15]]

        # it works!
        _, ax = mpl.pyplot.subplots()
        s1.plot(ax=ax)

        ax2 = s2.plot(style="g", ax=ax)
        lines = ax2.get_lines()
        msg = r"PeriodDtype\[B\] is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            idx1 = PeriodIndex(lines[0].get_xdata())
            idx2 = PeriodIndex(lines[1].get_xdata())

            tm.assert_index_equal(idx1, s1.index.to_period("B"))
            tm.assert_index_equal(idx2, s2.index.to_period("B"))

            left, right = ax2.get_xlim()
            pidx = s1.index.to_period()
        assert left <= pidx[0].ordinal
        assert right >= pidx[-1].ordinal

    def test_mixed_freq_irregular_first(self):
        s1 = Series(
            np.arange(20, dtype=np.float64), index=date_range("2020-01-01", periods=20)
        )
        s2 = s1.iloc[[0, 5, 10, 11, 12, 13, 14, 15]]
        _, ax = mpl.pyplot.subplots()
        s2.plot(style="g", ax=ax)
        s1.plot(ax=ax)
        assert not hasattr(ax, "freq")
        lines = ax.get_lines()
        x1 = lines[0].get_xdata()
        tm.assert_numpy_array_equal(x1, s2.index.astype(object).values)
        x2 = lines[1].get_xdata()
        tm.assert_numpy_array_equal(x2, s1.index.astype(object).values)

    def test_mixed_freq_regular_first_df(self):
        # GH 9852
        s1 = Series(
            np.arange(20, dtype=np.float64),
            index=date_range("2020-01-01", periods=20, freq="B"),
        ).to_frame()
        s2 = s1.iloc[[0, 5, 10, 11, 12, 13, 14, 15], :]
        _, ax = mpl.pyplot.subplots()
        s1.plot(ax=ax)
        ax2 = s2.plot(style="g", ax=ax)
        lines = ax2.get_lines()
        msg = r"PeriodDtype\[B\] is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            idx1 = PeriodIndex(lines[0].get_xdata())
            idx2 = PeriodIndex(lines[1].get_xdata())
            assert idx1.equals(s1.index.to_period("B"))
            assert idx2.equals(s2.index.to_period("B"))
            left, right = ax2.get_xlim()
            pidx = s1.index.to_period()
        assert left <= pidx[0].ordinal
        assert right >= pidx[-1].ordinal

    def test_mixed_freq_irregular_first_df(self):
        # GH 9852
        s1 = Series(
            np.arange(20, dtype=np.float64), index=date_range("2020-01-01", periods=20)
        ).to_frame()
        s2 = s1.iloc[[0, 5, 10, 11, 12, 13, 14, 15], :]
        _, ax = mpl.pyplot.subplots()
        s2.plot(style="g", ax=ax)
        s1.plot(ax=ax)
        assert not hasattr(ax, "freq")
        lines = ax.get_lines()
        x1 = lines[0].get_xdata()
        tm.assert_numpy_array_equal(x1, s2.index.astype(object).values)
        x2 = lines[1].get_xdata()
        tm.assert_numpy_array_equal(x2, s1.index.astype(object).values)

    def test_mixed_freq_hf_first(self):
        idxh = date_range("1/1/1999", periods=365, freq="D")
        idxl = date_range("1/1/1999", periods=12, freq="ME")
        high = Series(np.random.default_rng(2).standard_normal(len(idxh)), idxh)
        low = Series(np.random.default_rng(2).standard_normal(len(idxl)), idxl)
        _, ax = mpl.pyplot.subplots()
        high.plot(ax=ax)
        low.plot(ax=ax)
        for line in ax.get_lines():
            assert PeriodIndex(data=line.get_xdata()).freq == "D"

    def test_mixed_freq_alignment(self):
        ts_ind = date_range("2012-01-01 13:00", "2012-01-02", freq="h")
        ts_data = np.random.default_rng(2).standard_normal(12)

        ts = Series(ts_data, index=ts_ind)
        ts2 = ts.asfreq("min").interpolate()

        _, ax = mpl.pyplot.subplots()
        ax = ts.plot(ax=ax)
        ts2.plot(style="r", ax=ax)

        assert ax.lines[0].get_xdata()[0] == ax.lines[1].get_xdata()[0]

    def test_mixed_freq_lf_first(self):
        idxh = date_range("1/1/1999", periods=365, freq="D")
        idxl = date_range("1/1/1999", periods=12, freq="ME")
        high = Series(np.random.default_rng(2).standard_normal(len(idxh)), idxh)
        low = Series(np.random.default_rng(2).standard_normal(len(idxl)), idxl)
        _, ax = mpl.pyplot.subplots()
        low.plot(legend=True, ax=ax)
        high.plot(legend=True, ax=ax)
        for line in ax.get_lines():
            assert PeriodIndex(data=line.get_xdata()).freq == "D"
        leg = ax.get_legend()
        assert len(leg.texts) == 2
        mpl.pyplot.close(ax.get_figure())

    def test_mixed_freq_lf_first_hourly(self):
        idxh = date_range("1/1/1999", periods=240, freq="min")
        idxl = date_range("1/1/1999", periods=4, freq="h")
        high = Series(np.random.default_rng(2).standard_normal(len(idxh)), idxh)
        low = Series(np.random.default_rng(2).standard_normal(len(idxl)), idxl)
        _, ax = mpl.pyplot.subplots()
        low.plot(ax=ax)
        high.plot(ax=ax)
        for line in ax.get_lines():
            assert PeriodIndex(data=line.get_xdata()).freq == "min"

    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_mixed_freq_irreg_period(self):
        ts = Series(
            np.arange(30, dtype=np.float64), index=date_range("2020-01-01", periods=30)
        )
        irreg = ts.iloc[[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 16, 17, 18, 29]]
        msg = r"PeriodDtype\[B\] is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rng = period_range("1/3/2000", periods=30, freq="B")
        ps = Series(np.random.default_rng(2).standard_normal(len(rng)), rng)
        _, ax = mpl.pyplot.subplots()
        irreg.plot(ax=ax)
        ps.plot(ax=ax)

    def test_mixed_freq_shared_ax(self):
        # GH13341, using sharex=True
        idx1 = date_range("2015-01-01", periods=3, freq="ME")
        idx2 = idx1[:1].union(idx1[2:])
        s1 = Series(range(len(idx1)), idx1)
        s2 = Series(range(len(idx2)), idx2)

        _, (ax1, ax2) = mpl.pyplot.subplots(nrows=2, sharex=True)
        s1.plot(ax=ax1)
        s2.plot(ax=ax2)

        assert ax1.freq == "M"
        assert ax2.freq == "M"
        assert ax1.lines[0].get_xydata()[0, 0] == ax2.lines[0].get_xydata()[0, 0]

    def test_mixed_freq_shared_ax_twin_x(self):
        # GH13341, using sharex=True
        idx1 = date_range("2015-01-01", periods=3, freq="ME")
        idx2 = idx1[:1].union(idx1[2:])
        s1 = Series(range(len(idx1)), idx1)
        s2 = Series(range(len(idx2)), idx2)
        # using twinx
        _, ax1 = mpl.pyplot.subplots()
        ax2 = ax1.twinx()
        s1.plot(ax=ax1)
        s2.plot(ax=ax2)

        assert ax1.lines[0].get_xydata()[0, 0] == ax2.lines[0].get_xydata()[0, 0]

    @pytest.mark.xfail(reason="TODO (GH14330, GH14322)")
    def test_mixed_freq_shared_ax_twin_x_irregular_first(self):
        # GH13341, using sharex=True
        idx1 = date_range("2015-01-01", periods=3, freq="M")
        idx2 = idx1[:1].union(idx1[2:])
        s1 = Series(range(len(idx1)), idx1)
        s2 = Series(range(len(idx2)), idx2)
        _, ax1 = mpl.pyplot.subplots()
        ax2 = ax1.twinx()
        s2.plot(ax=ax1)
        s1.plot(ax=ax2)
        assert ax1.lines[0].get_xydata()[0, 0] == ax2.lines[0].get_xydata()[0, 0]

    def test_nat_handling(self):
        _, ax = mpl.pyplot.subplots()

        dti = DatetimeIndex(["2015-01-01", NaT, "2015-01-03"])
        s = Series(range(len(dti)), dti)
        s.plot(ax=ax)
        xdata = ax.get_lines()[0].get_xdata()
        # plot x data is bounded by index values
        assert s.index.min() <= Series(xdata).min()
        assert Series(xdata).max() <= s.index.max()

    def test_to_weekly_resampling_disallow_how_kwd(self):
        idxh = date_range("1/1/1999", periods=52, freq="W")
        idxl = date_range("1/1/1999", periods=12, freq="ME")
        high = Series(np.random.default_rng(2).standard_normal(len(idxh)), idxh)
        low = Series(np.random.default_rng(2).standard_normal(len(idxl)), idxl)
        _, ax = mpl.pyplot.subplots()
        high.plot(ax=ax)

        msg = (
            "'how' is not a valid keyword for plotting functions. If plotting "
            "multiple objects on shared axes, resample manually first."
        )
        with pytest.raises(ValueError, match=msg):
            low.plot(ax=ax, how="foo")

    def test_to_weekly_resampling(self):
        idxh = date_range("1/1/1999", periods=52, freq="W")
        idxl = date_range("1/1/1999", periods=12, freq="ME")
        high = Series(np.random.default_rng(2).standard_normal(len(idxh)), idxh)
        low = Series(np.random.default_rng(2).standard_normal(len(idxl)), idxl)
        _, ax = mpl.pyplot.subplots()
        high.plot(ax=ax)
        low.plot(ax=ax)
        for line in ax.get_lines():
            assert PeriodIndex(data=line.get_xdata()).freq == idxh.freq

    def test_from_weekly_resampling(self):
        idxh = date_range("1/1/1999", periods=52, freq="W")
        idxl = date_range("1/1/1999", periods=12, freq="ME")
        high = Series(np.random.default_rng(2).standard_normal(len(idxh)), idxh)
        low = Series(np.random.default_rng(2).standard_normal(len(idxl)), idxl)
        _, ax = mpl.pyplot.subplots()
        low.plot(ax=ax)
        high.plot(ax=ax)

        expected_h = idxh.to_period().asi8.astype(np.float64)
        expected_l = np.array(
            [1514, 1519, 1523, 1527, 1531, 1536, 1540, 1544, 1549, 1553, 1558, 1562],
            dtype=np.float64,
        )
        for line in ax.get_lines():
            assert PeriodIndex(data=line.get_xdata()).freq == idxh.freq
            xdata = line.get_xdata(orig=False)
            if len(xdata) == 12:  # idxl lines
                tm.assert_numpy_array_equal(xdata, expected_l)
            else:
                tm.assert_numpy_array_equal(xdata, expected_h)

    @pytest.mark.parametrize("kind1, kind2", [("line", "area"), ("area", "line")])
    def test_from_resampling_area_line_mixed(self, kind1, kind2):
        idxh = date_range("1/1/1999", periods=52, freq="W")
        idxl = date_range("1/1/1999", periods=12, freq="ME")
        high = DataFrame(
            np.random.default_rng(2).random((len(idxh), 3)),
            index=idxh,
            columns=[0, 1, 2],
        )
        low = DataFrame(
            np.random.default_rng(2).random((len(idxl), 3)),
            index=idxl,
            columns=[0, 1, 2],
        )

        _, ax = mpl.pyplot.subplots()
        low.plot(kind=kind1, stacked=True, ax=ax)
        high.plot(kind=kind2, stacked=True, ax=ax)

        # check low dataframe result
        expected_x = np.array(
            [
                1514,
                1519,
                1523,
                1527,
                1531,
                1536,
                1540,
                1544,
                1549,
                1553,
                1558,
                1562,
            ],
            dtype=np.float64,
        )
        expected_y = np.zeros(len(expected_x), dtype=np.float64)
        for i in range(3):
            line = ax.lines[i]
            assert PeriodIndex(line.get_xdata()).freq == idxh.freq
            tm.assert_numpy_array_equal(line.get_xdata(orig=False), expected_x)
            # check stacked values are correct
            expected_y += low[i].values
            tm.assert_numpy_array_equal(line.get_ydata(orig=False), expected_y)

        # check high dataframe result
        expected_x = idxh.to_period().asi8.astype(np.float64)
        expected_y = np.zeros(len(expected_x), dtype=np.float64)
        for i in range(3):
            line = ax.lines[3 + i]
            assert PeriodIndex(data=line.get_xdata()).freq == idxh.freq
            tm.assert_numpy_array_equal(line.get_xdata(orig=False), expected_x)
            expected_y += high[i].values
            tm.assert_numpy_array_equal(line.get_ydata(orig=False), expected_y)

    @pytest.mark.parametrize("kind1, kind2", [("line", "area"), ("area", "line")])
    def test_from_resampling_area_line_mixed_high_to_low(self, kind1, kind2):
        idxh = date_range("1/1/1999", periods=52, freq="W")
        idxl = date_range("1/1/1999", periods=12, freq="ME")
        high = DataFrame(
            np.random.default_rng(2).random((len(idxh), 3)),
            index=idxh,
            columns=[0, 1, 2],
        )
        low = DataFrame(
            np.random.default_rng(2).random((len(idxl), 3)),
            index=idxl,
            columns=[0, 1, 2],
        )
        _, ax = mpl.pyplot.subplots()
        high.plot(kind=kind1, stacked=True, ax=ax)
        low.plot(kind=kind2, stacked=True, ax=ax)

        # check high dataframe result
        expected_x = idxh.to_period().asi8.astype(np.float64)
        expected_y = np.zeros(len(expected_x), dtype=np.float64)
        for i in range(3):
            line = ax.lines[i]
            assert PeriodIndex(data=line.get_xdata()).freq == idxh.freq
            tm.assert_numpy_array_equal(line.get_xdata(orig=False), expected_x)
            expected_y += high[i].values
            tm.assert_numpy_array_equal(line.get_ydata(orig=False), expected_y)

        # check low dataframe result
        expected_x = np.array(
            [
                1514,
                1519,
                1523,
                1527,
                1531,
                1536,
                1540,
                1544,
                1549,
                1553,
                1558,
                1562,
            ],
            dtype=np.float64,
        )
        expected_y = np.zeros(len(expected_x), dtype=np.float64)
        for i in range(3):
            lines = ax.lines[3 + i]
            assert PeriodIndex(data=lines.get_xdata()).freq == idxh.freq
            tm.assert_numpy_array_equal(lines.get_xdata(orig=False), expected_x)
            expected_y += low[i].values
            tm.assert_numpy_array_equal(lines.get_ydata(orig=False), expected_y)

    def test_mixed_freq_second_millisecond(self):
        # GH 7772, GH 7760
        idxh = date_range("2014-07-01 09:00", freq="s", periods=50)
        idxl = date_range("2014-07-01 09:00", freq="100ms", periods=500)
        high = Series(np.random.default_rng(2).standard_normal(len(idxh)), idxh)
        low = Series(np.random.default_rng(2).standard_normal(len(idxl)), idxl)
        # high to low
        _, ax = mpl.pyplot.subplots()
        high.plot(ax=ax)
        low.plot(ax=ax)
        assert len(ax.get_lines()) == 2
        for line in ax.get_lines():
            assert PeriodIndex(data=line.get_xdata()).freq == "ms"

    def test_mixed_freq_second_millisecond_low_to_high(self):
        # GH 7772, GH 7760
        idxh = date_range("2014-07-01 09:00", freq="s", periods=50)
        idxl = date_range("2014-07-01 09:00", freq="100ms", periods=500)
        high = Series(np.random.default_rng(2).standard_normal(len(idxh)), idxh)
        low = Series(np.random.default_rng(2).standard_normal(len(idxl)), idxl)
        # low to high
        _, ax = mpl.pyplot.subplots()
        low.plot(ax=ax)
        high.plot(ax=ax)
        assert len(ax.get_lines()) == 2
        for line in ax.get_lines():
            assert PeriodIndex(data=line.get_xdata()).freq == "ms"

    def test_irreg_dtypes(self):
        # date
        idx = [date(2000, 1, 1), date(2000, 1, 5), date(2000, 1, 20)]
        df = DataFrame(
            np.random.default_rng(2).standard_normal((len(idx), 3)),
            Index(idx, dtype=object),
        )
        _check_plot_works(df.plot)

    def test_irreg_dtypes_dt64(self):
        # np.datetime64
        idx = date_range("1/1/2000", periods=10)
        idx = idx[[0, 2, 5, 9]].astype(object)
        df = DataFrame(np.random.default_rng(2).standard_normal((len(idx), 3)), idx)
        _, ax = mpl.pyplot.subplots()
        _check_plot_works(df.plot, ax=ax)

    def test_time(self):
        t = datetime(1, 1, 1, 3, 30, 0)
        deltas = np.random.default_rng(2).integers(1, 20, 3).cumsum()
        ts = np.array([(t + timedelta(minutes=int(x))).time() for x in deltas])
        df = DataFrame(
            {
                "a": np.random.default_rng(2).standard_normal(len(ts)),
                "b": np.random.default_rng(2).standard_normal(len(ts)),
            },
            index=ts,
        )
        _, ax = mpl.pyplot.subplots()
        df.plot(ax=ax)

        # verify tick labels
        ticks = ax.get_xticks()
        labels = ax.get_xticklabels()
        for _tick, _label in zip(ticks, labels):
            m, s = divmod(int(_tick), 60)
            h, m = divmod(m, 60)
            rs = _label.get_text()
            if len(rs) > 0:
                if s != 0:
                    xp = time(h, m, s).strftime("%H:%M:%S")
                else:
                    xp = time(h, m, s).strftime("%H:%M")
                assert xp == rs

    def test_time_change_xlim(self):
        t = datetime(1, 1, 1, 3, 30, 0)
        deltas = np.random.default_rng(2).integers(1, 20, 3).cumsum()
        ts = np.array([(t + timedelta(minutes=int(x))).time() for x in deltas])
        df = DataFrame(
            {
                "a": np.random.default_rng(2).standard_normal(len(ts)),
                "b": np.random.default_rng(2).standard_normal(len(ts)),
            },
            index=ts,
        )
        _, ax = mpl.pyplot.subplots()
        df.plot(ax=ax)

        # verify tick labels
        ticks = ax.get_xticks()
        labels = ax.get_xticklabels()
        for _tick, _label in zip(ticks, labels):
            m, s = divmod(int(_tick), 60)
            h, m = divmod(m, 60)
            rs = _label.get_text()
            if len(rs) > 0:
                if s != 0:
                    xp = time(h, m, s).strftime("%H:%M:%S")
                else:
                    xp = time(h, m, s).strftime("%H:%M")
                assert xp == rs

        # change xlim
        ax.set_xlim("1:30", "5:00")

        # check tick labels again
        ticks = ax.get_xticks()
        labels = ax.get_xticklabels()
        for _tick, _label in zip(ticks, labels):
            m, s = divmod(int(_tick), 60)
            h, m = divmod(m, 60)
            rs = _label.get_text()
            if len(rs) > 0:
                if s != 0:
                    xp = time(h, m, s).strftime("%H:%M:%S")
                else:
                    xp = time(h, m, s).strftime("%H:%M")
                assert xp == rs

    def test_time_musec(self):
        t = datetime(1, 1, 1, 3, 30, 0)
        deltas = np.random.default_rng(2).integers(1, 20, 3).cumsum()
        ts = np.array([(t + timedelta(microseconds=int(x))).time() for x in deltas])
        df = DataFrame(
            {
                "a": np.random.default_rng(2).standard_normal(len(ts)),
                "b": np.random.default_rng(2).standard_normal(len(ts)),
            },
            index=ts,
        )
        _, ax = mpl.pyplot.subplots()
        ax = df.plot(ax=ax)

        # verify tick labels
        ticks = ax.get_xticks()
        labels = ax.get_xticklabels()
        for _tick, _label in zip(ticks, labels):
            m, s = divmod(int(_tick), 60)

            us = round((_tick - int(_tick)) * 1e6)

            h, m = divmod(m, 60)
            rs = _label.get_text()
            if len(rs) > 0:
                if (us % 1000) != 0:
                    xp = time(h, m, s, us).strftime("%H:%M:%S.%f")
                elif (us // 1000) != 0:
                    xp = time(h, m, s, us).strftime("%H:%M:%S.%f")[:-3]
                elif s != 0:
                    xp = time(h, m, s, us).strftime("%H:%M:%S")
                else:
                    xp = time(h, m, s, us).strftime("%H:%M")
                assert xp == rs

    def test_secondary_upsample(self):
        idxh = date_range("1/1/1999", periods=365, freq="D")
        idxl = date_range("1/1/1999", periods=12, freq="ME")
        high = Series(np.random.default_rng(2).standard_normal(len(idxh)), idxh)
        low = Series(np.random.default_rng(2).standard_normal(len(idxl)), idxl)
        _, ax = mpl.pyplot.subplots()
        low.plot(ax=ax)
        ax = high.plot(secondary_y=True, ax=ax)
        for line in ax.get_lines():
            assert PeriodIndex(line.get_xdata()).freq == "D"
        assert hasattr(ax, "left_ax")
        assert not hasattr(ax, "right_ax")
        for line in ax.left_ax.get_lines():
            assert PeriodIndex(line.get_xdata()).freq == "D"

    def test_secondary_legend(self):
        fig = mpl.pyplot.figure()
        ax = fig.add_subplot(211)

        # ts
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        df.plot(secondary_y=["A", "B"], ax=ax)
        leg = ax.get_legend()
        assert len(leg.get_lines()) == 4
        assert leg.get_texts()[0].get_text() == "A (right)"
        assert leg.get_texts()[1].get_text() == "B (right)"
        assert leg.get_texts()[2].get_text() == "C"
        assert leg.get_texts()[3].get_text() == "D"
        assert ax.right_ax.get_legend() is None
        colors = set()
        for line in leg.get_lines():
            colors.add(line.get_color())

        # TODO: color cycle problems
        assert len(colors) == 4
        mpl.pyplot.close(fig)

    def test_secondary_legend_right(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        fig = mpl.pyplot.figure()
        ax = fig.add_subplot(211)
        df.plot(secondary_y=["A", "C"], mark_right=False, ax=ax)
        leg = ax.get_legend()
        assert len(leg.get_lines()) == 4
        assert leg.get_texts()[0].get_text() == "A"
        assert leg.get_texts()[1].get_text() == "B"
        assert leg.get_texts()[2].get_text() == "C"
        assert leg.get_texts()[3].get_text() == "D"
        mpl.pyplot.close(fig)

    def test_secondary_legend_bar(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        fig, ax = mpl.pyplot.subplots()
        df.plot(kind="bar", secondary_y=["A"], ax=ax)
        leg = ax.get_legend()
        assert leg.get_texts()[0].get_text() == "A (right)"
        assert leg.get_texts()[1].get_text() == "B"
        mpl.pyplot.close(fig)

    def test_secondary_legend_bar_right(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        fig, ax = mpl.pyplot.subplots()
        df.plot(kind="bar", secondary_y=["A"], mark_right=False, ax=ax)
        leg = ax.get_legend()
        assert leg.get_texts()[0].get_text() == "A"
        assert leg.get_texts()[1].get_text() == "B"
        mpl.pyplot.close(fig)

    def test_secondary_legend_multi_col(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        fig = mpl.pyplot.figure()
        ax = fig.add_subplot(211)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        ax = df.plot(secondary_y=["C", "D"], ax=ax)
        leg = ax.get_legend()
        assert len(leg.get_lines()) == 4
        assert ax.right_ax.get_legend() is None
        colors = set()
        for line in leg.get_lines():
            colors.add(line.get_color())

        # TODO: color cycle problems
        assert len(colors) == 4
        mpl.pyplot.close(fig)

    def test_secondary_legend_nonts(self):
        # non-ts
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=Index([f"i-{i}" for i in range(30)], dtype=object),
        )
        fig = mpl.pyplot.figure()
        ax = fig.add_subplot(211)
        ax = df.plot(secondary_y=["A", "B"], ax=ax)
        leg = ax.get_legend()
        assert len(leg.get_lines()) == 4
        assert ax.right_ax.get_legend() is None
        colors = set()
        for line in leg.get_lines():
            colors.add(line.get_color())

        # TODO: color cycle problems
        assert len(colors) == 4
        mpl.pyplot.close()

    def test_secondary_legend_nonts_multi_col(self):
        # non-ts
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=Index([f"i-{i}" for i in range(30)], dtype=object),
        )
        fig = mpl.pyplot.figure()
        ax = fig.add_subplot(211)
        ax = df.plot(secondary_y=["C", "D"], ax=ax)
        leg = ax.get_legend()
        assert len(leg.get_lines()) == 4
        assert ax.right_ax.get_legend() is None
        colors = set()
        for line in leg.get_lines():
            colors.add(line.get_color())

        # TODO: color cycle problems
        assert len(colors) == 4

    @pytest.mark.xfail(reason="Api changed in 3.6.0")
    def test_format_date_axis(self):
        rng = date_range("1/1/2012", periods=12, freq="ME")
        df = DataFrame(np.random.default_rng(2).standard_normal((len(rng), 3)), rng)
        _, ax = mpl.pyplot.subplots()
        ax = df.plot(ax=ax)
        xaxis = ax.get_xaxis()
        for line in xaxis.get_ticklabels():
            if len(line.get_text()) > 0:
                assert line.get_rotation() == 30

    def test_ax_plot(self):
        x = date_range(start="2012-01-02", periods=10, freq="D")
        y = list(range(len(x)))
        _, ax = mpl.pyplot.subplots()
        lines = ax.plot(x, y, label="Y")
        tm.assert_index_equal(DatetimeIndex(lines[0].get_xdata()), x)

    def test_mpl_nopandas(self):
        dates = [date(2008, 12, 31), date(2009, 1, 31)]
        values1 = np.arange(10.0, 11.0, 0.5)
        values2 = np.arange(11.0, 12.0, 0.5)

        _, ax = mpl.pyplot.subplots()
        (
            line1,
            line2,
        ) = ax.plot(
            [x.toordinal() for x in dates],
            values1,
            "-",
            [x.toordinal() for x in dates],
            values2,
            "-",
            linewidth=4,
        )

        exp = np.array([x.toordinal() for x in dates], dtype=np.float64)
        tm.assert_numpy_array_equal(line1.get_xydata()[:, 0], exp)
        exp = np.array([x.toordinal() for x in dates], dtype=np.float64)
        tm.assert_numpy_array_equal(line2.get_xydata()[:, 0], exp)

    def test_irregular_ts_shared_ax_xlim(self):
        # GH 2960
        from pandas.plotting._matplotlib.converter import DatetimeConverter

        ts = Series(
            np.arange(20, dtype=np.float64), index=date_range("2020-01-01", periods=20)
        )
        ts_irregular = ts.iloc[[1, 4, 5, 6, 8, 9, 10, 12, 13, 14, 15, 17, 18]]

        # plot the left section of the irregular series, then the right section
        _, ax = mpl.pyplot.subplots()
        ts_irregular[:5].plot(ax=ax)
        ts_irregular[5:].plot(ax=ax)

        # check that axis limits are correct
        left, right = ax.get_xlim()
        assert left <= DatetimeConverter.convert(ts_irregular.index.min(), "", ax)
        assert right >= DatetimeConverter.convert(ts_irregular.index.max(), "", ax)

    def test_secondary_y_non_ts_xlim(self):
        # GH 3490 - non-timeseries with secondary y
        index_1 = [1, 2, 3, 4]
        index_2 = [5, 6, 7, 8]
        s1 = Series(1, index=index_1)
        s2 = Series(2, index=index_2)

        _, ax = mpl.pyplot.subplots()
        s1.plot(ax=ax)
        left_before, right_before = ax.get_xlim()
        s2.plot(secondary_y=True, ax=ax)
        left_after, right_after = ax.get_xlim()

        assert left_before >= left_after
        assert right_before < right_after

    def test_secondary_y_regular_ts_xlim(self):
        # GH 3490 - regular-timeseries with secondary y
        index_1 = date_range(start="2000-01-01", periods=4, freq="D")
        index_2 = date_range(start="2000-01-05", periods=4, freq="D")
        s1 = Series(1, index=index_1)
        s2 = Series(2, index=index_2)

        _, ax = mpl.pyplot.subplots()
        s1.plot(ax=ax)
        left_before, right_before = ax.get_xlim()
        s2.plot(secondary_y=True, ax=ax)
        left_after, right_after = ax.get_xlim()

        assert left_before >= left_after
        assert right_before < right_after

    def test_secondary_y_mixed_freq_ts_xlim(self):
        # GH 3490 - mixed frequency timeseries with secondary y
        rng = date_range("2000-01-01", periods=10000, freq="min")
        ts = Series(1, index=rng)

        _, ax = mpl.pyplot.subplots()
        ts.plot(ax=ax)
        left_before, right_before = ax.get_xlim()
        ts.resample("D").mean().plot(secondary_y=True, ax=ax)
        left_after, right_after = ax.get_xlim()

        # a downsample should not have changed either limit
        assert left_before == left_after
        assert right_before == right_after

    def test_secondary_y_irregular_ts_xlim(self):
        # GH 3490 - irregular-timeseries with secondary y
        from pandas.plotting._matplotlib.converter import DatetimeConverter

        ts = Series(
            np.arange(20, dtype=np.float64), index=date_range("2020-01-01", periods=20)
        )
        ts_irregular = ts.iloc[[1, 4, 5, 6, 8, 9, 10, 12, 13, 14, 15, 17, 18]]

        _, ax = mpl.pyplot.subplots()
        ts_irregular[:5].plot(ax=ax)
        # plot higher-x values on secondary axis
        ts_irregular[5:].plot(secondary_y=True, ax=ax)
        # ensure secondary limits aren't overwritten by plot on primary
        ts_irregular[:5].plot(ax=ax)

        left, right = ax.get_xlim()
        assert left <= DatetimeConverter.convert(ts_irregular.index.min(), "", ax)
        assert right >= DatetimeConverter.convert(ts_irregular.index.max(), "", ax)

    def test_plot_outofbounds_datetime(self):
        # 2579 - checking this does not raise
        values = [date(1677, 1, 1), date(1677, 1, 2)]
        _, ax = mpl.pyplot.subplots()
        ax.plot(values)

        values = [datetime(1677, 1, 1, 12), datetime(1677, 1, 2, 12)]
        ax.plot(values)

    def test_format_timedelta_ticks_narrow(self):
        expected_labels = [f"00:00:00.0000000{i:0>2d}" for i in np.arange(10)]

        rng = timedelta_range("0", periods=10, freq="ns")
        df = DataFrame(np.random.default_rng(2).standard_normal((len(rng), 3)), rng)
        _, ax = mpl.pyplot.subplots()
        df.plot(fontsize=2, ax=ax)
        mpl.pyplot.draw()
        labels = ax.get_xticklabels()

        result_labels = [x.get_text() for x in labels]
        assert len(result_labels) == len(expected_labels)
        assert result_labels == expected_labels

    def test_format_timedelta_ticks_wide(self):
        expected_labels = [
            "00:00:00",
            "1 days 03:46:40",
            "2 days 07:33:20",
            "3 days 11:20:00",
            "4 days 15:06:40",
            "5 days 18:53:20",
            "6 days 22:40:00",
            "8 days 02:26:40",
            "9 days 06:13:20",
        ]

        rng = timedelta_range("0", periods=10, freq="1 d")
        df = DataFrame(np.random.default_rng(2).standard_normal((len(rng), 3)), rng)
        _, ax = mpl.pyplot.subplots()
        ax = df.plot(fontsize=2, ax=ax)
        mpl.pyplot.draw()
        labels = ax.get_xticklabels()

        result_labels = [x.get_text() for x in labels]
        assert len(result_labels) == len(expected_labels)
        assert result_labels == expected_labels

    def test_timedelta_plot(self):
        # test issue #8711
        s = Series(range(5), timedelta_range("1day", periods=5))
        _, ax = mpl.pyplot.subplots()
        _check_plot_works(s.plot, ax=ax)

    def test_timedelta_long_period(self):
        # test long period
        index = timedelta_range("1 day 2 hr 30 min 10 s", periods=10, freq="1 d")
        s = Series(np.random.default_rng(2).standard_normal(len(index)), index)
        _, ax = mpl.pyplot.subplots()
        _check_plot_works(s.plot, ax=ax)

    def test_timedelta_short_period(self):
        # test short period
        index = timedelta_range("1 day 2 hr 30 min 10 s", periods=10, freq="1 ns")
        s = Series(np.random.default_rng(2).standard_normal(len(index)), index)
        _, ax = mpl.pyplot.subplots()
        _check_plot_works(s.plot, ax=ax)

    def test_hist(self):
        # https://github.com/matplotlib/matplotlib/issues/8459
        rng = date_range("1/1/2011", periods=10, freq="h")
        x = rng
        w1 = np.arange(0, 1, 0.1)
        w2 = np.arange(0, 1, 0.1)[::-1]
        _, ax = mpl.pyplot.subplots()
        ax.hist([x, x], weights=[w1, w2])

    def test_overlapping_datetime(self):
        # GB 6608
        s1 = Series(
            [1, 2, 3],
            index=[
                datetime(1995, 12, 31),
                datetime(2000, 12, 31),
                datetime(2005, 12, 31),
            ],
        )
        s2 = Series(
            [1, 2, 3],
            index=[
                datetime(1997, 12, 31),
                datetime(2003, 12, 31),
                datetime(2008, 12, 31),
            ],
        )

        # plot first series, then add the second series to those axes,
        # then try adding the first series again
        _, ax = mpl.pyplot.subplots()
        s1.plot(ax=ax)
        s2.plot(ax=ax)
        s1.plot(ax=ax)

    @pytest.mark.xfail(reason="GH9053 matplotlib does not use ax.xaxis.converter")
    def test_add_matplotlib_datetime64(self):
        # GH9053 - ensure that a plot with PeriodConverter still understands
        # datetime64 data. This still fails because matplotlib overrides the
        # ax.xaxis.converter with a DatetimeConverter
        s = Series(
            np.random.default_rng(2).standard_normal(10),
            index=date_range("1970-01-02", periods=10),
        )
        ax = s.plot()
        with tm.assert_produces_warning(DeprecationWarning):
            # multi-dimensional indexing
            ax.plot(s.index, s.values, color="g")
        l1, l2 = ax.lines
        tm.assert_numpy_array_equal(l1.get_xydata(), l2.get_xydata())

    def test_matplotlib_scatter_datetime64(self):
        # https://github.com/matplotlib/matplotlib/issues/11391
        df = DataFrame(np.random.default_rng(2).random((10, 2)), columns=["x", "y"])
        df["time"] = date_range("2018-01-01", periods=10, freq="D")
        _, ax = mpl.pyplot.subplots()
        ax.scatter(x="time", y="y", data=df)
        mpl.pyplot.draw()
        label = ax.get_xticklabels()[0]
        expected = "2018-01-01"
        assert label.get_text() == expected

    def test_check_xticks_rot(self):
        # https://github.com/pandas-dev/pandas/issues/29460
        # regular time series
        x = to_datetime(["2020-05-01", "2020-05-02", "2020-05-03"])
        df = DataFrame({"x": x, "y": [1, 2, 3]})
        axes = df.plot(x="x", y="y")
        _check_ticks_props(axes, xrot=0)

    def test_check_xticks_rot_irregular(self):
        # irregular time series
        x = to_datetime(["2020-05-01", "2020-05-02", "2020-05-04"])
        df = DataFrame({"x": x, "y": [1, 2, 3]})
        axes = df.plot(x="x", y="y")
        _check_ticks_props(axes, xrot=30)

    def test_check_xticks_rot_use_idx(self):
        # irregular time series
        x = to_datetime(["2020-05-01", "2020-05-02", "2020-05-04"])
        df = DataFrame({"x": x, "y": [1, 2, 3]})
        # use timeseries index or not
        axes = df.set_index("x").plot(y="y", use_index=True)
        _check_ticks_props(axes, xrot=30)
        axes = df.set_index("x").plot(y="y", use_index=False)
        _check_ticks_props(axes, xrot=0)

    def test_check_xticks_rot_sharex(self):
        # irregular time series
        x = to_datetime(["2020-05-01", "2020-05-02", "2020-05-04"])
        df = DataFrame({"x": x, "y": [1, 2, 3]})
        # separate subplots
        axes = df.plot(x="x", y="y", subplots=True, sharex=True)
        _check_ticks_props(axes, xrot=30)
        axes = df.plot(x="x", y="y", subplots=True, sharex=False)
        _check_ticks_props(axes, xrot=0)


def _check_plot_works(f, freq=None, series=None, *args, **kwargs):
    import matplotlib.pyplot as plt

    fig = plt.gcf()

    try:
        plt.clf()
        ax = fig.add_subplot(211)
        orig_ax = kwargs.pop("ax", plt.gca())
        orig_axfreq = getattr(orig_ax, "freq", None)

        ret = f(*args, **kwargs)
        assert ret is not None  # do something more intelligent

        ax = kwargs.pop("ax", plt.gca())
        if series is not None:
            dfreq = series.index.freq
            if isinstance(dfreq, BaseOffset):
                dfreq = dfreq.rule_code
            if orig_axfreq is None:
                assert ax.freq == dfreq

        if freq is not None:
            ax_freq = to_offset(ax.freq, is_period=True)
        if freq is not None and orig_axfreq is None:
            assert ax_freq == freq

        ax = fig.add_subplot(212)
        kwargs["ax"] = ax
        ret = f(*args, **kwargs)
        assert ret is not None  # TODO: do something more intelligent

        # GH18439, GH#24088, statsmodels#4772
        with tm.ensure_clean(return_filelike=True) as path:
            pickle.dump(fig, path)
    finally:
        plt.close(fig)
