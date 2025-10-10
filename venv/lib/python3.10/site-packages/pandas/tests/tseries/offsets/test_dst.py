"""
Tests for DateOffset additions over Daylight Savings Time
"""
from datetime import timedelta

import pytest
import pytz

from pandas._libs.tslibs import Timestamp
from pandas._libs.tslibs.offsets import (
    BMonthBegin,
    BMonthEnd,
    BQuarterBegin,
    BQuarterEnd,
    BYearBegin,
    BYearEnd,
    CBMonthBegin,
    CBMonthEnd,
    CustomBusinessDay,
    DateOffset,
    Day,
    MonthBegin,
    MonthEnd,
    QuarterBegin,
    QuarterEnd,
    SemiMonthBegin,
    SemiMonthEnd,
    Week,
    YearBegin,
    YearEnd,
)
from pandas.errors import PerformanceWarning

from pandas import DatetimeIndex
import pandas._testing as tm
from pandas.util.version import Version

# error: Module has no attribute "__version__"
pytz_version = Version(pytz.__version__)  # type: ignore[attr-defined]


def get_utc_offset_hours(ts):
    # take a Timestamp and compute total hours of utc offset
    o = ts.utcoffset()
    return (o.days * 24 * 3600 + o.seconds) / 3600.0


class TestDST:
    # one microsecond before the DST transition
    ts_pre_fallback = "2013-11-03 01:59:59.999999"
    ts_pre_springfwd = "2013-03-10 01:59:59.999999"

    # test both basic names and dateutil timezones
    timezone_utc_offsets = {
        "US/Eastern": {"utc_offset_daylight": -4, "utc_offset_standard": -5},
        "dateutil/US/Pacific": {"utc_offset_daylight": -7, "utc_offset_standard": -8},
    }
    valid_date_offsets_singular = [
        "weekday",
        "day",
        "hour",
        "minute",
        "second",
        "microsecond",
    ]
    valid_date_offsets_plural = [
        "weeks",
        "days",
        "hours",
        "minutes",
        "seconds",
        "milliseconds",
        "microseconds",
    ]

    def _test_all_offsets(self, n, **kwds):
        valid_offsets = (
            self.valid_date_offsets_plural
            if n > 1
            else self.valid_date_offsets_singular
        )

        for name in valid_offsets:
            self._test_offset(offset_name=name, offset_n=n, **kwds)

    def _test_offset(self, offset_name, offset_n, tstart, expected_utc_offset):
        offset = DateOffset(**{offset_name: offset_n})

        if (
            offset_name in ["hour", "minute", "second", "microsecond"]
            and offset_n == 1
            and tstart == Timestamp("2013-11-03 01:59:59.999999-0500", tz="US/Eastern")
        ):
            # This addition results in an ambiguous wall time
            err_msg = {
                "hour": "2013-11-03 01:59:59.999999",
                "minute": "2013-11-03 01:01:59.999999",
                "second": "2013-11-03 01:59:01.999999",
                "microsecond": "2013-11-03 01:59:59.000001",
            }[offset_name]
            with pytest.raises(pytz.AmbiguousTimeError, match=err_msg):
                tstart + offset
            # While we're here, let's check that we get the same behavior in a
            #  vectorized path
            dti = DatetimeIndex([tstart])
            warn_msg = "Non-vectorized DateOffset"
            with pytest.raises(pytz.AmbiguousTimeError, match=err_msg):
                with tm.assert_produces_warning(PerformanceWarning, match=warn_msg):
                    dti + offset
            return

        t = tstart + offset
        if expected_utc_offset is not None:
            assert get_utc_offset_hours(t) == expected_utc_offset

        if offset_name == "weeks":
            # dates should match
            assert t.date() == timedelta(days=7 * offset.kwds["weeks"]) + tstart.date()
            # expect the same day of week, hour of day, minute, second, ...
            assert (
                t.dayofweek == tstart.dayofweek
                and t.hour == tstart.hour
                and t.minute == tstart.minute
                and t.second == tstart.second
            )
        elif offset_name == "days":
            # dates should match
            assert timedelta(offset.kwds["days"]) + tstart.date() == t.date()
            # expect the same hour of day, minute, second, ...
            assert (
                t.hour == tstart.hour
                and t.minute == tstart.minute
                and t.second == tstart.second
            )
        elif offset_name in self.valid_date_offsets_singular:
            # expect the singular offset value to match between tstart and t
            datepart_offset = getattr(
                t, offset_name if offset_name != "weekday" else "dayofweek"
            )
            assert datepart_offset == offset.kwds[offset_name]
        else:
            # the offset should be the same as if it was done in UTC
            assert t == (tstart.tz_convert("UTC") + offset).tz_convert("US/Pacific")

    def _make_timestamp(self, string, hrs_offset, tz):
        if hrs_offset >= 0:
            offset_string = f"{hrs_offset:02d}00"
        else:
            offset_string = f"-{(hrs_offset * -1):02}00"
        return Timestamp(string + offset_string).tz_convert(tz)

    def test_springforward_plural(self):
        # test moving from standard to daylight savings
        for tz, utc_offsets in self.timezone_utc_offsets.items():
            hrs_pre = utc_offsets["utc_offset_standard"]
            hrs_post = utc_offsets["utc_offset_daylight"]
            self._test_all_offsets(
                n=3,
                tstart=self._make_timestamp(self.ts_pre_springfwd, hrs_pre, tz),
                expected_utc_offset=hrs_post,
            )

    def test_fallback_singular(self):
        # in the case of singular offsets, we don't necessarily know which utc
        # offset the new Timestamp will wind up in (the tz for 1 month may be
        # different from 1 second) so we don't specify an expected_utc_offset
        for tz, utc_offsets in self.timezone_utc_offsets.items():
            hrs_pre = utc_offsets["utc_offset_standard"]
            self._test_all_offsets(
                n=1,
                tstart=self._make_timestamp(self.ts_pre_fallback, hrs_pre, tz),
                expected_utc_offset=None,
            )

    def test_springforward_singular(self):
        for tz, utc_offsets in self.timezone_utc_offsets.items():
            hrs_pre = utc_offsets["utc_offset_standard"]
            self._test_all_offsets(
                n=1,
                tstart=self._make_timestamp(self.ts_pre_springfwd, hrs_pre, tz),
                expected_utc_offset=None,
            )

    offset_classes = {
        MonthBegin: ["11/2/2012", "12/1/2012"],
        MonthEnd: ["11/2/2012", "11/30/2012"],
        BMonthBegin: ["11/2/2012", "12/3/2012"],
        BMonthEnd: ["11/2/2012", "11/30/2012"],
        CBMonthBegin: ["11/2/2012", "12/3/2012"],
        CBMonthEnd: ["11/2/2012", "11/30/2012"],
        SemiMonthBegin: ["11/2/2012", "11/15/2012"],
        SemiMonthEnd: ["11/2/2012", "11/15/2012"],
        Week: ["11/2/2012", "11/9/2012"],
        YearBegin: ["11/2/2012", "1/1/2013"],
        YearEnd: ["11/2/2012", "12/31/2012"],
        BYearBegin: ["11/2/2012", "1/1/2013"],
        BYearEnd: ["11/2/2012", "12/31/2012"],
        QuarterBegin: ["11/2/2012", "12/1/2012"],
        QuarterEnd: ["11/2/2012", "12/31/2012"],
        BQuarterBegin: ["11/2/2012", "12/3/2012"],
        BQuarterEnd: ["11/2/2012", "12/31/2012"],
        Day: ["11/4/2012", "11/4/2012 23:00"],
    }.items()

    @pytest.mark.parametrize("tup", offset_classes)
    def test_all_offset_classes(self, tup):
        offset, test_values = tup

        first = Timestamp(test_values[0], tz="US/Eastern") + offset()
        second = Timestamp(test_values[1], tz="US/Eastern")
        assert first == second


@pytest.mark.parametrize(
    "original_dt, target_dt, offset, tz",
    [
        pytest.param(
            Timestamp("1900-01-01"),
            Timestamp("1905-07-01"),
            MonthBegin(66),
            "Africa/Lagos",
            marks=pytest.mark.xfail(
                pytz_version < Version("2020.5") or pytz_version == Version("2022.2"),
                reason="GH#41906: pytz utc transition dates changed",
            ),
        ),
        (
            Timestamp("2021-10-01 01:15"),
            Timestamp("2021-10-31 01:15"),
            MonthEnd(1),
            "Europe/London",
        ),
        (
            Timestamp("2010-12-05 02:59"),
            Timestamp("2010-10-31 02:59"),
            SemiMonthEnd(-3),
            "Europe/Paris",
        ),
        (
            Timestamp("2021-10-31 01:20"),
            Timestamp("2021-11-07 01:20"),
            CustomBusinessDay(2, weekmask="Sun Mon"),
            "US/Eastern",
        ),
        (
            Timestamp("2020-04-03 01:30"),
            Timestamp("2020-11-01 01:30"),
            YearBegin(1, month=11),
            "America/Chicago",
        ),
    ],
)
def test_nontick_offset_with_ambiguous_time_error(original_dt, target_dt, offset, tz):
    # .apply for non-Tick offsets throws AmbiguousTimeError when the target dt
    # is dst-ambiguous
    localized_dt = original_dt.tz_localize(tz)

    msg = f"Cannot infer dst time from {target_dt}, try using the 'ambiguous' argument"
    with pytest.raises(pytz.AmbiguousTimeError, match=msg):
        localized_dt + offset
