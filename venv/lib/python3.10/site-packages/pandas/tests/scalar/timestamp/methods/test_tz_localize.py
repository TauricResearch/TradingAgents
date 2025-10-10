from datetime import timedelta
import re

from dateutil.tz import gettz
import pytest
import pytz
from pytz.exceptions import (
    AmbiguousTimeError,
    NonExistentTimeError,
)

from pandas._libs.tslibs.dtypes import NpyDatetimeUnit
from pandas.errors import OutOfBoundsDatetime

from pandas import (
    NaT,
    Timestamp,
)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Cannot assign to a type
    ZoneInfo = None  # type: ignore[misc, assignment]


class TestTimestampTZLocalize:
    @pytest.mark.skip_ubsan
    def test_tz_localize_pushes_out_of_bounds(self):
        # GH#12677
        # tz_localize that pushes away from the boundary is OK
        msg = (
            f"Converting {Timestamp.min.strftime('%Y-%m-%d %H:%M:%S')} "
            f"underflows past {Timestamp.min}"
        )
        pac = Timestamp.min.tz_localize("US/Pacific")
        assert pac._value > Timestamp.min._value
        pac.tz_convert("Asia/Tokyo")  # tz_convert doesn't change value
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            Timestamp.min.tz_localize("Asia/Tokyo")

        # tz_localize that pushes away from the boundary is OK
        msg = (
            f"Converting {Timestamp.max.strftime('%Y-%m-%d %H:%M:%S')} "
            f"overflows past {Timestamp.max}"
        )
        tokyo = Timestamp.max.tz_localize("Asia/Tokyo")
        assert tokyo._value < Timestamp.max._value
        tokyo.tz_convert("US/Pacific")  # tz_convert doesn't change value
        with pytest.raises(OutOfBoundsDatetime, match=msg):
            Timestamp.max.tz_localize("US/Pacific")

    @pytest.mark.parametrize("unit", ["ns", "us", "ms", "s"])
    def test_tz_localize_ambiguous_bool(self, unit):
        # make sure that we are correctly accepting bool values as ambiguous
        # GH#14402
        ts = Timestamp("2015-11-01 01:00:03").as_unit(unit)
        expected0 = Timestamp("2015-11-01 01:00:03-0500", tz="US/Central")
        expected1 = Timestamp("2015-11-01 01:00:03-0600", tz="US/Central")

        msg = "Cannot infer dst time from 2015-11-01 01:00:03"
        with pytest.raises(pytz.AmbiguousTimeError, match=msg):
            ts.tz_localize("US/Central")

        with pytest.raises(pytz.AmbiguousTimeError, match=msg):
            ts.tz_localize("dateutil/US/Central")

        if ZoneInfo is not None:
            try:
                tz = ZoneInfo("US/Central")
            except KeyError:
                # no tzdata
                pass
            else:
                with pytest.raises(pytz.AmbiguousTimeError, match=msg):
                    ts.tz_localize(tz)

        result = ts.tz_localize("US/Central", ambiguous=True)
        assert result == expected0
        assert result._creso == getattr(NpyDatetimeUnit, f"NPY_FR_{unit}").value

        result = ts.tz_localize("US/Central", ambiguous=False)
        assert result == expected1
        assert result._creso == getattr(NpyDatetimeUnit, f"NPY_FR_{unit}").value

    def test_tz_localize_ambiguous(self):
        ts = Timestamp("2014-11-02 01:00")
        ts_dst = ts.tz_localize("US/Eastern", ambiguous=True)
        ts_no_dst = ts.tz_localize("US/Eastern", ambiguous=False)

        assert ts_no_dst._value - ts_dst._value == 3600
        msg = re.escape(
            "'ambiguous' parameter must be one of: "
            "True, False, 'NaT', 'raise' (default)"
        )
        with pytest.raises(ValueError, match=msg):
            ts.tz_localize("US/Eastern", ambiguous="infer")

        # GH#8025
        msg = "Cannot localize tz-aware Timestamp, use tz_convert for conversions"
        with pytest.raises(TypeError, match=msg):
            Timestamp("2011-01-01", tz="US/Eastern").tz_localize("Asia/Tokyo")

        msg = "Cannot convert tz-naive Timestamp, use tz_localize to localize"
        with pytest.raises(TypeError, match=msg):
            Timestamp("2011-01-01").tz_convert("Asia/Tokyo")

    @pytest.mark.parametrize(
        "stamp, tz",
        [
            ("2015-03-08 02:00", "US/Eastern"),
            ("2015-03-08 02:30", "US/Pacific"),
            ("2015-03-29 02:00", "Europe/Paris"),
            ("2015-03-29 02:30", "Europe/Belgrade"),
        ],
    )
    def test_tz_localize_nonexistent(self, stamp, tz):
        # GH#13057
        ts = Timestamp(stamp)
        with pytest.raises(NonExistentTimeError, match=stamp):
            ts.tz_localize(tz)
        # GH 22644
        with pytest.raises(NonExistentTimeError, match=stamp):
            ts.tz_localize(tz, nonexistent="raise")
        assert ts.tz_localize(tz, nonexistent="NaT") is NaT

    @pytest.mark.parametrize(
        "stamp, tz, forward_expected, backward_expected",
        [
            (
                "2015-03-29 02:00:00",
                "Europe/Warsaw",
                "2015-03-29 03:00:00",
                "2015-03-29 01:59:59",
            ),  # utc+1 -> utc+2
            (
                "2023-03-12 02:00:00",
                "America/Los_Angeles",
                "2023-03-12 03:00:00",
                "2023-03-12 01:59:59",
            ),  # utc-8 -> utc-7
            (
                "2023-03-26 01:00:00",
                "Europe/London",
                "2023-03-26 02:00:00",
                "2023-03-26 00:59:59",
            ),  # utc+0 -> utc+1
            (
                "2023-03-26 00:00:00",
                "Atlantic/Azores",
                "2023-03-26 01:00:00",
                "2023-03-25 23:59:59",
            ),  # utc-1 -> utc+0
        ],
    )
    def test_tz_localize_nonexistent_shift(
        self, stamp, tz, forward_expected, backward_expected
    ):
        ts = Timestamp(stamp)
        forward_ts = ts.tz_localize(tz, nonexistent="shift_forward")
        assert forward_ts == Timestamp(forward_expected, tz=tz)
        backward_ts = ts.tz_localize(tz, nonexistent="shift_backward")
        assert backward_ts == Timestamp(backward_expected, tz=tz)

    def test_tz_localize_ambiguous_raise(self):
        # GH#13057
        ts = Timestamp("2015-11-1 01:00")
        msg = "Cannot infer dst time from 2015-11-01 01:00:00,"
        with pytest.raises(AmbiguousTimeError, match=msg):
            ts.tz_localize("US/Pacific", ambiguous="raise")

    def test_tz_localize_nonexistent_invalid_arg(self, warsaw):
        # GH 22644
        tz = warsaw
        ts = Timestamp("2015-03-29 02:00:00")
        msg = (
            "The nonexistent argument must be one of 'raise', 'NaT', "
            "'shift_forward', 'shift_backward' or a timedelta object"
        )
        with pytest.raises(ValueError, match=msg):
            ts.tz_localize(tz, nonexistent="foo")

    @pytest.mark.parametrize(
        "stamp",
        [
            "2014-02-01 09:00",
            "2014-07-08 09:00",
            "2014-11-01 17:00",
            "2014-11-05 00:00",
        ],
    )
    def test_tz_localize_roundtrip(self, stamp, tz_aware_fixture):
        tz = tz_aware_fixture
        ts = Timestamp(stamp)
        localized = ts.tz_localize(tz)
        assert localized == Timestamp(stamp, tz=tz)

        msg = "Cannot localize tz-aware Timestamp"
        with pytest.raises(TypeError, match=msg):
            localized.tz_localize(tz)

        reset = localized.tz_localize(None)
        assert reset == ts
        assert reset.tzinfo is None

    def test_tz_localize_ambiguous_compat(self):
        # validate that pytz and dateutil are compat for dst
        # when the transition happens
        naive = Timestamp("2013-10-27 01:00:00")

        pytz_zone = "Europe/London"
        dateutil_zone = "dateutil/Europe/London"
        result_pytz = naive.tz_localize(pytz_zone, ambiguous=False)
        result_dateutil = naive.tz_localize(dateutil_zone, ambiguous=False)
        assert result_pytz._value == result_dateutil._value
        assert result_pytz._value == 1382835600

        # fixed ambiguous behavior
        # see gh-14621, GH#45087
        assert result_pytz.to_pydatetime().tzname() == "GMT"
        assert result_dateutil.to_pydatetime().tzname() == "GMT"
        assert str(result_pytz) == str(result_dateutil)

        # 1 hour difference
        result_pytz = naive.tz_localize(pytz_zone, ambiguous=True)
        result_dateutil = naive.tz_localize(dateutil_zone, ambiguous=True)
        assert result_pytz._value == result_dateutil._value
        assert result_pytz._value == 1382832000

        # see gh-14621
        assert str(result_pytz) == str(result_dateutil)
        assert (
            result_pytz.to_pydatetime().tzname()
            == result_dateutil.to_pydatetime().tzname()
        )

    @pytest.mark.parametrize(
        "tz",
        [
            pytz.timezone("US/Eastern"),
            gettz("US/Eastern"),
            "US/Eastern",
            "dateutil/US/Eastern",
        ],
    )
    def test_timestamp_tz_localize(self, tz):
        stamp = Timestamp("3/11/2012 04:00")

        result = stamp.tz_localize(tz)
        expected = Timestamp("3/11/2012 04:00", tz=tz)
        assert result.hour == expected.hour
        assert result == expected

    @pytest.mark.parametrize(
        "start_ts, tz, end_ts, shift",
        [
            ["2015-03-29 02:20:00", "Europe/Warsaw", "2015-03-29 03:00:00", "forward"],
            [
                "2015-03-29 02:20:00",
                "Europe/Warsaw",
                "2015-03-29 01:59:59.999999999",
                "backward",
            ],
            [
                "2015-03-29 02:20:00",
                "Europe/Warsaw",
                "2015-03-29 03:20:00",
                timedelta(hours=1),
            ],
            [
                "2015-03-29 02:20:00",
                "Europe/Warsaw",
                "2015-03-29 01:20:00",
                timedelta(hours=-1),
            ],
            ["2018-03-11 02:33:00", "US/Pacific", "2018-03-11 03:00:00", "forward"],
            [
                "2018-03-11 02:33:00",
                "US/Pacific",
                "2018-03-11 01:59:59.999999999",
                "backward",
            ],
            [
                "2018-03-11 02:33:00",
                "US/Pacific",
                "2018-03-11 03:33:00",
                timedelta(hours=1),
            ],
            [
                "2018-03-11 02:33:00",
                "US/Pacific",
                "2018-03-11 01:33:00",
                timedelta(hours=-1),
            ],
        ],
    )
    @pytest.mark.parametrize("tz_type", ["", "dateutil/"])
    @pytest.mark.parametrize("unit", ["ns", "us", "ms", "s"])
    def test_timestamp_tz_localize_nonexistent_shift(
        self, start_ts, tz, end_ts, shift, tz_type, unit
    ):
        # GH 8917, 24466
        tz = tz_type + tz
        if isinstance(shift, str):
            shift = "shift_" + shift
        ts = Timestamp(start_ts).as_unit(unit)
        result = ts.tz_localize(tz, nonexistent=shift)
        expected = Timestamp(end_ts).tz_localize(tz)

        if unit == "us":
            assert result == expected.replace(nanosecond=0)
        elif unit == "ms":
            micros = expected.microsecond - expected.microsecond % 1000
            assert result == expected.replace(microsecond=micros, nanosecond=0)
        elif unit == "s":
            assert result == expected.replace(microsecond=0, nanosecond=0)
        else:
            assert result == expected
        assert result._creso == getattr(NpyDatetimeUnit, f"NPY_FR_{unit}").value

    @pytest.mark.parametrize("offset", [-1, 1])
    def test_timestamp_tz_localize_nonexistent_shift_invalid(self, offset, warsaw):
        # GH 8917, 24466
        tz = warsaw
        ts = Timestamp("2015-03-29 02:20:00")
        msg = "The provided timedelta will relocalize on a nonexistent time"
        with pytest.raises(ValueError, match=msg):
            ts.tz_localize(tz, nonexistent=timedelta(seconds=offset))

    @pytest.mark.parametrize("unit", ["ns", "us", "ms", "s"])
    def test_timestamp_tz_localize_nonexistent_NaT(self, warsaw, unit):
        # GH 8917
        tz = warsaw
        ts = Timestamp("2015-03-29 02:20:00").as_unit(unit)
        result = ts.tz_localize(tz, nonexistent="NaT")
        assert result is NaT

    @pytest.mark.parametrize("unit", ["ns", "us", "ms", "s"])
    def test_timestamp_tz_localize_nonexistent_raise(self, warsaw, unit):
        # GH 8917
        tz = warsaw
        ts = Timestamp("2015-03-29 02:20:00").as_unit(unit)
        msg = "2015-03-29 02:20:00"
        with pytest.raises(pytz.NonExistentTimeError, match=msg):
            ts.tz_localize(tz, nonexistent="raise")
        msg = (
            "The nonexistent argument must be one of 'raise', 'NaT', "
            "'shift_forward', 'shift_backward' or a timedelta object"
        )
        with pytest.raises(ValueError, match=msg):
            ts.tz_localize(tz, nonexistent="foo")
