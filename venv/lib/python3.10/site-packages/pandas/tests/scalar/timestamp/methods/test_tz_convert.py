import dateutil
import pytest

from pandas._libs.tslibs import timezones
import pandas.util._test_decorators as td

from pandas import Timestamp


class TestTimestampTZConvert:
    @pytest.mark.parametrize("tzstr", ["US/Eastern", "dateutil/US/Eastern"])
    def test_astimezone(self, tzstr):
        # astimezone is an alias for tz_convert, so keep it with
        # the tz_convert tests
        utcdate = Timestamp("3/11/2012 22:00", tz="UTC")
        expected = utcdate.tz_convert(tzstr)
        result = utcdate.astimezone(tzstr)
        assert expected == result
        assert isinstance(result, Timestamp)

    @pytest.mark.parametrize(
        "stamp",
        [
            "2014-02-01 09:00",
            "2014-07-08 09:00",
            "2014-11-01 17:00",
            "2014-11-05 00:00",
        ],
    )
    def test_tz_convert_roundtrip(self, stamp, tz_aware_fixture):
        tz = tz_aware_fixture

        ts = Timestamp(stamp, tz="UTC")
        converted = ts.tz_convert(tz)

        reset = converted.tz_convert(None)
        assert reset == Timestamp(stamp)
        assert reset.tzinfo is None
        assert reset == converted.tz_convert("UTC").tz_localize(None)

    @td.skip_if_windows
    def test_tz_convert_utc_with_system_utc(self):
        # from system utc to real utc
        ts = Timestamp("2001-01-05 11:56", tz=timezones.maybe_get_tz("dateutil/UTC"))
        # check that the time hasn't changed.
        assert ts == ts.tz_convert(dateutil.tz.tzutc())

        # from system utc to real utc
        ts = Timestamp("2001-01-05 11:56", tz=timezones.maybe_get_tz("dateutil/UTC"))
        # check that the time hasn't changed.
        assert ts == ts.tz_convert(dateutil.tz.tzutc())
