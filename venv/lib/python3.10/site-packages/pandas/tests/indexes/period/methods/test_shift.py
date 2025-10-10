import numpy as np
import pytest

from pandas import (
    PeriodIndex,
    period_range,
)
import pandas._testing as tm


class TestPeriodIndexShift:
    # ---------------------------------------------------------------
    # PeriodIndex.shift is used by __add__ and __sub__

    def test_pi_shift_ndarray(self):
        idx = PeriodIndex(
            ["2011-01", "2011-02", "NaT", "2011-04"], freq="M", name="idx"
        )
        result = idx.shift(np.array([1, 2, 3, 4]))
        expected = PeriodIndex(
            ["2011-02", "2011-04", "NaT", "2011-08"], freq="M", name="idx"
        )
        tm.assert_index_equal(result, expected)

        result = idx.shift(np.array([1, -2, 3, -4]))
        expected = PeriodIndex(
            ["2011-02", "2010-12", "NaT", "2010-12"], freq="M", name="idx"
        )
        tm.assert_index_equal(result, expected)

    def test_shift(self):
        pi1 = period_range(freq="Y", start="1/1/2001", end="12/1/2009")
        pi2 = period_range(freq="Y", start="1/1/2002", end="12/1/2010")

        tm.assert_index_equal(pi1.shift(0), pi1)

        assert len(pi1) == len(pi2)
        tm.assert_index_equal(pi1.shift(1), pi2)

        pi1 = period_range(freq="Y", start="1/1/2001", end="12/1/2009")
        pi2 = period_range(freq="Y", start="1/1/2000", end="12/1/2008")
        assert len(pi1) == len(pi2)
        tm.assert_index_equal(pi1.shift(-1), pi2)

        pi1 = period_range(freq="M", start="1/1/2001", end="12/1/2009")
        pi2 = period_range(freq="M", start="2/1/2001", end="1/1/2010")
        assert len(pi1) == len(pi2)
        tm.assert_index_equal(pi1.shift(1), pi2)

        pi1 = period_range(freq="M", start="1/1/2001", end="12/1/2009")
        pi2 = period_range(freq="M", start="12/1/2000", end="11/1/2009")
        assert len(pi1) == len(pi2)
        tm.assert_index_equal(pi1.shift(-1), pi2)

        pi1 = period_range(freq="D", start="1/1/2001", end="12/1/2009")
        pi2 = period_range(freq="D", start="1/2/2001", end="12/2/2009")
        assert len(pi1) == len(pi2)
        tm.assert_index_equal(pi1.shift(1), pi2)

        pi1 = period_range(freq="D", start="1/1/2001", end="12/1/2009")
        pi2 = period_range(freq="D", start="12/31/2000", end="11/30/2009")
        assert len(pi1) == len(pi2)
        tm.assert_index_equal(pi1.shift(-1), pi2)

    def test_shift_corner_cases(self):
        # GH#9903
        idx = PeriodIndex([], name="xxx", freq="h")

        msg = "`freq` argument is not supported for PeriodIndex.shift"
        with pytest.raises(TypeError, match=msg):
            # period shift doesn't accept freq
            idx.shift(1, freq="h")

        tm.assert_index_equal(idx.shift(0), idx)
        tm.assert_index_equal(idx.shift(3), idx)

        idx = PeriodIndex(
            ["2011-01-01 10:00", "2011-01-01 11:00", "2011-01-01 12:00"],
            name="xxx",
            freq="h",
        )
        tm.assert_index_equal(idx.shift(0), idx)
        exp = PeriodIndex(
            ["2011-01-01 13:00", "2011-01-01 14:00", "2011-01-01 15:00"],
            name="xxx",
            freq="h",
        )
        tm.assert_index_equal(idx.shift(3), exp)
        exp = PeriodIndex(
            ["2011-01-01 07:00", "2011-01-01 08:00", "2011-01-01 09:00"],
            name="xxx",
            freq="h",
        )
        tm.assert_index_equal(idx.shift(-3), exp)

    def test_shift_nat(self):
        idx = PeriodIndex(
            ["2011-01", "2011-02", "NaT", "2011-04"], freq="M", name="idx"
        )
        result = idx.shift(1)
        expected = PeriodIndex(
            ["2011-02", "2011-03", "NaT", "2011-05"], freq="M", name="idx"
        )
        tm.assert_index_equal(result, expected)
        assert result.name == expected.name

    def test_shift_gh8083(self):
        # test shift for PeriodIndex
        # GH#8083
        drange = period_range("20130101", periods=5, freq="D")
        result = drange.shift(1)
        expected = PeriodIndex(
            ["2013-01-02", "2013-01-03", "2013-01-04", "2013-01-05", "2013-01-06"],
            freq="D",
        )
        tm.assert_index_equal(result, expected)

    def test_shift_periods(self):
        # GH #22458 : argument 'n' was deprecated in favor of 'periods'
        idx = period_range(freq="Y", start="1/1/2001", end="12/1/2009")
        tm.assert_index_equal(idx.shift(periods=0), idx)
        tm.assert_index_equal(idx.shift(0), idx)
