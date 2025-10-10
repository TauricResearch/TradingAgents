"""
Tests for Timestamp timezone-related methods
"""
from datetime import datetime

from pandas._libs.tslibs import timezones

from pandas import Timestamp


class TestTimestampTZOperations:
    # ------------------------------------------------------------------

    def test_timestamp_timetz_equivalent_with_datetime_tz(self, tz_naive_fixture):
        # GH21358
        tz = timezones.maybe_get_tz(tz_naive_fixture)

        stamp = Timestamp("2018-06-04 10:20:30", tz=tz)
        _datetime = datetime(2018, 6, 4, hour=10, minute=20, second=30, tzinfo=tz)

        result = stamp.timetz()
        expected = _datetime.timetz()

        assert result == expected
