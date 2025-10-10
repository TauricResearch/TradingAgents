from datetime import timedelta
from itertools import product

import numpy as np
import pytest

from pandas._libs.tslibs import OutOfBoundsTimedelta
from pandas._libs.tslibs.dtypes import NpyDatetimeUnit

from pandas import (
    Index,
    NaT,
    Timedelta,
    TimedeltaIndex,
    offsets,
    to_timedelta,
)
import pandas._testing as tm


class TestTimedeltaConstructorUnitKeyword:
    @pytest.mark.parametrize("unit", ["Y", "y", "M"])
    def test_unit_m_y_raises(self, unit):
        msg = "Units 'M', 'Y', and 'y' are no longer supported"

        with pytest.raises(ValueError, match=msg):
            Timedelta(10, unit)

        with pytest.raises(ValueError, match=msg):
            to_timedelta(10, unit)

        with pytest.raises(ValueError, match=msg):
            to_timedelta([1, 2], unit)

    @pytest.mark.parametrize(
        "unit,unit_depr",
        [
            ("h", "H"),
            ("min", "T"),
            ("s", "S"),
            ("ms", "L"),
            ("ns", "N"),
            ("us", "U"),
        ],
    )
    def test_units_H_T_S_L_N_U_deprecated(self, unit, unit_depr):
        # GH#52536
        msg = f"'{unit_depr}' is deprecated and will be removed in a future version."

        expected = Timedelta(1, unit=unit)
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = Timedelta(1, unit=unit_depr)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize(
        "unit, np_unit",
        [(value, "W") for value in ["W", "w"]]
        + [(value, "D") for value in ["D", "d", "days", "day", "Days", "Day"]]
        + [
            (value, "m")
            for value in [
                "m",
                "minute",
                "min",
                "minutes",
                "Minute",
                "Min",
                "Minutes",
            ]
        ]
        + [
            (value, "s")
            for value in [
                "s",
                "seconds",
                "sec",
                "second",
                "Seconds",
                "Sec",
                "Second",
            ]
        ]
        + [
            (value, "ms")
            for value in [
                "ms",
                "milliseconds",
                "millisecond",
                "milli",
                "millis",
                "MS",
                "Milliseconds",
                "Millisecond",
                "Milli",
                "Millis",
            ]
        ]
        + [
            (value, "us")
            for value in [
                "us",
                "microseconds",
                "microsecond",
                "micro",
                "micros",
                "u",
                "US",
                "Microseconds",
                "Microsecond",
                "Micro",
                "Micros",
                "U",
            ]
        ]
        + [
            (value, "ns")
            for value in [
                "ns",
                "nanoseconds",
                "nanosecond",
                "nano",
                "nanos",
                "n",
                "NS",
                "Nanoseconds",
                "Nanosecond",
                "Nano",
                "Nanos",
                "N",
            ]
        ],
    )
    @pytest.mark.parametrize("wrapper", [np.array, list, Index])
    def test_unit_parser(self, unit, np_unit, wrapper):
        # validate all units, GH 6855, GH 21762
        # array-likes
        expected = TimedeltaIndex(
            [np.timedelta64(i, np_unit) for i in np.arange(5).tolist()],
            dtype="m8[ns]",
        )
        # TODO(2.0): the desired output dtype may have non-nano resolution
        msg = f"'{unit}' is deprecated and will be removed in a future version."

        if (unit, np_unit) in (("u", "us"), ("U", "us"), ("n", "ns"), ("N", "ns")):
            warn = FutureWarning
        else:
            warn = FutureWarning
            msg = "The 'unit' keyword in TimedeltaIndex construction is deprecated"
        with tm.assert_produces_warning(warn, match=msg):
            result = to_timedelta(wrapper(range(5)), unit=unit)
            tm.assert_index_equal(result, expected)
            result = TimedeltaIndex(wrapper(range(5)), unit=unit)
            tm.assert_index_equal(result, expected)

            str_repr = [f"{x}{unit}" for x in np.arange(5)]
            result = to_timedelta(wrapper(str_repr))
            tm.assert_index_equal(result, expected)
            result = to_timedelta(wrapper(str_repr))
            tm.assert_index_equal(result, expected)

            # scalar
            expected = Timedelta(np.timedelta64(2, np_unit).astype("timedelta64[ns]"))
            result = to_timedelta(2, unit=unit)
            assert result == expected
            result = Timedelta(2, unit=unit)
            assert result == expected

            result = to_timedelta(f"2{unit}")
            assert result == expected
            result = Timedelta(f"2{unit}")
            assert result == expected


def test_construct_from_kwargs_overflow():
    # GH#55503
    msg = "seconds=86400000000000000000, milliseconds=0, microseconds=0, nanoseconds=0"
    with pytest.raises(OutOfBoundsTimedelta, match=msg):
        Timedelta(days=10**6)
    msg = "seconds=60000000000000000000, milliseconds=0, microseconds=0, nanoseconds=0"
    with pytest.raises(OutOfBoundsTimedelta, match=msg):
        Timedelta(minutes=10**9)


def test_construct_with_weeks_unit_overflow():
    # GH#47268 don't silently wrap around
    with pytest.raises(OutOfBoundsTimedelta, match="without overflow"):
        Timedelta(1000000000000000000, unit="W")

    with pytest.raises(OutOfBoundsTimedelta, match="without overflow"):
        Timedelta(1000000000000000000.0, unit="W")


def test_construct_from_td64_with_unit():
    # ignore the unit, as it may cause silently overflows leading to incorrect
    #  results, and in non-overflow cases is irrelevant GH#46827
    obj = np.timedelta64(123456789000000000, "h")

    with pytest.raises(OutOfBoundsTimedelta, match="123456789000000000 hours"):
        Timedelta(obj, unit="ps")

    with pytest.raises(OutOfBoundsTimedelta, match="123456789000000000 hours"):
        Timedelta(obj, unit="ns")

    with pytest.raises(OutOfBoundsTimedelta, match="123456789000000000 hours"):
        Timedelta(obj)


def test_from_td64_retain_resolution():
    # case where we retain millisecond resolution
    obj = np.timedelta64(12345, "ms")

    td = Timedelta(obj)
    assert td._value == obj.view("i8")
    assert td._creso == NpyDatetimeUnit.NPY_FR_ms.value

    # Case where we cast to nearest-supported reso
    obj2 = np.timedelta64(1234, "D")
    td2 = Timedelta(obj2)
    assert td2._creso == NpyDatetimeUnit.NPY_FR_s.value
    assert td2 == obj2
    assert td2.days == 1234

    # Case that _would_ overflow if we didn't support non-nano
    obj3 = np.timedelta64(1000000000000000000, "us")
    td3 = Timedelta(obj3)
    assert td3.total_seconds() == 1000000000000
    assert td3._creso == NpyDatetimeUnit.NPY_FR_us.value


def test_from_pytimedelta_us_reso():
    # pytimedelta has microsecond resolution, so Timedelta(pytd) inherits that
    td = timedelta(days=4, minutes=3)
    result = Timedelta(td)
    assert result.to_pytimedelta() == td
    assert result._creso == NpyDatetimeUnit.NPY_FR_us.value


def test_from_tick_reso():
    tick = offsets.Nano()
    assert Timedelta(tick)._creso == NpyDatetimeUnit.NPY_FR_ns.value

    tick = offsets.Micro()
    assert Timedelta(tick)._creso == NpyDatetimeUnit.NPY_FR_us.value

    tick = offsets.Milli()
    assert Timedelta(tick)._creso == NpyDatetimeUnit.NPY_FR_ms.value

    tick = offsets.Second()
    assert Timedelta(tick)._creso == NpyDatetimeUnit.NPY_FR_s.value

    # everything above Second gets cast to the closest supported reso: second
    tick = offsets.Minute()
    assert Timedelta(tick)._creso == NpyDatetimeUnit.NPY_FR_s.value

    tick = offsets.Hour()
    assert Timedelta(tick)._creso == NpyDatetimeUnit.NPY_FR_s.value

    tick = offsets.Day()
    assert Timedelta(tick)._creso == NpyDatetimeUnit.NPY_FR_s.value


def test_construction():
    expected = np.timedelta64(10, "D").astype("m8[ns]").view("i8")
    assert Timedelta(10, unit="d")._value == expected
    assert Timedelta(10.0, unit="d")._value == expected
    assert Timedelta("10 days")._value == expected
    assert Timedelta(days=10)._value == expected
    assert Timedelta(days=10.0)._value == expected

    expected += np.timedelta64(10, "s").astype("m8[ns]").view("i8")
    assert Timedelta("10 days 00:00:10")._value == expected
    assert Timedelta(days=10, seconds=10)._value == expected
    assert Timedelta(days=10, milliseconds=10 * 1000)._value == expected
    assert Timedelta(days=10, microseconds=10 * 1000 * 1000)._value == expected

    # rounding cases
    assert Timedelta(82739999850000)._value == 82739999850000
    assert "0 days 22:58:59.999850" in str(Timedelta(82739999850000))
    assert Timedelta(123072001000000)._value == 123072001000000
    assert "1 days 10:11:12.001" in str(Timedelta(123072001000000))

    # string conversion with/without leading zero
    # GH#9570
    assert Timedelta("0:00:00") == timedelta(hours=0)
    assert Timedelta("00:00:00") == timedelta(hours=0)
    assert Timedelta("-1:00:00") == -timedelta(hours=1)
    assert Timedelta("-01:00:00") == -timedelta(hours=1)

    # more strings & abbrevs
    # GH#8190
    assert Timedelta("1 h") == timedelta(hours=1)
    assert Timedelta("1 hour") == timedelta(hours=1)
    assert Timedelta("1 hr") == timedelta(hours=1)
    assert Timedelta("1 hours") == timedelta(hours=1)
    assert Timedelta("-1 hours") == -timedelta(hours=1)
    assert Timedelta("1 m") == timedelta(minutes=1)
    assert Timedelta("1.5 m") == timedelta(seconds=90)
    assert Timedelta("1 minute") == timedelta(minutes=1)
    assert Timedelta("1 minutes") == timedelta(minutes=1)
    assert Timedelta("1 s") == timedelta(seconds=1)
    assert Timedelta("1 second") == timedelta(seconds=1)
    assert Timedelta("1 seconds") == timedelta(seconds=1)
    assert Timedelta("1 ms") == timedelta(milliseconds=1)
    assert Timedelta("1 milli") == timedelta(milliseconds=1)
    assert Timedelta("1 millisecond") == timedelta(milliseconds=1)
    assert Timedelta("1 us") == timedelta(microseconds=1)
    assert Timedelta("1 µs") == timedelta(microseconds=1)
    assert Timedelta("1 micros") == timedelta(microseconds=1)
    assert Timedelta("1 microsecond") == timedelta(microseconds=1)
    assert Timedelta("1.5 microsecond") == Timedelta("00:00:00.000001500")
    assert Timedelta("1 ns") == Timedelta("00:00:00.000000001")
    assert Timedelta("1 nano") == Timedelta("00:00:00.000000001")
    assert Timedelta("1 nanosecond") == Timedelta("00:00:00.000000001")

    # combos
    assert Timedelta("10 days 1 hour") == timedelta(days=10, hours=1)
    assert Timedelta("10 days 1 h") == timedelta(days=10, hours=1)
    assert Timedelta("10 days 1 h 1m 1s") == timedelta(
        days=10, hours=1, minutes=1, seconds=1
    )
    assert Timedelta("-10 days 1 h 1m 1s") == -timedelta(
        days=10, hours=1, minutes=1, seconds=1
    )
    assert Timedelta("-10 days 1 h 1m 1s") == -timedelta(
        days=10, hours=1, minutes=1, seconds=1
    )
    assert Timedelta("-10 days 1 h 1m 1s 3us") == -timedelta(
        days=10, hours=1, minutes=1, seconds=1, microseconds=3
    )
    assert Timedelta("-10 days 1 h 1.5m 1s 3us") == -timedelta(
        days=10, hours=1, minutes=1, seconds=31, microseconds=3
    )

    # Currently invalid as it has a - on the hh:mm:dd part
    # (only allowed on the days)
    msg = "only leading negative signs are allowed"
    with pytest.raises(ValueError, match=msg):
        Timedelta("-10 days -1 h 1.5m 1s 3us")

    # only leading neg signs are allowed
    with pytest.raises(ValueError, match=msg):
        Timedelta("10 days -1 h 1.5m 1s 3us")

    # no units specified
    msg = "no units specified"
    with pytest.raises(ValueError, match=msg):
        Timedelta("3.1415")

    # invalid construction
    msg = "cannot construct a Timedelta"
    with pytest.raises(ValueError, match=msg):
        Timedelta()

    msg = "unit abbreviation w/o a number"
    with pytest.raises(ValueError, match=msg):
        Timedelta("foo")

    msg = (
        "cannot construct a Timedelta from "
        "the passed arguments, allowed keywords are "
    )
    with pytest.raises(ValueError, match=msg):
        Timedelta(day=10)

    # floats
    expected = np.timedelta64(10, "s").astype("m8[ns]").view("i8") + np.timedelta64(
        500, "ms"
    ).astype("m8[ns]").view("i8")
    assert Timedelta(10.5, unit="s")._value == expected

    # offset
    assert to_timedelta(offsets.Hour(2)) == Timedelta(hours=2)
    assert Timedelta(offsets.Hour(2)) == Timedelta(hours=2)
    assert Timedelta(offsets.Second(2)) == Timedelta(seconds=2)

    # GH#11995: unicode
    expected = Timedelta("1h")
    result = Timedelta("1h")
    assert result == expected
    assert to_timedelta(offsets.Hour(2)) == Timedelta("0 days, 02:00:00")

    msg = "unit abbreviation w/o a number"
    with pytest.raises(ValueError, match=msg):
        Timedelta("foo bar")


@pytest.mark.parametrize(
    "item",
    list(
        {
            "days": "D",
            "seconds": "s",
            "microseconds": "us",
            "milliseconds": "ms",
            "minutes": "m",
            "hours": "h",
            "weeks": "W",
        }.items()
    ),
)
@pytest.mark.parametrize(
    "npdtype", [np.int64, np.int32, np.int16, np.float64, np.float32, np.float16]
)
def test_td_construction_with_np_dtypes(npdtype, item):
    # GH#8757: test construction with np dtypes
    pykwarg, npkwarg = item
    expected = np.timedelta64(1, npkwarg).astype("m8[ns]").view("i8")
    assert Timedelta(**{pykwarg: npdtype(1)})._value == expected


@pytest.mark.parametrize(
    "val",
    [
        "1s",
        "-1s",
        "1us",
        "-1us",
        "1 day",
        "-1 day",
        "-23:59:59.999999",
        "-1 days +23:59:59.999999",
        "-1ns",
        "1ns",
        "-23:59:59.999999999",
    ],
)
def test_td_from_repr_roundtrip(val):
    # round-trip both for string and value
    td = Timedelta(val)
    assert Timedelta(td._value) == td

    assert Timedelta(str(td)) == td
    assert Timedelta(td._repr_base(format="all")) == td
    assert Timedelta(td._repr_base()) == td


def test_overflow_on_construction():
    # GH#3374
    value = Timedelta("1day")._value * 20169940
    msg = "Cannot cast 1742682816000000000000 from ns to 'ns' without overflow"
    with pytest.raises(OutOfBoundsTimedelta, match=msg):
        Timedelta(value)

    # xref GH#17637
    msg = "Cannot cast 139993 from D to 'ns' without overflow"
    with pytest.raises(OutOfBoundsTimedelta, match=msg):
        Timedelta(7 * 19999, unit="D")

    # used to overflow before non-ns support
    td = Timedelta(timedelta(days=13 * 19999))
    assert td._creso == NpyDatetimeUnit.NPY_FR_us.value
    assert td.days == 13 * 19999


@pytest.mark.parametrize(
    "val, unit",
    [
        (15251, "W"),  # 1
        (106752, "D"),  # change from previous:
        (2562048, "h"),  # 0 hours
        (153722868, "m"),  # 13 minutes
        (9223372037, "s"),  # 44 seconds
    ],
)
def test_construction_out_of_bounds_td64ns(val, unit):
    # TODO: parametrize over units just above/below the implementation bounds
    #  once GH#38964 is resolved

    # Timedelta.max is just under 106752 days
    td64 = np.timedelta64(val, unit)
    assert td64.astype("m8[ns]").view("i8") < 0  # i.e. naive astype will be wrong

    td = Timedelta(td64)
    if unit != "M":
        # with unit="M" the conversion to "s" is poorly defined
        #  (and numpy issues DeprecationWarning)
        assert td.asm8 == td64
    assert td.asm8.dtype == "m8[s]"
    msg = r"Cannot cast 1067\d\d days .* to unit='ns' without overflow"
    with pytest.raises(OutOfBoundsTimedelta, match=msg):
        td.as_unit("ns")

    # But just back in bounds and we are OK
    assert Timedelta(td64 - 1) == td64 - 1

    td64 *= -1
    assert td64.astype("m8[ns]").view("i8") > 0  # i.e. naive astype will be wrong

    td2 = Timedelta(td64)
    msg = r"Cannot cast -1067\d\d days .* to unit='ns' without overflow"
    with pytest.raises(OutOfBoundsTimedelta, match=msg):
        td2.as_unit("ns")

    # But just back in bounds and we are OK
    assert Timedelta(td64 + 1) == td64 + 1


@pytest.mark.parametrize(
    "val, unit",
    [
        (15251 * 10**9, "W"),
        (106752 * 10**9, "D"),
        (2562048 * 10**9, "h"),
        (153722868 * 10**9, "m"),
    ],
)
def test_construction_out_of_bounds_td64s(val, unit):
    td64 = np.timedelta64(val, unit)
    with pytest.raises(OutOfBoundsTimedelta, match=str(td64)):
        Timedelta(td64)

    # But just back in bounds and we are OK
    assert Timedelta(td64 - 10**9) == td64 - 10**9


@pytest.mark.parametrize(
    "fmt,exp",
    [
        (
            "P6DT0H50M3.010010012S",
            Timedelta(
                days=6,
                minutes=50,
                seconds=3,
                milliseconds=10,
                microseconds=10,
                nanoseconds=12,
            ),
        ),
        (
            "P-6DT0H50M3.010010012S",
            Timedelta(
                days=-6,
                minutes=50,
                seconds=3,
                milliseconds=10,
                microseconds=10,
                nanoseconds=12,
            ),
        ),
        ("P4DT12H30M5S", Timedelta(days=4, hours=12, minutes=30, seconds=5)),
        ("P0DT0H0M0.000000123S", Timedelta(nanoseconds=123)),
        ("P0DT0H0M0.00001S", Timedelta(microseconds=10)),
        ("P0DT0H0M0.001S", Timedelta(milliseconds=1)),
        ("P0DT0H1M0S", Timedelta(minutes=1)),
        ("P1DT25H61M61S", Timedelta(days=1, hours=25, minutes=61, seconds=61)),
        ("PT1S", Timedelta(seconds=1)),
        ("PT0S", Timedelta(seconds=0)),
        ("P1WT0S", Timedelta(days=7, seconds=0)),
        ("P1D", Timedelta(days=1)),
        ("P1DT1H", Timedelta(days=1, hours=1)),
        ("P1W", Timedelta(days=7)),
        ("PT300S", Timedelta(seconds=300)),
        ("P1DT0H0M00000000000S", Timedelta(days=1)),
        ("PT-6H3M", Timedelta(hours=-6, minutes=3)),
        ("-PT6H3M", Timedelta(hours=-6, minutes=-3)),
        ("-PT-6H+3M", Timedelta(hours=6, minutes=-3)),
    ],
)
def test_iso_constructor(fmt, exp):
    assert Timedelta(fmt) == exp


@pytest.mark.parametrize(
    "fmt",
    [
        "PPPPPPPPPPPP",
        "PDTHMS",
        "P0DT999H999M999S",
        "P1DT0H0M0.0000000000000S",
        "P1DT0H0M0.S",
        "P",
        "-P",
    ],
)
def test_iso_constructor_raises(fmt):
    msg = f"Invalid ISO 8601 Duration format - {fmt}"
    with pytest.raises(ValueError, match=msg):
        Timedelta(fmt)


@pytest.mark.parametrize(
    "constructed_td, conversion",
    [
        (Timedelta(nanoseconds=100), "100ns"),
        (
            Timedelta(
                days=1,
                hours=1,
                minutes=1,
                weeks=1,
                seconds=1,
                milliseconds=1,
                microseconds=1,
                nanoseconds=1,
            ),
            694861001001001,
        ),
        (Timedelta(microseconds=1) + Timedelta(nanoseconds=1), "1us1ns"),
        (Timedelta(microseconds=1) - Timedelta(nanoseconds=1), "999ns"),
        (Timedelta(microseconds=1) + 5 * Timedelta(nanoseconds=-2), "990ns"),
    ],
)
def test_td_constructor_on_nanoseconds(constructed_td, conversion):
    # GH#9273
    assert constructed_td == Timedelta(conversion)


def test_td_constructor_value_error():
    msg = "Invalid type <class 'str'>. Must be int or float."
    with pytest.raises(TypeError, match=msg):
        Timedelta(nanoseconds="abc")


def test_timedelta_constructor_identity():
    # Test for #30543
    expected = Timedelta(np.timedelta64(1, "s"))
    result = Timedelta(expected)
    assert result is expected


def test_timedelta_pass_td_and_kwargs_raises():
    # don't silently ignore the kwargs GH#48898
    td = Timedelta(days=1)
    msg = (
        "Cannot pass both a Timedelta input and timedelta keyword arguments, "
        r"got \['days'\]"
    )
    with pytest.raises(ValueError, match=msg):
        Timedelta(td, days=2)


@pytest.mark.parametrize(
    "constructor, value, unit, expectation",
    [
        (Timedelta, "10s", "ms", (ValueError, "unit must not be specified")),
        (to_timedelta, "10s", "ms", (ValueError, "unit must not be specified")),
        (to_timedelta, ["1", 2, 3], "s", (ValueError, "unit must not be specified")),
    ],
)
def test_string_with_unit(constructor, value, unit, expectation):
    exp, match = expectation
    with pytest.raises(exp, match=match):
        _ = constructor(value, unit=unit)


@pytest.mark.parametrize(
    "value",
    [
        "".join(elements)
        for repetition in (1, 2)
        for elements in product("+-, ", repeat=repetition)
    ],
)
def test_string_without_numbers(value):
    # GH39710 Timedelta input string with only symbols and no digits raises an error
    msg = (
        "symbols w/o a number"
        if value != "--"
        else "only leading negative signs are allowed"
    )
    with pytest.raises(ValueError, match=msg):
        Timedelta(value)


def test_timedelta_new_npnat():
    # GH#48898
    nat = np.timedelta64("NaT", "h")
    assert Timedelta(nat) is NaT


def test_subclass_respected():
    # GH#49579
    class MyCustomTimedelta(Timedelta):
        pass

    td = MyCustomTimedelta("1 minute")
    assert isinstance(td, MyCustomTimedelta)


def test_non_nano_value():
    # https://github.com/pandas-dev/pandas/issues/49076
    result = Timedelta(10, unit="D").as_unit("s").value
    # `.value` shows nanoseconds, even though unit is 's'
    assert result == 864000000000000

    # out-of-nanoseconds-bounds `.value` raises informative message
    msg = (
        r"Cannot convert Timedelta to nanoseconds without overflow. "
        r"Use `.asm8.view\('i8'\)` to cast represent Timedelta in its "
        r"own unit \(here, s\).$"
    )
    td = Timedelta(1_000, "D").as_unit("s") * 1_000
    with pytest.raises(OverflowError, match=msg):
        td.value
    # check that the suggested workaround actually works
    result = td.asm8.view("i8")
    assert result == 86400000000
