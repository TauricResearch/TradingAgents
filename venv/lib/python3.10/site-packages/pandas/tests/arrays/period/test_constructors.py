import numpy as np
import pytest

from pandas._libs.tslibs import iNaT
from pandas._libs.tslibs.offsets import MonthEnd
from pandas._libs.tslibs.period import IncompatibleFrequency

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays import (
    PeriodArray,
    period_array,
)


@pytest.mark.parametrize(
    "data, freq, expected",
    [
        ([pd.Period("2017", "D")], None, [17167]),
        ([pd.Period("2017", "D")], "D", [17167]),
        ([2017], "D", [17167]),
        (["2017"], "D", [17167]),
        ([pd.Period("2017", "D")], pd.tseries.offsets.Day(), [17167]),
        ([pd.Period("2017", "D"), None], None, [17167, iNaT]),
        (pd.Series(pd.date_range("2017", periods=3)), None, [17167, 17168, 17169]),
        (pd.date_range("2017", periods=3), None, [17167, 17168, 17169]),
        (pd.period_range("2017", periods=4, freq="Q"), None, [188, 189, 190, 191]),
    ],
)
def test_period_array_ok(data, freq, expected):
    result = period_array(data, freq=freq).asi8
    expected = np.asarray(expected, dtype=np.int64)
    tm.assert_numpy_array_equal(result, expected)


def test_period_array_readonly_object():
    # https://github.com/pandas-dev/pandas/issues/25403
    pa = period_array([pd.Period("2019-01-01")])
    arr = np.asarray(pa, dtype="object")
    arr.setflags(write=False)

    result = period_array(arr)
    tm.assert_period_array_equal(result, pa)

    result = pd.Series(arr)
    tm.assert_series_equal(result, pd.Series(pa))

    result = pd.DataFrame({"A": arr})
    tm.assert_frame_equal(result, pd.DataFrame({"A": pa}))


def test_from_datetime64_freq_changes():
    # https://github.com/pandas-dev/pandas/issues/23438
    arr = pd.date_range("2017", periods=3, freq="D")
    result = PeriodArray._from_datetime64(arr, freq="M")
    expected = period_array(["2017-01-01", "2017-01-01", "2017-01-01"], freq="M")
    tm.assert_period_array_equal(result, expected)


@pytest.mark.parametrize("freq", ["2M", MonthEnd(2)])
def test_from_datetime64_freq_2M(freq):
    arr = np.array(
        ["2020-01-01T00:00:00", "2020-01-02T00:00:00"], dtype="datetime64[ns]"
    )
    result = PeriodArray._from_datetime64(arr, freq)
    expected = period_array(["2020-01", "2020-01"], freq=freq)
    tm.assert_period_array_equal(result, expected)


@pytest.mark.parametrize(
    "data, freq, msg",
    [
        (
            [pd.Period("2017", "D"), pd.Period("2017", "Y")],
            None,
            "Input has different freq",
        ),
        ([pd.Period("2017", "D")], "Y", "Input has different freq"),
    ],
)
def test_period_array_raises(data, freq, msg):
    with pytest.raises(IncompatibleFrequency, match=msg):
        period_array(data, freq)


def test_period_array_non_period_series_raies():
    ser = pd.Series([1, 2, 3])
    with pytest.raises(TypeError, match="dtype"):
        PeriodArray(ser, dtype="period[D]")


def test_period_array_freq_mismatch():
    arr = period_array(["2000", "2001"], freq="D")
    with pytest.raises(IncompatibleFrequency, match="freq"):
        PeriodArray(arr, dtype="period[M]")

    dtype = pd.PeriodDtype(pd.tseries.offsets.MonthEnd())
    with pytest.raises(IncompatibleFrequency, match="freq"):
        PeriodArray(arr, dtype=dtype)


def test_from_sequence_disallows_i8():
    arr = period_array(["2000", "2001"], freq="D")

    msg = str(arr[0].ordinal)
    with pytest.raises(TypeError, match=msg):
        PeriodArray._from_sequence(arr.asi8, dtype=arr.dtype)

    with pytest.raises(TypeError, match=msg):
        PeriodArray._from_sequence(list(arr.asi8), dtype=arr.dtype)


def test_from_td64nat_sequence_raises():
    # GH#44507
    td = pd.NaT.to_numpy("m8[ns]")

    dtype = pd.period_range("2005-01-01", periods=3, freq="D").dtype

    arr = np.array([None], dtype=object)
    arr[0] = td

    msg = "Value must be Period, string, integer, or datetime"
    with pytest.raises(ValueError, match=msg):
        PeriodArray._from_sequence(arr, dtype=dtype)

    with pytest.raises(ValueError, match=msg):
        pd.PeriodIndex(arr, dtype=dtype)
    with pytest.raises(ValueError, match=msg):
        pd.Index(arr, dtype=dtype)
    with pytest.raises(ValueError, match=msg):
        pd.array(arr, dtype=dtype)
    with pytest.raises(ValueError, match=msg):
        pd.Series(arr, dtype=dtype)
    with pytest.raises(ValueError, match=msg):
        pd.DataFrame(arr, dtype=dtype)


def test_freq_deprecated():
    # GH#52462
    data = np.arange(5).astype(np.int64)
    msg = "The 'freq' keyword in the PeriodArray constructor is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        res = PeriodArray(data, freq="M")

    expected = PeriodArray(data, dtype="period[M]")
    tm.assert_equal(res, expected)


def test_period_array_from_datetime64():
    arr = np.array(
        ["2020-01-01T00:00:00", "2020-02-02T00:00:00"], dtype="datetime64[ns]"
    )
    result = PeriodArray._from_datetime64(arr, freq=MonthEnd(2))

    expected = period_array(["2020-01-01", "2020-02-01"], freq=MonthEnd(2))
    tm.assert_period_array_equal(result, expected)
