import pytest

from pandas import (
    DatetimeIndex,
    Series,
    Timestamp,
    date_range,
)
import pandas._testing as tm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Setting a value on a view:FutureWarning"
)


@pytest.mark.parametrize(
    "cons",
    [
        lambda x: DatetimeIndex(x),
        lambda x: DatetimeIndex(DatetimeIndex(x)),
    ],
)
def test_datetimeindex(using_copy_on_write, cons):
    dt = date_range("2019-12-31", periods=3, freq="D")
    ser = Series(dt)
    idx = cons(ser)
    expected = idx.copy(deep=True)
    ser.iloc[0] = Timestamp("2020-12-31")
    if using_copy_on_write:
        tm.assert_index_equal(idx, expected)


def test_datetimeindex_tz_convert(using_copy_on_write):
    dt = date_range("2019-12-31", periods=3, freq="D", tz="Europe/Berlin")
    ser = Series(dt)
    idx = DatetimeIndex(ser).tz_convert("US/Eastern")
    expected = idx.copy(deep=True)
    ser.iloc[0] = Timestamp("2020-12-31", tz="Europe/Berlin")
    if using_copy_on_write:
        tm.assert_index_equal(idx, expected)


def test_datetimeindex_tz_localize(using_copy_on_write):
    dt = date_range("2019-12-31", periods=3, freq="D")
    ser = Series(dt)
    idx = DatetimeIndex(ser).tz_localize("Europe/Berlin")
    expected = idx.copy(deep=True)
    ser.iloc[0] = Timestamp("2020-12-31")
    if using_copy_on_write:
        tm.assert_index_equal(idx, expected)


def test_datetimeindex_isocalendar(using_copy_on_write):
    dt = date_range("2019-12-31", periods=3, freq="D")
    ser = Series(dt)
    df = DatetimeIndex(ser).isocalendar()
    expected = df.index.copy(deep=True)
    ser.iloc[0] = Timestamp("2020-12-31")
    if using_copy_on_write:
        tm.assert_index_equal(df.index, expected)


def test_index_values(using_copy_on_write):
    idx = date_range("2019-12-31", periods=3, freq="D")
    result = idx.values
    if using_copy_on_write:
        assert result.flags.writeable is False
    else:
        assert result.flags.writeable is True
