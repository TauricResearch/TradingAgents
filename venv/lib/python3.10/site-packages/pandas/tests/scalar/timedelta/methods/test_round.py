from hypothesis import (
    given,
    strategies as st,
)
import numpy as np
import pytest

from pandas._libs import lib
from pandas._libs.tslibs import iNaT
from pandas.errors import OutOfBoundsTimedelta

from pandas import Timedelta


class TestTimedeltaRound:
    @pytest.mark.parametrize(
        "freq,s1,s2",
        [
            # This first case has s1, s2 being the same as t1,t2 below
            (
                "ns",
                Timedelta("1 days 02:34:56.789123456"),
                Timedelta("-1 days 02:34:56.789123456"),
            ),
            (
                "us",
                Timedelta("1 days 02:34:56.789123000"),
                Timedelta("-1 days 02:34:56.789123000"),
            ),
            (
                "ms",
                Timedelta("1 days 02:34:56.789000000"),
                Timedelta("-1 days 02:34:56.789000000"),
            ),
            ("s", Timedelta("1 days 02:34:57"), Timedelta("-1 days 02:34:57")),
            ("2s", Timedelta("1 days 02:34:56"), Timedelta("-1 days 02:34:56")),
            ("5s", Timedelta("1 days 02:34:55"), Timedelta("-1 days 02:34:55")),
            ("min", Timedelta("1 days 02:35:00"), Timedelta("-1 days 02:35:00")),
            ("12min", Timedelta("1 days 02:36:00"), Timedelta("-1 days 02:36:00")),
            ("h", Timedelta("1 days 03:00:00"), Timedelta("-1 days 03:00:00")),
            ("d", Timedelta("1 days"), Timedelta("-1 days")),
        ],
    )
    def test_round(self, freq, s1, s2):
        t1 = Timedelta("1 days 02:34:56.789123456")
        t2 = Timedelta("-1 days 02:34:56.789123456")

        r1 = t1.round(freq)
        assert r1 == s1
        r2 = t2.round(freq)
        assert r2 == s2

    def test_round_invalid(self):
        t1 = Timedelta("1 days 02:34:56.789123456")

        for freq, msg in [
            ("YE", "<YearEnd: month=12> is a non-fixed frequency"),
            ("ME", "<MonthEnd> is a non-fixed frequency"),
            ("foobar", "Invalid frequency: foobar"),
        ]:
            with pytest.raises(ValueError, match=msg):
                t1.round(freq)

    @pytest.mark.skip_ubsan
    def test_round_implementation_bounds(self):
        # See also: analogous test for Timestamp
        # GH#38964
        result = Timedelta.min.ceil("s")
        expected = Timedelta.min + Timedelta(seconds=1) - Timedelta(145224193)
        assert result == expected

        result = Timedelta.max.floor("s")
        expected = Timedelta.max - Timedelta(854775807)
        assert result == expected

        msg = (
            r"Cannot round -106752 days \+00:12:43.145224193 to freq=s without overflow"
        )
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            Timedelta.min.floor("s")
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            Timedelta.min.round("s")

        msg = "Cannot round 106751 days 23:47:16.854775807 to freq=s without overflow"
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            Timedelta.max.ceil("s")
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            Timedelta.max.round("s")

    @pytest.mark.skip_ubsan
    @given(val=st.integers(min_value=iNaT + 1, max_value=lib.i8max))
    @pytest.mark.parametrize(
        "method", [Timedelta.round, Timedelta.floor, Timedelta.ceil]
    )
    def test_round_sanity(self, val, method):
        cls = Timedelta
        err_cls = OutOfBoundsTimedelta

        val = np.int64(val)
        td = cls(val)

        def checker(ts, nanos, unit):
            # First check that we do raise in cases where we should
            if nanos == 1:
                pass
            else:
                div, mod = divmod(ts._value, nanos)
                diff = int(nanos - mod)
                lb = ts._value - mod
                assert lb <= ts._value  # i.e. no overflows with python ints
                ub = ts._value + diff
                assert ub > ts._value  # i.e. no overflows with python ints

                msg = "without overflow"
                if mod == 0:
                    # We should never be raising in this
                    pass
                elif method is cls.ceil:
                    if ub > cls.max._value:
                        with pytest.raises(err_cls, match=msg):
                            method(ts, unit)
                        return
                elif method is cls.floor:
                    if lb < cls.min._value:
                        with pytest.raises(err_cls, match=msg):
                            method(ts, unit)
                        return
                elif mod >= diff:
                    if ub > cls.max._value:
                        with pytest.raises(err_cls, match=msg):
                            method(ts, unit)
                        return
                elif lb < cls.min._value:
                    with pytest.raises(err_cls, match=msg):
                        method(ts, unit)
                    return

            res = method(ts, unit)

            td = res - ts
            diff = abs(td._value)
            assert diff < nanos
            assert res._value % nanos == 0

            if method is cls.round:
                assert diff <= nanos / 2
            elif method is cls.floor:
                assert res <= ts
            elif method is cls.ceil:
                assert res >= ts

        nanos = 1
        checker(td, nanos, "ns")

        nanos = 1000
        checker(td, nanos, "us")

        nanos = 1_000_000
        checker(td, nanos, "ms")

        nanos = 1_000_000_000
        checker(td, nanos, "s")

        nanos = 60 * 1_000_000_000
        checker(td, nanos, "min")

        nanos = 60 * 60 * 1_000_000_000
        checker(td, nanos, "h")

        nanos = 24 * 60 * 60 * 1_000_000_000
        checker(td, nanos, "D")

    @pytest.mark.parametrize("unit", ["ns", "us", "ms", "s"])
    def test_round_non_nano(self, unit):
        td = Timedelta("1 days 02:34:57").as_unit(unit)

        res = td.round("min")
        assert res == Timedelta("1 days 02:35:00")
        assert res._creso == td._creso

        res = td.floor("min")
        assert res == Timedelta("1 days 02:34:00")
        assert res._creso == td._creso

        res = td.ceil("min")
        assert res == Timedelta("1 days 02:35:00")
        assert res._creso == td._creso
