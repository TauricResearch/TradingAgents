from datetime import timezone

import pytest
import pytz

from pandas._libs.tslibs import timezones

from pandas import (
    DatetimeIndex,
    NaT,
    Series,
    Timestamp,
    date_range,
)
import pandas._testing as tm


class TestTZLocalize:
    def test_series_tz_localize_ambiguous_bool(self):
        # make sure that we are correctly accepting bool values as ambiguous

        # GH#14402
        ts = Timestamp("2015-11-01 01:00:03")
        expected0 = Timestamp("2015-11-01 01:00:03-0500", tz="US/Central")
        expected1 = Timestamp("2015-11-01 01:00:03-0600", tz="US/Central")

        ser = Series([ts])
        expected0 = Series([expected0])
        expected1 = Series([expected1])

        with tm.external_error_raised(pytz.AmbiguousTimeError):
            ser.dt.tz_localize("US/Central")

        result = ser.dt.tz_localize("US/Central", ambiguous=True)
        tm.assert_series_equal(result, expected0)

        result = ser.dt.tz_localize("US/Central", ambiguous=[True])
        tm.assert_series_equal(result, expected0)

        result = ser.dt.tz_localize("US/Central", ambiguous=False)
        tm.assert_series_equal(result, expected1)

        result = ser.dt.tz_localize("US/Central", ambiguous=[False])
        tm.assert_series_equal(result, expected1)

    def test_series_tz_localize_matching_index(self):
        # Matching the index of the result with that of the original series
        # GH 43080
        dt_series = Series(
            date_range(start="2021-01-01T02:00:00", periods=5, freq="1D"),
            index=[2, 6, 7, 8, 11],
            dtype="category",
        )
        result = dt_series.dt.tz_localize("Europe/Berlin")
        expected = Series(
            date_range(
                start="2021-01-01T02:00:00", periods=5, freq="1D", tz="Europe/Berlin"
            ),
            index=[2, 6, 7, 8, 11],
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "method, exp",
        [
            ["shift_forward", "2015-03-29 03:00:00"],
            ["shift_backward", "2015-03-29 01:59:59.999999999"],
            ["NaT", NaT],
            ["raise", None],
            ["foo", "invalid"],
        ],
    )
    def test_tz_localize_nonexistent(self, warsaw, method, exp, unit):
        # GH 8917
        tz = warsaw
        n = 60
        dti = date_range(start="2015-03-29 02:00:00", periods=n, freq="min", unit=unit)
        ser = Series(1, index=dti)
        df = ser.to_frame()

        if method == "raise":
            with tm.external_error_raised(pytz.NonExistentTimeError):
                dti.tz_localize(tz, nonexistent=method)
            with tm.external_error_raised(pytz.NonExistentTimeError):
                ser.tz_localize(tz, nonexistent=method)
            with tm.external_error_raised(pytz.NonExistentTimeError):
                df.tz_localize(tz, nonexistent=method)

        elif exp == "invalid":
            msg = (
                "The nonexistent argument must be one of "
                "'raise', 'NaT', 'shift_forward', 'shift_backward' "
                "or a timedelta object"
            )
            with pytest.raises(ValueError, match=msg):
                dti.tz_localize(tz, nonexistent=method)
            with pytest.raises(ValueError, match=msg):
                ser.tz_localize(tz, nonexistent=method)
            with pytest.raises(ValueError, match=msg):
                df.tz_localize(tz, nonexistent=method)

        else:
            result = ser.tz_localize(tz, nonexistent=method)
            expected = Series(1, index=DatetimeIndex([exp] * n, tz=tz).as_unit(unit))
            tm.assert_series_equal(result, expected)

            result = df.tz_localize(tz, nonexistent=method)
            expected = expected.to_frame()
            tm.assert_frame_equal(result, expected)

            res_index = dti.tz_localize(tz, nonexistent=method)
            tm.assert_index_equal(res_index, expected.index)

    @pytest.mark.parametrize("tzstr", ["US/Eastern", "dateutil/US/Eastern"])
    def test_series_tz_localize_empty(self, tzstr):
        # GH#2248
        ser = Series(dtype=object)

        ser2 = ser.tz_localize("utc")
        assert ser2.index.tz == timezone.utc

        ser2 = ser.tz_localize(tzstr)
        timezones.tz_compare(ser2.index.tz, timezones.maybe_get_tz(tzstr))
