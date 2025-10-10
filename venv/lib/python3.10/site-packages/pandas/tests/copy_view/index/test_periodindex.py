import pytest

from pandas import (
    Period,
    PeriodIndex,
    Series,
    period_range,
)
import pandas._testing as tm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Setting a value on a view:FutureWarning"
)


@pytest.mark.parametrize(
    "cons",
    [
        lambda x: PeriodIndex(x),
        lambda x: PeriodIndex(PeriodIndex(x)),
    ],
)
def test_periodindex(using_copy_on_write, cons):
    dt = period_range("2019-12-31", periods=3, freq="D")
    ser = Series(dt)
    idx = cons(ser)
    expected = idx.copy(deep=True)
    ser.iloc[0] = Period("2020-12-31")
    if using_copy_on_write:
        tm.assert_index_equal(idx, expected)
