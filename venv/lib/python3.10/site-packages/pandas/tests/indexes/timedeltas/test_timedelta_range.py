import numpy as np
import pytest

from pandas import (
    Timedelta,
    TimedeltaIndex,
    timedelta_range,
    to_timedelta,
)
import pandas._testing as tm

from pandas.tseries.offsets import (
    Day,
    Second,
)


class TestTimedeltas:
    def test_timedelta_range_unit(self):
        # GH#49824
        tdi = timedelta_range("0 Days", periods=10, freq="100000D", unit="s")
        exp_arr = (np.arange(10, dtype="i8") * 100_000).view("m8[D]").astype("m8[s]")
        tm.assert_numpy_array_equal(tdi.to_numpy(), exp_arr)

    def test_timedelta_range(self):
        expected = to_timedelta(np.arange(5), unit="D")
        result = timedelta_range("0 days", periods=5, freq="D")
        tm.assert_index_equal(result, expected)

        expected = to_timedelta(np.arange(11), unit="D")
        result = timedelta_range("0 days", "10 days", freq="D")
        tm.assert_index_equal(result, expected)

        expected = to_timedelta(np.arange(5), unit="D") + Second(2) + Day()
        result = timedelta_range("1 days, 00:00:02", "5 days, 00:00:02", freq="D")
        tm.assert_index_equal(result, expected)

        expected = to_timedelta([1, 3, 5, 7, 9], unit="D") + Second(2)
        result = timedelta_range("1 days, 00:00:02", periods=5, freq="2D")
        tm.assert_index_equal(result, expected)

        expected = to_timedelta(np.arange(50), unit="min") * 30
        result = timedelta_range("0 days", freq="30min", periods=50)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "depr_unit, unit",
        [
            ("H", "hour"),
            ("T", "minute"),
            ("t", "minute"),
            ("S", "second"),
            ("L", "millisecond"),
            ("l", "millisecond"),
            ("U", "microsecond"),
            ("u", "microsecond"),
            ("N", "nanosecond"),
            ("n", "nanosecond"),
        ],
    )
    def test_timedelta_units_H_T_S_L_U_N_deprecated(self, depr_unit, unit):
        # GH#52536
        depr_msg = (
            f"'{depr_unit}' is deprecated and will be removed in a future version."
        )

        expected = to_timedelta(np.arange(5), unit=unit)
        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            result = to_timedelta(np.arange(5), unit=depr_unit)
            tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "periods, freq", [(3, "2D"), (5, "D"), (6, "19h12min"), (7, "16h"), (9, "12h")]
    )
    def test_linspace_behavior(self, periods, freq):
        # GH 20976
        result = timedelta_range(start="0 days", end="4 days", periods=periods)
        expected = timedelta_range(start="0 days", end="4 days", freq=freq)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("msg_freq, freq", [("H", "19H12min"), ("T", "19h12T")])
    def test_timedelta_range_H_T_deprecated(self, freq, msg_freq):
        # GH#52536
        msg = f"'{msg_freq}' is deprecated and will be removed in a future version."

        result = timedelta_range(start="0 days", end="4 days", periods=6)
        with tm.assert_produces_warning(FutureWarning, match=msg):
            expected = timedelta_range(start="0 days", end="4 days", freq=freq)
        tm.assert_index_equal(result, expected)

    def test_errors(self):
        # not enough params
        msg = (
            "Of the four parameters: start, end, periods, and freq, "
            "exactly three must be specified"
        )
        with pytest.raises(ValueError, match=msg):
            timedelta_range(start="0 days")

        with pytest.raises(ValueError, match=msg):
            timedelta_range(end="5 days")

        with pytest.raises(ValueError, match=msg):
            timedelta_range(periods=2)

        with pytest.raises(ValueError, match=msg):
            timedelta_range()

        # too many params
        with pytest.raises(ValueError, match=msg):
            timedelta_range(start="0 days", end="5 days", periods=10, freq="h")

    @pytest.mark.parametrize(
        "start, end, freq, expected_periods",
        [
            ("1D", "10D", "2D", (10 - 1) // 2 + 1),
            ("2D", "30D", "3D", (30 - 2) // 3 + 1),
            ("2s", "50s", "5s", (50 - 2) // 5 + 1),
            # tests that worked before GH 33498:
            ("4D", "16D", "3D", (16 - 4) // 3 + 1),
            ("8D", "16D", "40s", (16 * 3600 * 24 - 8 * 3600 * 24) // 40 + 1),
        ],
    )
    def test_timedelta_range_freq_divide_end(self, start, end, freq, expected_periods):
        # GH 33498 only the cases where `(end % freq) == 0` used to fail
        res = timedelta_range(start=start, end=end, freq=freq)
        assert Timedelta(start) == res[0]
        assert Timedelta(end) >= res[-1]
        assert len(res) == expected_periods

    def test_timedelta_range_infer_freq(self):
        # https://github.com/pandas-dev/pandas/issues/35897
        result = timedelta_range("0s", "1s", periods=31)
        assert result.freq is None

    @pytest.mark.parametrize(
        "freq_depr, start, end, expected_values, expected_freq",
        [
            (
                "3.5S",
                "05:03:01",
                "05:03:10",
                ["0 days 05:03:01", "0 days 05:03:04.500000", "0 days 05:03:08"],
                "3500ms",
            ),
            (
                "2.5T",
                "5 hours",
                "5 hours 8 minutes",
                [
                    "0 days 05:00:00",
                    "0 days 05:02:30",
                    "0 days 05:05:00",
                    "0 days 05:07:30",
                ],
                "150s",
            ),
        ],
    )
    def test_timedelta_range_deprecated_freq(
        self, freq_depr, start, end, expected_values, expected_freq
    ):
        # GH#52536
        msg = (
            f"'{freq_depr[-1]}' is deprecated and will be removed in a future version."
        )

        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = timedelta_range(start=start, end=end, freq=freq_depr)
        expected = TimedeltaIndex(
            expected_values, dtype="timedelta64[ns]", freq=expected_freq
        )
        tm.assert_index_equal(result, expected)
