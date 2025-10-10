"""
Tests of pandas.tseries.offsets
"""
from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
)

import numpy as np
import pytest

from pandas._libs.tslibs import (
    NaT,
    Timedelta,
    Timestamp,
    conversion,
    timezones,
)
import pandas._libs.tslibs.offsets as liboffsets
from pandas._libs.tslibs.offsets import (
    _get_offset,
    _offset_map,
    to_offset,
)
from pandas._libs.tslibs.period import INVALID_FREQ_ERR_MSG
from pandas.errors import PerformanceWarning

from pandas import (
    DataFrame,
    DatetimeIndex,
    Series,
    date_range,
)
import pandas._testing as tm
from pandas.tests.tseries.offsets.common import WeekDay

from pandas.tseries import offsets
from pandas.tseries.offsets import (
    FY5253,
    BDay,
    BMonthEnd,
    BusinessHour,
    CustomBusinessDay,
    CustomBusinessHour,
    CustomBusinessMonthBegin,
    CustomBusinessMonthEnd,
    DateOffset,
    Easter,
    FY5253Quarter,
    LastWeekOfMonth,
    MonthBegin,
    Nano,
    Tick,
    Week,
    WeekOfMonth,
)

_ARITHMETIC_DATE_OFFSET = [
    "years",
    "months",
    "weeks",
    "days",
    "hours",
    "minutes",
    "seconds",
    "milliseconds",
    "microseconds",
]


def _create_offset(klass, value=1, normalize=False):
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
        getattr(offsets, o)
        for o in offsets.__all__
        if issubclass(getattr(offsets, o), liboffsets.MonthOffset)
        and o != "MonthOffset"
    ]
)
def month_classes(request):
    """
    Fixture for month based datetime offsets available for a time series.
    """
    return request.param


@pytest.fixture(
    params=[
        getattr(offsets, o) for o in offsets.__all__ if o not in ("Tick", "BaseOffset")
    ]
)
def offset_types(request):
    """
    Fixture for all the datetime offsets available for a time series.
    """
    return request.param


@pytest.fixture
def dt():
    return Timestamp(datetime(2008, 1, 2))


@pytest.fixture
def expecteds():
    # executed value created by _create_offset
    # are applied to 2011/01/01 09:00 (Saturday)
    # used for .apply and .rollforward
    return {
        "Day": Timestamp("2011-01-02 09:00:00"),
        "DateOffset": Timestamp("2011-01-02 09:00:00"),
        "BusinessDay": Timestamp("2011-01-03 09:00:00"),
        "CustomBusinessDay": Timestamp("2011-01-03 09:00:00"),
        "CustomBusinessMonthEnd": Timestamp("2011-01-31 09:00:00"),
        "CustomBusinessMonthBegin": Timestamp("2011-01-03 09:00:00"),
        "MonthBegin": Timestamp("2011-02-01 09:00:00"),
        "BusinessMonthBegin": Timestamp("2011-01-03 09:00:00"),
        "MonthEnd": Timestamp("2011-01-31 09:00:00"),
        "SemiMonthEnd": Timestamp("2011-01-15 09:00:00"),
        "SemiMonthBegin": Timestamp("2011-01-15 09:00:00"),
        "BusinessMonthEnd": Timestamp("2011-01-31 09:00:00"),
        "YearBegin": Timestamp("2012-01-01 09:00:00"),
        "BYearBegin": Timestamp("2011-01-03 09:00:00"),
        "YearEnd": Timestamp("2011-12-31 09:00:00"),
        "BYearEnd": Timestamp("2011-12-30 09:00:00"),
        "QuarterBegin": Timestamp("2011-03-01 09:00:00"),
        "BQuarterBegin": Timestamp("2011-03-01 09:00:00"),
        "QuarterEnd": Timestamp("2011-03-31 09:00:00"),
        "BQuarterEnd": Timestamp("2011-03-31 09:00:00"),
        "BusinessHour": Timestamp("2011-01-03 10:00:00"),
        "CustomBusinessHour": Timestamp("2011-01-03 10:00:00"),
        "WeekOfMonth": Timestamp("2011-01-08 09:00:00"),
        "LastWeekOfMonth": Timestamp("2011-01-29 09:00:00"),
        "FY5253Quarter": Timestamp("2011-01-25 09:00:00"),
        "FY5253": Timestamp("2011-01-25 09:00:00"),
        "Week": Timestamp("2011-01-08 09:00:00"),
        "Easter": Timestamp("2011-04-24 09:00:00"),
        "Hour": Timestamp("2011-01-01 10:00:00"),
        "Minute": Timestamp("2011-01-01 09:01:00"),
        "Second": Timestamp("2011-01-01 09:00:01"),
        "Milli": Timestamp("2011-01-01 09:00:00.001000"),
        "Micro": Timestamp("2011-01-01 09:00:00.000001"),
        "Nano": Timestamp("2011-01-01T09:00:00.000000001"),
    }


class TestCommon:
    def test_immutable(self, offset_types):
        # GH#21341 check that __setattr__ raises
        offset = _create_offset(offset_types)
        msg = "objects is not writable|DateOffset objects are immutable"
        with pytest.raises(AttributeError, match=msg):
            offset.normalize = True
        with pytest.raises(AttributeError, match=msg):
            offset.n = 91

    def test_return_type(self, offset_types):
        offset = _create_offset(offset_types)

        # make sure that we are returning a Timestamp
        result = Timestamp("20080101") + offset
        assert isinstance(result, Timestamp)

        # make sure that we are returning NaT
        assert NaT + offset is NaT
        assert offset + NaT is NaT

        assert NaT - offset is NaT
        assert (-offset)._apply(NaT) is NaT

    def test_offset_n(self, offset_types):
        offset = _create_offset(offset_types)
        assert offset.n == 1

        neg_offset = offset * -1
        assert neg_offset.n == -1

        mul_offset = offset * 3
        assert mul_offset.n == 3

    def test_offset_timedelta64_arg(self, offset_types):
        # check that offset._validate_n raises TypeError on a timedelt64
        #  object
        off = _create_offset(offset_types)

        td64 = np.timedelta64(4567, "s")
        with pytest.raises(TypeError, match="argument must be an integer"):
            type(off)(n=td64, **off.kwds)

    def test_offset_mul_ndarray(self, offset_types):
        off = _create_offset(offset_types)

        expected = np.array([[off, off * 2], [off * 3, off * 4]])

        result = np.array([[1, 2], [3, 4]]) * off
        tm.assert_numpy_array_equal(result, expected)

        result = off * np.array([[1, 2], [3, 4]])
        tm.assert_numpy_array_equal(result, expected)

    def test_offset_freqstr(self, offset_types):
        offset = _create_offset(offset_types)

        freqstr = offset.freqstr
        if freqstr not in ("<Easter>", "<DateOffset: days=1>", "LWOM-SAT"):
            code = _get_offset(freqstr)
            assert offset.rule_code == code

    def _check_offsetfunc_works(self, offset, funcname, dt, expected, normalize=False):
        if normalize and issubclass(offset, Tick):
            # normalize=True disallowed for Tick subclasses GH#21427
            return

        offset_s = _create_offset(offset, normalize=normalize)
        func = getattr(offset_s, funcname)

        result = func(dt)
        assert isinstance(result, Timestamp)
        assert result == expected

        result = func(Timestamp(dt))
        assert isinstance(result, Timestamp)
        assert result == expected

        # see gh-14101
        ts = Timestamp(dt) + Nano(5)
        # test nanosecond is preserved
        with tm.assert_produces_warning(None):
            result = func(ts)

        assert isinstance(result, Timestamp)
        if normalize is False:
            assert result == expected + Nano(5)
        else:
            assert result == expected

        if isinstance(dt, np.datetime64):
            # test tz when input is datetime or Timestamp
            return

        for tz in [
            None,
            "UTC",
            "Asia/Tokyo",
            "US/Eastern",
            "dateutil/Asia/Tokyo",
            "dateutil/US/Pacific",
        ]:
            expected_localize = expected.tz_localize(tz)
            tz_obj = timezones.maybe_get_tz(tz)
            dt_tz = conversion.localize_pydatetime(dt, tz_obj)

            result = func(dt_tz)
            assert isinstance(result, Timestamp)
            assert result == expected_localize

            result = func(Timestamp(dt, tz=tz))
            assert isinstance(result, Timestamp)
            assert result == expected_localize

            # see gh-14101
            ts = Timestamp(dt, tz=tz) + Nano(5)
            # test nanosecond is preserved
            with tm.assert_produces_warning(None):
                result = func(ts)
            assert isinstance(result, Timestamp)
            if normalize is False:
                assert result == expected_localize + Nano(5)
            else:
                assert result == expected_localize

    def test_apply(self, offset_types, expecteds):
        sdt = datetime(2011, 1, 1, 9, 0)
        ndt = np.datetime64("2011-01-01 09:00")

        expected = expecteds[offset_types.__name__]
        expected_norm = Timestamp(expected.date())

        for dt in [sdt, ndt]:
            self._check_offsetfunc_works(offset_types, "_apply", dt, expected)

            self._check_offsetfunc_works(
                offset_types, "_apply", dt, expected_norm, normalize=True
            )

    def test_rollforward(self, offset_types, expecteds):
        expecteds = expecteds.copy()

        # result will not be changed if the target is on the offset
        no_changes = [
            "Day",
            "MonthBegin",
            "SemiMonthBegin",
            "YearBegin",
            "Week",
            "Hour",
            "Minute",
            "Second",
            "Milli",
            "Micro",
            "Nano",
            "DateOffset",
        ]
        for n in no_changes:
            expecteds[n] = Timestamp("2011/01/01 09:00")

        expecteds["BusinessHour"] = Timestamp("2011-01-03 09:00:00")
        expecteds["CustomBusinessHour"] = Timestamp("2011-01-03 09:00:00")

        # but be changed when normalize=True
        norm_expected = expecteds.copy()
        for k in norm_expected:
            norm_expected[k] = Timestamp(norm_expected[k].date())

        normalized = {
            "Day": Timestamp("2011-01-02 00:00:00"),
            "DateOffset": Timestamp("2011-01-02 00:00:00"),
            "MonthBegin": Timestamp("2011-02-01 00:00:00"),
            "SemiMonthBegin": Timestamp("2011-01-15 00:00:00"),
            "YearBegin": Timestamp("2012-01-01 00:00:00"),
            "Week": Timestamp("2011-01-08 00:00:00"),
            "Hour": Timestamp("2011-01-01 00:00:00"),
            "Minute": Timestamp("2011-01-01 00:00:00"),
            "Second": Timestamp("2011-01-01 00:00:00"),
            "Milli": Timestamp("2011-01-01 00:00:00"),
            "Micro": Timestamp("2011-01-01 00:00:00"),
        }
        norm_expected.update(normalized)

        sdt = datetime(2011, 1, 1, 9, 0)
        ndt = np.datetime64("2011-01-01 09:00")

        for dt in [sdt, ndt]:
            expected = expecteds[offset_types.__name__]
            self._check_offsetfunc_works(offset_types, "rollforward", dt, expected)
            expected = norm_expected[offset_types.__name__]
            self._check_offsetfunc_works(
                offset_types, "rollforward", dt, expected, normalize=True
            )

    def test_rollback(self, offset_types):
        expecteds = {
            "BusinessDay": Timestamp("2010-12-31 09:00:00"),
            "CustomBusinessDay": Timestamp("2010-12-31 09:00:00"),
            "CustomBusinessMonthEnd": Timestamp("2010-12-31 09:00:00"),
            "CustomBusinessMonthBegin": Timestamp("2010-12-01 09:00:00"),
            "BusinessMonthBegin": Timestamp("2010-12-01 09:00:00"),
            "MonthEnd": Timestamp("2010-12-31 09:00:00"),
            "SemiMonthEnd": Timestamp("2010-12-31 09:00:00"),
            "BusinessMonthEnd": Timestamp("2010-12-31 09:00:00"),
            "BYearBegin": Timestamp("2010-01-01 09:00:00"),
            "YearEnd": Timestamp("2010-12-31 09:00:00"),
            "BYearEnd": Timestamp("2010-12-31 09:00:00"),
            "QuarterBegin": Timestamp("2010-12-01 09:00:00"),
            "BQuarterBegin": Timestamp("2010-12-01 09:00:00"),
            "QuarterEnd": Timestamp("2010-12-31 09:00:00"),
            "BQuarterEnd": Timestamp("2010-12-31 09:00:00"),
            "BusinessHour": Timestamp("2010-12-31 17:00:00"),
            "CustomBusinessHour": Timestamp("2010-12-31 17:00:00"),
            "WeekOfMonth": Timestamp("2010-12-11 09:00:00"),
            "LastWeekOfMonth": Timestamp("2010-12-25 09:00:00"),
            "FY5253Quarter": Timestamp("2010-10-26 09:00:00"),
            "FY5253": Timestamp("2010-01-26 09:00:00"),
            "Easter": Timestamp("2010-04-04 09:00:00"),
        }

        # result will not be changed if the target is on the offset
        for n in [
            "Day",
            "MonthBegin",
            "SemiMonthBegin",
            "YearBegin",
            "Week",
            "Hour",
            "Minute",
            "Second",
            "Milli",
            "Micro",
            "Nano",
            "DateOffset",
        ]:
            expecteds[n] = Timestamp("2011/01/01 09:00")

        # but be changed when normalize=True
        norm_expected = expecteds.copy()
        for k in norm_expected:
            norm_expected[k] = Timestamp(norm_expected[k].date())

        normalized = {
            "Day": Timestamp("2010-12-31 00:00:00"),
            "DateOffset": Timestamp("2010-12-31 00:00:00"),
            "MonthBegin": Timestamp("2010-12-01 00:00:00"),
            "SemiMonthBegin": Timestamp("2010-12-15 00:00:00"),
            "YearBegin": Timestamp("2010-01-01 00:00:00"),
            "Week": Timestamp("2010-12-25 00:00:00"),
            "Hour": Timestamp("2011-01-01 00:00:00"),
            "Minute": Timestamp("2011-01-01 00:00:00"),
            "Second": Timestamp("2011-01-01 00:00:00"),
            "Milli": Timestamp("2011-01-01 00:00:00"),
            "Micro": Timestamp("2011-01-01 00:00:00"),
        }
        norm_expected.update(normalized)

        sdt = datetime(2011, 1, 1, 9, 0)
        ndt = np.datetime64("2011-01-01 09:00")

        for dt in [sdt, ndt]:
            expected = expecteds[offset_types.__name__]
            self._check_offsetfunc_works(offset_types, "rollback", dt, expected)

            expected = norm_expected[offset_types.__name__]
            self._check_offsetfunc_works(
                offset_types, "rollback", dt, expected, normalize=True
            )

    def test_is_on_offset(self, offset_types, expecteds):
        dt = expecteds[offset_types.__name__]
        offset_s = _create_offset(offset_types)
        assert offset_s.is_on_offset(dt)

        # when normalize=True, is_on_offset checks time is 00:00:00
        if issubclass(offset_types, Tick):
            # normalize=True disallowed for Tick subclasses GH#21427
            return
        offset_n = _create_offset(offset_types, normalize=True)
        assert not offset_n.is_on_offset(dt)

        if offset_types in (BusinessHour, CustomBusinessHour):
            # In default BusinessHour (9:00-17:00), normalized time
            # cannot be in business hour range
            return
        date = datetime(dt.year, dt.month, dt.day)
        assert offset_n.is_on_offset(date)

    def test_add(self, offset_types, tz_naive_fixture, expecteds):
        tz = tz_naive_fixture
        dt = datetime(2011, 1, 1, 9, 0)

        offset_s = _create_offset(offset_types)
        expected = expecteds[offset_types.__name__]

        result_dt = dt + offset_s
        result_ts = Timestamp(dt) + offset_s
        for result in [result_dt, result_ts]:
            assert isinstance(result, Timestamp)
            assert result == expected

        expected_localize = expected.tz_localize(tz)
        result = Timestamp(dt, tz=tz) + offset_s
        assert isinstance(result, Timestamp)
        assert result == expected_localize

        # normalize=True, disallowed for Tick subclasses GH#21427
        if issubclass(offset_types, Tick):
            return
        offset_s = _create_offset(offset_types, normalize=True)
        expected = Timestamp(expected.date())

        result_dt = dt + offset_s
        result_ts = Timestamp(dt) + offset_s
        for result in [result_dt, result_ts]:
            assert isinstance(result, Timestamp)
            assert result == expected

        expected_localize = expected.tz_localize(tz)
        result = Timestamp(dt, tz=tz) + offset_s
        assert isinstance(result, Timestamp)
        assert result == expected_localize

    def test_add_empty_datetimeindex(self, offset_types, tz_naive_fixture):
        # GH#12724, GH#30336
        offset_s = _create_offset(offset_types)

        dti = DatetimeIndex([], tz=tz_naive_fixture).as_unit("ns")

        warn = None
        if isinstance(
            offset_s,
            (
                Easter,
                WeekOfMonth,
                LastWeekOfMonth,
                CustomBusinessDay,
                BusinessHour,
                CustomBusinessHour,
                CustomBusinessMonthBegin,
                CustomBusinessMonthEnd,
                FY5253,
                FY5253Quarter,
            ),
        ):
            # We don't have an optimized apply_index
            warn = PerformanceWarning

        # stacklevel checking is slow, and we have ~800 of variants of this
        #  test, so let's only check the stacklevel in a subset of them
        check_stacklevel = tz_naive_fixture is None
        with tm.assert_produces_warning(warn, check_stacklevel=check_stacklevel):
            result = dti + offset_s
        tm.assert_index_equal(result, dti)
        with tm.assert_produces_warning(warn, check_stacklevel=check_stacklevel):
            result = offset_s + dti
        tm.assert_index_equal(result, dti)

        dta = dti._data
        with tm.assert_produces_warning(warn, check_stacklevel=check_stacklevel):
            result = dta + offset_s
        tm.assert_equal(result, dta)
        with tm.assert_produces_warning(warn, check_stacklevel=check_stacklevel):
            result = offset_s + dta
        tm.assert_equal(result, dta)

    def test_pickle_roundtrip(self, offset_types):
        off = _create_offset(offset_types)
        res = tm.round_trip_pickle(off)
        assert off == res
        if type(off) is not DateOffset:
            for attr in off._attributes:
                if attr == "calendar":
                    # np.busdaycalendar __eq__ will return False;
                    #  we check holidays and weekmask attrs so are OK
                    continue
                # Make sure nothings got lost from _params (which __eq__) is based on
                assert getattr(off, attr) == getattr(res, attr)

    def test_pickle_dateoffset_odd_inputs(self):
        # GH#34511
        off = DateOffset(months=12)
        res = tm.round_trip_pickle(off)
        assert off == res

        base_dt = datetime(2020, 1, 1)
        assert base_dt + off == base_dt + res

    def test_offsets_hashable(self, offset_types):
        # GH: 37267
        off = _create_offset(offset_types)
        assert hash(off) is not None

    # TODO: belongs in arithmetic tests?
    @pytest.mark.filterwarnings(
        "ignore:Non-vectorized DateOffset being applied to Series or DatetimeIndex"
    )
    @pytest.mark.parametrize("unit", ["s", "ms", "us"])
    def test_add_dt64_ndarray_non_nano(self, offset_types, unit):
        # check that the result with non-nano matches nano
        off = _create_offset(offset_types)

        dti = date_range("2016-01-01", periods=35, freq="D", unit=unit)

        result = (dti + off)._with_freq(None)

        exp_unit = unit
        if isinstance(off, Tick) and off._creso > dti._data._creso:
            # cast to higher reso like we would with Timedelta scalar
            exp_unit = Timedelta(off).unit
        # TODO(GH#55564): as_unit will be unnecessary
        expected = DatetimeIndex([x + off for x in dti]).as_unit(exp_unit)

        tm.assert_index_equal(result, expected)


class TestDateOffset:
    def setup_method(self):
        _offset_map.clear()

    def test_repr(self):
        repr(DateOffset())
        repr(DateOffset(2))
        repr(2 * DateOffset())
        repr(2 * DateOffset(months=2))

    def test_mul(self):
        assert DateOffset(2) == 2 * DateOffset(1)
        assert DateOffset(2) == DateOffset(1) * 2

    @pytest.mark.parametrize("kwd", sorted(liboffsets._relativedelta_kwds))
    def test_constructor(self, kwd, request):
        if kwd == "millisecond":
            request.applymarker(
                pytest.mark.xfail(
                    raises=NotImplementedError,
                    reason="Constructing DateOffset object with `millisecond` is not "
                    "yet supported.",
                )
            )
        offset = DateOffset(**{kwd: 2})
        assert offset.kwds == {kwd: 2}
        assert getattr(offset, kwd) == 2

    def test_default_constructor(self, dt):
        assert (dt + DateOffset(2)) == datetime(2008, 1, 4)

    def test_is_anchored(self):
        msg = "DateOffset.is_anchored is deprecated "

        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert not DateOffset(2).is_anchored()
            assert DateOffset(1).is_anchored()

    def test_copy(self):
        assert DateOffset(months=2).copy() == DateOffset(months=2)
        assert DateOffset(milliseconds=1).copy() == DateOffset(milliseconds=1)

    @pytest.mark.parametrize(
        "arithmatic_offset_type, expected",
        zip(
            _ARITHMETIC_DATE_OFFSET,
            [
                "2009-01-02",
                "2008-02-02",
                "2008-01-09",
                "2008-01-03",
                "2008-01-02 01:00:00",
                "2008-01-02 00:01:00",
                "2008-01-02 00:00:01",
                "2008-01-02 00:00:00.001000000",
                "2008-01-02 00:00:00.000001000",
            ],
        ),
    )
    def test_add(self, arithmatic_offset_type, expected, dt):
        assert DateOffset(**{arithmatic_offset_type: 1}) + dt == Timestamp(expected)
        assert dt + DateOffset(**{arithmatic_offset_type: 1}) == Timestamp(expected)

    @pytest.mark.parametrize(
        "arithmatic_offset_type, expected",
        zip(
            _ARITHMETIC_DATE_OFFSET,
            [
                "2007-01-02",
                "2007-12-02",
                "2007-12-26",
                "2008-01-01",
                "2008-01-01 23:00:00",
                "2008-01-01 23:59:00",
                "2008-01-01 23:59:59",
                "2008-01-01 23:59:59.999000000",
                "2008-01-01 23:59:59.999999000",
            ],
        ),
    )
    def test_sub(self, arithmatic_offset_type, expected, dt):
        assert dt - DateOffset(**{arithmatic_offset_type: 1}) == Timestamp(expected)
        with pytest.raises(TypeError, match="Cannot subtract datetime from offset"):
            DateOffset(**{arithmatic_offset_type: 1}) - dt

    @pytest.mark.parametrize(
        "arithmatic_offset_type, n, expected",
        zip(
            _ARITHMETIC_DATE_OFFSET,
            range(1, 10),
            [
                "2009-01-02",
                "2008-03-02",
                "2008-01-23",
                "2008-01-06",
                "2008-01-02 05:00:00",
                "2008-01-02 00:06:00",
                "2008-01-02 00:00:07",
                "2008-01-02 00:00:00.008000000",
                "2008-01-02 00:00:00.000009000",
            ],
        ),
    )
    def test_mul_add(self, arithmatic_offset_type, n, expected, dt):
        assert DateOffset(**{arithmatic_offset_type: 1}) * n + dt == Timestamp(expected)
        assert n * DateOffset(**{arithmatic_offset_type: 1}) + dt == Timestamp(expected)
        assert dt + DateOffset(**{arithmatic_offset_type: 1}) * n == Timestamp(expected)
        assert dt + n * DateOffset(**{arithmatic_offset_type: 1}) == Timestamp(expected)

    @pytest.mark.parametrize(
        "arithmatic_offset_type, n, expected",
        zip(
            _ARITHMETIC_DATE_OFFSET,
            range(1, 10),
            [
                "2007-01-02",
                "2007-11-02",
                "2007-12-12",
                "2007-12-29",
                "2008-01-01 19:00:00",
                "2008-01-01 23:54:00",
                "2008-01-01 23:59:53",
                "2008-01-01 23:59:59.992000000",
                "2008-01-01 23:59:59.999991000",
            ],
        ),
    )
    def test_mul_sub(self, arithmatic_offset_type, n, expected, dt):
        assert dt - DateOffset(**{arithmatic_offset_type: 1}) * n == Timestamp(expected)
        assert dt - n * DateOffset(**{arithmatic_offset_type: 1}) == Timestamp(expected)

    def test_leap_year(self):
        d = datetime(2008, 1, 31)
        assert (d + DateOffset(months=1)) == datetime(2008, 2, 29)

    def test_eq(self):
        offset1 = DateOffset(days=1)
        offset2 = DateOffset(days=365)

        assert offset1 != offset2

        assert DateOffset(milliseconds=3) != DateOffset(milliseconds=7)

    @pytest.mark.parametrize(
        "offset_kwargs, expected_arg",
        [
            ({"microseconds": 1, "milliseconds": 1}, "2022-01-01 00:00:00.001001"),
            ({"seconds": 1, "milliseconds": 1}, "2022-01-01 00:00:01.001"),
            ({"minutes": 1, "milliseconds": 1}, "2022-01-01 00:01:00.001"),
            ({"hours": 1, "milliseconds": 1}, "2022-01-01 01:00:00.001"),
            ({"days": 1, "milliseconds": 1}, "2022-01-02 00:00:00.001"),
            ({"weeks": 1, "milliseconds": 1}, "2022-01-08 00:00:00.001"),
            ({"months": 1, "milliseconds": 1}, "2022-02-01 00:00:00.001"),
            ({"years": 1, "milliseconds": 1}, "2023-01-01 00:00:00.001"),
        ],
    )
    def test_milliseconds_combination(self, offset_kwargs, expected_arg):
        # GH 49897
        offset = DateOffset(**offset_kwargs)
        ts = Timestamp("2022-01-01")
        result = ts + offset
        expected = Timestamp(expected_arg)

        assert result == expected

    def test_offset_invalid_arguments(self):
        msg = "^Invalid argument/s or bad combination of arguments"
        with pytest.raises(ValueError, match=msg):
            DateOffset(picoseconds=1)


class TestOffsetNames:
    def test_get_offset_name(self):
        assert BDay().freqstr == "B"
        assert BDay(2).freqstr == "2B"
        assert BMonthEnd().freqstr == "BME"
        assert Week(weekday=0).freqstr == "W-MON"
        assert Week(weekday=1).freqstr == "W-TUE"
        assert Week(weekday=2).freqstr == "W-WED"
        assert Week(weekday=3).freqstr == "W-THU"
        assert Week(weekday=4).freqstr == "W-FRI"

        assert LastWeekOfMonth(weekday=WeekDay.SUN).freqstr == "LWOM-SUN"


def test_get_offset():
    with pytest.raises(ValueError, match=INVALID_FREQ_ERR_MSG):
        _get_offset("gibberish")
    with pytest.raises(ValueError, match=INVALID_FREQ_ERR_MSG):
        _get_offset("QS-JAN-B")

    pairs = [
        ("B", BDay()),
        ("b", BDay()),
        ("bme", BMonthEnd()),
        ("Bme", BMonthEnd()),
        ("W-MON", Week(weekday=0)),
        ("W-TUE", Week(weekday=1)),
        ("W-WED", Week(weekday=2)),
        ("W-THU", Week(weekday=3)),
        ("W-FRI", Week(weekday=4)),
    ]

    for name, expected in pairs:
        offset = _get_offset(name)
        assert offset == expected, (
            f"Expected {repr(name)} to yield {repr(expected)} "
            f"(actual: {repr(offset)})"
        )


def test_get_offset_legacy():
    pairs = [("w@Sat", Week(weekday=5))]
    for name, expected in pairs:
        with pytest.raises(ValueError, match=INVALID_FREQ_ERR_MSG):
            _get_offset(name)


class TestOffsetAliases:
    def setup_method(self):
        _offset_map.clear()

    def test_alias_equality(self):
        for k, v in _offset_map.items():
            if v is None:
                continue
            assert k == v.copy()

    def test_rule_code(self):
        lst = ["ME", "MS", "BME", "BMS", "D", "B", "h", "min", "s", "ms", "us"]
        for k in lst:
            assert k == _get_offset(k).rule_code
            # should be cached - this is kind of an internals test...
            assert k in _offset_map
            assert k == (_get_offset(k) * 3).rule_code

        suffix_lst = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        base = "W"
        for v in suffix_lst:
            alias = "-".join([base, v])
            assert alias == _get_offset(alias).rule_code
            assert alias == (_get_offset(alias) * 5).rule_code

        suffix_lst = [
            "JAN",
            "FEB",
            "MAR",
            "APR",
            "MAY",
            "JUN",
            "JUL",
            "AUG",
            "SEP",
            "OCT",
            "NOV",
            "DEC",
        ]
        base_lst = ["YE", "YS", "BYE", "BYS", "QE", "QS", "BQE", "BQS"]
        for base in base_lst:
            for v in suffix_lst:
                alias = "-".join([base, v])
                assert alias == _get_offset(alias).rule_code
                assert alias == (_get_offset(alias) * 5).rule_code


def test_freq_offsets():
    off = BDay(1, offset=timedelta(0, 1800))
    assert off.freqstr == "B+30Min"

    off = BDay(1, offset=timedelta(0, -1800))
    assert off.freqstr == "B-30Min"


class TestReprNames:
    def test_str_for_named_is_name(self):
        # look at all the amazing combinations!
        month_prefixes = ["YE", "YS", "BYE", "BYS", "QE", "BQE", "BQS", "QS"]
        names = [
            prefix + "-" + month
            for prefix in month_prefixes
            for month in [
                "JAN",
                "FEB",
                "MAR",
                "APR",
                "MAY",
                "JUN",
                "JUL",
                "AUG",
                "SEP",
                "OCT",
                "NOV",
                "DEC",
            ]
        ]
        days = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        names += ["W-" + day for day in days]
        names += ["WOM-" + week + day for week in ("1", "2", "3", "4") for day in days]
        _offset_map.clear()
        for name in names:
            offset = _get_offset(name)
            assert offset.freqstr == name


# ---------------------------------------------------------------------


def test_valid_default_arguments(offset_types):
    # GH#19142 check that the calling the constructors without passing
    # any keyword arguments produce valid offsets
    cls = offset_types
    cls()


@pytest.mark.parametrize("kwd", sorted(liboffsets._relativedelta_kwds))
def test_valid_month_attributes(kwd, month_classes):
    # GH#18226
    cls = month_classes
    # check that we cannot create e.g. MonthEnd(weeks=3)
    msg = rf"__init__\(\) got an unexpected keyword argument '{kwd}'"
    with pytest.raises(TypeError, match=msg):
        cls(**{kwd: 3})


def test_month_offset_name(month_classes):
    # GH#33757 off.name with n != 1 should not raise AttributeError
    obj = month_classes(1)
    obj2 = month_classes(2)
    assert obj2.name == obj.name


@pytest.mark.parametrize("kwd", sorted(liboffsets._relativedelta_kwds))
def test_valid_relativedelta_kwargs(kwd, request):
    if kwd == "millisecond":
        request.applymarker(
            pytest.mark.xfail(
                raises=NotImplementedError,
                reason="Constructing DateOffset object with `millisecond` is not "
                "yet supported.",
            )
        )
    # Check that all the arguments specified in liboffsets._relativedelta_kwds
    # are in fact valid relativedelta keyword args
    DateOffset(**{kwd: 1})


@pytest.mark.parametrize("kwd", sorted(liboffsets._relativedelta_kwds))
def test_valid_tick_attributes(kwd, tick_classes):
    # GH#18226
    cls = tick_classes
    # check that we cannot create e.g. Hour(weeks=3)
    msg = rf"__init__\(\) got an unexpected keyword argument '{kwd}'"
    with pytest.raises(TypeError, match=msg):
        cls(**{kwd: 3})


def test_validate_n_error():
    with pytest.raises(TypeError, match="argument must be an integer"):
        DateOffset(n="Doh!")

    with pytest.raises(TypeError, match="argument must be an integer"):
        MonthBegin(n=timedelta(1))

    with pytest.raises(TypeError, match="argument must be an integer"):
        BDay(n=np.array([1, 2], dtype=np.int64))


def test_require_integers(offset_types):
    cls = offset_types
    with pytest.raises(ValueError, match="argument must be an integer"):
        cls(n=1.5)


def test_tick_normalize_raises(tick_classes):
    # check that trying to create a Tick object with normalize=True raises
    # GH#21427
    cls = tick_classes
    msg = "Tick offset with `normalize=True` are not allowed."
    with pytest.raises(ValueError, match=msg):
        cls(n=3, normalize=True)


@pytest.mark.parametrize(
    "offset_kwargs, expected_arg",
    [
        ({"nanoseconds": 1}, "1970-01-01 00:00:00.000000001"),
        ({"nanoseconds": 5}, "1970-01-01 00:00:00.000000005"),
        ({"nanoseconds": -1}, "1969-12-31 23:59:59.999999999"),
        ({"microseconds": 1}, "1970-01-01 00:00:00.000001"),
        ({"microseconds": -1}, "1969-12-31 23:59:59.999999"),
        ({"seconds": 1}, "1970-01-01 00:00:01"),
        ({"seconds": -1}, "1969-12-31 23:59:59"),
        ({"minutes": 1}, "1970-01-01 00:01:00"),
        ({"minutes": -1}, "1969-12-31 23:59:00"),
        ({"hours": 1}, "1970-01-01 01:00:00"),
        ({"hours": -1}, "1969-12-31 23:00:00"),
        ({"days": 1}, "1970-01-02 00:00:00"),
        ({"days": -1}, "1969-12-31 00:00:00"),
        ({"weeks": 1}, "1970-01-08 00:00:00"),
        ({"weeks": -1}, "1969-12-25 00:00:00"),
        ({"months": 1}, "1970-02-01 00:00:00"),
        ({"months": -1}, "1969-12-01 00:00:00"),
        ({"years": 1}, "1971-01-01 00:00:00"),
        ({"years": -1}, "1969-01-01 00:00:00"),
    ],
)
def test_dateoffset_add_sub(offset_kwargs, expected_arg):
    offset = DateOffset(**offset_kwargs)
    ts = Timestamp(0)
    result = ts + offset
    expected = Timestamp(expected_arg)
    assert result == expected
    result -= offset
    assert result == ts
    result = offset + ts
    assert result == expected


def test_dateoffset_add_sub_timestamp_with_nano():
    offset = DateOffset(minutes=2, nanoseconds=9)
    ts = Timestamp(4)
    result = ts + offset
    expected = Timestamp("1970-01-01 00:02:00.000000013")
    assert result == expected
    result -= offset
    assert result == ts
    result = offset + ts
    assert result == expected

    offset2 = DateOffset(minutes=2, nanoseconds=9, hour=1)
    assert offset2._use_relativedelta
    with tm.assert_produces_warning(None):
        # no warning about Discarding nonzero nanoseconds
        result2 = ts + offset2
    expected2 = Timestamp("1970-01-01 01:02:00.000000013")
    assert result2 == expected2


@pytest.mark.parametrize(
    "attribute",
    [
        "hours",
        "days",
        "weeks",
        "months",
        "years",
    ],
)
def test_dateoffset_immutable(attribute):
    offset = DateOffset(**{attribute: 0})
    msg = "DateOffset objects are immutable"
    with pytest.raises(AttributeError, match=msg):
        setattr(offset, attribute, 5)


def test_dateoffset_misc():
    oset = offsets.DateOffset(months=2, days=4)
    # it works
    oset.freqstr

    assert not offsets.DateOffset(months=2) == 2


@pytest.mark.parametrize("n", [-1, 1, 3])
def test_construct_int_arg_no_kwargs_assumed_days(n):
    # GH 45890, 45643
    offset = DateOffset(n)
    assert offset._offset == timedelta(1)
    result = Timestamp(2022, 1, 2) + offset
    expected = Timestamp(2022, 1, 2 + n)
    assert result == expected


@pytest.mark.parametrize(
    "offset, expected",
    [
        (
            DateOffset(minutes=7, nanoseconds=18),
            Timestamp("2022-01-01 00:07:00.000000018"),
        ),
        (DateOffset(nanoseconds=3), Timestamp("2022-01-01 00:00:00.000000003")),
    ],
)
def test_dateoffset_add_sub_timestamp_series_with_nano(offset, expected):
    # GH 47856
    start_time = Timestamp("2022-01-01")
    teststamp = start_time
    testseries = Series([start_time])
    testseries = testseries + offset
    assert testseries[0] == expected
    testseries -= offset
    assert testseries[0] == teststamp
    testseries = offset + testseries
    assert testseries[0] == expected


@pytest.mark.parametrize(
    "n_months, scaling_factor, start_timestamp, expected_timestamp",
    [
        (1, 2, "2020-01-30", "2020-03-30"),
        (2, 1, "2020-01-30", "2020-03-30"),
        (1, 0, "2020-01-30", "2020-01-30"),
        (2, 0, "2020-01-30", "2020-01-30"),
        (1, -1, "2020-01-30", "2019-12-30"),
        (2, -1, "2020-01-30", "2019-11-30"),
    ],
)
def test_offset_multiplication(
    n_months, scaling_factor, start_timestamp, expected_timestamp
):
    # GH 47953
    mo1 = DateOffset(months=n_months)

    startscalar = Timestamp(start_timestamp)
    startarray = Series([startscalar])

    resultscalar = startscalar + (mo1 * scaling_factor)
    resultarray = startarray + (mo1 * scaling_factor)

    expectedscalar = Timestamp(expected_timestamp)
    expectedarray = Series([expectedscalar])
    assert resultscalar == expectedscalar

    tm.assert_series_equal(resultarray, expectedarray)


def test_dateoffset_operations_on_dataframes():
    # GH 47953
    df = DataFrame({"T": [Timestamp("2019-04-30")], "D": [DateOffset(months=1)]})
    frameresult1 = df["T"] + 26 * df["D"]
    df2 = DataFrame(
        {
            "T": [Timestamp("2019-04-30"), Timestamp("2019-04-30")],
            "D": [DateOffset(months=1), DateOffset(months=1)],
        }
    )
    expecteddate = Timestamp("2021-06-30")
    with tm.assert_produces_warning(PerformanceWarning):
        frameresult2 = df2["T"] + 26 * df2["D"]

    assert frameresult1[0] == expecteddate
    assert frameresult2[0] == expecteddate


def test_is_yqm_start_end():
    freq_m = to_offset("ME")
    bm = to_offset("BME")
    qfeb = to_offset("QE-FEB")
    qsfeb = to_offset("QS-FEB")
    bq = to_offset("BQE")
    bqs_apr = to_offset("BQS-APR")
    as_nov = to_offset("YS-NOV")

    tests = [
        (freq_m.is_month_start(Timestamp("2013-06-01")), 1),
        (bm.is_month_start(Timestamp("2013-06-01")), 0),
        (freq_m.is_month_start(Timestamp("2013-06-03")), 0),
        (bm.is_month_start(Timestamp("2013-06-03")), 1),
        (qfeb.is_month_end(Timestamp("2013-02-28")), 1),
        (qfeb.is_quarter_end(Timestamp("2013-02-28")), 1),
        (qfeb.is_year_end(Timestamp("2013-02-28")), 1),
        (qfeb.is_month_start(Timestamp("2013-03-01")), 1),
        (qfeb.is_quarter_start(Timestamp("2013-03-01")), 1),
        (qfeb.is_year_start(Timestamp("2013-03-01")), 1),
        (qsfeb.is_month_end(Timestamp("2013-03-31")), 1),
        (qsfeb.is_quarter_end(Timestamp("2013-03-31")), 0),
        (qsfeb.is_year_end(Timestamp("2013-03-31")), 0),
        (qsfeb.is_month_start(Timestamp("2013-02-01")), 1),
        (qsfeb.is_quarter_start(Timestamp("2013-02-01")), 1),
        (qsfeb.is_year_start(Timestamp("2013-02-01")), 1),
        (bq.is_month_end(Timestamp("2013-06-30")), 0),
        (bq.is_quarter_end(Timestamp("2013-06-30")), 0),
        (bq.is_year_end(Timestamp("2013-06-30")), 0),
        (bq.is_month_end(Timestamp("2013-06-28")), 1),
        (bq.is_quarter_end(Timestamp("2013-06-28")), 1),
        (bq.is_year_end(Timestamp("2013-06-28")), 0),
        (bqs_apr.is_month_end(Timestamp("2013-06-30")), 0),
        (bqs_apr.is_quarter_end(Timestamp("2013-06-30")), 0),
        (bqs_apr.is_year_end(Timestamp("2013-06-30")), 0),
        (bqs_apr.is_month_end(Timestamp("2013-06-28")), 1),
        (bqs_apr.is_quarter_end(Timestamp("2013-06-28")), 1),
        (bqs_apr.is_year_end(Timestamp("2013-03-29")), 1),
        (as_nov.is_year_start(Timestamp("2013-11-01")), 1),
        (as_nov.is_year_end(Timestamp("2013-10-31")), 1),
        (Timestamp("2012-02-01").days_in_month, 29),
        (Timestamp("2013-02-01").days_in_month, 28),
    ]

    for ts, value in tests:
        assert ts == value
