"""
Tests for the following offsets:
- Week
- WeekOfMonth
- LastWeekOfMonth
"""
from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
)

import pytest

from pandas._libs.tslibs import Timestamp
from pandas._libs.tslibs.offsets import (
    Day,
    LastWeekOfMonth,
    Week,
    WeekOfMonth,
)

import pandas._testing as tm
from pandas.tests.tseries.offsets.common import (
    WeekDay,
    assert_is_on_offset,
    assert_offset_equal,
)


class TestWeek:
    def test_repr(self):
        assert repr(Week(weekday=0)) == "<Week: weekday=0>"
        assert repr(Week(n=-1, weekday=0)) == "<-1 * Week: weekday=0>"
        assert repr(Week(n=-2, weekday=0)) == "<-2 * Weeks: weekday=0>"

    def test_corner(self):
        with pytest.raises(ValueError, match="Day must be"):
            Week(weekday=7)

        with pytest.raises(ValueError, match="Day must be"):
            Week(weekday=-1)

    def test_is_anchored(self):
        msg = "Week.is_anchored is deprecated "

        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert Week(weekday=0).is_anchored()
            assert not Week().is_anchored()
            assert not Week(2, weekday=2).is_anchored()
            assert not Week(2).is_anchored()

    offset_cases = []
    # not business week
    offset_cases.append(
        (
            Week(),
            {
                datetime(2008, 1, 1): datetime(2008, 1, 8),
                datetime(2008, 1, 4): datetime(2008, 1, 11),
                datetime(2008, 1, 5): datetime(2008, 1, 12),
                datetime(2008, 1, 6): datetime(2008, 1, 13),
                datetime(2008, 1, 7): datetime(2008, 1, 14),
            },
        )
    )

    # Mon
    offset_cases.append(
        (
            Week(weekday=0),
            {
                datetime(2007, 12, 31): datetime(2008, 1, 7),
                datetime(2008, 1, 4): datetime(2008, 1, 7),
                datetime(2008, 1, 5): datetime(2008, 1, 7),
                datetime(2008, 1, 6): datetime(2008, 1, 7),
                datetime(2008, 1, 7): datetime(2008, 1, 14),
            },
        )
    )

    # n=0 -> roll forward. Mon
    offset_cases.append(
        (
            Week(0, weekday=0),
            {
                datetime(2007, 12, 31): datetime(2007, 12, 31),
                datetime(2008, 1, 4): datetime(2008, 1, 7),
                datetime(2008, 1, 5): datetime(2008, 1, 7),
                datetime(2008, 1, 6): datetime(2008, 1, 7),
                datetime(2008, 1, 7): datetime(2008, 1, 7),
            },
        )
    )

    # n=0 -> roll forward. Mon
    offset_cases.append(
        (
            Week(-2, weekday=1),
            {
                datetime(2010, 4, 6): datetime(2010, 3, 23),
                datetime(2010, 4, 8): datetime(2010, 3, 30),
                datetime(2010, 4, 5): datetime(2010, 3, 23),
            },
        )
    )

    @pytest.mark.parametrize("case", offset_cases)
    def test_offset(self, case):
        offset, cases = case
        for base, expected in cases.items():
            assert_offset_equal(offset, base, expected)

    @pytest.mark.parametrize("weekday", range(7))
    def test_is_on_offset(self, weekday):
        offset = Week(weekday=weekday)

        for day in range(1, 8):
            date = datetime(2008, 1, day)
            expected = day % 7 == weekday
        assert_is_on_offset(offset, date, expected)

    @pytest.mark.parametrize(
        "n,date",
        [
            (2, "1862-01-13 09:03:34.873477378+0210"),
            (-2, "1856-10-24 16:18:36.556360110-0717"),
        ],
    )
    def test_is_on_offset_weekday_none(self, n, date):
        # GH 18510 Week with weekday = None, normalize = False
        # should always be is_on_offset
        offset = Week(n=n, weekday=None)
        ts = Timestamp(date, tz="Africa/Lusaka")
        fast = offset.is_on_offset(ts)
        slow = (ts + offset) - offset == ts
        assert fast == slow

    def test_week_add_invalid(self):
        # Week with weekday should raise TypeError and _not_ AttributeError
        #  when adding invalid offset
        offset = Week(weekday=1)
        other = Day()
        with pytest.raises(TypeError, match="Cannot add"):
            offset + other


class TestWeekOfMonth:
    def test_constructor(self):
        with pytest.raises(ValueError, match="^Week"):
            WeekOfMonth(n=1, week=4, weekday=0)

        with pytest.raises(ValueError, match="^Week"):
            WeekOfMonth(n=1, week=-1, weekday=0)

        with pytest.raises(ValueError, match="^Day"):
            WeekOfMonth(n=1, week=0, weekday=-1)

        with pytest.raises(ValueError, match="^Day"):
            WeekOfMonth(n=1, week=0, weekday=-7)

    def test_repr(self):
        assert (
            repr(WeekOfMonth(weekday=1, week=2)) == "<WeekOfMonth: week=2, weekday=1>"
        )

    def test_offset(self):
        date1 = datetime(2011, 1, 4)  # 1st Tuesday of Month
        date2 = datetime(2011, 1, 11)  # 2nd Tuesday of Month
        date3 = datetime(2011, 1, 18)  # 3rd Tuesday of Month
        date4 = datetime(2011, 1, 25)  # 4th Tuesday of Month

        # see for loop for structure
        test_cases = [
            (-2, 2, 1, date1, datetime(2010, 11, 16)),
            (-2, 2, 1, date2, datetime(2010, 11, 16)),
            (-2, 2, 1, date3, datetime(2010, 11, 16)),
            (-2, 2, 1, date4, datetime(2010, 12, 21)),
            (-1, 2, 1, date1, datetime(2010, 12, 21)),
            (-1, 2, 1, date2, datetime(2010, 12, 21)),
            (-1, 2, 1, date3, datetime(2010, 12, 21)),
            (-1, 2, 1, date4, datetime(2011, 1, 18)),
            (0, 0, 1, date1, datetime(2011, 1, 4)),
            (0, 0, 1, date2, datetime(2011, 2, 1)),
            (0, 0, 1, date3, datetime(2011, 2, 1)),
            (0, 0, 1, date4, datetime(2011, 2, 1)),
            (0, 1, 1, date1, datetime(2011, 1, 11)),
            (0, 1, 1, date2, datetime(2011, 1, 11)),
            (0, 1, 1, date3, datetime(2011, 2, 8)),
            (0, 1, 1, date4, datetime(2011, 2, 8)),
            (0, 0, 1, date1, datetime(2011, 1, 4)),
            (0, 1, 1, date2, datetime(2011, 1, 11)),
            (0, 2, 1, date3, datetime(2011, 1, 18)),
            (0, 3, 1, date4, datetime(2011, 1, 25)),
            (1, 0, 0, date1, datetime(2011, 2, 7)),
            (1, 0, 0, date2, datetime(2011, 2, 7)),
            (1, 0, 0, date3, datetime(2011, 2, 7)),
            (1, 0, 0, date4, datetime(2011, 2, 7)),
            (1, 0, 1, date1, datetime(2011, 2, 1)),
            (1, 0, 1, date2, datetime(2011, 2, 1)),
            (1, 0, 1, date3, datetime(2011, 2, 1)),
            (1, 0, 1, date4, datetime(2011, 2, 1)),
            (1, 0, 2, date1, datetime(2011, 1, 5)),
            (1, 0, 2, date2, datetime(2011, 2, 2)),
            (1, 0, 2, date3, datetime(2011, 2, 2)),
            (1, 0, 2, date4, datetime(2011, 2, 2)),
            (1, 2, 1, date1, datetime(2011, 1, 18)),
            (1, 2, 1, date2, datetime(2011, 1, 18)),
            (1, 2, 1, date3, datetime(2011, 2, 15)),
            (1, 2, 1, date4, datetime(2011, 2, 15)),
            (2, 2, 1, date1, datetime(2011, 2, 15)),
            (2, 2, 1, date2, datetime(2011, 2, 15)),
            (2, 2, 1, date3, datetime(2011, 3, 15)),
            (2, 2, 1, date4, datetime(2011, 3, 15)),
        ]

        for n, week, weekday, dt, expected in test_cases:
            offset = WeekOfMonth(n, week=week, weekday=weekday)
            assert_offset_equal(offset, dt, expected)

        # try subtracting
        result = datetime(2011, 2, 1) - WeekOfMonth(week=1, weekday=2)
        assert result == datetime(2011, 1, 12)

        result = datetime(2011, 2, 3) - WeekOfMonth(week=0, weekday=2)
        assert result == datetime(2011, 2, 2)

    on_offset_cases = [
        (0, 0, datetime(2011, 2, 7), True),
        (0, 0, datetime(2011, 2, 6), False),
        (0, 0, datetime(2011, 2, 14), False),
        (1, 0, datetime(2011, 2, 14), True),
        (0, 1, datetime(2011, 2, 1), True),
        (0, 1, datetime(2011, 2, 8), False),
    ]

    @pytest.mark.parametrize("case", on_offset_cases)
    def test_is_on_offset(self, case):
        week, weekday, dt, expected = case
        offset = WeekOfMonth(week=week, weekday=weekday)
        assert offset.is_on_offset(dt) == expected

    @pytest.mark.parametrize(
        "n,week,date,tz",
        [
            (2, 2, "1916-05-15 01:14:49.583410462+0422", "Asia/Qyzylorda"),
            (-3, 1, "1980-12-08 03:38:52.878321185+0500", "Asia/Oral"),
        ],
    )
    def test_is_on_offset_nanoseconds(self, n, week, date, tz):
        # GH 18864
        # Make sure that nanoseconds don't trip up is_on_offset (and with it apply)
        offset = WeekOfMonth(n=n, week=week, weekday=0)
        ts = Timestamp(date, tz=tz)
        fast = offset.is_on_offset(ts)
        slow = (ts + offset) - offset == ts
        assert fast == slow


class TestLastWeekOfMonth:
    def test_constructor(self):
        with pytest.raises(ValueError, match="^N cannot be 0"):
            LastWeekOfMonth(n=0, weekday=1)

        with pytest.raises(ValueError, match="^Day"):
            LastWeekOfMonth(n=1, weekday=-1)

        with pytest.raises(ValueError, match="^Day"):
            LastWeekOfMonth(n=1, weekday=7)

    def test_offset(self):
        # Saturday
        last_sat = datetime(2013, 8, 31)
        next_sat = datetime(2013, 9, 28)
        offset_sat = LastWeekOfMonth(n=1, weekday=5)

        one_day_before = last_sat + timedelta(days=-1)
        assert one_day_before + offset_sat == last_sat

        one_day_after = last_sat + timedelta(days=+1)
        assert one_day_after + offset_sat == next_sat

        # Test On that day
        assert last_sat + offset_sat == next_sat

        # Thursday

        offset_thur = LastWeekOfMonth(n=1, weekday=3)
        last_thurs = datetime(2013, 1, 31)
        next_thurs = datetime(2013, 2, 28)

        one_day_before = last_thurs + timedelta(days=-1)
        assert one_day_before + offset_thur == last_thurs

        one_day_after = last_thurs + timedelta(days=+1)
        assert one_day_after + offset_thur == next_thurs

        # Test on that day
        assert last_thurs + offset_thur == next_thurs

        three_before = last_thurs + timedelta(days=-3)
        assert three_before + offset_thur == last_thurs

        two_after = last_thurs + timedelta(days=+2)
        assert two_after + offset_thur == next_thurs

        offset_sunday = LastWeekOfMonth(n=1, weekday=WeekDay.SUN)
        assert datetime(2013, 7, 31) + offset_sunday == datetime(2013, 8, 25)

    on_offset_cases = [
        (WeekDay.SUN, datetime(2013, 1, 27), True),
        (WeekDay.SAT, datetime(2013, 3, 30), True),
        (WeekDay.MON, datetime(2013, 2, 18), False),  # Not the last Mon
        (WeekDay.SUN, datetime(2013, 2, 25), False),  # Not a SUN
        (WeekDay.MON, datetime(2013, 2, 25), True),
        (WeekDay.SAT, datetime(2013, 11, 30), True),
        (WeekDay.SAT, datetime(2006, 8, 26), True),
        (WeekDay.SAT, datetime(2007, 8, 25), True),
        (WeekDay.SAT, datetime(2008, 8, 30), True),
        (WeekDay.SAT, datetime(2009, 8, 29), True),
        (WeekDay.SAT, datetime(2010, 8, 28), True),
        (WeekDay.SAT, datetime(2011, 8, 27), True),
        (WeekDay.SAT, datetime(2019, 8, 31), True),
    ]

    @pytest.mark.parametrize("case", on_offset_cases)
    def test_is_on_offset(self, case):
        weekday, dt, expected = case
        offset = LastWeekOfMonth(weekday=weekday)
        assert offset.is_on_offset(dt) == expected

    @pytest.mark.parametrize(
        "n,weekday,date,tz",
        [
            (4, 6, "1917-05-27 20:55:27.084284178+0200", "Europe/Warsaw"),
            (-4, 5, "2005-08-27 05:01:42.799392561-0500", "America/Rainy_River"),
        ],
    )
    def test_last_week_of_month_on_offset(self, n, weekday, date, tz):
        # GH 19036, GH 18977 _adjust_dst was incorrect for LastWeekOfMonth
        offset = LastWeekOfMonth(n=n, weekday=weekday)
        ts = Timestamp(date, tz=tz)
        slow = (ts + offset) - offset == ts
        fast = offset.is_on_offset(ts)
        assert fast == slow

    def test_repr(self):
        assert (
            repr(LastWeekOfMonth(n=2, weekday=1)) == "<2 * LastWeekOfMonths: weekday=1>"
        )
