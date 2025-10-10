"""
Tests for offset behavior with indices.
"""
import pytest

from pandas import (
    Series,
    date_range,
)

from pandas.tseries.offsets import (
    BMonthBegin,
    BMonthEnd,
    BQuarterBegin,
    BQuarterEnd,
    BYearBegin,
    BYearEnd,
    MonthBegin,
    MonthEnd,
    QuarterBegin,
    QuarterEnd,
    YearBegin,
    YearEnd,
)


@pytest.mark.parametrize("n", [-2, 1])
@pytest.mark.parametrize(
    "cls",
    [
        MonthBegin,
        MonthEnd,
        BMonthBegin,
        BMonthEnd,
        QuarterBegin,
        QuarterEnd,
        BQuarterBegin,
        BQuarterEnd,
        YearBegin,
        YearEnd,
        BYearBegin,
        BYearEnd,
    ],
)
def test_apply_index(cls, n):
    offset = cls(n=n)
    rng = date_range(start="1/1/2000", periods=100000, freq="min")
    ser = Series(rng)

    res = rng + offset
    assert res.freq is None  # not retained
    assert res[0] == rng[0] + offset
    assert res[-1] == rng[-1] + offset
    res2 = ser + offset
    # apply_index is only for indexes, not series, so no res2_v2
    assert res2.iloc[0] == ser.iloc[0] + offset
    assert res2.iloc[-1] == ser.iloc[-1] + offset
