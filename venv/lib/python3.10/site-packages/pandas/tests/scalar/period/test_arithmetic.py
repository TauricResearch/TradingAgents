from datetime import timedelta

import numpy as np
import pytest

from pandas._libs.tslibs.period import IncompatibleFrequency

from pandas import (
    NaT,
    Period,
    Timedelta,
    Timestamp,
    offsets,
)


class TestPeriodArithmetic:
    def test_add_overflow_raises(self):
        # GH#55503
        per = Timestamp.max.to_period("ns")

        msg = "|".join(
            [
                "Python int too large to convert to C long",
                # windows, 32bit linux builds
                "int too big to convert",
            ]
        )
        with pytest.raises(OverflowError, match=msg):
            per + 1

        msg = "value too large"
        with pytest.raises(OverflowError, match=msg):
            per + Timedelta(1)
        with pytest.raises(OverflowError, match=msg):
            per + offsets.Nano(1)

    def test_period_add_integer(self):
        per1 = Period(freq="D", year=2008, month=1, day=1)
        per2 = Period(freq="D", year=2008, month=1, day=2)
        assert per1 + 1 == per2
        assert 1 + per1 == per2

    def test_period_add_invalid(self):
        # GH#4731
        per1 = Period(freq="D", year=2008, month=1, day=1)
        per2 = Period(freq="D", year=2008, month=1, day=2)

        msg = "|".join(
            [
                r"unsupported operand type\(s\)",
                "can only concatenate str",
                "must be str, not Period",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            per1 + "str"
        with pytest.raises(TypeError, match=msg):
            "str" + per1
        with pytest.raises(TypeError, match=msg):
            per1 + per2

    def test_period_sub_period_annual(self):
        left, right = Period("2011", freq="Y"), Period("2007", freq="Y")
        result = left - right
        assert result == 4 * right.freq

        msg = r"Input has different freq=M from Period\(freq=Y-DEC\)"
        with pytest.raises(IncompatibleFrequency, match=msg):
            left - Period("2007-01", freq="M")

    def test_period_sub_period(self):
        per1 = Period("2011-01-01", freq="D")
        per2 = Period("2011-01-15", freq="D")

        off = per1.freq
        assert per1 - per2 == -14 * off
        assert per2 - per1 == 14 * off

        msg = r"Input has different freq=M from Period\(freq=D\)"
        with pytest.raises(IncompatibleFrequency, match=msg):
            per1 - Period("2011-02", freq="M")

    @pytest.mark.parametrize("n", [1, 2, 3, 4])
    def test_sub_n_gt_1_ticks(self, tick_classes, n):
        # GH#23878
        p1 = Period("19910905", freq=tick_classes(n))
        p2 = Period("19920406", freq=tick_classes(n))

        expected = Period(str(p2), freq=p2.freq.base) - Period(
            str(p1), freq=p1.freq.base
        )

        assert (p2 - p1) == expected

    @pytest.mark.parametrize("normalize", [True, False])
    @pytest.mark.parametrize("n", [1, 2, 3, 4])
    @pytest.mark.parametrize(
        "offset, kwd_name",
        [
            (offsets.YearEnd, "month"),
            (offsets.QuarterEnd, "startingMonth"),
            (offsets.MonthEnd, None),
            (offsets.Week, "weekday"),
        ],
    )
    def test_sub_n_gt_1_offsets(self, offset, kwd_name, n, normalize):
        # GH#23878
        kwds = {kwd_name: 3} if kwd_name is not None else {}
        p1_d = "19910905"
        p2_d = "19920406"
        p1 = Period(p1_d, freq=offset(n, normalize, **kwds))
        p2 = Period(p2_d, freq=offset(n, normalize, **kwds))

        expected = Period(p2_d, freq=p2.freq.base) - Period(p1_d, freq=p1.freq.base)

        assert (p2 - p1) == expected

    def test_period_add_offset(self):
        # freq is DateOffset
        for freq in ["Y", "2Y", "3Y"]:
            per = Period("2011", freq=freq)
            exp = Period("2013", freq=freq)
            assert per + offsets.YearEnd(2) == exp
            assert offsets.YearEnd(2) + per == exp

            for off in [
                offsets.YearBegin(2),
                offsets.MonthBegin(1),
                offsets.Minute(),
                np.timedelta64(365, "D"),
                timedelta(365),
            ]:
                msg = "Input has different freq|Input cannot be converted to Period"
                with pytest.raises(IncompatibleFrequency, match=msg):
                    per + off
                with pytest.raises(IncompatibleFrequency, match=msg):
                    off + per

        for freq in ["M", "2M", "3M"]:
            per = Period("2011-03", freq=freq)
            exp = Period("2011-05", freq=freq)
            assert per + offsets.MonthEnd(2) == exp
            assert offsets.MonthEnd(2) + per == exp

            exp = Period("2012-03", freq=freq)
            assert per + offsets.MonthEnd(12) == exp
            assert offsets.MonthEnd(12) + per == exp

            msg = "|".join(
                [
                    "Input has different freq",
                    "Input cannot be converted to Period",
                ]
            )

            for off in [
                offsets.YearBegin(2),
                offsets.MonthBegin(1),
                offsets.Minute(),
                np.timedelta64(365, "D"),
                timedelta(365),
            ]:
                with pytest.raises(IncompatibleFrequency, match=msg):
                    per + off
                with pytest.raises(IncompatibleFrequency, match=msg):
                    off + per

        # freq is Tick
        for freq in ["D", "2D", "3D"]:
            per = Period("2011-04-01", freq=freq)

            exp = Period("2011-04-06", freq=freq)
            assert per + offsets.Day(5) == exp
            assert offsets.Day(5) + per == exp

            exp = Period("2011-04-02", freq=freq)
            assert per + offsets.Hour(24) == exp
            assert offsets.Hour(24) + per == exp

            exp = Period("2011-04-03", freq=freq)
            assert per + np.timedelta64(2, "D") == exp
            assert np.timedelta64(2, "D") + per == exp

            exp = Period("2011-04-02", freq=freq)
            assert per + np.timedelta64(3600 * 24, "s") == exp
            assert np.timedelta64(3600 * 24, "s") + per == exp

            exp = Period("2011-03-30", freq=freq)
            assert per + timedelta(-2) == exp
            assert timedelta(-2) + per == exp

            exp = Period("2011-04-03", freq=freq)
            assert per + timedelta(hours=48) == exp
            assert timedelta(hours=48) + per == exp

            msg = "|".join(
                [
                    "Input has different freq",
                    "Input cannot be converted to Period",
                ]
            )

            for off in [
                offsets.YearBegin(2),
                offsets.MonthBegin(1),
                offsets.Minute(),
                np.timedelta64(4, "h"),
                timedelta(hours=23),
            ]:
                with pytest.raises(IncompatibleFrequency, match=msg):
                    per + off
                with pytest.raises(IncompatibleFrequency, match=msg):
                    off + per

        for freq in ["h", "2h", "3h"]:
            per = Period("2011-04-01 09:00", freq=freq)

            exp = Period("2011-04-03 09:00", freq=freq)
            assert per + offsets.Day(2) == exp
            assert offsets.Day(2) + per == exp

            exp = Period("2011-04-01 12:00", freq=freq)
            assert per + offsets.Hour(3) == exp
            assert offsets.Hour(3) + per == exp

            msg = "cannot use operands with types"
            exp = Period("2011-04-01 12:00", freq=freq)
            assert per + np.timedelta64(3, "h") == exp
            assert np.timedelta64(3, "h") + per == exp

            exp = Period("2011-04-01 10:00", freq=freq)
            assert per + np.timedelta64(3600, "s") == exp
            assert np.timedelta64(3600, "s") + per == exp

            exp = Period("2011-04-01 11:00", freq=freq)
            assert per + timedelta(minutes=120) == exp
            assert timedelta(minutes=120) + per == exp

            exp = Period("2011-04-05 12:00", freq=freq)
            assert per + timedelta(days=4, minutes=180) == exp
            assert timedelta(days=4, minutes=180) + per == exp

            msg = "|".join(
                [
                    "Input has different freq",
                    "Input cannot be converted to Period",
                ]
            )

            for off in [
                offsets.YearBegin(2),
                offsets.MonthBegin(1),
                offsets.Minute(),
                np.timedelta64(3200, "s"),
                timedelta(hours=23, minutes=30),
            ]:
                with pytest.raises(IncompatibleFrequency, match=msg):
                    per + off
                with pytest.raises(IncompatibleFrequency, match=msg):
                    off + per

    def test_period_sub_offset(self):
        # freq is DateOffset
        msg = "|".join(
            [
                "Input has different freq",
                "Input cannot be converted to Period",
            ]
        )

        for freq in ["Y", "2Y", "3Y"]:
            per = Period("2011", freq=freq)
            assert per - offsets.YearEnd(2) == Period("2009", freq=freq)

            for off in [
                offsets.YearBegin(2),
                offsets.MonthBegin(1),
                offsets.Minute(),
                np.timedelta64(365, "D"),
                timedelta(365),
            ]:
                with pytest.raises(IncompatibleFrequency, match=msg):
                    per - off

        for freq in ["M", "2M", "3M"]:
            per = Period("2011-03", freq=freq)
            assert per - offsets.MonthEnd(2) == Period("2011-01", freq=freq)
            assert per - offsets.MonthEnd(12) == Period("2010-03", freq=freq)

            for off in [
                offsets.YearBegin(2),
                offsets.MonthBegin(1),
                offsets.Minute(),
                np.timedelta64(365, "D"),
                timedelta(365),
            ]:
                with pytest.raises(IncompatibleFrequency, match=msg):
                    per - off

        # freq is Tick
        for freq in ["D", "2D", "3D"]:
            per = Period("2011-04-01", freq=freq)
            assert per - offsets.Day(5) == Period("2011-03-27", freq=freq)
            assert per - offsets.Hour(24) == Period("2011-03-31", freq=freq)
            assert per - np.timedelta64(2, "D") == Period("2011-03-30", freq=freq)
            assert per - np.timedelta64(3600 * 24, "s") == Period(
                "2011-03-31", freq=freq
            )
            assert per - timedelta(-2) == Period("2011-04-03", freq=freq)
            assert per - timedelta(hours=48) == Period("2011-03-30", freq=freq)

            for off in [
                offsets.YearBegin(2),
                offsets.MonthBegin(1),
                offsets.Minute(),
                np.timedelta64(4, "h"),
                timedelta(hours=23),
            ]:
                with pytest.raises(IncompatibleFrequency, match=msg):
                    per - off

        for freq in ["h", "2h", "3h"]:
            per = Period("2011-04-01 09:00", freq=freq)
            assert per - offsets.Day(2) == Period("2011-03-30 09:00", freq=freq)
            assert per - offsets.Hour(3) == Period("2011-04-01 06:00", freq=freq)
            assert per - np.timedelta64(3, "h") == Period("2011-04-01 06:00", freq=freq)
            assert per - np.timedelta64(3600, "s") == Period(
                "2011-04-01 08:00", freq=freq
            )
            assert per - timedelta(minutes=120) == Period("2011-04-01 07:00", freq=freq)
            assert per - timedelta(days=4, minutes=180) == Period(
                "2011-03-28 06:00", freq=freq
            )

            for off in [
                offsets.YearBegin(2),
                offsets.MonthBegin(1),
                offsets.Minute(),
                np.timedelta64(3200, "s"),
                timedelta(hours=23, minutes=30),
            ]:
                with pytest.raises(IncompatibleFrequency, match=msg):
                    per - off

    @pytest.mark.parametrize("freq", ["M", "2M", "3M"])
    def test_period_addsub_nat(self, freq):
        # GH#13071
        per = Period("2011-01", freq=freq)

        # For subtraction, NaT is treated as another Period object
        assert NaT - per is NaT
        assert per - NaT is NaT

        # For addition, NaT is treated as offset-like
        assert NaT + per is NaT
        assert per + NaT is NaT

    @pytest.mark.parametrize("unit", ["ns", "us", "ms", "s", "m"])
    def test_period_add_sub_td64_nat(self, unit):
        # GH#47196
        per = Period("2022-06-01", "D")
        nat = np.timedelta64("NaT", unit)

        assert per + nat is NaT
        assert nat + per is NaT
        assert per - nat is NaT

        with pytest.raises(TypeError, match="unsupported operand"):
            nat - per

    def test_period_ops_offset(self):
        per = Period("2011-04-01", freq="D")
        result = per + offsets.Day()
        exp = Period("2011-04-02", freq="D")
        assert result == exp

        result = per - offsets.Day(2)
        exp = Period("2011-03-30", freq="D")
        assert result == exp

        msg = r"Input cannot be converted to Period\(freq=D\)"
        with pytest.raises(IncompatibleFrequency, match=msg):
            per + offsets.Hour(2)

        with pytest.raises(IncompatibleFrequency, match=msg):
            per - offsets.Hour(2)

    def test_period_add_timestamp_raises(self):
        # GH#17983
        ts = Timestamp("2017")
        per = Period("2017", freq="M")

        msg = r"unsupported operand type\(s\) for \+: 'Timestamp' and 'Period'"
        with pytest.raises(TypeError, match=msg):
            ts + per

        msg = r"unsupported operand type\(s\) for \+: 'Period' and 'Timestamp'"
        with pytest.raises(TypeError, match=msg):
            per + ts


class TestPeriodComparisons:
    def test_period_comparison_same_freq(self):
        jan = Period("2000-01", "M")
        feb = Period("2000-02", "M")

        assert not jan == feb
        assert jan != feb
        assert jan < feb
        assert jan <= feb
        assert not jan > feb
        assert not jan >= feb

    def test_period_comparison_same_period_different_object(self):
        # Separate Period objects for the same period
        left = Period("2000-01", "M")
        right = Period("2000-01", "M")

        assert left == right
        assert left >= right
        assert left <= right
        assert not left < right
        assert not left > right

    def test_period_comparison_mismatched_freq(self):
        jan = Period("2000-01", "M")
        day = Period("2012-01-01", "D")

        assert not jan == day
        assert jan != day
        msg = r"Input has different freq=D from Period\(freq=M\)"
        with pytest.raises(IncompatibleFrequency, match=msg):
            jan < day
        with pytest.raises(IncompatibleFrequency, match=msg):
            jan <= day
        with pytest.raises(IncompatibleFrequency, match=msg):
            jan > day
        with pytest.raises(IncompatibleFrequency, match=msg):
            jan >= day

    def test_period_comparison_invalid_type(self):
        jan = Period("2000-01", "M")

        assert not jan == 1
        assert jan != 1

        int_or_per = "'(Period|int)'"
        msg = f"not supported between instances of {int_or_per} and {int_or_per}"
        for left, right in [(jan, 1), (1, jan)]:
            with pytest.raises(TypeError, match=msg):
                left > right
            with pytest.raises(TypeError, match=msg):
                left >= right
            with pytest.raises(TypeError, match=msg):
                left < right
            with pytest.raises(TypeError, match=msg):
                left <= right

    def test_period_comparison_nat(self):
        per = Period("2011-01-01", freq="D")

        ts = Timestamp("2011-01-01")
        # confirm Period('NaT') work identical with Timestamp('NaT')
        for left, right in [
            (NaT, per),
            (per, NaT),
            (NaT, ts),
            (ts, NaT),
        ]:
            assert not left < right
            assert not left > right
            assert not left == right
            assert left != right
            assert not left <= right
            assert not left >= right

    @pytest.mark.parametrize(
        "zerodim_arr, expected",
        ((np.array(0), False), (np.array(Period("2000-01", "M")), True)),
    )
    def test_period_comparison_numpy_zerodim_arr(self, zerodim_arr, expected):
        per = Period("2000-01", "M")

        assert (per == zerodim_arr) is expected
        assert (zerodim_arr == per) is expected
