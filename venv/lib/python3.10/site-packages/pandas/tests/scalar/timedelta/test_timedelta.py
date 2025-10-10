""" test the scalar Timedelta """
from datetime import timedelta
import sys

from hypothesis import (
    given,
    strategies as st,
)
import numpy as np
import pytest

from pandas._libs import lib
from pandas._libs.tslibs import (
    NaT,
    iNaT,
)
from pandas._libs.tslibs.dtypes import NpyDatetimeUnit
from pandas.errors import OutOfBoundsTimedelta

from pandas import (
    Timedelta,
    to_timedelta,
)
import pandas._testing as tm


class TestNonNano:
    @pytest.fixture(params=["s", "ms", "us"])
    def unit_str(self, request):
        return request.param

    @pytest.fixture
    def unit(self, unit_str):
        # 7, 8, 9 correspond to second, millisecond, and microsecond, respectively
        attr = f"NPY_FR_{unit_str}"
        return getattr(NpyDatetimeUnit, attr).value

    @pytest.fixture
    def val(self, unit):
        # microsecond that would be just out of bounds for nano
        us = 9223372800000000
        if unit == NpyDatetimeUnit.NPY_FR_us.value:
            value = us
        elif unit == NpyDatetimeUnit.NPY_FR_ms.value:
            value = us // 1000
        else:
            value = us // 1_000_000
        return value

    @pytest.fixture
    def td(self, unit, val):
        return Timedelta._from_value_and_reso(val, unit)

    def test_from_value_and_reso(self, unit, val):
        # Just checking that the fixture is giving us what we asked for
        td = Timedelta._from_value_and_reso(val, unit)
        assert td._value == val
        assert td._creso == unit
        assert td.days == 106752

    def test_unary_non_nano(self, td, unit):
        assert abs(td)._creso == unit
        assert (-td)._creso == unit
        assert (+td)._creso == unit

    def test_sub_preserves_reso(self, td, unit):
        res = td - td
        expected = Timedelta._from_value_and_reso(0, unit)
        assert res == expected
        assert res._creso == unit

    def test_mul_preserves_reso(self, td, unit):
        # The td fixture should always be far from the implementation
        #  bound, so doubling does not risk overflow.
        res = td * 2
        assert res._value == td._value * 2
        assert res._creso == unit

    def test_cmp_cross_reso(self, td):
        # numpy gets this wrong because of silent overflow
        other = Timedelta(days=106751, unit="ns")
        assert other < td
        assert td > other
        assert not other == td
        assert td != other

    def test_to_pytimedelta(self, td):
        res = td.to_pytimedelta()
        expected = timedelta(days=106752)
        assert type(res) is timedelta
        assert res == expected

    def test_to_timedelta64(self, td, unit):
        for res in [td.to_timedelta64(), td.to_numpy(), td.asm8]:
            assert isinstance(res, np.timedelta64)
            assert res.view("i8") == td._value
            if unit == NpyDatetimeUnit.NPY_FR_s.value:
                assert res.dtype == "m8[s]"
            elif unit == NpyDatetimeUnit.NPY_FR_ms.value:
                assert res.dtype == "m8[ms]"
            elif unit == NpyDatetimeUnit.NPY_FR_us.value:
                assert res.dtype == "m8[us]"

    def test_truediv_timedeltalike(self, td):
        assert td / td == 1
        assert (2.5 * td) / td == 2.5

        other = Timedelta(td._value)
        msg = "Cannot cast 106752 days 00:00:00 to unit='ns' without overflow."
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            td / other

        # Timedelta(other.to_pytimedelta()) has microsecond resolution,
        #  so the division doesn't require casting all the way to nanos,
        #  so succeeds
        res = other.to_pytimedelta() / td
        expected = other.to_pytimedelta() / td.to_pytimedelta()
        assert res == expected

        # if there's no overflow, we cast to the higher reso
        left = Timedelta._from_value_and_reso(50, NpyDatetimeUnit.NPY_FR_us.value)
        right = Timedelta._from_value_and_reso(50, NpyDatetimeUnit.NPY_FR_ms.value)
        result = left / right
        assert result == 0.001

        result = right / left
        assert result == 1000

    def test_truediv_numeric(self, td):
        assert td / np.nan is NaT

        res = td / 2
        assert res._value == td._value / 2
        assert res._creso == td._creso

        res = td / 2.0
        assert res._value == td._value / 2
        assert res._creso == td._creso

    def test_floordiv_timedeltalike(self, td):
        assert td // td == 1
        assert (2.5 * td) // td == 2

        other = Timedelta(td._value)
        msg = "Cannot cast 106752 days 00:00:00 to unit='ns' without overflow"
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            td // other

        # Timedelta(other.to_pytimedelta()) has microsecond resolution,
        #  so the floordiv doesn't require casting all the way to nanos,
        #  so succeeds
        res = other.to_pytimedelta() // td
        assert res == 0

        # if there's no overflow, we cast to the higher reso
        left = Timedelta._from_value_and_reso(50050, NpyDatetimeUnit.NPY_FR_us.value)
        right = Timedelta._from_value_and_reso(50, NpyDatetimeUnit.NPY_FR_ms.value)
        result = left // right
        assert result == 1
        result = right // left
        assert result == 0

    def test_floordiv_numeric(self, td):
        assert td // np.nan is NaT

        res = td // 2
        assert res._value == td._value // 2
        assert res._creso == td._creso

        res = td // 2.0
        assert res._value == td._value // 2
        assert res._creso == td._creso

        assert td // np.array(np.nan) is NaT

        res = td // np.array(2)
        assert res._value == td._value // 2
        assert res._creso == td._creso

        res = td // np.array(2.0)
        assert res._value == td._value // 2
        assert res._creso == td._creso

    def test_addsub_mismatched_reso(self, td):
        # need to cast to since td is out of bounds for ns, so
        #  so we would raise OverflowError without casting
        other = Timedelta(days=1).as_unit("us")

        # td is out of bounds for ns
        result = td + other
        assert result._creso == other._creso
        assert result.days == td.days + 1

        result = other + td
        assert result._creso == other._creso
        assert result.days == td.days + 1

        result = td - other
        assert result._creso == other._creso
        assert result.days == td.days - 1

        result = other - td
        assert result._creso == other._creso
        assert result.days == 1 - td.days

        other2 = Timedelta(500)
        msg = "Cannot cast 106752 days 00:00:00 to unit='ns' without overflow"
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            td + other2
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            other2 + td
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            td - other2
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            other2 - td

    def test_min(self, td):
        assert td.min <= td
        assert td.min._creso == td._creso
        assert td.min._value == NaT._value + 1

    def test_max(self, td):
        assert td.max >= td
        assert td.max._creso == td._creso
        assert td.max._value == np.iinfo(np.int64).max

    def test_resolution(self, td):
        expected = Timedelta._from_value_and_reso(1, td._creso)
        result = td.resolution
        assert result == expected
        assert result._creso == expected._creso

    def test_hash(self) -> None:
        # GH#54037
        second_resolution_max = Timedelta(0).as_unit("s").max

        assert hash(second_resolution_max)


def test_timedelta_class_min_max_resolution():
    # when accessed on the class (as opposed to an instance), we default
    #  to nanoseconds
    assert Timedelta.min == Timedelta(NaT._value + 1)
    assert Timedelta.min._creso == NpyDatetimeUnit.NPY_FR_ns.value

    assert Timedelta.max == Timedelta(np.iinfo(np.int64).max)
    assert Timedelta.max._creso == NpyDatetimeUnit.NPY_FR_ns.value

    assert Timedelta.resolution == Timedelta(1)
    assert Timedelta.resolution._creso == NpyDatetimeUnit.NPY_FR_ns.value


class TestTimedeltaUnaryOps:
    def test_invert(self):
        td = Timedelta(10, unit="d")

        msg = "bad operand type for unary ~"
        with pytest.raises(TypeError, match=msg):
            ~td

        # check this matches pytimedelta and timedelta64
        with pytest.raises(TypeError, match=msg):
            ~(td.to_pytimedelta())

        umsg = "ufunc 'invert' not supported for the input types"
        with pytest.raises(TypeError, match=umsg):
            ~(td.to_timedelta64())

    def test_unary_ops(self):
        td = Timedelta(10, unit="d")

        # __neg__, __pos__
        assert -td == Timedelta(-10, unit="d")
        assert -td == Timedelta("-10d")
        assert +td == Timedelta(10, unit="d")

        # __abs__, __abs__(__neg__)
        assert abs(td) == td
        assert abs(-td) == td
        assert abs(-td) == Timedelta("10d")


class TestTimedeltas:
    @pytest.mark.parametrize(
        "unit, value, expected",
        [
            ("us", 9.999, 9999),
            ("ms", 9.999999, 9999999),
            ("s", 9.999999999, 9999999999),
        ],
    )
    def test_rounding_on_int_unit_construction(self, unit, value, expected):
        # GH 12690
        result = Timedelta(value, unit=unit)
        assert result._value == expected
        result = Timedelta(str(value) + unit)
        assert result._value == expected

    def test_total_seconds_scalar(self):
        # see gh-10939
        rng = Timedelta("1 days, 10:11:12.100123456")
        expt = 1 * 86400 + 10 * 3600 + 11 * 60 + 12 + 100123456.0 / 1e9
        tm.assert_almost_equal(rng.total_seconds(), expt)

        rng = Timedelta(np.nan)
        assert np.isnan(rng.total_seconds())

    def test_conversion(self):
        for td in [Timedelta(10, unit="d"), Timedelta("1 days, 10:11:12.012345")]:
            pydt = td.to_pytimedelta()
            assert td == Timedelta(pydt)
            assert td == pydt
            assert isinstance(pydt, timedelta) and not isinstance(pydt, Timedelta)

            assert td == np.timedelta64(td._value, "ns")
            td64 = td.to_timedelta64()

            assert td64 == np.timedelta64(td._value, "ns")
            assert td == td64

            assert isinstance(td64, np.timedelta64)

        # this is NOT equal and cannot be roundtripped (because of the nanos)
        td = Timedelta("1 days, 10:11:12.012345678")
        assert td != td.to_pytimedelta()

    def test_fields(self):
        def check(value):
            # that we are int
            assert isinstance(value, int)

        # compat to datetime.timedelta
        rng = to_timedelta("1 days, 10:11:12")
        assert rng.days == 1
        assert rng.seconds == 10 * 3600 + 11 * 60 + 12
        assert rng.microseconds == 0
        assert rng.nanoseconds == 0

        msg = "'Timedelta' object has no attribute '{}'"
        with pytest.raises(AttributeError, match=msg.format("hours")):
            rng.hours
        with pytest.raises(AttributeError, match=msg.format("minutes")):
            rng.minutes
        with pytest.raises(AttributeError, match=msg.format("milliseconds")):
            rng.milliseconds

        # GH 10050
        check(rng.days)
        check(rng.seconds)
        check(rng.microseconds)
        check(rng.nanoseconds)

        td = Timedelta("-1 days, 10:11:12")
        assert abs(td) == Timedelta("13:48:48")
        assert str(td) == "-1 days +10:11:12"
        assert -td == Timedelta("0 days 13:48:48")
        assert -Timedelta("-1 days, 10:11:12")._value == 49728000000000
        assert Timedelta("-1 days, 10:11:12")._value == -49728000000000

        rng = to_timedelta("-1 days, 10:11:12.100123456")
        assert rng.days == -1
        assert rng.seconds == 10 * 3600 + 11 * 60 + 12
        assert rng.microseconds == 100 * 1000 + 123
        assert rng.nanoseconds == 456
        msg = "'Timedelta' object has no attribute '{}'"
        with pytest.raises(AttributeError, match=msg.format("hours")):
            rng.hours
        with pytest.raises(AttributeError, match=msg.format("minutes")):
            rng.minutes
        with pytest.raises(AttributeError, match=msg.format("milliseconds")):
            rng.milliseconds

        # components
        tup = to_timedelta(-1, "us").components
        assert tup.days == -1
        assert tup.hours == 23
        assert tup.minutes == 59
        assert tup.seconds == 59
        assert tup.milliseconds == 999
        assert tup.microseconds == 999
        assert tup.nanoseconds == 0

        # GH 10050
        check(tup.days)
        check(tup.hours)
        check(tup.minutes)
        check(tup.seconds)
        check(tup.milliseconds)
        check(tup.microseconds)
        check(tup.nanoseconds)

        tup = Timedelta("-1 days 1 us").components
        assert tup.days == -2
        assert tup.hours == 23
        assert tup.minutes == 59
        assert tup.seconds == 59
        assert tup.milliseconds == 999
        assert tup.microseconds == 999
        assert tup.nanoseconds == 0

    # TODO: this is a test of to_timedelta string parsing
    def test_iso_conversion(self):
        # GH #21877
        expected = Timedelta(1, unit="s")
        assert to_timedelta("P0DT0H0M1S") == expected

    # TODO: this is a test of to_timedelta returning NaT
    def test_nat_converters(self):
        result = to_timedelta("nat").to_numpy()
        assert result.dtype.kind == "M"
        assert result.astype("int64") == iNaT

        result = to_timedelta("nan").to_numpy()
        assert result.dtype.kind == "M"
        assert result.astype("int64") == iNaT

    def test_numeric_conversions(self):
        assert Timedelta(0) == np.timedelta64(0, "ns")
        assert Timedelta(10) == np.timedelta64(10, "ns")
        assert Timedelta(10, unit="ns") == np.timedelta64(10, "ns")

        assert Timedelta(10, unit="us") == np.timedelta64(10, "us")
        assert Timedelta(10, unit="ms") == np.timedelta64(10, "ms")
        assert Timedelta(10, unit="s") == np.timedelta64(10, "s")
        assert Timedelta(10, unit="d") == np.timedelta64(10, "D")

    def test_timedelta_conversions(self):
        assert Timedelta(timedelta(seconds=1)) == np.timedelta64(1, "s").astype(
            "m8[ns]"
        )
        assert Timedelta(timedelta(microseconds=1)) == np.timedelta64(1, "us").astype(
            "m8[ns]"
        )
        assert Timedelta(timedelta(days=1)) == np.timedelta64(1, "D").astype("m8[ns]")

    def test_to_numpy_alias(self):
        # GH 24653: alias .to_numpy() for scalars
        td = Timedelta("10m7s")
        assert td.to_timedelta64() == td.to_numpy()

        # GH#44460
        msg = "dtype and copy arguments are ignored"
        with pytest.raises(ValueError, match=msg):
            td.to_numpy("m8[s]")
        with pytest.raises(ValueError, match=msg):
            td.to_numpy(copy=True)

    def test_identity(self):
        td = Timedelta(10, unit="d")
        assert isinstance(td, Timedelta)
        assert isinstance(td, timedelta)

    def test_short_format_converters(self):
        def conv(v):
            return v.astype("m8[ns]")

        assert Timedelta("10") == np.timedelta64(10, "ns")
        assert Timedelta("10ns") == np.timedelta64(10, "ns")
        assert Timedelta("100") == np.timedelta64(100, "ns")
        assert Timedelta("100ns") == np.timedelta64(100, "ns")

        assert Timedelta("1000") == np.timedelta64(1000, "ns")
        assert Timedelta("1000ns") == np.timedelta64(1000, "ns")
        assert Timedelta("1000NS") == np.timedelta64(1000, "ns")

        assert Timedelta("10us") == np.timedelta64(10000, "ns")
        assert Timedelta("100us") == np.timedelta64(100000, "ns")
        assert Timedelta("1000us") == np.timedelta64(1000000, "ns")
        assert Timedelta("1000Us") == np.timedelta64(1000000, "ns")
        assert Timedelta("1000uS") == np.timedelta64(1000000, "ns")

        assert Timedelta("1ms") == np.timedelta64(1000000, "ns")
        assert Timedelta("10ms") == np.timedelta64(10000000, "ns")
        assert Timedelta("100ms") == np.timedelta64(100000000, "ns")
        assert Timedelta("1000ms") == np.timedelta64(1000000000, "ns")

        assert Timedelta("-1s") == -np.timedelta64(1000000000, "ns")
        assert Timedelta("1s") == np.timedelta64(1000000000, "ns")
        assert Timedelta("10s") == np.timedelta64(10000000000, "ns")
        assert Timedelta("100s") == np.timedelta64(100000000000, "ns")
        assert Timedelta("1000s") == np.timedelta64(1000000000000, "ns")

        assert Timedelta("1d") == conv(np.timedelta64(1, "D"))
        assert Timedelta("-1d") == -conv(np.timedelta64(1, "D"))
        assert Timedelta("1D") == conv(np.timedelta64(1, "D"))
        assert Timedelta("10D") == conv(np.timedelta64(10, "D"))
        assert Timedelta("100D") == conv(np.timedelta64(100, "D"))
        assert Timedelta("1000D") == conv(np.timedelta64(1000, "D"))
        assert Timedelta("10000D") == conv(np.timedelta64(10000, "D"))

        # space
        assert Timedelta(" 10000D ") == conv(np.timedelta64(10000, "D"))
        assert Timedelta(" - 10000D ") == -conv(np.timedelta64(10000, "D"))

        # invalid
        msg = "invalid unit abbreviation"
        with pytest.raises(ValueError, match=msg):
            Timedelta("1foo")
        msg = "unit abbreviation w/o a number"
        with pytest.raises(ValueError, match=msg):
            Timedelta("foo")

    def test_full_format_converters(self):
        def conv(v):
            return v.astype("m8[ns]")

        d1 = np.timedelta64(1, "D")

        assert Timedelta("1days") == conv(d1)
        assert Timedelta("1days,") == conv(d1)
        assert Timedelta("- 1days,") == -conv(d1)

        assert Timedelta("00:00:01") == conv(np.timedelta64(1, "s"))
        assert Timedelta("06:00:01") == conv(np.timedelta64(6 * 3600 + 1, "s"))
        assert Timedelta("06:00:01.0") == conv(np.timedelta64(6 * 3600 + 1, "s"))
        assert Timedelta("06:00:01.01") == conv(
            np.timedelta64(1000 * (6 * 3600 + 1) + 10, "ms")
        )

        assert Timedelta("- 1days, 00:00:01") == conv(-d1 + np.timedelta64(1, "s"))
        assert Timedelta("1days, 06:00:01") == conv(
            d1 + np.timedelta64(6 * 3600 + 1, "s")
        )
        assert Timedelta("1days, 06:00:01.01") == conv(
            d1 + np.timedelta64(1000 * (6 * 3600 + 1) + 10, "ms")
        )

        # invalid
        msg = "have leftover units"
        with pytest.raises(ValueError, match=msg):
            Timedelta("- 1days, 00")

    def test_pickle(self):
        v = Timedelta("1 days 10:11:12.0123456")
        v_p = tm.round_trip_pickle(v)
        assert v == v_p

    def test_timedelta_hash_equality(self):
        # GH 11129
        v = Timedelta(1, "D")
        td = timedelta(days=1)
        assert hash(v) == hash(td)

        d = {td: 2}
        assert d[v] == 2

        tds = [Timedelta(seconds=1) + Timedelta(days=n) for n in range(20)]
        assert all(hash(td) == hash(td.to_pytimedelta()) for td in tds)

        # python timedeltas drop ns resolution
        ns_td = Timedelta(1, "ns")
        assert hash(ns_td) != hash(ns_td.to_pytimedelta())

    @pytest.mark.skip_ubsan
    @pytest.mark.xfail(
        reason="pd.Timedelta violates the Python hash invariant (GH#44504).",
    )
    @given(
        st.integers(
            min_value=(-sys.maxsize - 1) // 500,
            max_value=sys.maxsize // 500,
        )
    )
    def test_hash_equality_invariance(self, half_microseconds: int) -> None:
        # GH#44504

        nanoseconds = half_microseconds * 500

        pandas_timedelta = Timedelta(nanoseconds)
        numpy_timedelta = np.timedelta64(nanoseconds)

        # See: https://docs.python.org/3/glossary.html#term-hashable
        # Hashable objects which compare equal must have the same hash value.
        assert pandas_timedelta != numpy_timedelta or hash(pandas_timedelta) == hash(
            numpy_timedelta
        )

    def test_implementation_limits(self):
        min_td = Timedelta(Timedelta.min)
        max_td = Timedelta(Timedelta.max)

        # GH 12727
        # timedelta limits correspond to int64 boundaries
        assert min_td._value == iNaT + 1
        assert max_td._value == lib.i8max

        # Beyond lower limit, a NAT before the Overflow
        assert (min_td - Timedelta(1, "ns")) is NaT

        msg = "int too (large|big) to convert"
        with pytest.raises(OverflowError, match=msg):
            min_td - Timedelta(2, "ns")

        with pytest.raises(OverflowError, match=msg):
            max_td + Timedelta(1, "ns")

        # Same tests using the internal nanosecond values
        td = Timedelta(min_td._value - 1, "ns")
        assert td is NaT

        msg = "Cannot cast -9223372036854775809 from ns to 'ns' without overflow"
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            Timedelta(min_td._value - 2, "ns")

        msg = "Cannot cast 9223372036854775808 from ns to 'ns' without overflow"
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            Timedelta(max_td._value + 1, "ns")

    def test_total_seconds_precision(self):
        # GH 19458
        assert Timedelta("30s").total_seconds() == 30.0
        assert Timedelta("0").total_seconds() == 0.0
        assert Timedelta("-2s").total_seconds() == -2.0
        assert Timedelta("5.324s").total_seconds() == 5.324
        assert (Timedelta("30s").total_seconds() - 30.0) < 1e-20
        assert (30.0 - Timedelta("30s").total_seconds()) < 1e-20

    def test_resolution_string(self):
        assert Timedelta(days=1).resolution_string == "D"
        assert Timedelta(days=1, hours=6).resolution_string == "h"
        assert Timedelta(days=1, minutes=6).resolution_string == "min"
        assert Timedelta(days=1, seconds=6).resolution_string == "s"
        assert Timedelta(days=1, milliseconds=6).resolution_string == "ms"
        assert Timedelta(days=1, microseconds=6).resolution_string == "us"
        assert Timedelta(days=1, nanoseconds=6).resolution_string == "ns"

    def test_resolution_deprecated(self):
        # GH#21344
        td = Timedelta(days=4, hours=3)
        result = td.resolution
        assert result == Timedelta(nanoseconds=1)

        # Check that the attribute is available on the class, mirroring
        #  the stdlib timedelta behavior
        result = Timedelta.resolution
        assert result == Timedelta(nanoseconds=1)


@pytest.mark.parametrize(
    "value, expected",
    [
        (Timedelta("10s"), True),
        (Timedelta("-10s"), True),
        (Timedelta(10, unit="ns"), True),
        (Timedelta(0, unit="ns"), False),
        (Timedelta(-10, unit="ns"), True),
        (Timedelta(None), True),
        (NaT, True),
    ],
)
def test_truthiness(value, expected):
    # https://github.com/pandas-dev/pandas/issues/21484
    assert bool(value) is expected


def test_timedelta_attribute_precision():
    # GH 31354
    td = Timedelta(1552211999999999872, unit="ns")
    result = td.days * 86400
    result += td.seconds
    result *= 1000000
    result += td.microseconds
    result *= 1000
    result += td.nanoseconds
    expected = td._value
    assert result == expected
