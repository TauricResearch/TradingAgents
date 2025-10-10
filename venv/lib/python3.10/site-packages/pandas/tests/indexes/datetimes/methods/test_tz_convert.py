from datetime import datetime

import dateutil.tz
from dateutil.tz import gettz
import numpy as np
import pytest
import pytz

from pandas._libs.tslibs import timezones

from pandas import (
    DatetimeIndex,
    Index,
    NaT,
    Timestamp,
    date_range,
    offsets,
)
import pandas._testing as tm


class TestTZConvert:
    def test_tz_convert_nat(self):
        # GH#5546
        dates = [NaT]
        idx = DatetimeIndex(dates)
        idx = idx.tz_localize("US/Pacific")
        tm.assert_index_equal(idx, DatetimeIndex(dates, tz="US/Pacific"))
        idx = idx.tz_convert("US/Eastern")
        tm.assert_index_equal(idx, DatetimeIndex(dates, tz="US/Eastern"))
        idx = idx.tz_convert("UTC")
        tm.assert_index_equal(idx, DatetimeIndex(dates, tz="UTC"))

        dates = ["2010-12-01 00:00", "2010-12-02 00:00", NaT]
        idx = DatetimeIndex(dates)
        idx = idx.tz_localize("US/Pacific")
        tm.assert_index_equal(idx, DatetimeIndex(dates, tz="US/Pacific"))
        idx = idx.tz_convert("US/Eastern")
        expected = ["2010-12-01 03:00", "2010-12-02 03:00", NaT]
        tm.assert_index_equal(idx, DatetimeIndex(expected, tz="US/Eastern"))

        idx = idx + offsets.Hour(5)
        expected = ["2010-12-01 08:00", "2010-12-02 08:00", NaT]
        tm.assert_index_equal(idx, DatetimeIndex(expected, tz="US/Eastern"))
        idx = idx.tz_convert("US/Pacific")
        expected = ["2010-12-01 05:00", "2010-12-02 05:00", NaT]
        tm.assert_index_equal(idx, DatetimeIndex(expected, tz="US/Pacific"))

        idx = idx + np.timedelta64(3, "h")
        expected = ["2010-12-01 08:00", "2010-12-02 08:00", NaT]
        tm.assert_index_equal(idx, DatetimeIndex(expected, tz="US/Pacific"))

        idx = idx.tz_convert("US/Eastern")
        expected = ["2010-12-01 11:00", "2010-12-02 11:00", NaT]
        tm.assert_index_equal(idx, DatetimeIndex(expected, tz="US/Eastern"))

    @pytest.mark.parametrize("prefix", ["", "dateutil/"])
    def test_dti_tz_convert_compat_timestamp(self, prefix):
        strdates = ["1/1/2012", "3/1/2012", "4/1/2012"]
        idx = DatetimeIndex(strdates, tz=prefix + "US/Eastern")

        conv = idx[0].tz_convert(prefix + "US/Pacific")
        expected = idx.tz_convert(prefix + "US/Pacific")[0]

        assert conv == expected

    def test_dti_tz_convert_hour_overflow_dst(self):
        # Regression test for GH#13306

        # sorted case US/Eastern -> UTC
        ts = ["2008-05-12 09:50:00", "2008-12-12 09:50:35", "2009-05-12 09:50:32"]
        tt = DatetimeIndex(ts).tz_localize("US/Eastern")
        ut = tt.tz_convert("UTC")
        expected = Index([13, 14, 13], dtype=np.int32)
        tm.assert_index_equal(ut.hour, expected)

        # sorted case UTC -> US/Eastern
        ts = ["2008-05-12 13:50:00", "2008-12-12 14:50:35", "2009-05-12 13:50:32"]
        tt = DatetimeIndex(ts).tz_localize("UTC")
        ut = tt.tz_convert("US/Eastern")
        expected = Index([9, 9, 9], dtype=np.int32)
        tm.assert_index_equal(ut.hour, expected)

        # unsorted case US/Eastern -> UTC
        ts = ["2008-05-12 09:50:00", "2008-12-12 09:50:35", "2008-05-12 09:50:32"]
        tt = DatetimeIndex(ts).tz_localize("US/Eastern")
        ut = tt.tz_convert("UTC")
        expected = Index([13, 14, 13], dtype=np.int32)
        tm.assert_index_equal(ut.hour, expected)

        # unsorted case UTC -> US/Eastern
        ts = ["2008-05-12 13:50:00", "2008-12-12 14:50:35", "2008-05-12 13:50:32"]
        tt = DatetimeIndex(ts).tz_localize("UTC")
        ut = tt.tz_convert("US/Eastern")
        expected = Index([9, 9, 9], dtype=np.int32)
        tm.assert_index_equal(ut.hour, expected)

    @pytest.mark.parametrize("tz", ["US/Eastern", "dateutil/US/Eastern"])
    def test_dti_tz_convert_hour_overflow_dst_timestamps(self, tz):
        # Regression test for GH#13306

        # sorted case US/Eastern -> UTC
        ts = [
            Timestamp("2008-05-12 09:50:00", tz=tz),
            Timestamp("2008-12-12 09:50:35", tz=tz),
            Timestamp("2009-05-12 09:50:32", tz=tz),
        ]
        tt = DatetimeIndex(ts)
        ut = tt.tz_convert("UTC")
        expected = Index([13, 14, 13], dtype=np.int32)
        tm.assert_index_equal(ut.hour, expected)

        # sorted case UTC -> US/Eastern
        ts = [
            Timestamp("2008-05-12 13:50:00", tz="UTC"),
            Timestamp("2008-12-12 14:50:35", tz="UTC"),
            Timestamp("2009-05-12 13:50:32", tz="UTC"),
        ]
        tt = DatetimeIndex(ts)
        ut = tt.tz_convert("US/Eastern")
        expected = Index([9, 9, 9], dtype=np.int32)
        tm.assert_index_equal(ut.hour, expected)

        # unsorted case US/Eastern -> UTC
        ts = [
            Timestamp("2008-05-12 09:50:00", tz=tz),
            Timestamp("2008-12-12 09:50:35", tz=tz),
            Timestamp("2008-05-12 09:50:32", tz=tz),
        ]
        tt = DatetimeIndex(ts)
        ut = tt.tz_convert("UTC")
        expected = Index([13, 14, 13], dtype=np.int32)
        tm.assert_index_equal(ut.hour, expected)

        # unsorted case UTC -> US/Eastern
        ts = [
            Timestamp("2008-05-12 13:50:00", tz="UTC"),
            Timestamp("2008-12-12 14:50:35", tz="UTC"),
            Timestamp("2008-05-12 13:50:32", tz="UTC"),
        ]
        tt = DatetimeIndex(ts)
        ut = tt.tz_convert("US/Eastern")
        expected = Index([9, 9, 9], dtype=np.int32)
        tm.assert_index_equal(ut.hour, expected)

    @pytest.mark.parametrize("freq, n", [("h", 1), ("min", 60), ("s", 3600)])
    def test_dti_tz_convert_trans_pos_plus_1__bug(self, freq, n):
        # Regression test for tslib.tz_convert(vals, tz1, tz2).
        # See GH#4496 for details.
        idx = date_range(datetime(2011, 3, 26, 23), datetime(2011, 3, 27, 1), freq=freq)
        idx = idx.tz_localize("UTC")
        idx = idx.tz_convert("Europe/Moscow")

        expected = np.repeat(np.array([3, 4, 5]), np.array([n, n, 1]))
        tm.assert_index_equal(idx.hour, Index(expected, dtype=np.int32))

    def test_dti_tz_convert_dst(self):
        for freq, n in [("h", 1), ("min", 60), ("s", 3600)]:
            # Start DST
            idx = date_range(
                "2014-03-08 23:00", "2014-03-09 09:00", freq=freq, tz="UTC"
            )
            idx = idx.tz_convert("US/Eastern")
            expected = np.repeat(
                np.array([18, 19, 20, 21, 22, 23, 0, 1, 3, 4, 5]),
                np.array([n, n, n, n, n, n, n, n, n, n, 1]),
            )
            tm.assert_index_equal(idx.hour, Index(expected, dtype=np.int32))

            idx = date_range(
                "2014-03-08 18:00", "2014-03-09 05:00", freq=freq, tz="US/Eastern"
            )
            idx = idx.tz_convert("UTC")
            expected = np.repeat(
                np.array([23, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9]),
                np.array([n, n, n, n, n, n, n, n, n, n, 1]),
            )
            tm.assert_index_equal(idx.hour, Index(expected, dtype=np.int32))

            # End DST
            idx = date_range(
                "2014-11-01 23:00", "2014-11-02 09:00", freq=freq, tz="UTC"
            )
            idx = idx.tz_convert("US/Eastern")
            expected = np.repeat(
                np.array([19, 20, 21, 22, 23, 0, 1, 1, 2, 3, 4]),
                np.array([n, n, n, n, n, n, n, n, n, n, 1]),
            )
            tm.assert_index_equal(idx.hour, Index(expected, dtype=np.int32))

            idx = date_range(
                "2014-11-01 18:00", "2014-11-02 05:00", freq=freq, tz="US/Eastern"
            )
            idx = idx.tz_convert("UTC")
            expected = np.repeat(
                np.array([22, 23, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
                np.array([n, n, n, n, n, n, n, n, n, n, n, n, 1]),
            )
            tm.assert_index_equal(idx.hour, Index(expected, dtype=np.int32))

        # daily
        # Start DST
        idx = date_range("2014-03-08 00:00", "2014-03-09 00:00", freq="D", tz="UTC")
        idx = idx.tz_convert("US/Eastern")
        tm.assert_index_equal(idx.hour, Index([19, 19], dtype=np.int32))

        idx = date_range(
            "2014-03-08 00:00", "2014-03-09 00:00", freq="D", tz="US/Eastern"
        )
        idx = idx.tz_convert("UTC")
        tm.assert_index_equal(idx.hour, Index([5, 5], dtype=np.int32))

        # End DST
        idx = date_range("2014-11-01 00:00", "2014-11-02 00:00", freq="D", tz="UTC")
        idx = idx.tz_convert("US/Eastern")
        tm.assert_index_equal(idx.hour, Index([20, 20], dtype=np.int32))

        idx = date_range(
            "2014-11-01 00:00", "2014-11-02 000:00", freq="D", tz="US/Eastern"
        )
        idx = idx.tz_convert("UTC")
        tm.assert_index_equal(idx.hour, Index([4, 4], dtype=np.int32))

    def test_tz_convert_roundtrip(self, tz_aware_fixture):
        tz = tz_aware_fixture
        idx1 = date_range(start="2014-01-01", end="2014-12-31", freq="ME", tz="UTC")
        exp1 = date_range(start="2014-01-01", end="2014-12-31", freq="ME")

        idx2 = date_range(start="2014-01-01", end="2014-12-31", freq="D", tz="UTC")
        exp2 = date_range(start="2014-01-01", end="2014-12-31", freq="D")

        idx3 = date_range(start="2014-01-01", end="2014-03-01", freq="h", tz="UTC")
        exp3 = date_range(start="2014-01-01", end="2014-03-01", freq="h")

        idx4 = date_range(start="2014-08-01", end="2014-10-31", freq="min", tz="UTC")
        exp4 = date_range(start="2014-08-01", end="2014-10-31", freq="min")

        for idx, expected in [(idx1, exp1), (idx2, exp2), (idx3, exp3), (idx4, exp4)]:
            converted = idx.tz_convert(tz)
            reset = converted.tz_convert(None)
            tm.assert_index_equal(reset, expected)
            assert reset.tzinfo is None
            expected = converted.tz_convert("UTC").tz_localize(None)
            expected = expected._with_freq("infer")
            tm.assert_index_equal(reset, expected)

    def test_dti_tz_convert_tzlocal(self):
        # GH#13583
        # tz_convert doesn't affect to internal
        dti = date_range(start="2001-01-01", end="2001-03-01", tz="UTC")
        dti2 = dti.tz_convert(dateutil.tz.tzlocal())
        tm.assert_numpy_array_equal(dti2.asi8, dti.asi8)

        dti = date_range(start="2001-01-01", end="2001-03-01", tz=dateutil.tz.tzlocal())
        dti2 = dti.tz_convert(None)
        tm.assert_numpy_array_equal(dti2.asi8, dti.asi8)

    @pytest.mark.parametrize(
        "tz",
        [
            "US/Eastern",
            "dateutil/US/Eastern",
            pytz.timezone("US/Eastern"),
            gettz("US/Eastern"),
        ],
    )
    def test_dti_tz_convert_utc_to_local_no_modify(self, tz):
        rng = date_range("3/11/2012", "3/12/2012", freq="h", tz="utc")
        rng_eastern = rng.tz_convert(tz)

        # Values are unmodified
        tm.assert_numpy_array_equal(rng.asi8, rng_eastern.asi8)

        assert timezones.tz_compare(rng_eastern.tz, timezones.maybe_get_tz(tz))

    @pytest.mark.parametrize("tzstr", ["US/Eastern", "dateutil/US/Eastern"])
    def test_tz_convert_unsorted(self, tzstr):
        dr = date_range("2012-03-09", freq="h", periods=100, tz="utc")
        dr = dr.tz_convert(tzstr)

        result = dr[::-1].hour
        exp = dr.hour[::-1]
        tm.assert_almost_equal(result, exp)
