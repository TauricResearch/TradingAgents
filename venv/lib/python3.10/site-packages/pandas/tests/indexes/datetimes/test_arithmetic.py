# Arithmetic tests specific to DatetimeIndex are generally about `freq`
#  rentention or inference.  Other arithmetic tests belong in
#  tests/arithmetic/test_datetime64.py
import pytest

from pandas import (
    Timedelta,
    TimedeltaIndex,
    Timestamp,
    date_range,
    timedelta_range,
)
import pandas._testing as tm


class TestDatetimeIndexArithmetic:
    def test_add_timedelta_preserves_freq(self):
        # GH#37295 should hold for any DTI with freq=None or Tick freq
        tz = "Canada/Eastern"
        dti = date_range(
            start=Timestamp("2019-03-26 00:00:00-0400", tz=tz),
            end=Timestamp("2020-10-17 00:00:00-0400", tz=tz),
            freq="D",
        )
        result = dti + Timedelta(days=1)
        assert result.freq == dti.freq

    def test_sub_datetime_preserves_freq(self, tz_naive_fixture):
        # GH#48818
        dti = date_range("2016-01-01", periods=12, tz=tz_naive_fixture)

        res = dti - dti[0]
        expected = timedelta_range("0 Days", "11 Days")
        tm.assert_index_equal(res, expected)
        assert res.freq == expected.freq

    @pytest.mark.xfail(
        reason="The inherited freq is incorrect bc dti.freq is incorrect "
        "https://github.com/pandas-dev/pandas/pull/48818/files#r982793461"
    )
    def test_sub_datetime_preserves_freq_across_dst(self):
        # GH#48818
        ts = Timestamp("2016-03-11", tz="US/Pacific")
        dti = date_range(ts, periods=4)

        res = dti - dti[0]
        expected = TimedeltaIndex(
            [
                Timedelta(days=0),
                Timedelta(days=1),
                Timedelta(days=2),
                Timedelta(days=2, hours=23),
            ]
        )
        tm.assert_index_equal(res, expected)
        assert res.freq == expected.freq
