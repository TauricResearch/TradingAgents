import pytest

from pandas._libs.tslibs import to_offset
from pandas._libs.tslibs.offsets import INVALID_FREQ_ERR_MSG

from pandas import (
    DatetimeIndex,
    Timestamp,
    date_range,
)
import pandas._testing as tm


class TestDatetimeIndexRound:
    def test_round_daily(self):
        dti = date_range("20130101 09:10:11", periods=5)
        result = dti.round("D")
        expected = date_range("20130101", periods=5)
        tm.assert_index_equal(result, expected)

        dti = dti.tz_localize("UTC").tz_convert("US/Eastern")
        result = dti.round("D")
        expected = date_range("20130101", periods=5).tz_localize("US/Eastern")
        tm.assert_index_equal(result, expected)

        result = dti.round("s")
        tm.assert_index_equal(result, dti)

    @pytest.mark.parametrize(
        "freq, error_msg",
        [
            ("YE", "<YearEnd: month=12> is a non-fixed frequency"),
            ("ME", "<MonthEnd> is a non-fixed frequency"),
            ("foobar", "Invalid frequency: foobar"),
        ],
    )
    def test_round_invalid(self, freq, error_msg):
        dti = date_range("20130101 09:10:11", periods=5)
        dti = dti.tz_localize("UTC").tz_convert("US/Eastern")
        with pytest.raises(ValueError, match=error_msg):
            dti.round(freq)

    def test_round(self, tz_naive_fixture, unit):
        tz = tz_naive_fixture
        rng = date_range(start="2016-01-01", periods=5, freq="30Min", tz=tz, unit=unit)
        elt = rng[1]

        expected_rng = DatetimeIndex(
            [
                Timestamp("2016-01-01 00:00:00", tz=tz),
                Timestamp("2016-01-01 00:00:00", tz=tz),
                Timestamp("2016-01-01 01:00:00", tz=tz),
                Timestamp("2016-01-01 02:00:00", tz=tz),
                Timestamp("2016-01-01 02:00:00", tz=tz),
            ]
        ).as_unit(unit)
        expected_elt = expected_rng[1]

        result = rng.round(freq="h")
        tm.assert_index_equal(result, expected_rng)
        assert elt.round(freq="h") == expected_elt

        msg = INVALID_FREQ_ERR_MSG
        with pytest.raises(ValueError, match=msg):
            rng.round(freq="foo")
        with pytest.raises(ValueError, match=msg):
            elt.round(freq="foo")

        msg = "<MonthEnd> is a non-fixed frequency"
        with pytest.raises(ValueError, match=msg):
            rng.round(freq="ME")
        with pytest.raises(ValueError, match=msg):
            elt.round(freq="ME")

    def test_round2(self, tz_naive_fixture):
        tz = tz_naive_fixture
        # GH#14440 & GH#15578
        index = DatetimeIndex(["2016-10-17 12:00:00.0015"], tz=tz).as_unit("ns")
        result = index.round("ms")
        expected = DatetimeIndex(["2016-10-17 12:00:00.002000"], tz=tz).as_unit("ns")
        tm.assert_index_equal(result, expected)

        for freq in ["us", "ns"]:
            tm.assert_index_equal(index, index.round(freq))

    def test_round3(self, tz_naive_fixture):
        tz = tz_naive_fixture
        index = DatetimeIndex(["2016-10-17 12:00:00.00149"], tz=tz).as_unit("ns")
        result = index.round("ms")
        expected = DatetimeIndex(["2016-10-17 12:00:00.001000"], tz=tz).as_unit("ns")
        tm.assert_index_equal(result, expected)

    def test_round4(self, tz_naive_fixture):
        index = DatetimeIndex(["2016-10-17 12:00:00.001501031"], dtype="M8[ns]")
        result = index.round("10ns")
        expected = DatetimeIndex(["2016-10-17 12:00:00.001501030"], dtype="M8[ns]")
        tm.assert_index_equal(result, expected)

        ts = "2016-10-17 12:00:00.001501031"
        dti = DatetimeIndex([ts], dtype="M8[ns]")
        with tm.assert_produces_warning(False):
            dti.round("1010ns")

    def test_no_rounding_occurs(self, tz_naive_fixture):
        # GH 21262
        tz = tz_naive_fixture
        rng = date_range(start="2016-01-01", periods=5, freq="2Min", tz=tz)

        expected_rng = DatetimeIndex(
            [
                Timestamp("2016-01-01 00:00:00", tz=tz),
                Timestamp("2016-01-01 00:02:00", tz=tz),
                Timestamp("2016-01-01 00:04:00", tz=tz),
                Timestamp("2016-01-01 00:06:00", tz=tz),
                Timestamp("2016-01-01 00:08:00", tz=tz),
            ]
        ).as_unit("ns")

        result = rng.round(freq="2min")
        tm.assert_index_equal(result, expected_rng)

    @pytest.mark.parametrize(
        "test_input, rounder, freq, expected",
        [
            (["2117-01-01 00:00:45"], "floor", "15s", ["2117-01-01 00:00:45"]),
            (["2117-01-01 00:00:45"], "ceil", "15s", ["2117-01-01 00:00:45"]),
            (
                ["2117-01-01 00:00:45.000000012"],
                "floor",
                "10ns",
                ["2117-01-01 00:00:45.000000010"],
            ),
            (
                ["1823-01-01 00:00:01.000000012"],
                "ceil",
                "10ns",
                ["1823-01-01 00:00:01.000000020"],
            ),
            (["1823-01-01 00:00:01"], "floor", "1s", ["1823-01-01 00:00:01"]),
            (["1823-01-01 00:00:01"], "ceil", "1s", ["1823-01-01 00:00:01"]),
            (["2018-01-01 00:15:00"], "ceil", "15min", ["2018-01-01 00:15:00"]),
            (["2018-01-01 00:15:00"], "floor", "15min", ["2018-01-01 00:15:00"]),
            (["1823-01-01 03:00:00"], "ceil", "3h", ["1823-01-01 03:00:00"]),
            (["1823-01-01 03:00:00"], "floor", "3h", ["1823-01-01 03:00:00"]),
            (
                ("NaT", "1823-01-01 00:00:01"),
                "floor",
                "1s",
                ("NaT", "1823-01-01 00:00:01"),
            ),
            (
                ("NaT", "1823-01-01 00:00:01"),
                "ceil",
                "1s",
                ("NaT", "1823-01-01 00:00:01"),
            ),
        ],
    )
    def test_ceil_floor_edge(self, test_input, rounder, freq, expected):
        dt = DatetimeIndex(list(test_input))
        func = getattr(dt, rounder)
        result = func(freq)
        expected = DatetimeIndex(list(expected))
        assert expected.equals(result)

    @pytest.mark.parametrize(
        "start, index_freq, periods",
        [("2018-01-01", "12h", 25), ("2018-01-01 0:0:0.124999", "1ns", 1000)],
    )
    @pytest.mark.parametrize(
        "round_freq",
        [
            "2ns",
            "3ns",
            "4ns",
            "5ns",
            "6ns",
            "7ns",
            "250ns",
            "500ns",
            "750ns",
            "1us",
            "19us",
            "250us",
            "500us",
            "750us",
            "1s",
            "2s",
            "3s",
            "12h",
            "1D",
        ],
    )
    def test_round_int64(self, start, index_freq, periods, round_freq):
        dt = date_range(start=start, freq=index_freq, periods=periods)
        unit = to_offset(round_freq).nanos

        # test floor
        result = dt.floor(round_freq)
        diff = dt.asi8 - result.asi8
        mod = result.asi8 % unit
        assert (mod == 0).all(), f"floor not a {round_freq} multiple"
        assert (0 <= diff).all() and (diff < unit).all(), "floor error"

        # test ceil
        result = dt.ceil(round_freq)
        diff = result.asi8 - dt.asi8
        mod = result.asi8 % unit
        assert (mod == 0).all(), f"ceil not a {round_freq} multiple"
        assert (0 <= diff).all() and (diff < unit).all(), "ceil error"

        # test round
        result = dt.round(round_freq)
        diff = abs(result.asi8 - dt.asi8)
        mod = result.asi8 % unit
        assert (mod == 0).all(), f"round not a {round_freq} multiple"
        assert (diff <= unit // 2).all(), "round error"
        if unit % 2 == 0:
            assert (
                result.asi8[diff == unit // 2] % 2 == 0
            ).all(), "round half to even error"
