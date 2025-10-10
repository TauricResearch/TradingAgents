from datetime import datetime

import pytest

from pandas.tseries.holiday import (
    after_nearest_workday,
    before_nearest_workday,
    nearest_workday,
    next_monday,
    next_monday_or_tuesday,
    next_workday,
    previous_friday,
    previous_workday,
    sunday_to_monday,
    weekend_to_monday,
)

_WEDNESDAY = datetime(2014, 4, 9)
_THURSDAY = datetime(2014, 4, 10)
_FRIDAY = datetime(2014, 4, 11)
_SATURDAY = datetime(2014, 4, 12)
_SUNDAY = datetime(2014, 4, 13)
_MONDAY = datetime(2014, 4, 14)
_TUESDAY = datetime(2014, 4, 15)
_NEXT_WEDNESDAY = datetime(2014, 4, 16)


@pytest.mark.parametrize("day", [_SATURDAY, _SUNDAY])
def test_next_monday(day):
    assert next_monday(day) == _MONDAY


@pytest.mark.parametrize(
    "day,expected", [(_SATURDAY, _MONDAY), (_SUNDAY, _TUESDAY), (_MONDAY, _TUESDAY)]
)
def test_next_monday_or_tuesday(day, expected):
    assert next_monday_or_tuesday(day) == expected


@pytest.mark.parametrize("day", [_SATURDAY, _SUNDAY])
def test_previous_friday(day):
    assert previous_friday(day) == _FRIDAY


def test_sunday_to_monday():
    assert sunday_to_monday(_SUNDAY) == _MONDAY


@pytest.mark.parametrize(
    "day,expected", [(_SATURDAY, _FRIDAY), (_SUNDAY, _MONDAY), (_MONDAY, _MONDAY)]
)
def test_nearest_workday(day, expected):
    assert nearest_workday(day) == expected


@pytest.mark.parametrize(
    "day,expected", [(_SATURDAY, _MONDAY), (_SUNDAY, _MONDAY), (_MONDAY, _MONDAY)]
)
def test_weekend_to_monday(day, expected):
    assert weekend_to_monday(day) == expected


@pytest.mark.parametrize(
    "day,expected",
    [
        (_WEDNESDAY, _THURSDAY),
        (_THURSDAY, _FRIDAY),
        (_SATURDAY, _MONDAY),
        (_SUNDAY, _MONDAY),
        (_MONDAY, _TUESDAY),
        (_TUESDAY, _NEXT_WEDNESDAY),  # WED is same week as TUE
    ],
)
def test_next_workday(day, expected):
    assert next_workday(day) == expected


@pytest.mark.parametrize(
    "day,expected", [(_SATURDAY, _FRIDAY), (_SUNDAY, _FRIDAY), (_TUESDAY, _MONDAY)]
)
def test_previous_workday(day, expected):
    assert previous_workday(day) == expected


@pytest.mark.parametrize(
    "day,expected",
    [
        (_THURSDAY, _WEDNESDAY),
        (_FRIDAY, _THURSDAY),
        (_SATURDAY, _THURSDAY),
        (_SUNDAY, _FRIDAY),
        (_MONDAY, _FRIDAY),  # last week Friday
        (_TUESDAY, _MONDAY),
        (_NEXT_WEDNESDAY, _TUESDAY),  # WED is same week as TUE
    ],
)
def test_before_nearest_workday(day, expected):
    assert before_nearest_workday(day) == expected


@pytest.mark.parametrize(
    "day,expected", [(_SATURDAY, _MONDAY), (_SUNDAY, _TUESDAY), (_FRIDAY, _MONDAY)]
)
def test_after_nearest_workday(day, expected):
    assert after_nearest_workday(day) == expected
