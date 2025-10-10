"""
Tests for the following offsets:
- Easter
"""
from __future__ import annotations

from datetime import datetime

import pytest

from pandas.tests.tseries.offsets.common import assert_offset_equal

from pandas.tseries.offsets import Easter


class TestEaster:
    @pytest.mark.parametrize(
        "offset,date,expected",
        [
            (Easter(), datetime(2010, 1, 1), datetime(2010, 4, 4)),
            (Easter(), datetime(2010, 4, 5), datetime(2011, 4, 24)),
            (Easter(2), datetime(2010, 1, 1), datetime(2011, 4, 24)),
            (Easter(), datetime(2010, 4, 4), datetime(2011, 4, 24)),
            (Easter(2), datetime(2010, 4, 4), datetime(2012, 4, 8)),
            (-Easter(), datetime(2011, 1, 1), datetime(2010, 4, 4)),
            (-Easter(), datetime(2010, 4, 5), datetime(2010, 4, 4)),
            (-Easter(2), datetime(2011, 1, 1), datetime(2009, 4, 12)),
            (-Easter(), datetime(2010, 4, 4), datetime(2009, 4, 12)),
            (-Easter(2), datetime(2010, 4, 4), datetime(2008, 3, 23)),
        ],
    )
    def test_offset(self, offset, date, expected):
        assert_offset_equal(offset, date, expected)
