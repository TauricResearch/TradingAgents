from datetime import datetime

from dateutil.tz.tz import tzlocal
import pytest

from pandas._libs.tslibs import (
    OutOfBoundsDatetime,
    Timestamp,
)
from pandas.compat import (
    IS64,
    is_platform_windows,
)

from pandas.tseries.offsets import (
    FY5253,
    BDay,
    BMonthBegin,
    BMonthEnd,
    BQuarterBegin,
    BQuarterEnd,
    BusinessHour,
    BYearBegin,
    BYearEnd,
    CBMonthBegin,
    CBMonthEnd,
    CDay,
    CustomBusinessHour,
    DateOffset,
    FY5253Quarter,
    LastWeekOfMonth,
    MonthBegin,
    MonthEnd,
    QuarterEnd,
    SemiMonthBegin,
    SemiMonthEnd,
    Week,
    WeekOfMonth,
    YearBegin,
    YearEnd,
)


def _get_offset(klass, value=1, normalize=False):
    # create instance from offset class
    if klass is FY5253:
        klass = klass(
            n=value,
            startingMonth=1,
            weekday=1,
            variation="last",
            normalize=normalize,
        )
    elif klass is FY5253Quarter:
        klass = klass(
            n=value,
            startingMonth=1,
            weekday=1,
            qtr_with_extra_week=1,
            variation="last",
            normalize=normalize,
        )
    elif klass is LastWeekOfMonth:
        klass = klass(n=value, weekday=5, normalize=normalize)
    elif klass is WeekOfMonth:
        klass = klass(n=value, week=1, weekday=5, normalize=normalize)
    elif klass is Week:
        klass = klass(n=value, weekday=5, normalize=normalize)
    elif klass is DateOffset:
        klass = klass(days=value, normalize=normalize)
    else:
        klass = klass(value, normalize=normalize)
    return klass


@pytest.fixture(
    params=[
        BDay,
        BusinessHour,
        BMonthEnd,
        BMonthBegin,
        BQuarterEnd,
        BQuarterBegin,
        BYearEnd,
        BYearBegin,
        CDay,
        CustomBusinessHour,
        CBMonthEnd,
        CBMonthBegin,
        MonthEnd,
        MonthBegin,
        SemiMonthBegin,
        SemiMonthEnd,
        QuarterEnd,
        LastWeekOfMonth,
        WeekOfMonth,
        Week,
        YearBegin,
        YearEnd,
        FY5253,
        FY5253Quarter,
        DateOffset,
    ]
)
def _offset(request):
    return request.param


@pytest.fixture
def dt(_offset):
    if _offset in (CBMonthBegin, CBMonthEnd, BDay):
        return Timestamp(2008, 1, 1)
    elif _offset is (CustomBusinessHour, BusinessHour):
        return Timestamp(2014, 7, 1, 10, 00)
    return Timestamp(2008, 1, 2)


def test_apply_out_of_range(request, tz_naive_fixture, _offset):
    tz = tz_naive_fixture

    # try to create an out-of-bounds result timestamp; if we can't create
    # the offset skip
    try:
        if _offset in (BusinessHour, CustomBusinessHour):
            # Using 10000 in BusinessHour fails in tz check because of DST
            # difference
            offset = _get_offset(_offset, value=100000)
        else:
            offset = _get_offset(_offset, value=10000)

        result = Timestamp("20080101") + offset
        assert isinstance(result, datetime)
        assert result.tzinfo is None

        # Check tz is preserved
        t = Timestamp("20080101", tz=tz)
        result = t + offset
        assert isinstance(result, datetime)
        if tz is not None:
            assert t.tzinfo is not None

        if isinstance(tz, tzlocal) and not IS64 and _offset is not DateOffset:
            # If we hit OutOfBoundsDatetime on non-64 bit machines
            # we'll drop out of the try clause before the next test
            request.applymarker(
                pytest.mark.xfail(reason="OverflowError inside tzlocal past 2038")
            )
        elif (
            isinstance(tz, tzlocal)
            and is_platform_windows()
            and _offset in (QuarterEnd, BQuarterBegin, BQuarterEnd)
        ):
            request.applymarker(
                pytest.mark.xfail(reason="After GH#49737 t.tzinfo is None on CI")
            )
        assert str(t.tzinfo) == str(result.tzinfo)

    except OutOfBoundsDatetime:
        pass
    except (ValueError, KeyError):
        # we are creating an invalid offset
        # so ignore
        pass


def test_offsets_compare_equal(_offset):
    # root cause of GH#456: __ne__ was not implemented
    offset1 = _offset()
    offset2 = _offset()
    assert not offset1 != offset2
    assert offset1 == offset2


@pytest.mark.parametrize(
    "date, offset2",
    [
        [Timestamp(2008, 1, 1), BDay(2)],
        [Timestamp(2014, 7, 1, 10, 00), BusinessHour(n=3)],
        [
            Timestamp(2014, 7, 1, 10),
            CustomBusinessHour(
                holidays=["2014-06-27", Timestamp(2014, 6, 30), Timestamp("2014-07-02")]
            ),
        ],
        [Timestamp(2008, 1, 2), SemiMonthEnd(2)],
        [Timestamp(2008, 1, 2), SemiMonthBegin(2)],
        [Timestamp(2008, 1, 2), Week(2)],
        [Timestamp(2008, 1, 2), WeekOfMonth(2)],
        [Timestamp(2008, 1, 2), LastWeekOfMonth(2)],
    ],
)
def test_rsub(date, offset2):
    assert date - offset2 == (-offset2)._apply(date)


@pytest.mark.parametrize(
    "date, offset2",
    [
        [Timestamp(2008, 1, 1), BDay(2)],
        [Timestamp(2014, 7, 1, 10, 00), BusinessHour(n=3)],
        [
            Timestamp(2014, 7, 1, 10),
            CustomBusinessHour(
                holidays=["2014-06-27", Timestamp(2014, 6, 30), Timestamp("2014-07-02")]
            ),
        ],
        [Timestamp(2008, 1, 2), SemiMonthEnd(2)],
        [Timestamp(2008, 1, 2), SemiMonthBegin(2)],
        [Timestamp(2008, 1, 2), Week(2)],
        [Timestamp(2008, 1, 2), WeekOfMonth(2)],
        [Timestamp(2008, 1, 2), LastWeekOfMonth(2)],
    ],
)
def test_radd(date, offset2):
    assert date + offset2 == offset2 + date


@pytest.mark.parametrize(
    "date, offset_box, offset2",
    [
        [Timestamp(2008, 1, 1), BDay, BDay(2)],
        [Timestamp(2008, 1, 2), SemiMonthEnd, SemiMonthEnd(2)],
        [Timestamp(2008, 1, 2), SemiMonthBegin, SemiMonthBegin(2)],
        [Timestamp(2008, 1, 2), Week, Week(2)],
        [Timestamp(2008, 1, 2), WeekOfMonth, WeekOfMonth(2)],
        [Timestamp(2008, 1, 2), LastWeekOfMonth, LastWeekOfMonth(2)],
    ],
)
def test_sub(date, offset_box, offset2):
    off = offset2
    msg = "Cannot subtract datetime from offset"
    with pytest.raises(TypeError, match=msg):
        off - date

    assert 2 * off - off == off
    assert date - offset2 == date + offset_box(-2)
    assert date - offset2 == date - (2 * off - off)


@pytest.mark.parametrize(
    "offset_box, offset1",
    [
        [BDay, BDay()],
        [LastWeekOfMonth, LastWeekOfMonth()],
        [WeekOfMonth, WeekOfMonth()],
        [Week, Week()],
        [SemiMonthBegin, SemiMonthBegin()],
        [SemiMonthEnd, SemiMonthEnd()],
        [CustomBusinessHour, CustomBusinessHour(weekmask="Tue Wed Thu Fri")],
        [BusinessHour, BusinessHour()],
    ],
)
def test_Mult1(offset_box, offset1):
    dt = Timestamp(2008, 1, 2)
    assert dt + 10 * offset1 == dt + offset_box(10)
    assert dt + 5 * offset1 == dt + offset_box(5)


def test_compare_str(_offset):
    # GH#23524
    # comparing to strings that cannot be cast to DateOffsets should
    #  not raise for __eq__ or __ne__
    off = _get_offset(_offset)

    assert not off == "infer"
    assert off != "foo"
    # Note: inequalities are only implemented for Tick subclasses;
    #  tests for this are in test_ticks
