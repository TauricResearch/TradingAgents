"""
Tests for offsets.BDay
"""
from __future__ import annotations

from datetime import (
    date,
    datetime,
    timedelta,
)

import numpy as np
import pytest

from pandas._libs.tslibs.offsets import (
    ApplyTypeError,
    BDay,
    BMonthEnd,
)

from pandas import (
    DatetimeIndex,
    Timedelta,
    _testing as tm,
)
from pandas.tests.tseries.offsets.common import (
    assert_is_on_offset,
    assert_offset_equal,
)

from pandas.tseries import offsets


@pytest.fixture
def dt():
    return datetime(2008, 1, 1)


@pytest.fixture
def _offset():
    return BDay


@pytest.fixture
def offset(_offset):
    return _offset()


@pytest.fixture
def offset2(_offset):
    return _offset(2)


class TestBusinessDay:
    def test_different_normalize_equals(self, _offset, offset2):
        # GH#21404 changed __eq__ to return False when `normalize` does not match
        offset = _offset()
        offset2 = _offset(normalize=True)
        assert offset != offset2

    def test_repr(self, offset, offset2):
        assert repr(offset) == "<BusinessDay>"
        assert repr(offset2) == "<2 * BusinessDays>"

        expected = "<BusinessDay: offset=datetime.timedelta(days=1)>"
        assert repr(offset + timedelta(1)) == expected

    def test_with_offset(self, dt, offset):
        offset = offset + timedelta(hours=2)

        assert (dt + offset) == datetime(2008, 1, 2, 2)

    @pytest.mark.parametrize(
        "td",
        [
            Timedelta(hours=2),
            Timedelta(hours=2).to_pytimedelta(),
            Timedelta(hours=2).to_timedelta64(),
        ],
        ids=lambda x: type(x),
    )
    def test_with_offset_index(self, td, dt, offset):
        dti = DatetimeIndex([dt])
        expected = DatetimeIndex([datetime(2008, 1, 2, 2)])

        result = dti + (td + offset)
        tm.assert_index_equal(result, expected)

        result = dti + (offset + td)
        tm.assert_index_equal(result, expected)

    def test_eq(self, offset2):
        assert offset2 == offset2

    def test_hash(self, offset2):
        assert hash(offset2) == hash(offset2)

    def test_add_datetime(self, dt, offset2):
        assert offset2 + dt == datetime(2008, 1, 3)
        assert offset2 + np.datetime64("2008-01-01 00:00:00") == datetime(2008, 1, 3)

    def testRollback1(self, dt, _offset):
        assert _offset(10).rollback(dt) == dt

    def testRollback2(self, _offset):
        assert _offset(10).rollback(datetime(2008, 1, 5)) == datetime(2008, 1, 4)

    def testRollforward1(self, dt, _offset):
        assert _offset(10).rollforward(dt) == dt

    def testRollforward2(self, _offset):
        assert _offset(10).rollforward(datetime(2008, 1, 5)) == datetime(2008, 1, 7)

    def test_roll_date_object(self, offset):
        dt = date(2012, 9, 15)

        result = offset.rollback(dt)
        assert result == datetime(2012, 9, 14)

        result = offset.rollforward(dt)
        assert result == datetime(2012, 9, 17)

        offset = offsets.Day()
        result = offset.rollback(dt)
        assert result == datetime(2012, 9, 15)

        result = offset.rollforward(dt)
        assert result == datetime(2012, 9, 15)

    @pytest.mark.parametrize(
        "dt, expected",
        [
            (datetime(2008, 1, 1), True),
            (datetime(2008, 1, 5), False),
        ],
    )
    def test_is_on_offset(self, offset, dt, expected):
        assert_is_on_offset(offset, dt, expected)

    apply_cases: list[tuple[int, dict[datetime, datetime]]] = [
        (
            1,
            {
                datetime(2008, 1, 1): datetime(2008, 1, 2),
                datetime(2008, 1, 4): datetime(2008, 1, 7),
                datetime(2008, 1, 5): datetime(2008, 1, 7),
                datetime(2008, 1, 6): datetime(2008, 1, 7),
                datetime(2008, 1, 7): datetime(2008, 1, 8),
            },
        ),
        (
            2,
            {
                datetime(2008, 1, 1): datetime(2008, 1, 3),
                datetime(2008, 1, 4): datetime(2008, 1, 8),
                datetime(2008, 1, 5): datetime(2008, 1, 8),
                datetime(2008, 1, 6): datetime(2008, 1, 8),
                datetime(2008, 1, 7): datetime(2008, 1, 9),
            },
        ),
        (
            -1,
            {
                datetime(2008, 1, 1): datetime(2007, 12, 31),
                datetime(2008, 1, 4): datetime(2008, 1, 3),
                datetime(2008, 1, 5): datetime(2008, 1, 4),
                datetime(2008, 1, 6): datetime(2008, 1, 4),
                datetime(2008, 1, 7): datetime(2008, 1, 4),
                datetime(2008, 1, 8): datetime(2008, 1, 7),
            },
        ),
        (
            -2,
            {
                datetime(2008, 1, 1): datetime(2007, 12, 28),
                datetime(2008, 1, 4): datetime(2008, 1, 2),
                datetime(2008, 1, 5): datetime(2008, 1, 3),
                datetime(2008, 1, 6): datetime(2008, 1, 3),
                datetime(2008, 1, 7): datetime(2008, 1, 3),
                datetime(2008, 1, 8): datetime(2008, 1, 4),
                datetime(2008, 1, 9): datetime(2008, 1, 7),
            },
        ),
        (
            0,
            {
                datetime(2008, 1, 1): datetime(2008, 1, 1),
                datetime(2008, 1, 4): datetime(2008, 1, 4),
                datetime(2008, 1, 5): datetime(2008, 1, 7),
                datetime(2008, 1, 6): datetime(2008, 1, 7),
                datetime(2008, 1, 7): datetime(2008, 1, 7),
            },
        ),
    ]

    @pytest.mark.parametrize("case", apply_cases)
    def test_apply(self, case, _offset):
        n, cases = case
        offset = _offset(n)
        for base, expected in cases.items():
            assert_offset_equal(offset, base, expected)

    def test_apply_large_n(self, _offset):
        dt = datetime(2012, 10, 23)

        result = dt + _offset(10)
        assert result == datetime(2012, 11, 6)

        result = dt + _offset(100) - _offset(100)
        assert result == dt

        off = _offset() * 6
        rs = datetime(2012, 1, 1) - off
        xp = datetime(2011, 12, 23)
        assert rs == xp

        st = datetime(2011, 12, 18)
        rs = st + off
        xp = datetime(2011, 12, 26)
        assert rs == xp

        off = _offset() * 10
        rs = datetime(2014, 1, 5) + off  # see #5890
        xp = datetime(2014, 1, 17)
        assert rs == xp

    def test_apply_corner(self, _offset):
        if _offset is BDay:
            msg = "Only know how to combine business day with datetime or timedelta"
        else:
            msg = (
                "Only know how to combine trading day "
                "with datetime, datetime64 or timedelta"
            )
        with pytest.raises(ApplyTypeError, match=msg):
            _offset()._apply(BMonthEnd())
