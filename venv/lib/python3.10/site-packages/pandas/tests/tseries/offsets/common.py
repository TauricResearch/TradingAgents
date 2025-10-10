"""
Assertion helpers and base class for offsets tests
"""
from __future__ import annotations


def assert_offset_equal(offset, base, expected):
    actual = offset + base
    actual_swapped = base + offset
    actual_apply = offset._apply(base)
    try:
        assert actual == expected
        assert actual_swapped == expected
        assert actual_apply == expected
    except AssertionError as err:
        raise AssertionError(
            f"\nExpected: {expected}\nActual: {actual}\nFor Offset: {offset})"
            f"\nAt Date: {base}"
        ) from err


def assert_is_on_offset(offset, date, expected):
    actual = offset.is_on_offset(date)
    assert actual == expected, (
        f"\nExpected: {expected}\nActual: {actual}\nFor Offset: {offset})"
        f"\nAt Date: {date}"
    )


class WeekDay:
    MON = 0
    TUE = 1
    WED = 2
    THU = 3
    FRI = 4
    SAT = 5
    SUN = 6
