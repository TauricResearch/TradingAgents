from datetime import time

import numpy as np
import pytest
import pytz

from pandas._libs.tslibs import timezones

from pandas import (
    DataFrame,
    date_range,
)
import pandas._testing as tm


class TestAtTime:
    @pytest.mark.parametrize("tzstr", ["US/Eastern", "dateutil/US/Eastern"])
    def test_localized_at_time(self, tzstr, frame_or_series):
        tz = timezones.maybe_get_tz(tzstr)

        rng = date_range("4/16/2012", "5/1/2012", freq="h")
        ts = frame_or_series(
            np.random.default_rng(2).standard_normal(len(rng)), index=rng
        )

        ts_local = ts.tz_localize(tzstr)

        result = ts_local.at_time(time(10, 0))
        expected = ts.at_time(time(10, 0)).tz_localize(tzstr)
        tm.assert_equal(result, expected)
        assert timezones.tz_compare(result.index.tz, tz)

    def test_at_time(self, frame_or_series):
        rng = date_range("1/1/2000", "1/5/2000", freq="5min")
        ts = DataFrame(
            np.random.default_rng(2).standard_normal((len(rng), 2)), index=rng
        )
        ts = tm.get_obj(ts, frame_or_series)
        rs = ts.at_time(rng[1])
        assert (rs.index.hour == rng[1].hour).all()
        assert (rs.index.minute == rng[1].minute).all()
        assert (rs.index.second == rng[1].second).all()

        result = ts.at_time("9:30")
        expected = ts.at_time(time(9, 30))
        tm.assert_equal(result, expected)

    def test_at_time_midnight(self, frame_or_series):
        # midnight, everything
        rng = date_range("1/1/2000", "1/31/2000")
        ts = DataFrame(
            np.random.default_rng(2).standard_normal((len(rng), 3)), index=rng
        )
        ts = tm.get_obj(ts, frame_or_series)

        result = ts.at_time(time(0, 0))
        tm.assert_equal(result, ts)

    def test_at_time_nonexistent(self, frame_or_series):
        # time doesn't exist
        rng = date_range("1/1/2012", freq="23Min", periods=384)
        ts = DataFrame(np.random.default_rng(2).standard_normal(len(rng)), rng)
        ts = tm.get_obj(ts, frame_or_series)
        rs = ts.at_time("16:00")
        assert len(rs) == 0

    @pytest.mark.parametrize(
        "hour", ["1:00", "1:00AM", time(1), time(1, tzinfo=pytz.UTC)]
    )
    def test_at_time_errors(self, hour):
        # GH#24043
        dti = date_range("2018", periods=3, freq="h")
        df = DataFrame(list(range(len(dti))), index=dti)
        if getattr(hour, "tzinfo", None) is None:
            result = df.at_time(hour)
            expected = df.iloc[1:2]
            tm.assert_frame_equal(result, expected)
        else:
            with pytest.raises(ValueError, match="Index must be timezone"):
                df.at_time(hour)

    def test_at_time_tz(self):
        # GH#24043
        dti = date_range("2018", periods=3, freq="h", tz="US/Pacific")
        df = DataFrame(list(range(len(dti))), index=dti)
        result = df.at_time(time(4, tzinfo=pytz.timezone("US/Eastern")))
        expected = df.iloc[1:2]
        tm.assert_frame_equal(result, expected)

    def test_at_time_raises(self, frame_or_series):
        # GH#20725
        obj = DataFrame([[1, 2, 3], [4, 5, 6]])
        obj = tm.get_obj(obj, frame_or_series)
        msg = "Index must be DatetimeIndex"
        with pytest.raises(TypeError, match=msg):  # index is not a DatetimeIndex
            obj.at_time("00:00")

    @pytest.mark.parametrize("axis", ["index", "columns", 0, 1])
    def test_at_time_axis(self, axis):
        # issue 8839
        rng = date_range("1/1/2000", "1/5/2000", freq="5min")
        ts = DataFrame(np.random.default_rng(2).standard_normal((len(rng), len(rng))))
        ts.index, ts.columns = rng, rng

        indices = rng[(rng.hour == 9) & (rng.minute == 30) & (rng.second == 0)]

        if axis in ["index", 0]:
            expected = ts.loc[indices, :]
        elif axis in ["columns", 1]:
            expected = ts.loc[:, indices]

        result = ts.at_time("9:30", axis=axis)

        # Without clearing freq, result has freq 1440T and expected 5T
        result.index = result.index._with_freq(None)
        expected.index = expected.index._with_freq(None)
        tm.assert_frame_equal(result, expected)

    def test_at_time_datetimeindex(self):
        index = date_range("2012-01-01", "2012-01-05", freq="30min")
        df = DataFrame(
            np.random.default_rng(2).standard_normal((len(index), 5)), index=index
        )
        akey = time(12, 0, 0)
        ainds = [24, 72, 120, 168]

        result = df.at_time(akey)
        expected = df.loc[akey]
        expected2 = df.iloc[ainds]
        tm.assert_frame_equal(result, expected)
        tm.assert_frame_equal(result, expected2)
        assert len(result) == 4
