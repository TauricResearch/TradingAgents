"""
Tests for Fiscal Year and Fiscal Quarter offset classes
"""
from datetime import datetime

from dateutil.relativedelta import relativedelta
import pytest

from pandas import Timestamp
import pandas._testing as tm
from pandas.tests.tseries.offsets.common import (
    WeekDay,
    assert_is_on_offset,
    assert_offset_equal,
)

from pandas.tseries.offsets import (
    FY5253,
    FY5253Quarter,
)


def makeFY5253LastOfMonthQuarter(*args, **kwds):
    return FY5253Quarter(*args, variation="last", **kwds)


def makeFY5253NearestEndMonthQuarter(*args, **kwds):
    return FY5253Quarter(*args, variation="nearest", **kwds)


def makeFY5253NearestEndMonth(*args, **kwds):
    return FY5253(*args, variation="nearest", **kwds)


def makeFY5253LastOfMonth(*args, **kwds):
    return FY5253(*args, variation="last", **kwds)


def test_get_offset_name():
    assert (
        makeFY5253LastOfMonthQuarter(
            weekday=1, startingMonth=3, qtr_with_extra_week=4
        ).freqstr
        == "REQ-L-MAR-TUE-4"
    )
    assert (
        makeFY5253NearestEndMonthQuarter(
            weekday=1, startingMonth=3, qtr_with_extra_week=3
        ).freqstr
        == "REQ-N-MAR-TUE-3"
    )


class TestFY5253LastOfMonth:
    offset_lom_sat_aug = makeFY5253LastOfMonth(1, startingMonth=8, weekday=WeekDay.SAT)
    offset_lom_sat_sep = makeFY5253LastOfMonth(1, startingMonth=9, weekday=WeekDay.SAT)

    on_offset_cases = [
        # From Wikipedia (see:
        # https://en.wikipedia.org/wiki/4%E2%80%934%E2%80%935_calendar#Last_Saturday_of_the_month_at_fiscal_year_end)
        (offset_lom_sat_aug, datetime(2006, 8, 26), True),
        (offset_lom_sat_aug, datetime(2007, 8, 25), True),
        (offset_lom_sat_aug, datetime(2008, 8, 30), True),
        (offset_lom_sat_aug, datetime(2009, 8, 29), True),
        (offset_lom_sat_aug, datetime(2010, 8, 28), True),
        (offset_lom_sat_aug, datetime(2011, 8, 27), True),
        (offset_lom_sat_aug, datetime(2012, 8, 25), True),
        (offset_lom_sat_aug, datetime(2013, 8, 31), True),
        (offset_lom_sat_aug, datetime(2014, 8, 30), True),
        (offset_lom_sat_aug, datetime(2015, 8, 29), True),
        (offset_lom_sat_aug, datetime(2016, 8, 27), True),
        (offset_lom_sat_aug, datetime(2017, 8, 26), True),
        (offset_lom_sat_aug, datetime(2018, 8, 25), True),
        (offset_lom_sat_aug, datetime(2019, 8, 31), True),
        (offset_lom_sat_aug, datetime(2006, 8, 27), False),
        (offset_lom_sat_aug, datetime(2007, 8, 28), False),
        (offset_lom_sat_aug, datetime(2008, 8, 31), False),
        (offset_lom_sat_aug, datetime(2009, 8, 30), False),
        (offset_lom_sat_aug, datetime(2010, 8, 29), False),
        (offset_lom_sat_aug, datetime(2011, 8, 28), False),
        (offset_lom_sat_aug, datetime(2006, 8, 25), False),
        (offset_lom_sat_aug, datetime(2007, 8, 24), False),
        (offset_lom_sat_aug, datetime(2008, 8, 29), False),
        (offset_lom_sat_aug, datetime(2009, 8, 28), False),
        (offset_lom_sat_aug, datetime(2010, 8, 27), False),
        (offset_lom_sat_aug, datetime(2011, 8, 26), False),
        (offset_lom_sat_aug, datetime(2019, 8, 30), False),
        # From GMCR (see for example:
        # http://yahoo.brand.edgar-online.com/Default.aspx?
        # companyid=3184&formtypeID=7)
        (offset_lom_sat_sep, datetime(2010, 9, 25), True),
        (offset_lom_sat_sep, datetime(2011, 9, 24), True),
        (offset_lom_sat_sep, datetime(2012, 9, 29), True),
    ]

    @pytest.mark.parametrize("case", on_offset_cases)
    def test_is_on_offset(self, case):
        offset, dt, expected = case
        assert_is_on_offset(offset, dt, expected)

    def test_apply(self):
        offset_lom_aug_sat = makeFY5253LastOfMonth(startingMonth=8, weekday=WeekDay.SAT)
        offset_lom_aug_sat_1 = makeFY5253LastOfMonth(
            n=1, startingMonth=8, weekday=WeekDay.SAT
        )

        date_seq_lom_aug_sat = [
            datetime(2006, 8, 26),
            datetime(2007, 8, 25),
            datetime(2008, 8, 30),
            datetime(2009, 8, 29),
            datetime(2010, 8, 28),
            datetime(2011, 8, 27),
            datetime(2012, 8, 25),
            datetime(2013, 8, 31),
            datetime(2014, 8, 30),
            datetime(2015, 8, 29),
            datetime(2016, 8, 27),
        ]

        tests = [
            (offset_lom_aug_sat, date_seq_lom_aug_sat),
            (offset_lom_aug_sat_1, date_seq_lom_aug_sat),
            (offset_lom_aug_sat, [datetime(2006, 8, 25)] + date_seq_lom_aug_sat),
            (offset_lom_aug_sat_1, [datetime(2006, 8, 27)] + date_seq_lom_aug_sat[1:]),
            (
                makeFY5253LastOfMonth(n=-1, startingMonth=8, weekday=WeekDay.SAT),
                list(reversed(date_seq_lom_aug_sat)),
            ),
        ]
        for test in tests:
            offset, data = test
            current = data[0]
            for datum in data[1:]:
                current = current + offset
                assert current == datum


class TestFY5253NearestEndMonth:
    def test_get_year_end(self):
        assert makeFY5253NearestEndMonth(
            startingMonth=8, weekday=WeekDay.SAT
        ).get_year_end(datetime(2013, 1, 1)) == datetime(2013, 8, 31)
        assert makeFY5253NearestEndMonth(
            startingMonth=8, weekday=WeekDay.SUN
        ).get_year_end(datetime(2013, 1, 1)) == datetime(2013, 9, 1)
        assert makeFY5253NearestEndMonth(
            startingMonth=8, weekday=WeekDay.FRI
        ).get_year_end(datetime(2013, 1, 1)) == datetime(2013, 8, 30)

        offset_n = FY5253(weekday=WeekDay.TUE, startingMonth=12, variation="nearest")
        assert offset_n.get_year_end(datetime(2012, 1, 1)) == datetime(2013, 1, 1)
        assert offset_n.get_year_end(datetime(2012, 1, 10)) == datetime(2013, 1, 1)

        assert offset_n.get_year_end(datetime(2013, 1, 1)) == datetime(2013, 12, 31)
        assert offset_n.get_year_end(datetime(2013, 1, 2)) == datetime(2013, 12, 31)
        assert offset_n.get_year_end(datetime(2013, 1, 3)) == datetime(2013, 12, 31)
        assert offset_n.get_year_end(datetime(2013, 1, 10)) == datetime(2013, 12, 31)

        JNJ = FY5253(n=1, startingMonth=12, weekday=6, variation="nearest")
        assert JNJ.get_year_end(datetime(2006, 1, 1)) == datetime(2006, 12, 31)

    offset_lom_aug_sat = makeFY5253NearestEndMonth(
        1, startingMonth=8, weekday=WeekDay.SAT
    )
    offset_lom_aug_thu = makeFY5253NearestEndMonth(
        1, startingMonth=8, weekday=WeekDay.THU
    )
    offset_n = FY5253(weekday=WeekDay.TUE, startingMonth=12, variation="nearest")

    on_offset_cases = [
        #    From Wikipedia (see:
        #    https://en.wikipedia.org/wiki/4%E2%80%934%E2%80%935_calendar
        #    #Saturday_nearest_the_end_of_month)
        #    2006-09-02   2006 September 2
        #    2007-09-01   2007 September 1
        #    2008-08-30   2008 August 30    (leap year)
        #    2009-08-29   2009 August 29
        #    2010-08-28   2010 August 28
        #    2011-09-03   2011 September 3
        #    2012-09-01   2012 September 1  (leap year)
        #    2013-08-31   2013 August 31
        #    2014-08-30   2014 August 30
        #    2015-08-29   2015 August 29
        #    2016-09-03   2016 September 3  (leap year)
        #    2017-09-02   2017 September 2
        #    2018-09-01   2018 September 1
        #    2019-08-31   2019 August 31
        (offset_lom_aug_sat, datetime(2006, 9, 2), True),
        (offset_lom_aug_sat, datetime(2007, 9, 1), True),
        (offset_lom_aug_sat, datetime(2008, 8, 30), True),
        (offset_lom_aug_sat, datetime(2009, 8, 29), True),
        (offset_lom_aug_sat, datetime(2010, 8, 28), True),
        (offset_lom_aug_sat, datetime(2011, 9, 3), True),
        (offset_lom_aug_sat, datetime(2016, 9, 3), True),
        (offset_lom_aug_sat, datetime(2017, 9, 2), True),
        (offset_lom_aug_sat, datetime(2018, 9, 1), True),
        (offset_lom_aug_sat, datetime(2019, 8, 31), True),
        (offset_lom_aug_sat, datetime(2006, 8, 27), False),
        (offset_lom_aug_sat, datetime(2007, 8, 28), False),
        (offset_lom_aug_sat, datetime(2008, 8, 31), False),
        (offset_lom_aug_sat, datetime(2009, 8, 30), False),
        (offset_lom_aug_sat, datetime(2010, 8, 29), False),
        (offset_lom_aug_sat, datetime(2011, 8, 28), False),
        (offset_lom_aug_sat, datetime(2006, 8, 25), False),
        (offset_lom_aug_sat, datetime(2007, 8, 24), False),
        (offset_lom_aug_sat, datetime(2008, 8, 29), False),
        (offset_lom_aug_sat, datetime(2009, 8, 28), False),
        (offset_lom_aug_sat, datetime(2010, 8, 27), False),
        (offset_lom_aug_sat, datetime(2011, 8, 26), False),
        (offset_lom_aug_sat, datetime(2019, 8, 30), False),
        # From Micron, see:
        # http://google.brand.edgar-online.com/?sym=MU&formtypeID=7
        (offset_lom_aug_thu, datetime(2012, 8, 30), True),
        (offset_lom_aug_thu, datetime(2011, 9, 1), True),
        (offset_n, datetime(2012, 12, 31), False),
        (offset_n, datetime(2013, 1, 1), True),
        (offset_n, datetime(2013, 1, 2), False),
    ]

    @pytest.mark.parametrize("case", on_offset_cases)
    def test_is_on_offset(self, case):
        offset, dt, expected = case
        assert_is_on_offset(offset, dt, expected)

    def test_apply(self):
        date_seq_nem_8_sat = [
            datetime(2006, 9, 2),
            datetime(2007, 9, 1),
            datetime(2008, 8, 30),
            datetime(2009, 8, 29),
            datetime(2010, 8, 28),
            datetime(2011, 9, 3),
        ]

        JNJ = [
            datetime(2005, 1, 2),
            datetime(2006, 1, 1),
            datetime(2006, 12, 31),
            datetime(2007, 12, 30),
            datetime(2008, 12, 28),
            datetime(2010, 1, 3),
            datetime(2011, 1, 2),
            datetime(2012, 1, 1),
            datetime(2012, 12, 30),
        ]

        DEC_SAT = FY5253(n=-1, startingMonth=12, weekday=5, variation="nearest")

        tests = [
            (
                makeFY5253NearestEndMonth(startingMonth=8, weekday=WeekDay.SAT),
                date_seq_nem_8_sat,
            ),
            (
                makeFY5253NearestEndMonth(n=1, startingMonth=8, weekday=WeekDay.SAT),
                date_seq_nem_8_sat,
            ),
            (
                makeFY5253NearestEndMonth(startingMonth=8, weekday=WeekDay.SAT),
                [datetime(2006, 9, 1)] + date_seq_nem_8_sat,
            ),
            (
                makeFY5253NearestEndMonth(n=1, startingMonth=8, weekday=WeekDay.SAT),
                [datetime(2006, 9, 3)] + date_seq_nem_8_sat[1:],
            ),
            (
                makeFY5253NearestEndMonth(n=-1, startingMonth=8, weekday=WeekDay.SAT),
                list(reversed(date_seq_nem_8_sat)),
            ),
            (
                makeFY5253NearestEndMonth(n=1, startingMonth=12, weekday=WeekDay.SUN),
                JNJ,
            ),
            (
                makeFY5253NearestEndMonth(n=-1, startingMonth=12, weekday=WeekDay.SUN),
                list(reversed(JNJ)),
            ),
            (
                makeFY5253NearestEndMonth(n=1, startingMonth=12, weekday=WeekDay.SUN),
                [datetime(2005, 1, 2), datetime(2006, 1, 1)],
            ),
            (
                makeFY5253NearestEndMonth(n=1, startingMonth=12, weekday=WeekDay.SUN),
                [datetime(2006, 1, 2), datetime(2006, 12, 31)],
            ),
            (DEC_SAT, [datetime(2013, 1, 15), datetime(2012, 12, 29)]),
        ]
        for test in tests:
            offset, data = test
            current = data[0]
            for datum in data[1:]:
                current = current + offset
                assert current == datum


class TestFY5253LastOfMonthQuarter:
    def test_is_anchored(self):
        msg = "FY5253Quarter.is_anchored is deprecated "

        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert makeFY5253LastOfMonthQuarter(
                startingMonth=1, weekday=WeekDay.SAT, qtr_with_extra_week=4
            ).is_anchored()
            assert makeFY5253LastOfMonthQuarter(
                weekday=WeekDay.SAT, startingMonth=3, qtr_with_extra_week=4
            ).is_anchored()
            assert not makeFY5253LastOfMonthQuarter(
                2, startingMonth=1, weekday=WeekDay.SAT, qtr_with_extra_week=4
            ).is_anchored()

    def test_equality(self):
        assert makeFY5253LastOfMonthQuarter(
            startingMonth=1, weekday=WeekDay.SAT, qtr_with_extra_week=4
        ) == makeFY5253LastOfMonthQuarter(
            startingMonth=1, weekday=WeekDay.SAT, qtr_with_extra_week=4
        )
        assert makeFY5253LastOfMonthQuarter(
            startingMonth=1, weekday=WeekDay.SAT, qtr_with_extra_week=4
        ) != makeFY5253LastOfMonthQuarter(
            startingMonth=1, weekday=WeekDay.SUN, qtr_with_extra_week=4
        )
        assert makeFY5253LastOfMonthQuarter(
            startingMonth=1, weekday=WeekDay.SAT, qtr_with_extra_week=4
        ) != makeFY5253LastOfMonthQuarter(
            startingMonth=2, weekday=WeekDay.SAT, qtr_with_extra_week=4
        )

    def test_offset(self):
        offset = makeFY5253LastOfMonthQuarter(
            1, startingMonth=9, weekday=WeekDay.SAT, qtr_with_extra_week=4
        )
        offset2 = makeFY5253LastOfMonthQuarter(
            2, startingMonth=9, weekday=WeekDay.SAT, qtr_with_extra_week=4
        )
        offset4 = makeFY5253LastOfMonthQuarter(
            4, startingMonth=9, weekday=WeekDay.SAT, qtr_with_extra_week=4
        )

        offset_neg1 = makeFY5253LastOfMonthQuarter(
            -1, startingMonth=9, weekday=WeekDay.SAT, qtr_with_extra_week=4
        )
        offset_neg2 = makeFY5253LastOfMonthQuarter(
            -2, startingMonth=9, weekday=WeekDay.SAT, qtr_with_extra_week=4
        )

        GMCR = [
            datetime(2010, 3, 27),
            datetime(2010, 6, 26),
            datetime(2010, 9, 25),
            datetime(2010, 12, 25),
            datetime(2011, 3, 26),
            datetime(2011, 6, 25),
            datetime(2011, 9, 24),
            datetime(2011, 12, 24),
            datetime(2012, 3, 24),
            datetime(2012, 6, 23),
            datetime(2012, 9, 29),
            datetime(2012, 12, 29),
            datetime(2013, 3, 30),
            datetime(2013, 6, 29),
        ]

        assert_offset_equal(offset, base=GMCR[0], expected=GMCR[1])
        assert_offset_equal(
            offset, base=GMCR[0] + relativedelta(days=-1), expected=GMCR[0]
        )
        assert_offset_equal(offset, base=GMCR[1], expected=GMCR[2])

        assert_offset_equal(offset2, base=GMCR[0], expected=GMCR[2])
        assert_offset_equal(offset4, base=GMCR[0], expected=GMCR[4])

        assert_offset_equal(offset_neg1, base=GMCR[-1], expected=GMCR[-2])
        assert_offset_equal(
            offset_neg1, base=GMCR[-1] + relativedelta(days=+1), expected=GMCR[-1]
        )
        assert_offset_equal(offset_neg2, base=GMCR[-1], expected=GMCR[-3])

        date = GMCR[0] + relativedelta(days=-1)
        for expected in GMCR:
            assert_offset_equal(offset, date, expected)
            date = date + offset

        date = GMCR[-1] + relativedelta(days=+1)
        for expected in reversed(GMCR):
            assert_offset_equal(offset_neg1, date, expected)
            date = date + offset_neg1

    lomq_aug_sat_4 = makeFY5253LastOfMonthQuarter(
        1, startingMonth=8, weekday=WeekDay.SAT, qtr_with_extra_week=4
    )
    lomq_sep_sat_4 = makeFY5253LastOfMonthQuarter(
        1, startingMonth=9, weekday=WeekDay.SAT, qtr_with_extra_week=4
    )

    on_offset_cases = [
        # From Wikipedia
        (lomq_aug_sat_4, datetime(2006, 8, 26), True),
        (lomq_aug_sat_4, datetime(2007, 8, 25), True),
        (lomq_aug_sat_4, datetime(2008, 8, 30), True),
        (lomq_aug_sat_4, datetime(2009, 8, 29), True),
        (lomq_aug_sat_4, datetime(2010, 8, 28), True),
        (lomq_aug_sat_4, datetime(2011, 8, 27), True),
        (lomq_aug_sat_4, datetime(2019, 8, 31), True),
        (lomq_aug_sat_4, datetime(2006, 8, 27), False),
        (lomq_aug_sat_4, datetime(2007, 8, 28), False),
        (lomq_aug_sat_4, datetime(2008, 8, 31), False),
        (lomq_aug_sat_4, datetime(2009, 8, 30), False),
        (lomq_aug_sat_4, datetime(2010, 8, 29), False),
        (lomq_aug_sat_4, datetime(2011, 8, 28), False),
        (lomq_aug_sat_4, datetime(2006, 8, 25), False),
        (lomq_aug_sat_4, datetime(2007, 8, 24), False),
        (lomq_aug_sat_4, datetime(2008, 8, 29), False),
        (lomq_aug_sat_4, datetime(2009, 8, 28), False),
        (lomq_aug_sat_4, datetime(2010, 8, 27), False),
        (lomq_aug_sat_4, datetime(2011, 8, 26), False),
        (lomq_aug_sat_4, datetime(2019, 8, 30), False),
        # From GMCR
        (lomq_sep_sat_4, datetime(2010, 9, 25), True),
        (lomq_sep_sat_4, datetime(2011, 9, 24), True),
        (lomq_sep_sat_4, datetime(2012, 9, 29), True),
        (lomq_sep_sat_4, datetime(2013, 6, 29), True),
        (lomq_sep_sat_4, datetime(2012, 6, 23), True),
        (lomq_sep_sat_4, datetime(2012, 6, 30), False),
        (lomq_sep_sat_4, datetime(2013, 3, 30), True),
        (lomq_sep_sat_4, datetime(2012, 3, 24), True),
        (lomq_sep_sat_4, datetime(2012, 12, 29), True),
        (lomq_sep_sat_4, datetime(2011, 12, 24), True),
        # INTC (extra week in Q1)
        # See: http://www.intc.com/releasedetail.cfm?ReleaseID=542844
        (
            makeFY5253LastOfMonthQuarter(
                1, startingMonth=12, weekday=WeekDay.SAT, qtr_with_extra_week=1
            ),
            datetime(2011, 4, 2),
            True,
        ),
        # see: http://google.brand.edgar-online.com/?sym=INTC&formtypeID=7
        (
            makeFY5253LastOfMonthQuarter(
                1, startingMonth=12, weekday=WeekDay.SAT, qtr_with_extra_week=1
            ),
            datetime(2012, 12, 29),
            True,
        ),
        (
            makeFY5253LastOfMonthQuarter(
                1, startingMonth=12, weekday=WeekDay.SAT, qtr_with_extra_week=1
            ),
            datetime(2011, 12, 31),
            True,
        ),
        (
            makeFY5253LastOfMonthQuarter(
                1, startingMonth=12, weekday=WeekDay.SAT, qtr_with_extra_week=1
            ),
            datetime(2010, 12, 25),
            True,
        ),
    ]

    @pytest.mark.parametrize("case", on_offset_cases)
    def test_is_on_offset(self, case):
        offset, dt, expected = case
        assert_is_on_offset(offset, dt, expected)

    def test_year_has_extra_week(self):
        # End of long Q1
        assert makeFY5253LastOfMonthQuarter(
            1, startingMonth=12, weekday=WeekDay.SAT, qtr_with_extra_week=1
        ).year_has_extra_week(datetime(2011, 4, 2))

        # Start of long Q1
        assert makeFY5253LastOfMonthQuarter(
            1, startingMonth=12, weekday=WeekDay.SAT, qtr_with_extra_week=1
        ).year_has_extra_week(datetime(2010, 12, 26))

        # End of year before year with long Q1
        assert not makeFY5253LastOfMonthQuarter(
            1, startingMonth=12, weekday=WeekDay.SAT, qtr_with_extra_week=1
        ).year_has_extra_week(datetime(2010, 12, 25))

        for year in [
            x for x in range(1994, 2011 + 1) if x not in [2011, 2005, 2000, 1994]
        ]:
            assert not makeFY5253LastOfMonthQuarter(
                1, startingMonth=12, weekday=WeekDay.SAT, qtr_with_extra_week=1
            ).year_has_extra_week(datetime(year, 4, 2))

        # Other long years
        assert makeFY5253LastOfMonthQuarter(
            1, startingMonth=12, weekday=WeekDay.SAT, qtr_with_extra_week=1
        ).year_has_extra_week(datetime(2005, 4, 2))

        assert makeFY5253LastOfMonthQuarter(
            1, startingMonth=12, weekday=WeekDay.SAT, qtr_with_extra_week=1
        ).year_has_extra_week(datetime(2000, 4, 2))

        assert makeFY5253LastOfMonthQuarter(
            1, startingMonth=12, weekday=WeekDay.SAT, qtr_with_extra_week=1
        ).year_has_extra_week(datetime(1994, 4, 2))

    def test_get_weeks(self):
        sat_dec_1 = makeFY5253LastOfMonthQuarter(
            1, startingMonth=12, weekday=WeekDay.SAT, qtr_with_extra_week=1
        )
        sat_dec_4 = makeFY5253LastOfMonthQuarter(
            1, startingMonth=12, weekday=WeekDay.SAT, qtr_with_extra_week=4
        )

        assert sat_dec_1.get_weeks(datetime(2011, 4, 2)) == [14, 13, 13, 13]
        assert sat_dec_4.get_weeks(datetime(2011, 4, 2)) == [13, 13, 13, 14]
        assert sat_dec_1.get_weeks(datetime(2010, 12, 25)) == [13, 13, 13, 13]


class TestFY5253NearestEndMonthQuarter:
    offset_nem_sat_aug_4 = makeFY5253NearestEndMonthQuarter(
        1, startingMonth=8, weekday=WeekDay.SAT, qtr_with_extra_week=4
    )
    offset_nem_thu_aug_4 = makeFY5253NearestEndMonthQuarter(
        1, startingMonth=8, weekday=WeekDay.THU, qtr_with_extra_week=4
    )
    offset_n = FY5253(weekday=WeekDay.TUE, startingMonth=12, variation="nearest")

    on_offset_cases = [
        # From Wikipedia
        (offset_nem_sat_aug_4, datetime(2006, 9, 2), True),
        (offset_nem_sat_aug_4, datetime(2007, 9, 1), True),
        (offset_nem_sat_aug_4, datetime(2008, 8, 30), True),
        (offset_nem_sat_aug_4, datetime(2009, 8, 29), True),
        (offset_nem_sat_aug_4, datetime(2010, 8, 28), True),
        (offset_nem_sat_aug_4, datetime(2011, 9, 3), True),
        (offset_nem_sat_aug_4, datetime(2016, 9, 3), True),
        (offset_nem_sat_aug_4, datetime(2017, 9, 2), True),
        (offset_nem_sat_aug_4, datetime(2018, 9, 1), True),
        (offset_nem_sat_aug_4, datetime(2019, 8, 31), True),
        (offset_nem_sat_aug_4, datetime(2006, 8, 27), False),
        (offset_nem_sat_aug_4, datetime(2007, 8, 28), False),
        (offset_nem_sat_aug_4, datetime(2008, 8, 31), False),
        (offset_nem_sat_aug_4, datetime(2009, 8, 30), False),
        (offset_nem_sat_aug_4, datetime(2010, 8, 29), False),
        (offset_nem_sat_aug_4, datetime(2011, 8, 28), False),
        (offset_nem_sat_aug_4, datetime(2006, 8, 25), False),
        (offset_nem_sat_aug_4, datetime(2007, 8, 24), False),
        (offset_nem_sat_aug_4, datetime(2008, 8, 29), False),
        (offset_nem_sat_aug_4, datetime(2009, 8, 28), False),
        (offset_nem_sat_aug_4, datetime(2010, 8, 27), False),
        (offset_nem_sat_aug_4, datetime(2011, 8, 26), False),
        (offset_nem_sat_aug_4, datetime(2019, 8, 30), False),
        # From Micron, see:
        # http://google.brand.edgar-online.com/?sym=MU&formtypeID=7
        (offset_nem_thu_aug_4, datetime(2012, 8, 30), True),
        (offset_nem_thu_aug_4, datetime(2011, 9, 1), True),
        # See: http://google.brand.edgar-online.com/?sym=MU&formtypeID=13
        (offset_nem_thu_aug_4, datetime(2013, 5, 30), True),
        (offset_nem_thu_aug_4, datetime(2013, 2, 28), True),
        (offset_nem_thu_aug_4, datetime(2012, 11, 29), True),
        (offset_nem_thu_aug_4, datetime(2012, 5, 31), True),
        (offset_nem_thu_aug_4, datetime(2007, 3, 1), True),
        (offset_nem_thu_aug_4, datetime(1994, 3, 3), True),
        (offset_n, datetime(2012, 12, 31), False),
        (offset_n, datetime(2013, 1, 1), True),
        (offset_n, datetime(2013, 1, 2), False),
    ]

    @pytest.mark.parametrize("case", on_offset_cases)
    def test_is_on_offset(self, case):
        offset, dt, expected = case
        assert_is_on_offset(offset, dt, expected)

    def test_offset(self):
        offset = makeFY5253NearestEndMonthQuarter(
            1, startingMonth=8, weekday=WeekDay.THU, qtr_with_extra_week=4
        )

        MU = [
            datetime(2012, 5, 31),
            datetime(2012, 8, 30),
            datetime(2012, 11, 29),
            datetime(2013, 2, 28),
            datetime(2013, 5, 30),
        ]

        date = MU[0] + relativedelta(days=-1)
        for expected in MU:
            assert_offset_equal(offset, date, expected)
            date = date + offset

        assert_offset_equal(offset, datetime(2012, 5, 31), datetime(2012, 8, 30))
        assert_offset_equal(offset, datetime(2012, 5, 30), datetime(2012, 5, 31))

        offset2 = FY5253Quarter(
            weekday=5, startingMonth=12, variation="last", qtr_with_extra_week=4
        )

        assert_offset_equal(offset2, datetime(2013, 1, 15), datetime(2013, 3, 30))


def test_bunched_yearends():
    # GH#14774 cases with two fiscal year-ends in the same calendar-year
    fy = FY5253(n=1, weekday=5, startingMonth=12, variation="nearest")
    dt = Timestamp("2004-01-01")
    assert fy.rollback(dt) == Timestamp("2002-12-28")
    assert (-fy)._apply(dt) == Timestamp("2002-12-28")
    assert dt - fy == Timestamp("2002-12-28")

    assert fy.rollforward(dt) == Timestamp("2004-01-03")
    assert fy._apply(dt) == Timestamp("2004-01-03")
    assert fy + dt == Timestamp("2004-01-03")
    assert dt + fy == Timestamp("2004-01-03")

    # Same thing, but starting from a Timestamp in the previous year.
    dt = Timestamp("2003-12-31")
    assert fy.rollback(dt) == Timestamp("2002-12-28")
    assert (-fy)._apply(dt) == Timestamp("2002-12-28")
    assert dt - fy == Timestamp("2002-12-28")


def test_fy5253_last_onoffset():
    # GH#18877 dates on the year-end but not normalized to midnight
    offset = FY5253(n=-5, startingMonth=5, variation="last", weekday=0)
    ts = Timestamp("1984-05-28 06:29:43.955911354+0200", tz="Europe/San_Marino")
    fast = offset.is_on_offset(ts)
    slow = (ts + offset) - offset == ts
    assert fast == slow


def test_fy5253_nearest_onoffset():
    # GH#18877 dates on the year-end but not normalized to midnight
    offset = FY5253(n=3, startingMonth=7, variation="nearest", weekday=2)
    ts = Timestamp("2032-07-28 00:12:59.035729419+0000", tz="Africa/Dakar")
    fast = offset.is_on_offset(ts)
    slow = (ts + offset) - offset == ts
    assert fast == slow


def test_fy5253qtr_onoffset_nearest():
    # GH#19036
    ts = Timestamp("1985-09-02 23:57:46.232550356-0300", tz="Atlantic/Bermuda")
    offset = FY5253Quarter(
        n=3, qtr_with_extra_week=1, startingMonth=2, variation="nearest", weekday=0
    )
    fast = offset.is_on_offset(ts)
    slow = (ts + offset) - offset == ts
    assert fast == slow


def test_fy5253qtr_onoffset_last():
    # GH#19036
    offset = FY5253Quarter(
        n=-2, qtr_with_extra_week=1, startingMonth=7, variation="last", weekday=2
    )
    ts = Timestamp("2011-01-26 19:03:40.331096129+0200", tz="Africa/Windhoek")
    slow = (ts + offset) - offset == ts
    fast = offset.is_on_offset(ts)
    assert fast == slow
