from datetime import (
    date,
    datetime,
)
import subprocess
import sys

import numpy as np
import pytest

import pandas._config.config as cf

from pandas._libs.tslibs import to_offset

from pandas import (
    Index,
    Period,
    PeriodIndex,
    Series,
    Timestamp,
    arrays,
    date_range,
)
import pandas._testing as tm

from pandas.plotting import (
    deregister_matplotlib_converters,
    register_matplotlib_converters,
)
from pandas.tseries.offsets import (
    Day,
    Micro,
    Milli,
    Second,
)

try:
    from pandas.plotting._matplotlib import converter
except ImportError:
    # try / except, rather than skip, to avoid internal refactoring
    # causing an improper skip
    pass

pytest.importorskip("matplotlib.pyplot")
dates = pytest.importorskip("matplotlib.dates")


@pytest.mark.single_cpu
def test_registry_mpl_resets():
    # Check that Matplotlib converters are properly reset (see issue #27481)
    code = (
        "import matplotlib.units as units; "
        "import matplotlib.dates as mdates; "
        "n_conv = len(units.registry); "
        "import pandas as pd; "
        "pd.plotting.register_matplotlib_converters(); "
        "pd.plotting.deregister_matplotlib_converters(); "
        "assert len(units.registry) == n_conv"
    )
    call = [sys.executable, "-c", code]
    subprocess.check_output(call)


def test_timtetonum_accepts_unicode():
    assert converter.time2num("00:01") == converter.time2num("00:01")


class TestRegistration:
    @pytest.mark.single_cpu
    def test_dont_register_by_default(self):
        # Run in subprocess to ensure a clean state
        code = (
            "import matplotlib.units; "
            "import pandas as pd; "
            "units = dict(matplotlib.units.registry); "
            "assert pd.Timestamp not in units"
        )
        call = [sys.executable, "-c", code]
        assert subprocess.check_call(call) == 0

    def test_registering_no_warning(self):
        plt = pytest.importorskip("matplotlib.pyplot")
        s = Series(range(12), index=date_range("2017", periods=12))
        _, ax = plt.subplots()

        # Set to the "warn" state, in case this isn't the first test run
        register_matplotlib_converters()
        ax.plot(s.index, s.values)
        plt.close()

    def test_pandas_plots_register(self):
        plt = pytest.importorskip("matplotlib.pyplot")
        s = Series(range(12), index=date_range("2017", periods=12))
        # Set to the "warn" state, in case this isn't the first test run
        with tm.assert_produces_warning(None) as w:
            s.plot()

        try:
            assert len(w) == 0
        finally:
            plt.close()

    def test_matplotlib_formatters(self):
        units = pytest.importorskip("matplotlib.units")

        # Can't make any assertion about the start state.
        # We we check that toggling converters off removes it, and toggling it
        # on restores it.

        with cf.option_context("plotting.matplotlib.register_converters", True):
            with cf.option_context("plotting.matplotlib.register_converters", False):
                assert Timestamp not in units.registry
            assert Timestamp in units.registry

    def test_option_no_warning(self):
        pytest.importorskip("matplotlib.pyplot")
        ctx = cf.option_context("plotting.matplotlib.register_converters", False)
        plt = pytest.importorskip("matplotlib.pyplot")
        s = Series(range(12), index=date_range("2017", periods=12))
        _, ax = plt.subplots()

        # Test without registering first, no warning
        with ctx:
            ax.plot(s.index, s.values)

        # Now test with registering
        register_matplotlib_converters()
        with ctx:
            ax.plot(s.index, s.values)
        plt.close()

    def test_registry_resets(self):
        units = pytest.importorskip("matplotlib.units")
        dates = pytest.importorskip("matplotlib.dates")

        # make a copy, to reset to
        original = dict(units.registry)

        try:
            # get to a known state
            units.registry.clear()
            date_converter = dates.DateConverter()
            units.registry[datetime] = date_converter
            units.registry[date] = date_converter

            register_matplotlib_converters()
            assert units.registry[date] is not date_converter
            deregister_matplotlib_converters()
            assert units.registry[date] is date_converter

        finally:
            # restore original stater
            units.registry.clear()
            for k, v in original.items():
                units.registry[k] = v


class TestDateTimeConverter:
    @pytest.fixture
    def dtc(self):
        return converter.DatetimeConverter()

    def test_convert_accepts_unicode(self, dtc):
        r1 = dtc.convert("2000-01-01 12:22", None, None)
        r2 = dtc.convert("2000-01-01 12:22", None, None)
        assert r1 == r2, "DatetimeConverter.convert should accept unicode"

    def test_conversion(self, dtc):
        rs = dtc.convert(["2012-1-1"], None, None)[0]
        xp = dates.date2num(datetime(2012, 1, 1))
        assert rs == xp

        rs = dtc.convert("2012-1-1", None, None)
        assert rs == xp

        rs = dtc.convert(date(2012, 1, 1), None, None)
        assert rs == xp

        rs = dtc.convert("2012-1-1", None, None)
        assert rs == xp

        rs = dtc.convert(Timestamp("2012-1-1"), None, None)
        assert rs == xp

        # also testing datetime64 dtype (GH8614)
        rs = dtc.convert("2012-01-01", None, None)
        assert rs == xp

        rs = dtc.convert("2012-01-01 00:00:00+0000", None, None)
        assert rs == xp

        rs = dtc.convert(
            np.array(["2012-01-01 00:00:00+0000", "2012-01-02 00:00:00+0000"]),
            None,
            None,
        )
        assert rs[0] == xp

        # we have a tz-aware date (constructed to that when we turn to utc it
        # is the same as our sample)
        ts = Timestamp("2012-01-01").tz_localize("UTC").tz_convert("US/Eastern")
        rs = dtc.convert(ts, None, None)
        assert rs == xp

        rs = dtc.convert(ts.to_pydatetime(), None, None)
        assert rs == xp

        rs = dtc.convert(Index([ts - Day(1), ts]), None, None)
        assert rs[1] == xp

        rs = dtc.convert(Index([ts - Day(1), ts]).to_pydatetime(), None, None)
        assert rs[1] == xp

    def test_conversion_float(self, dtc):
        rtol = 0.5 * 10**-9

        rs = dtc.convert(Timestamp("2012-1-1 01:02:03", tz="UTC"), None, None)
        xp = converter.mdates.date2num(Timestamp("2012-1-1 01:02:03", tz="UTC"))
        tm.assert_almost_equal(rs, xp, rtol=rtol)

        rs = dtc.convert(
            Timestamp("2012-1-1 09:02:03", tz="Asia/Hong_Kong"), None, None
        )
        tm.assert_almost_equal(rs, xp, rtol=rtol)

        rs = dtc.convert(datetime(2012, 1, 1, 1, 2, 3), None, None)
        tm.assert_almost_equal(rs, xp, rtol=rtol)

    @pytest.mark.parametrize(
        "values",
        [
            [date(1677, 1, 1), date(1677, 1, 2)],
            [datetime(1677, 1, 1, 12), datetime(1677, 1, 2, 12)],
        ],
    )
    def test_conversion_outofbounds_datetime(self, dtc, values):
        # 2579
        rs = dtc.convert(values, None, None)
        xp = converter.mdates.date2num(values)
        tm.assert_numpy_array_equal(rs, xp)
        rs = dtc.convert(values[0], None, None)
        xp = converter.mdates.date2num(values[0])
        assert rs == xp

    @pytest.mark.parametrize(
        "time,format_expected",
        [
            (0, "00:00"),  # time2num(datetime.time.min)
            (86399.999999, "23:59:59.999999"),  # time2num(datetime.time.max)
            (90000, "01:00"),
            (3723, "01:02:03"),
            (39723.2, "11:02:03.200"),
        ],
    )
    def test_time_formatter(self, time, format_expected):
        # issue 18478
        result = converter.TimeFormatter(None)(time)
        assert result == format_expected

    @pytest.mark.parametrize("freq", ("B", "ms", "s"))
    def test_dateindex_conversion(self, freq, dtc):
        rtol = 10**-9
        dateindex = date_range("2020-01-01", periods=10, freq=freq)
        rs = dtc.convert(dateindex, None, None)
        xp = converter.mdates.date2num(dateindex._mpl_repr())
        tm.assert_almost_equal(rs, xp, rtol=rtol)

    @pytest.mark.parametrize("offset", [Second(), Milli(), Micro(50)])
    def test_resolution(self, offset, dtc):
        # Matplotlib's time representation using floats cannot distinguish
        # intervals smaller than ~10 microsecond in the common range of years.
        ts1 = Timestamp("2012-1-1")
        ts2 = ts1 + offset
        val1 = dtc.convert(ts1, None, None)
        val2 = dtc.convert(ts2, None, None)
        if not val1 < val2:
            raise AssertionError(f"{val1} is not less than {val2}.")

    def test_convert_nested(self, dtc):
        inner = [Timestamp("2017-01-01"), Timestamp("2017-01-02")]
        data = [inner, inner]
        result = dtc.convert(data, None, None)
        expected = [dtc.convert(x, None, None) for x in data]
        assert (np.array(result) == expected).all()


class TestPeriodConverter:
    @pytest.fixture
    def pc(self):
        return converter.PeriodConverter()

    @pytest.fixture
    def axis(self):
        class Axis:
            pass

        axis = Axis()
        axis.freq = "D"
        return axis

    def test_convert_accepts_unicode(self, pc, axis):
        r1 = pc.convert("2012-1-1", None, axis)
        r2 = pc.convert("2012-1-1", None, axis)
        assert r1 == r2

    def test_conversion(self, pc, axis):
        rs = pc.convert(["2012-1-1"], None, axis)[0]
        xp = Period("2012-1-1").ordinal
        assert rs == xp

        rs = pc.convert("2012-1-1", None, axis)
        assert rs == xp

        rs = pc.convert([date(2012, 1, 1)], None, axis)[0]
        assert rs == xp

        rs = pc.convert(date(2012, 1, 1), None, axis)
        assert rs == xp

        rs = pc.convert([Timestamp("2012-1-1")], None, axis)[0]
        assert rs == xp

        rs = pc.convert(Timestamp("2012-1-1"), None, axis)
        assert rs == xp

        rs = pc.convert("2012-01-01", None, axis)
        assert rs == xp

        rs = pc.convert("2012-01-01 00:00:00+0000", None, axis)
        assert rs == xp

        rs = pc.convert(
            np.array(
                ["2012-01-01 00:00:00", "2012-01-02 00:00:00"],
                dtype="datetime64[ns]",
            ),
            None,
            axis,
        )
        assert rs[0] == xp

    def test_integer_passthrough(self, pc, axis):
        # GH9012
        rs = pc.convert([0, 1], None, axis)
        xp = [0, 1]
        assert rs == xp

    def test_convert_nested(self, pc, axis):
        data = ["2012-1-1", "2012-1-2"]
        r1 = pc.convert([data, data], None, axis)
        r2 = [pc.convert(data, None, axis) for _ in range(2)]
        assert r1 == r2


class TestTimeDeltaConverter:
    """Test timedelta converter"""

    @pytest.mark.parametrize(
        "x, decimal, format_expected",
        [
            (0.0, 0, "00:00:00"),
            (3972320000000, 1, "01:06:12.3"),
            (713233432000000, 2, "8 days 06:07:13.43"),
            (32423432000000, 4, "09:00:23.4320"),
        ],
    )
    def test_format_timedelta_ticks(self, x, decimal, format_expected):
        tdc = converter.TimeSeries_TimedeltaFormatter
        result = tdc.format_timedelta_ticks(x, pos=None, n_decimals=decimal)
        assert result == format_expected

    @pytest.mark.parametrize("view_interval", [(1, 2), (2, 1)])
    def test_call_w_different_view_intervals(self, view_interval, monkeypatch):
        # previously broke on reversed xlmits; see GH37454
        class mock_axis:
            def get_view_interval(self):
                return view_interval

        tdc = converter.TimeSeries_TimedeltaFormatter()
        monkeypatch.setattr(tdc, "axis", mock_axis())
        tdc(0.0, 0)


@pytest.mark.parametrize("year_span", [11.25, 30, 80, 150, 400, 800, 1500, 2500, 3500])
# The range is limited to 11.25 at the bottom by if statements in
# the _quarterly_finder() function
def test_quarterly_finder(year_span):
    vmin = -1000
    vmax = vmin + year_span * 4
    span = vmax - vmin + 1
    if span < 45:
        pytest.skip("the quarterly finder is only invoked if the span is >= 45")
    nyears = span / 4
    (min_anndef, maj_anndef) = converter._get_default_annual_spacing(nyears)
    result = converter._quarterly_finder(vmin, vmax, to_offset("QE"))
    quarters = PeriodIndex(
        arrays.PeriodArray(np.array([x[0] for x in result]), dtype="period[Q]")
    )
    majors = np.array([x[1] for x in result])
    minors = np.array([x[2] for x in result])
    major_quarters = quarters[majors]
    minor_quarters = quarters[minors]
    check_major_years = major_quarters.year % maj_anndef == 0
    check_minor_years = minor_quarters.year % min_anndef == 0
    check_major_quarters = major_quarters.quarter == 1
    check_minor_quarters = minor_quarters.quarter == 1
    assert np.all(check_major_years)
    assert np.all(check_minor_years)
    assert np.all(check_major_quarters)
    assert np.all(check_minor_quarters)
