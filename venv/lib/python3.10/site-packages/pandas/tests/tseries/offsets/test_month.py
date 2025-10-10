"""
Tests for the following offsets:
- SemiMonthBegin
- SemiMonthEnd
- MonthBegin
- MonthEnd
"""
from __future__ import annotations

from datetime import datetime

import pytest

from pandas._libs.tslibs import Timestamp
from pandas._libs.tslibs.offsets import (
    MonthBegin,
    MonthEnd,
    SemiMonthBegin,
    SemiMonthEnd,
)

from pandas import (
    DatetimeIndex,
    Series,
    _testing as tm,
)
from pandas.tests.tseries.offsets.common import (
    assert_is_on_offset,
    assert_offset_equal,
)


class TestSemiMonthEnd:
    def test_offset_whole_year(self):
        dates = (
            datetime(2007, 12, 31),
            datetime(2008, 1, 15),
            datetime(2008, 1, 31),
            datetime(2008, 2, 15),
            datetime(2008, 2, 29),
            datetime(2008, 3, 15),
            datetime(2008, 3, 31),
            datetime(2008, 4, 15),
            datetime(2008, 4, 30),
            datetime(2008, 5, 15),
            datetime(2008, 5, 31),
            datetime(2008, 6, 15),
            datetime(2008, 6, 30),
            datetime(2008, 7, 15),
            datetime(2008, 7, 31),
            datetime(2008, 8, 15),
            datetime(2008, 8, 31),
            datetime(2008, 9, 15),
            datetime(2008, 9, 30),
            datetime(2008, 10, 15),
            datetime(2008, 10, 31),
            datetime(2008, 11, 15),
            datetime(2008, 11, 30),
            datetime(2008, 12, 15),
            datetime(2008, 12, 31),
        )

        for base, exp_date in zip(dates[:-1], dates[1:]):
            assert_offset_equal(SemiMonthEnd(), base, exp_date)

        # ensure .apply_index works as expected
        shift = DatetimeIndex(dates[:-1])
        with tm.assert_produces_warning(None):
            # GH#22535 check that we don't get a FutureWarning from adding
            # an integer array to PeriodIndex
            result = SemiMonthEnd() + shift

        exp = DatetimeIndex(dates[1:])
        tm.assert_index_equal(result, exp)

    offset_cases = []
    offset_cases.append(
        (
            SemiMonthEnd(),
            {
                datetime(2008, 1, 1): datetime(2008, 1, 15),
                datetime(2008, 1, 15): datetime(2008, 1, 31),
                datetime(2008, 1, 31): datetime(2008, 2, 15),
                datetime(2006, 12, 14): datetime(2006, 12, 15),
                datetime(2006, 12, 29): datetime(2006, 12, 31),
                datetime(2006, 12, 31): datetime(2007, 1, 15),
                datetime(2007, 1, 1): datetime(2007, 1, 15),
                datetime(2006, 12, 1): datetime(2006, 12, 15),
                datetime(2006, 12, 15): datetime(2006, 12, 31),
            },
        )
    )

    offset_cases.append(
        (
            SemiMonthEnd(day_of_month=20),
            {
                datetime(2008, 1, 1): datetime(2008, 1, 20),
                datetime(2008, 1, 15): datetime(2008, 1, 20),
                datetime(2008, 1, 21): datetime(2008, 1, 31),
                datetime(2008, 1, 31): datetime(2008, 2, 20),
                datetime(2006, 12, 14): datetime(2006, 12, 20),
                datetime(2006, 12, 29): datetime(2006, 12, 31),
                datetime(2006, 12, 31): datetime(2007, 1, 20),
                datetime(2007, 1, 1): datetime(2007, 1, 20),
                datetime(2006, 12, 1): datetime(2006, 12, 20),
                datetime(2006, 12, 15): datetime(2006, 12, 20),
            },
        )
    )

    offset_cases.append(
        (
            SemiMonthEnd(0),
            {
                datetime(2008, 1, 1): datetime(2008, 1, 15),
                datetime(2008, 1, 16): datetime(2008, 1, 31),
                datetime(2008, 1, 15): datetime(2008, 1, 15),
                datetime(2008, 1, 31): datetime(2008, 1, 31),
                datetime(2006, 12, 29): datetime(2006, 12, 31),
                datetime(2006, 12, 31): datetime(2006, 12, 31),
                datetime(2007, 1, 1): datetime(2007, 1, 15),
            },
        )
    )

    offset_cases.append(
        (
            SemiMonthEnd(0, day_of_month=16),
            {
                datetime(2008, 1, 1): datetime(2008, 1, 16),
                datetime(2008, 1, 16): datetime(2008, 1, 16),
                datetime(2008, 1, 15): datetime(2008, 1, 16),
                datetime(2008, 1, 31): datetime(2008, 1, 31),
                datetime(2006, 12, 29): datetime(2006, 12, 31),
                datetime(2006, 12, 31): datetime(2006, 12, 31),
                datetime(2007, 1, 1): datetime(2007, 1, 16),
            },
        )
    )

    offset_cases.append(
        (
            SemiMonthEnd(2),
            {
                datetime(2008, 1, 1): datetime(2008, 1, 31),
                datetime(2008, 1, 31): datetime(2008, 2, 29),
                datetime(2006, 12, 29): datetime(2007, 1, 15),
                datetime(2006, 12, 31): datetime(2007, 1, 31),
                datetime(2007, 1, 1): datetime(2007, 1, 31),
                datetime(2007, 1, 16): datetime(2007, 2, 15),
                datetime(2006, 11, 1): datetime(2006, 11, 30),
            },
        )
    )

    offset_cases.append(
        (
            SemiMonthEnd(-1),
            {
                datetime(2007, 1, 1): datetime(2006, 12, 31),
                datetime(2008, 6, 30): datetime(2008, 6, 15),
                datetime(2008, 12, 31): datetime(2008, 12, 15),
                datetime(2006, 12, 29): datetime(2006, 12, 15),
                datetime(2006, 12, 30): datetime(2006, 12, 15),
                datetime(2007, 1, 1): datetime(2006, 12, 31),
            },
        )
    )

    offset_cases.append(
        (
            SemiMonthEnd(-1, day_of_month=4),
            {
                datetime(2007, 1, 1): datetime(2006, 12, 31),
                datetime(2007, 1, 4): datetime(2006, 12, 31),
                datetime(2008, 6, 30): datetime(2008, 6, 4),
                datetime(2008, 12, 31): datetime(2008, 12, 4),
                datetime(2006, 12, 5): datetime(2006, 12, 4),
                datetime(2006, 12, 30): datetime(2006, 12, 4),
                datetime(2007, 1, 1): datetime(2006, 12, 31),
            },
        )
    )

    offset_cases.append(
        (
            SemiMonthEnd(-2),
            {
                datetime(2007, 1, 1): datetime(2006, 12, 15),
                datetime(2008, 6, 30): datetime(2008, 5, 31),
                datetime(2008, 3, 15): datetime(2008, 2, 15),
                datetime(2008, 12, 31): datetime(2008, 11, 30),
                datetime(2006, 12, 29): datetime(2006, 11, 30),
                datetime(2006, 12, 14): datetime(2006, 11, 15),
                datetime(2007, 1, 1): datetime(2006, 12, 15),
            },
        )
    )

    @pytest.mark.parametrize("case", offset_cases)
    def test_offset(self, case):
        offset, cases = case
        for base, expected in cases.items():
            assert_offset_equal(offset, base, expected)

    @pytest.mark.parametrize("case", offset_cases)
    def test_apply_index(self, case):
        # https://github.com/pandas-dev/pandas/issues/34580
        offset, cases = case
        shift = DatetimeIndex(cases.keys())
        exp = DatetimeIndex(cases.values())

        with tm.assert_produces_warning(None):
            # GH#22535 check that we don't get a FutureWarning from adding
            # an integer array to PeriodIndex
            result = offset + shift
        tm.assert_index_equal(result, exp)

    on_offset_cases = [
        (datetime(2007, 12, 31), True),
        (datetime(2007, 12, 15), True),
        (datetime(2007, 12, 14), False),
        (datetime(2007, 12, 1), False),
        (datetime(2008, 2, 29), True),
    ]

    @pytest.mark.parametrize("case", on_offset_cases)
    def test_is_on_offset(self, case):
        dt, expected = case
        assert_is_on_offset(SemiMonthEnd(), dt, expected)

    @pytest.mark.parametrize("klass", [Series, DatetimeIndex])
    def test_vectorized_offset_addition(self, klass):
        shift = klass(
            [
                Timestamp("2000-01-15 00:15:00", tz="US/Central"),
                Timestamp("2000-02-15", tz="US/Central"),
            ],
            name="a",
        )

        with tm.assert_produces_warning(None):
            # GH#22535 check that we don't get a FutureWarning from adding
            # an integer array to PeriodIndex
            result = shift + SemiMonthEnd()
            result2 = SemiMonthEnd() + shift

        exp = klass(
            [
                Timestamp("2000-01-31 00:15:00", tz="US/Central"),
                Timestamp("2000-02-29", tz="US/Central"),
            ],
            name="a",
        )
        tm.assert_equal(result, exp)
        tm.assert_equal(result2, exp)

        shift = klass(
            [
                Timestamp("2000-01-01 00:15:00", tz="US/Central"),
                Timestamp("2000-02-01", tz="US/Central"),
            ],
            name="a",
        )

        with tm.assert_produces_warning(None):
            # GH#22535 check that we don't get a FutureWarning from adding
            # an integer array to PeriodIndex
            result = shift + SemiMonthEnd()
            result2 = SemiMonthEnd() + shift

        exp = klass(
            [
                Timestamp("2000-01-15 00:15:00", tz="US/Central"),
                Timestamp("2000-02-15", tz="US/Central"),
            ],
            name="a",
        )
        tm.assert_equal(result, exp)
        tm.assert_equal(result2, exp)


class TestSemiMonthBegin:
    def test_offset_whole_year(self):
        dates = (
            datetime(2007, 12, 15),
            datetime(2008, 1, 1),
            datetime(2008, 1, 15),
            datetime(2008, 2, 1),
            datetime(2008, 2, 15),
            datetime(2008, 3, 1),
            datetime(2008, 3, 15),
            datetime(2008, 4, 1),
            datetime(2008, 4, 15),
            datetime(2008, 5, 1),
            datetime(2008, 5, 15),
            datetime(2008, 6, 1),
            datetime(2008, 6, 15),
            datetime(2008, 7, 1),
            datetime(2008, 7, 15),
            datetime(2008, 8, 1),
            datetime(2008, 8, 15),
            datetime(2008, 9, 1),
            datetime(2008, 9, 15),
            datetime(2008, 10, 1),
            datetime(2008, 10, 15),
            datetime(2008, 11, 1),
            datetime(2008, 11, 15),
            datetime(2008, 12, 1),
            datetime(2008, 12, 15),
        )

        for base, exp_date in zip(dates[:-1], dates[1:]):
            assert_offset_equal(SemiMonthBegin(), base, exp_date)

        # ensure .apply_index works as expected
        shift = DatetimeIndex(dates[:-1])
        with tm.assert_produces_warning(None):
            # GH#22535 check that we don't get a FutureWarning from adding
            # an integer array to PeriodIndex
            result = SemiMonthBegin() + shift

        exp = DatetimeIndex(dates[1:])
        tm.assert_index_equal(result, exp)

    offset_cases = [
        (
            SemiMonthBegin(),
            {
                datetime(2008, 1, 1): datetime(2008, 1, 15),
                datetime(2008, 1, 15): datetime(2008, 2, 1),
                datetime(2008, 1, 31): datetime(2008, 2, 1),
                datetime(2006, 12, 14): datetime(2006, 12, 15),
                datetime(2006, 12, 29): datetime(2007, 1, 1),
                datetime(2006, 12, 31): datetime(2007, 1, 1),
                datetime(2007, 1, 1): datetime(2007, 1, 15),
                datetime(2006, 12, 1): datetime(2006, 12, 15),
                datetime(2006, 12, 15): datetime(2007, 1, 1),
            },
        ),
        (
            SemiMonthBegin(day_of_month=20),
            {
                datetime(2008, 1, 1): datetime(2008, 1, 20),
                datetime(2008, 1, 15): datetime(2008, 1, 20),
                datetime(2008, 1, 21): datetime(2008, 2, 1),
                datetime(2008, 1, 31): datetime(2008, 2, 1),
                datetime(2006, 12, 14): datetime(2006, 12, 20),
                datetime(2006, 12, 29): datetime(2007, 1, 1),
                datetime(2006, 12, 31): datetime(2007, 1, 1),
                datetime(2007, 1, 1): datetime(2007, 1, 20),
                datetime(2006, 12, 1): datetime(2006, 12, 20),
                datetime(2006, 12, 15): datetime(2006, 12, 20),
            },
        ),
        (
            SemiMonthBegin(0),
            {
                datetime(2008, 1, 1): datetime(2008, 1, 1),
                datetime(2008, 1, 16): datetime(2008, 2, 1),
                datetime(2008, 1, 15): datetime(2008, 1, 15),
                datetime(2008, 1, 31): datetime(2008, 2, 1),
                datetime(2006, 12, 29): datetime(2007, 1, 1),
                datetime(2006, 12, 2): datetime(2006, 12, 15),
                datetime(2007, 1, 1): datetime(2007, 1, 1),
            },
        ),
        (
            SemiMonthBegin(0, day_of_month=16),
            {
                datetime(2008, 1, 1): datetime(2008, 1, 1),
                datetime(2008, 1, 16): datetime(2008, 1, 16),
                datetime(2008, 1, 15): datetime(2008, 1, 16),
                datetime(2008, 1, 31): datetime(2008, 2, 1),
                datetime(2006, 12, 29): datetime(2007, 1, 1),
                datetime(2006, 12, 31): datetime(2007, 1, 1),
                datetime(2007, 1, 5): datetime(2007, 1, 16),
                datetime(2007, 1, 1): datetime(2007, 1, 1),
            },
        ),
        (
            SemiMonthBegin(2),
            {
                datetime(2008, 1, 1): datetime(2008, 2, 1),
                datetime(2008, 1, 31): datetime(2008, 2, 15),
                datetime(2006, 12, 1): datetime(2007, 1, 1),
                datetime(2006, 12, 29): datetime(2007, 1, 15),
                datetime(2006, 12, 15): datetime(2007, 1, 15),
                datetime(2007, 1, 1): datetime(2007, 2, 1),
                datetime(2007, 1, 16): datetime(2007, 2, 15),
                datetime(2006, 11, 1): datetime(2006, 12, 1),
            },
        ),
        (
            SemiMonthBegin(-1),
            {
                datetime(2007, 1, 1): datetime(2006, 12, 15),
                datetime(2008, 6, 30): datetime(2008, 6, 15),
                datetime(2008, 6, 14): datetime(2008, 6, 1),
                datetime(2008, 12, 31): datetime(2008, 12, 15),
                datetime(2006, 12, 29): datetime(2006, 12, 15),
                datetime(2006, 12, 15): datetime(2006, 12, 1),
                datetime(2007, 1, 1): datetime(2006, 12, 15),
            },
        ),
        (
            SemiMonthBegin(-1, day_of_month=4),
            {
                datetime(2007, 1, 1): datetime(2006, 12, 4),
                datetime(2007, 1, 4): datetime(2007, 1, 1),
                datetime(2008, 6, 30): datetime(2008, 6, 4),
                datetime(2008, 12, 31): datetime(2008, 12, 4),
                datetime(2006, 12, 5): datetime(2006, 12, 4),
                datetime(2006, 12, 30): datetime(2006, 12, 4),
                datetime(2006, 12, 2): datetime(2006, 12, 1),
                datetime(2007, 1, 1): datetime(2006, 12, 4),
            },
        ),
        (
            SemiMonthBegin(-2),
            {
                datetime(2007, 1, 1): datetime(2006, 12, 1),
                datetime(2008, 6, 30): datetime(2008, 6, 1),
                datetime(2008, 6, 14): datetime(2008, 5, 15),
                datetime(2008, 12, 31): datetime(2008, 12, 1),
                datetime(2006, 12, 29): datetime(2006, 12, 1),
                datetime(2006, 12, 15): datetime(2006, 11, 15),
                datetime(2007, 1, 1): datetime(2006, 12, 1),
            },
        ),
    ]

    @pytest.mark.parametrize("case", offset_cases)
    def test_offset(self, case):
        offset, cases = case
        for base, expected in cases.items():
            assert_offset_equal(offset, base, expected)

    @pytest.mark.parametrize("case", offset_cases)
    def test_apply_index(self, case):
        offset, cases = case
        shift = DatetimeIndex(cases.keys())

        with tm.assert_produces_warning(None):
            # GH#22535 check that we don't get a FutureWarning from adding
            # an integer array to PeriodIndex
            result = offset + shift

        exp = DatetimeIndex(cases.values())
        tm.assert_index_equal(result, exp)

    on_offset_cases = [
        (datetime(2007, 12, 1), True),
        (datetime(2007, 12, 15), True),
        (datetime(2007, 12, 14), False),
        (datetime(2007, 12, 31), False),
        (datetime(2008, 2, 15), True),
    ]

    @pytest.mark.parametrize("case", on_offset_cases)
    def test_is_on_offset(self, case):
        dt, expected = case
        assert_is_on_offset(SemiMonthBegin(), dt, expected)

    @pytest.mark.parametrize("klass", [Series, DatetimeIndex])
    def test_vectorized_offset_addition(self, klass):
        shift = klass(
            [
                Timestamp("2000-01-15 00:15:00", tz="US/Central"),
                Timestamp("2000-02-15", tz="US/Central"),
            ],
            name="a",
        )
        with tm.assert_produces_warning(None):
            # GH#22535 check that we don't get a FutureWarning from adding
            # an integer array to PeriodIndex
            result = shift + SemiMonthBegin()
            result2 = SemiMonthBegin() + shift

        exp = klass(
            [
                Timestamp("2000-02-01 00:15:00", tz="US/Central"),
                Timestamp("2000-03-01", tz="US/Central"),
            ],
            name="a",
        )
        tm.assert_equal(result, exp)
        tm.assert_equal(result2, exp)

        shift = klass(
            [
                Timestamp("2000-01-01 00:15:00", tz="US/Central"),
                Timestamp("2000-02-01", tz="US/Central"),
            ],
            name="a",
        )
        with tm.assert_produces_warning(None):
            # GH#22535 check that we don't get a FutureWarning from adding
            # an integer array to PeriodIndex
            result = shift + SemiMonthBegin()
            result2 = SemiMonthBegin() + shift

        exp = klass(
            [
                Timestamp("2000-01-15 00:15:00", tz="US/Central"),
                Timestamp("2000-02-15", tz="US/Central"),
            ],
            name="a",
        )
        tm.assert_equal(result, exp)
        tm.assert_equal(result2, exp)


class TestMonthBegin:
    offset_cases = []
    # NOTE: I'm not entirely happy with the logic here for Begin -ss
    # see thread 'offset conventions' on the ML
    offset_cases.append(
        (
            MonthBegin(),
            {
                datetime(2008, 1, 31): datetime(2008, 2, 1),
                datetime(2008, 2, 1): datetime(2008, 3, 1),
                datetime(2006, 12, 31): datetime(2007, 1, 1),
                datetime(2006, 12, 1): datetime(2007, 1, 1),
                datetime(2007, 1, 31): datetime(2007, 2, 1),
            },
        )
    )

    offset_cases.append(
        (
            MonthBegin(0),
            {
                datetime(2008, 1, 31): datetime(2008, 2, 1),
                datetime(2008, 1, 1): datetime(2008, 1, 1),
                datetime(2006, 12, 3): datetime(2007, 1, 1),
                datetime(2007, 1, 31): datetime(2007, 2, 1),
            },
        )
    )

    offset_cases.append(
        (
            MonthBegin(2),
            {
                datetime(2008, 2, 29): datetime(2008, 4, 1),
                datetime(2008, 1, 31): datetime(2008, 3, 1),
                datetime(2006, 12, 31): datetime(2007, 2, 1),
                datetime(2007, 12, 28): datetime(2008, 2, 1),
                datetime(2007, 1, 1): datetime(2007, 3, 1),
                datetime(2006, 11, 1): datetime(2007, 1, 1),
            },
        )
    )

    offset_cases.append(
        (
            MonthBegin(-1),
            {
                datetime(2007, 1, 1): datetime(2006, 12, 1),
                datetime(2008, 5, 31): datetime(2008, 5, 1),
                datetime(2008, 12, 31): datetime(2008, 12, 1),
                datetime(2006, 12, 29): datetime(2006, 12, 1),
                datetime(2006, 1, 2): datetime(2006, 1, 1),
            },
        )
    )

    @pytest.mark.parametrize("case", offset_cases)
    def test_offset(self, case):
        offset, cases = case
        for base, expected in cases.items():
            assert_offset_equal(offset, base, expected)


class TestMonthEnd:
    def test_day_of_month(self):
        dt = datetime(2007, 1, 1)
        offset = MonthEnd()

        result = dt + offset
        assert result == Timestamp(2007, 1, 31)

        result = result + offset
        assert result == Timestamp(2007, 2, 28)

    def test_normalize(self):
        dt = datetime(2007, 1, 1, 3)

        result = dt + MonthEnd(normalize=True)
        expected = dt.replace(hour=0) + MonthEnd()
        assert result == expected

    offset_cases = []
    offset_cases.append(
        (
            MonthEnd(),
            {
                datetime(2008, 1, 1): datetime(2008, 1, 31),
                datetime(2008, 1, 31): datetime(2008, 2, 29),
                datetime(2006, 12, 29): datetime(2006, 12, 31),
                datetime(2006, 12, 31): datetime(2007, 1, 31),
                datetime(2007, 1, 1): datetime(2007, 1, 31),
                datetime(2006, 12, 1): datetime(2006, 12, 31),
            },
        )
    )

    offset_cases.append(
        (
            MonthEnd(0),
            {
                datetime(2008, 1, 1): datetime(2008, 1, 31),
                datetime(2008, 1, 31): datetime(2008, 1, 31),
                datetime(2006, 12, 29): datetime(2006, 12, 31),
                datetime(2006, 12, 31): datetime(2006, 12, 31),
                datetime(2007, 1, 1): datetime(2007, 1, 31),
            },
        )
    )

    offset_cases.append(
        (
            MonthEnd(2),
            {
                datetime(2008, 1, 1): datetime(2008, 2, 29),
                datetime(2008, 1, 31): datetime(2008, 3, 31),
                datetime(2006, 12, 29): datetime(2007, 1, 31),
                datetime(2006, 12, 31): datetime(2007, 2, 28),
                datetime(2007, 1, 1): datetime(2007, 2, 28),
                datetime(2006, 11, 1): datetime(2006, 12, 31),
            },
        )
    )

    offset_cases.append(
        (
            MonthEnd(-1),
            {
                datetime(2007, 1, 1): datetime(2006, 12, 31),
                datetime(2008, 6, 30): datetime(2008, 5, 31),
                datetime(2008, 12, 31): datetime(2008, 11, 30),
                datetime(2006, 12, 29): datetime(2006, 11, 30),
                datetime(2006, 12, 30): datetime(2006, 11, 30),
                datetime(2007, 1, 1): datetime(2006, 12, 31),
            },
        )
    )

    @pytest.mark.parametrize("case", offset_cases)
    def test_offset(self, case):
        offset, cases = case
        for base, expected in cases.items():
            assert_offset_equal(offset, base, expected)

    on_offset_cases = [
        (MonthEnd(), datetime(2007, 12, 31), True),
        (MonthEnd(), datetime(2008, 1, 1), False),
    ]

    @pytest.mark.parametrize("case", on_offset_cases)
    def test_is_on_offset(self, case):
        offset, dt, expected = case
        assert_is_on_offset(offset, dt, expected)
