"""
Tests for offsets.CustomBusinessDay / CDay
"""
from datetime import (
    datetime,
    timedelta,
)

import numpy as np
import pytest

from pandas._libs.tslibs.offsets import CDay

from pandas import (
    _testing as tm,
    read_pickle,
)
from pandas.tests.tseries.offsets.common import assert_offset_equal

from pandas.tseries.holiday import USFederalHolidayCalendar


@pytest.fixture
def offset():
    return CDay()


@pytest.fixture
def offset2():
    return CDay(2)


class TestCustomBusinessDay:
    def test_repr(self, offset, offset2):
        assert repr(offset) == "<CustomBusinessDay>"
        assert repr(offset2) == "<2 * CustomBusinessDays>"

        expected = "<BusinessDay: offset=datetime.timedelta(days=1)>"
        assert repr(offset + timedelta(1)) == expected

    def test_holidays(self):
        # Define a TradingDay offset
        holidays = ["2012-05-01", datetime(2013, 5, 1), np.datetime64("2014-05-01")]
        tday = CDay(holidays=holidays)
        for year in range(2012, 2015):
            dt = datetime(year, 4, 30)
            xp = datetime(year, 5, 2)
            rs = dt + tday
            assert rs == xp

    def test_weekmask(self):
        weekmask_saudi = "Sat Sun Mon Tue Wed"  # Thu-Fri Weekend
        weekmask_uae = "1111001"  # Fri-Sat Weekend
        weekmask_egypt = [1, 1, 1, 1, 0, 0, 1]  # Fri-Sat Weekend
        bday_saudi = CDay(weekmask=weekmask_saudi)
        bday_uae = CDay(weekmask=weekmask_uae)
        bday_egypt = CDay(weekmask=weekmask_egypt)
        dt = datetime(2013, 5, 1)
        xp_saudi = datetime(2013, 5, 4)
        xp_uae = datetime(2013, 5, 2)
        xp_egypt = datetime(2013, 5, 2)
        assert xp_saudi == dt + bday_saudi
        assert xp_uae == dt + bday_uae
        assert xp_egypt == dt + bday_egypt
        xp2 = datetime(2013, 5, 5)
        assert xp2 == dt + 2 * bday_saudi
        assert xp2 == dt + 2 * bday_uae
        assert xp2 == dt + 2 * bday_egypt

    def test_weekmask_and_holidays(self):
        weekmask_egypt = "Sun Mon Tue Wed Thu"  # Fri-Sat Weekend
        holidays = ["2012-05-01", datetime(2013, 5, 1), np.datetime64("2014-05-01")]
        bday_egypt = CDay(holidays=holidays, weekmask=weekmask_egypt)
        dt = datetime(2013, 4, 30)
        xp_egypt = datetime(2013, 5, 5)
        assert xp_egypt == dt + 2 * bday_egypt

    @pytest.mark.filterwarnings("ignore:Non:pandas.errors.PerformanceWarning")
    def test_calendar(self):
        calendar = USFederalHolidayCalendar()
        dt = datetime(2014, 1, 17)
        assert_offset_equal(CDay(calendar=calendar), dt, datetime(2014, 1, 21))

    def test_roundtrip_pickle(self, offset, offset2):
        def _check_roundtrip(obj):
            unpickled = tm.round_trip_pickle(obj)
            assert unpickled == obj

        _check_roundtrip(offset)
        _check_roundtrip(offset2)
        _check_roundtrip(offset * 2)

    def test_pickle_compat_0_14_1(self, datapath):
        hdays = [datetime(2013, 1, 1) for ele in range(4)]
        pth = datapath("tseries", "offsets", "data", "cday-0.14.1.pickle")
        cday0_14_1 = read_pickle(pth)
        cday = CDay(holidays=hdays)
        assert cday == cday0_14_1
