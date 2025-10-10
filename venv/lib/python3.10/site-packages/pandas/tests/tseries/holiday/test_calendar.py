from datetime import datetime

import pytest

from pandas import (
    DatetimeIndex,
    offsets,
    to_datetime,
)
import pandas._testing as tm

from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    Holiday,
    Timestamp,
    USFederalHolidayCalendar,
    USLaborDay,
    USThanksgivingDay,
    get_calendar,
)


@pytest.mark.parametrize(
    "transform", [lambda x: x, lambda x: x.strftime("%Y-%m-%d"), lambda x: Timestamp(x)]
)
def test_calendar(transform):
    start_date = datetime(2012, 1, 1)
    end_date = datetime(2012, 12, 31)

    calendar = USFederalHolidayCalendar()
    holidays = calendar.holidays(transform(start_date), transform(end_date))

    expected = [
        datetime(2012, 1, 2),
        datetime(2012, 1, 16),
        datetime(2012, 2, 20),
        datetime(2012, 5, 28),
        datetime(2012, 7, 4),
        datetime(2012, 9, 3),
        datetime(2012, 10, 8),
        datetime(2012, 11, 12),
        datetime(2012, 11, 22),
        datetime(2012, 12, 25),
    ]

    assert list(holidays.to_pydatetime()) == expected


def test_calendar_caching():
    # see gh-9552.

    class TestCalendar(AbstractHolidayCalendar):
        def __init__(self, name=None, rules=None) -> None:
            super().__init__(name=name, rules=rules)

    jan1 = TestCalendar(rules=[Holiday("jan1", year=2015, month=1, day=1)])
    jan2 = TestCalendar(rules=[Holiday("jan2", year=2015, month=1, day=2)])

    # Getting holidays for Jan 1 should not alter results for Jan 2.
    expected = DatetimeIndex(["01-Jan-2015"]).as_unit("ns")
    tm.assert_index_equal(jan1.holidays(), expected)

    expected2 = DatetimeIndex(["02-Jan-2015"]).as_unit("ns")
    tm.assert_index_equal(jan2.holidays(), expected2)


def test_calendar_observance_dates():
    # see gh-11477
    us_fed_cal = get_calendar("USFederalHolidayCalendar")
    holidays0 = us_fed_cal.holidays(
        datetime(2015, 7, 3), datetime(2015, 7, 3)
    )  # <-- same start and end dates
    holidays1 = us_fed_cal.holidays(
        datetime(2015, 7, 3), datetime(2015, 7, 6)
    )  # <-- different start and end dates
    holidays2 = us_fed_cal.holidays(
        datetime(2015, 7, 3), datetime(2015, 7, 3)
    )  # <-- same start and end dates

    # These should all produce the same result.
    #
    # In addition, calling with different start and end
    # dates should not alter the output if we call the
    # function again with the same start and end date.
    tm.assert_index_equal(holidays0, holidays1)
    tm.assert_index_equal(holidays0, holidays2)


def test_rule_from_name():
    us_fed_cal = get_calendar("USFederalHolidayCalendar")
    assert us_fed_cal.rule_from_name("Thanksgiving Day") == USThanksgivingDay


def test_calendar_2031():
    # See gh-27790
    #
    # Labor Day 2031 is on September 1. Saturday before is August 30.
    # Next working day after August 30 ought to be Tuesday, September 2.

    class testCalendar(AbstractHolidayCalendar):
        rules = [USLaborDay]

    cal = testCalendar()
    workDay = offsets.CustomBusinessDay(calendar=cal)
    Sat_before_Labor_Day_2031 = to_datetime("2031-08-30")
    next_working_day = Sat_before_Labor_Day_2031 + 0 * workDay
    assert next_working_day == to_datetime("2031-09-02")


def test_no_holidays_calendar():
    # Test for issue #31415

    class NoHolidaysCalendar(AbstractHolidayCalendar):
        pass

    cal = NoHolidaysCalendar()
    holidays = cal.holidays(Timestamp("01-Jan-2020"), Timestamp("01-Jan-2021"))
    empty_index = DatetimeIndex([])  # Type is DatetimeIndex since return_name=False
    tm.assert_index_equal(holidays, empty_index)
