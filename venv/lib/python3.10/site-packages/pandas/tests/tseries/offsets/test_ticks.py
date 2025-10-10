"""
Tests for offsets.Tick and subclasses
"""
from datetime import (
    datetime,
    timedelta,
)

from hypothesis import (
    assume,
    example,
    given,
)
import numpy as np
import pytest

from pandas._libs.tslibs.offsets import delta_to_tick
from pandas.errors import OutOfBoundsTimedelta

from pandas import (
    Timedelta,
    Timestamp,
)
import pandas._testing as tm
from pandas._testing._hypothesis import INT_NEG_999_TO_POS_999
from pandas.tests.tseries.offsets.common import assert_offset_equal

from pandas.tseries import offsets
from pandas.tseries.offsets import (
    Hour,
    Micro,
    Milli,
    Minute,
    Nano,
    Second,
)

# ---------------------------------------------------------------------
# Test Helpers

tick_classes = [Hour, Minute, Second, Milli, Micro, Nano]


# ---------------------------------------------------------------------


def test_apply_ticks():
    result = offsets.Hour(3) + offsets.Hour(4)
    exp = offsets.Hour(7)
    assert result == exp


def test_delta_to_tick():
    delta = timedelta(3)

    tick = delta_to_tick(delta)
    assert tick == offsets.Day(3)

    td = Timedelta(nanoseconds=5)
    tick = delta_to_tick(td)
    assert tick == Nano(5)


@pytest.mark.parametrize("cls", tick_classes)
@example(n=2, m=3)
@example(n=800, m=300)
@example(n=1000, m=5)
@given(n=INT_NEG_999_TO_POS_999, m=INT_NEG_999_TO_POS_999)
def test_tick_add_sub(cls, n, m):
    # For all Tick subclasses and all integers n, m, we should have
    # tick(n) + tick(m) == tick(n+m)
    # tick(n) - tick(m) == tick(n-m)
    left = cls(n)
    right = cls(m)
    expected = cls(n + m)

    assert left + right == expected

    expected = cls(n - m)
    assert left - right == expected


@pytest.mark.arm_slow
@pytest.mark.parametrize("cls", tick_classes)
@example(n=2, m=3)
@given(n=INT_NEG_999_TO_POS_999, m=INT_NEG_999_TO_POS_999)
def test_tick_equality(cls, n, m):
    assume(m != n)
    # tick == tock iff tick.n == tock.n
    left = cls(n)
    right = cls(m)
    assert left != right

    right = cls(n)
    assert left == right
    assert not left != right

    if n != 0:
        assert cls(n) != cls(-n)


# ---------------------------------------------------------------------


def test_Hour():
    assert_offset_equal(Hour(), datetime(2010, 1, 1), datetime(2010, 1, 1, 1))
    assert_offset_equal(Hour(-1), datetime(2010, 1, 1, 1), datetime(2010, 1, 1))
    assert_offset_equal(2 * Hour(), datetime(2010, 1, 1), datetime(2010, 1, 1, 2))
    assert_offset_equal(-1 * Hour(), datetime(2010, 1, 1, 1), datetime(2010, 1, 1))

    assert Hour(3) + Hour(2) == Hour(5)
    assert Hour(3) - Hour(2) == Hour()

    assert Hour(4) != Hour(1)


def test_Minute():
    assert_offset_equal(Minute(), datetime(2010, 1, 1), datetime(2010, 1, 1, 0, 1))
    assert_offset_equal(Minute(-1), datetime(2010, 1, 1, 0, 1), datetime(2010, 1, 1))
    assert_offset_equal(2 * Minute(), datetime(2010, 1, 1), datetime(2010, 1, 1, 0, 2))
    assert_offset_equal(-1 * Minute(), datetime(2010, 1, 1, 0, 1), datetime(2010, 1, 1))

    assert Minute(3) + Minute(2) == Minute(5)
    assert Minute(3) - Minute(2) == Minute()
    assert Minute(5) != Minute()


def test_Second():
    assert_offset_equal(Second(), datetime(2010, 1, 1), datetime(2010, 1, 1, 0, 0, 1))
    assert_offset_equal(Second(-1), datetime(2010, 1, 1, 0, 0, 1), datetime(2010, 1, 1))
    assert_offset_equal(
        2 * Second(), datetime(2010, 1, 1), datetime(2010, 1, 1, 0, 0, 2)
    )
    assert_offset_equal(
        -1 * Second(), datetime(2010, 1, 1, 0, 0, 1), datetime(2010, 1, 1)
    )

    assert Second(3) + Second(2) == Second(5)
    assert Second(3) - Second(2) == Second()


def test_Millisecond():
    assert_offset_equal(
        Milli(), datetime(2010, 1, 1), datetime(2010, 1, 1, 0, 0, 0, 1000)
    )
    assert_offset_equal(
        Milli(-1), datetime(2010, 1, 1, 0, 0, 0, 1000), datetime(2010, 1, 1)
    )
    assert_offset_equal(
        Milli(2), datetime(2010, 1, 1), datetime(2010, 1, 1, 0, 0, 0, 2000)
    )
    assert_offset_equal(
        2 * Milli(), datetime(2010, 1, 1), datetime(2010, 1, 1, 0, 0, 0, 2000)
    )
    assert_offset_equal(
        -1 * Milli(), datetime(2010, 1, 1, 0, 0, 0, 1000), datetime(2010, 1, 1)
    )

    assert Milli(3) + Milli(2) == Milli(5)
    assert Milli(3) - Milli(2) == Milli()


def test_MillisecondTimestampArithmetic():
    assert_offset_equal(
        Milli(), Timestamp("2010-01-01"), Timestamp("2010-01-01 00:00:00.001")
    )
    assert_offset_equal(
        Milli(-1), Timestamp("2010-01-01 00:00:00.001"), Timestamp("2010-01-01")
    )


def test_Microsecond():
    assert_offset_equal(Micro(), datetime(2010, 1, 1), datetime(2010, 1, 1, 0, 0, 0, 1))
    assert_offset_equal(
        Micro(-1), datetime(2010, 1, 1, 0, 0, 0, 1), datetime(2010, 1, 1)
    )

    assert_offset_equal(
        2 * Micro(), datetime(2010, 1, 1), datetime(2010, 1, 1, 0, 0, 0, 2)
    )
    assert_offset_equal(
        -1 * Micro(), datetime(2010, 1, 1, 0, 0, 0, 1), datetime(2010, 1, 1)
    )

    assert Micro(3) + Micro(2) == Micro(5)
    assert Micro(3) - Micro(2) == Micro()


def test_NanosecondGeneric():
    timestamp = Timestamp(datetime(2010, 1, 1))
    assert timestamp.nanosecond == 0

    result = timestamp + Nano(10)
    assert result.nanosecond == 10

    reverse_result = Nano(10) + timestamp
    assert reverse_result.nanosecond == 10


def test_Nanosecond():
    timestamp = Timestamp(datetime(2010, 1, 1))
    assert_offset_equal(Nano(), timestamp, timestamp + np.timedelta64(1, "ns"))
    assert_offset_equal(Nano(-1), timestamp + np.timedelta64(1, "ns"), timestamp)
    assert_offset_equal(2 * Nano(), timestamp, timestamp + np.timedelta64(2, "ns"))
    assert_offset_equal(-1 * Nano(), timestamp + np.timedelta64(1, "ns"), timestamp)

    assert Nano(3) + Nano(2) == Nano(5)
    assert Nano(3) - Nano(2) == Nano()

    # GH9284
    assert Nano(1) + Nano(10) == Nano(11)
    assert Nano(5) + Micro(1) == Nano(1005)
    assert Micro(5) + Nano(1) == Nano(5001)


@pytest.mark.parametrize(
    "kls, expected",
    [
        (Hour, Timedelta(hours=5)),
        (Minute, Timedelta(hours=2, minutes=3)),
        (Second, Timedelta(hours=2, seconds=3)),
        (Milli, Timedelta(hours=2, milliseconds=3)),
        (Micro, Timedelta(hours=2, microseconds=3)),
        (Nano, Timedelta(hours=2, nanoseconds=3)),
    ],
)
def test_tick_addition(kls, expected):
    offset = kls(3)
    td = Timedelta(hours=2)

    for other in [td, td.to_pytimedelta(), td.to_timedelta64()]:
        result = offset + other
        assert isinstance(result, Timedelta)
        assert result == expected

        result = other + offset
        assert isinstance(result, Timedelta)
        assert result == expected


def test_tick_delta_overflow():
    # GH#55503 raise OutOfBoundsTimedelta, not OverflowError
    tick = offsets.Day(10**9)
    msg = "Cannot cast 1000000000 days 00:00:00 to unit='ns' without overflow"
    depr_msg = "Day.delta is deprecated"
    with pytest.raises(OutOfBoundsTimedelta, match=msg):
        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            tick.delta


@pytest.mark.parametrize("cls", tick_classes)
def test_tick_division(cls):
    off = cls(10)

    assert off / cls(5) == 2
    assert off / 2 == cls(5)
    assert off / 2.0 == cls(5)

    assert off / off._as_pd_timedelta == 1
    assert off / off._as_pd_timedelta.to_timedelta64() == 1

    assert off / Nano(1) == off._as_pd_timedelta / Nano(1)._as_pd_timedelta

    if cls is not Nano:
        # A case where we end up with a smaller class
        result = off / 1000
        assert isinstance(result, offsets.Tick)
        assert not isinstance(result, cls)
        assert result._as_pd_timedelta == off._as_pd_timedelta / 1000

    if cls._nanos_inc < Timedelta(seconds=1)._value:
        # Case where we end up with a bigger class
        result = off / 0.001
        assert isinstance(result, offsets.Tick)
        assert not isinstance(result, cls)
        assert result._as_pd_timedelta == off._as_pd_timedelta / 0.001


def test_tick_mul_float():
    off = Micro(2)

    # Case where we retain type
    result = off * 1.5
    expected = Micro(3)
    assert result == expected
    assert isinstance(result, Micro)

    # Case where we bump up to the next type
    result = off * 1.25
    expected = Nano(2500)
    assert result == expected
    assert isinstance(result, Nano)


@pytest.mark.parametrize("cls", tick_classes)
def test_tick_rdiv(cls):
    off = cls(10)
    delta = off._as_pd_timedelta
    td64 = delta.to_timedelta64()
    instance__type = ".".join([cls.__module__, cls.__name__])
    msg = (
        "unsupported operand type\\(s\\) for \\/: 'int'|'float' and "
        f"'{instance__type}'"
    )

    with pytest.raises(TypeError, match=msg):
        2 / off
    with pytest.raises(TypeError, match=msg):
        2.0 / off

    assert (td64 * 2.5) / off == 2.5

    if cls is not Nano:
        # skip pytimedelta for Nano since it gets dropped
        assert (delta.to_pytimedelta() * 2) / off == 2

    result = np.array([2 * td64, td64]) / off
    expected = np.array([2.0, 1.0])
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("cls1", tick_classes)
@pytest.mark.parametrize("cls2", tick_classes)
def test_tick_zero(cls1, cls2):
    assert cls1(0) == cls2(0)
    assert cls1(0) + cls2(0) == cls1(0)

    if cls1 is not Nano:
        assert cls1(2) + cls2(0) == cls1(2)

    if cls1 is Nano:
        assert cls1(2) + Nano(0) == cls1(2)


@pytest.mark.parametrize("cls", tick_classes)
def test_tick_equalities(cls):
    assert cls() == cls(1)


@pytest.mark.parametrize("cls", tick_classes)
def test_tick_offset(cls):
    msg = f"{cls.__name__}.is_anchored is deprecated "

    with tm.assert_produces_warning(FutureWarning, match=msg):
        assert not cls().is_anchored()


@pytest.mark.parametrize("cls", tick_classes)
def test_compare_ticks(cls):
    three = cls(3)
    four = cls(4)

    assert three < cls(4)
    assert cls(3) < four
    assert four > cls(3)
    assert cls(4) > three
    assert cls(3) == cls(3)
    assert cls(3) != cls(4)


@pytest.mark.parametrize("cls", tick_classes)
def test_compare_ticks_to_strs(cls):
    # GH#23524
    off = cls(19)

    # These tests should work with any strings, but we particularly are
    #  interested in "infer" as that comparison is convenient to make in
    #  Datetime/Timedelta Array/Index constructors
    assert not off == "infer"
    assert not "foo" == off

    instance_type = ".".join([cls.__module__, cls.__name__])
    msg = (
        "'<'|'<='|'>'|'>=' not supported between instances of "
        f"'str' and '{instance_type}'|'{instance_type}' and 'str'"
    )

    for left, right in [("infer", off), (off, "infer")]:
        with pytest.raises(TypeError, match=msg):
            left < right
        with pytest.raises(TypeError, match=msg):
            left <= right
        with pytest.raises(TypeError, match=msg):
            left > right
        with pytest.raises(TypeError, match=msg):
            left >= right


@pytest.mark.parametrize("cls", tick_classes)
def test_compare_ticks_to_timedeltalike(cls):
    off = cls(19)

    td = off._as_pd_timedelta

    others = [td, td.to_timedelta64()]
    if cls is not Nano:
        others.append(td.to_pytimedelta())

    for other in others:
        assert off == other
        assert not off != other
        assert not off < other
        assert not off > other
        assert off <= other
        assert off >= other
