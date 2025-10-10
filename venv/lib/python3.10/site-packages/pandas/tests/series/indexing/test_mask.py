import numpy as np
import pytest

from pandas import Series
import pandas._testing as tm


def test_mask():
    # compare with tested results in test_where
    s = Series(np.random.default_rng(2).standard_normal(5))
    cond = s > 0

    rs = s.where(~cond, np.nan)
    tm.assert_series_equal(rs, s.mask(cond))

    rs = s.where(~cond)
    rs2 = s.mask(cond)
    tm.assert_series_equal(rs, rs2)

    rs = s.where(~cond, -s)
    rs2 = s.mask(cond, -s)
    tm.assert_series_equal(rs, rs2)

    cond = Series([True, False, False, True, False], index=s.index)
    s2 = -(s.abs())
    rs = s2.where(~cond[:3])
    rs2 = s2.mask(cond[:3])
    tm.assert_series_equal(rs, rs2)

    rs = s2.where(~cond[:3], -s2)
    rs2 = s2.mask(cond[:3], -s2)
    tm.assert_series_equal(rs, rs2)

    msg = "Array conditional must be same shape as self"
    with pytest.raises(ValueError, match=msg):
        s.mask(1)
    with pytest.raises(ValueError, match=msg):
        s.mask(cond[:3].values, -s)


def test_mask_casts():
    # dtype changes
    ser = Series([1, 2, 3, 4])
    result = ser.mask(ser > 2, np.nan)
    expected = Series([1, 2, np.nan, np.nan])
    tm.assert_series_equal(result, expected)


def test_mask_casts2():
    # see gh-21891
    ser = Series([1, 2])
    res = ser.mask([True, False])

    exp = Series([np.nan, 2])
    tm.assert_series_equal(res, exp)


def test_mask_inplace():
    s = Series(np.random.default_rng(2).standard_normal(5))
    cond = s > 0

    rs = s.copy()
    rs.mask(cond, inplace=True)
    tm.assert_series_equal(rs.dropna(), s[~cond])
    tm.assert_series_equal(rs, s.mask(cond))

    rs = s.copy()
    rs.mask(cond, -s, inplace=True)
    tm.assert_series_equal(rs, s.mask(cond, -s))
