from datetime import datetime
import pprint

import dateutil.tz
import pytest
import pytz  # a test below uses pytz but only inside a `eval` call

from pandas import Timestamp

ts_no_ns = Timestamp(
    year=2019,
    month=5,
    day=18,
    hour=15,
    minute=17,
    second=8,
    microsecond=132263,
)
ts_no_ns_year1 = Timestamp(
    year=1,
    month=5,
    day=18,
    hour=15,
    minute=17,
    second=8,
    microsecond=132263,
)
ts_ns = Timestamp(
    year=2019,
    month=5,
    day=18,
    hour=15,
    minute=17,
    second=8,
    microsecond=132263,
    nanosecond=123,
)
ts_ns_tz = Timestamp(
    year=2019,
    month=5,
    day=18,
    hour=15,
    minute=17,
    second=8,
    microsecond=132263,
    nanosecond=123,
    tz="UTC",
)
ts_no_us = Timestamp(
    year=2019,
    month=5,
    day=18,
    hour=15,
    minute=17,
    second=8,
    microsecond=0,
    nanosecond=123,
)


@pytest.mark.parametrize(
    "ts, timespec, expected_iso",
    [
        (ts_no_ns, "auto", "2019-05-18T15:17:08.132263"),
        (ts_no_ns, "seconds", "2019-05-18T15:17:08"),
        (ts_no_ns, "nanoseconds", "2019-05-18T15:17:08.132263000"),
        (ts_no_ns_year1, "seconds", "0001-05-18T15:17:08"),
        (ts_no_ns_year1, "nanoseconds", "0001-05-18T15:17:08.132263000"),
        (ts_ns, "auto", "2019-05-18T15:17:08.132263123"),
        (ts_ns, "hours", "2019-05-18T15"),
        (ts_ns, "minutes", "2019-05-18T15:17"),
        (ts_ns, "seconds", "2019-05-18T15:17:08"),
        (ts_ns, "milliseconds", "2019-05-18T15:17:08.132"),
        (ts_ns, "microseconds", "2019-05-18T15:17:08.132263"),
        (ts_ns, "nanoseconds", "2019-05-18T15:17:08.132263123"),
        (ts_ns_tz, "auto", "2019-05-18T15:17:08.132263123+00:00"),
        (ts_ns_tz, "hours", "2019-05-18T15+00:00"),
        (ts_ns_tz, "minutes", "2019-05-18T15:17+00:00"),
        (ts_ns_tz, "seconds", "2019-05-18T15:17:08+00:00"),
        (ts_ns_tz, "milliseconds", "2019-05-18T15:17:08.132+00:00"),
        (ts_ns_tz, "microseconds", "2019-05-18T15:17:08.132263+00:00"),
        (ts_ns_tz, "nanoseconds", "2019-05-18T15:17:08.132263123+00:00"),
        (ts_no_us, "auto", "2019-05-18T15:17:08.000000123"),
    ],
)
def test_isoformat(ts, timespec, expected_iso):
    assert ts.isoformat(timespec=timespec) == expected_iso


class TestTimestampRendering:
    timezones = ["UTC", "Asia/Tokyo", "US/Eastern", "dateutil/America/Los_Angeles"]

    @pytest.mark.parametrize("tz", timezones)
    @pytest.mark.parametrize("freq", ["D", "M", "S", "N"])
    @pytest.mark.parametrize(
        "date", ["2014-03-07", "2014-01-01 09:00", "2014-01-01 00:00:00.000000001"]
    )
    def test_repr(self, date, freq, tz):
        # avoid to match with timezone name
        freq_repr = f"'{freq}'"
        if tz.startswith("dateutil"):
            tz_repr = tz.replace("dateutil", "")
        else:
            tz_repr = tz

        date_only = Timestamp(date)
        assert date in repr(date_only)
        assert tz_repr not in repr(date_only)
        assert freq_repr not in repr(date_only)
        assert date_only == eval(repr(date_only))

        date_tz = Timestamp(date, tz=tz)
        assert date in repr(date_tz)
        assert tz_repr in repr(date_tz)
        assert freq_repr not in repr(date_tz)
        assert date_tz == eval(repr(date_tz))

    def test_repr_utcoffset(self):
        # This can cause the tz field to be populated, but it's redundant to
        # include this information in the date-string.
        date_with_utc_offset = Timestamp("2014-03-13 00:00:00-0400", tz=None)
        assert "2014-03-13 00:00:00-0400" in repr(date_with_utc_offset)
        assert "tzoffset" not in repr(date_with_utc_offset)
        assert "UTC-04:00" in repr(date_with_utc_offset)
        expr = repr(date_with_utc_offset)
        assert date_with_utc_offset == eval(expr)

    def test_timestamp_repr_pre1900(self):
        # pre-1900
        stamp = Timestamp("1850-01-01", tz="US/Eastern")
        repr(stamp)

        iso8601 = "1850-01-01 01:23:45.012345"
        stamp = Timestamp(iso8601, tz="US/Eastern")
        result = repr(stamp)
        assert iso8601 in result

    def test_pprint(self):
        # GH#12622
        nested_obj = {"foo": 1, "bar": [{"w": {"a": Timestamp("2011-01-01")}}] * 10}
        result = pprint.pformat(nested_obj, width=50)
        expected = r"""{'bar': [{'w': {'a': Timestamp('2011-01-01 00:00:00')}},
         {'w': {'a': Timestamp('2011-01-01 00:00:00')}},
         {'w': {'a': Timestamp('2011-01-01 00:00:00')}},
         {'w': {'a': Timestamp('2011-01-01 00:00:00')}},
         {'w': {'a': Timestamp('2011-01-01 00:00:00')}},
         {'w': {'a': Timestamp('2011-01-01 00:00:00')}},
         {'w': {'a': Timestamp('2011-01-01 00:00:00')}},
         {'w': {'a': Timestamp('2011-01-01 00:00:00')}},
         {'w': {'a': Timestamp('2011-01-01 00:00:00')}},
         {'w': {'a': Timestamp('2011-01-01 00:00:00')}}],
 'foo': 1}"""
        assert result == expected

    def test_to_timestamp_repr_is_code(self):
        zs = [
            Timestamp("99-04-17 00:00:00", tz="UTC"),
            Timestamp("2001-04-17 00:00:00", tz="UTC"),
            Timestamp("2001-04-17 00:00:00", tz="America/Los_Angeles"),
            Timestamp("2001-04-17 00:00:00", tz=None),
        ]
        for z in zs:
            assert eval(repr(z)) == z

    def test_repr_matches_pydatetime_no_tz(self):
        dt_date = datetime(2013, 1, 2)
        assert str(dt_date) == str(Timestamp(dt_date))

        dt_datetime = datetime(2013, 1, 2, 12, 1, 3)
        assert str(dt_datetime) == str(Timestamp(dt_datetime))

        dt_datetime_us = datetime(2013, 1, 2, 12, 1, 3, 45)
        assert str(dt_datetime_us) == str(Timestamp(dt_datetime_us))

        ts_nanos_only = Timestamp(200)
        assert str(ts_nanos_only) == "1970-01-01 00:00:00.000000200"

        ts_nanos_micros = Timestamp(1200)
        assert str(ts_nanos_micros) == "1970-01-01 00:00:00.000001200"

    def test_repr_matches_pydatetime_tz_pytz(self):
        dt_date = datetime(2013, 1, 2, tzinfo=pytz.utc)
        assert str(dt_date) == str(Timestamp(dt_date))

        dt_datetime = datetime(2013, 1, 2, 12, 1, 3, tzinfo=pytz.utc)
        assert str(dt_datetime) == str(Timestamp(dt_datetime))

        dt_datetime_us = datetime(2013, 1, 2, 12, 1, 3, 45, tzinfo=pytz.utc)
        assert str(dt_datetime_us) == str(Timestamp(dt_datetime_us))

    def test_repr_matches_pydatetime_tz_dateutil(self):
        utc = dateutil.tz.tzutc()

        dt_date = datetime(2013, 1, 2, tzinfo=utc)
        assert str(dt_date) == str(Timestamp(dt_date))

        dt_datetime = datetime(2013, 1, 2, 12, 1, 3, tzinfo=utc)
        assert str(dt_datetime) == str(Timestamp(dt_datetime))

        dt_datetime_us = datetime(2013, 1, 2, 12, 1, 3, 45, tzinfo=utc)
        assert str(dt_datetime_us) == str(Timestamp(dt_datetime_us))
