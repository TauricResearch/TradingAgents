from datetime import (
    date,
    datetime,
    timedelta,
)

import numpy as np
import pytest

from pandas.core.dtypes.cast import (
    infer_dtype_from,
    infer_dtype_from_array,
    infer_dtype_from_scalar,
)
from pandas.core.dtypes.common import is_dtype_equal

from pandas import (
    Categorical,
    Interval,
    Period,
    Series,
    Timedelta,
    Timestamp,
    date_range,
)


def test_infer_dtype_from_int_scalar(any_int_numpy_dtype):
    # Test that infer_dtype_from_scalar is
    # returning correct dtype for int and float.
    data = np.dtype(any_int_numpy_dtype).type(12)
    dtype, val = infer_dtype_from_scalar(data)
    assert dtype == type(data)


def test_infer_dtype_from_float_scalar(float_numpy_dtype):
    float_numpy_dtype = np.dtype(float_numpy_dtype).type
    data = float_numpy_dtype(12)

    dtype, val = infer_dtype_from_scalar(data)
    assert dtype == float_numpy_dtype


@pytest.mark.parametrize(
    "data,exp_dtype", [(12, np.int64), (np.float64(12), np.float64)]
)
def test_infer_dtype_from_python_scalar(data, exp_dtype):
    dtype, val = infer_dtype_from_scalar(data)
    assert dtype == exp_dtype


@pytest.mark.parametrize("bool_val", [True, False])
def test_infer_dtype_from_boolean(bool_val):
    dtype, val = infer_dtype_from_scalar(bool_val)
    assert dtype == np.bool_


def test_infer_dtype_from_complex(complex_dtype):
    data = np.dtype(complex_dtype).type(1)
    dtype, val = infer_dtype_from_scalar(data)
    assert dtype == np.complex128


def test_infer_dtype_from_datetime():
    dt64 = np.datetime64(1, "ns")
    dtype, val = infer_dtype_from_scalar(dt64)
    assert dtype == "M8[ns]"

    ts = Timestamp(1)
    dtype, val = infer_dtype_from_scalar(ts)
    assert dtype == "M8[ns]"

    dt = datetime(2000, 1, 1, 0, 0)
    dtype, val = infer_dtype_from_scalar(dt)
    assert dtype == "M8[us]"


def test_infer_dtype_from_timedelta():
    td64 = np.timedelta64(1, "ns")
    dtype, val = infer_dtype_from_scalar(td64)
    assert dtype == "m8[ns]"

    pytd = timedelta(1)
    dtype, val = infer_dtype_from_scalar(pytd)
    assert dtype == "m8[us]"

    td = Timedelta(1)
    dtype, val = infer_dtype_from_scalar(td)
    assert dtype == "m8[ns]"


@pytest.mark.parametrize("freq", ["M", "D"])
def test_infer_dtype_from_period(freq):
    p = Period("2011-01-01", freq=freq)
    dtype, val = infer_dtype_from_scalar(p)

    exp_dtype = f"period[{freq}]"

    assert dtype == exp_dtype
    assert val == p


def test_infer_dtype_misc():
    dt = date(2000, 1, 1)
    dtype, val = infer_dtype_from_scalar(dt)
    assert dtype == np.object_

    ts = Timestamp(1, tz="US/Eastern")
    dtype, val = infer_dtype_from_scalar(ts)
    assert dtype == "datetime64[ns, US/Eastern]"


@pytest.mark.parametrize("tz", ["UTC", "US/Eastern", "Asia/Tokyo"])
def test_infer_from_scalar_tz(tz):
    dt = Timestamp(1, tz=tz)
    dtype, val = infer_dtype_from_scalar(dt)

    exp_dtype = f"datetime64[ns, {tz}]"

    assert dtype == exp_dtype
    assert val == dt


@pytest.mark.parametrize(
    "left, right, subtype",
    [
        (0, 1, "int64"),
        (0.0, 1.0, "float64"),
        (Timestamp(0), Timestamp(1), "datetime64[ns]"),
        (Timestamp(0, tz="UTC"), Timestamp(1, tz="UTC"), "datetime64[ns, UTC]"),
        (Timedelta(0), Timedelta(1), "timedelta64[ns]"),
    ],
)
def test_infer_from_interval(left, right, subtype, closed):
    # GH 30337
    interval = Interval(left, right, closed)
    result_dtype, result_value = infer_dtype_from_scalar(interval)
    expected_dtype = f"interval[{subtype}, {closed}]"
    assert result_dtype == expected_dtype
    assert result_value == interval


def test_infer_dtype_from_scalar_errors():
    msg = "invalid ndarray passed to infer_dtype_from_scalar"

    with pytest.raises(ValueError, match=msg):
        infer_dtype_from_scalar(np.array([1]))


@pytest.mark.parametrize(
    "value, expected",
    [
        ("foo", np.object_),
        (b"foo", np.object_),
        (1, np.int64),
        (1.5, np.float64),
        (np.datetime64("2016-01-01"), np.dtype("M8[s]")),
        (Timestamp("20160101"), np.dtype("M8[s]")),
        (Timestamp("20160101", tz="UTC"), "datetime64[s, UTC]"),
    ],
)
def test_infer_dtype_from_scalar(value, expected, using_infer_string):
    dtype, _ = infer_dtype_from_scalar(value)
    if using_infer_string and value == "foo":
        expected = "string"
    assert is_dtype_equal(dtype, expected)

    with pytest.raises(TypeError, match="must be list-like"):
        infer_dtype_from_array(value)


@pytest.mark.parametrize(
    "arr, expected",
    [
        ([1], np.dtype(int)),
        (np.array([1], dtype=np.int64), np.int64),
        ([np.nan, 1, ""], np.object_),
        (np.array([[1.0, 2.0]]), np.float64),
        (Categorical(list("aabc")), "category"),
        (Categorical([1, 2, 3]), "category"),
        (date_range("20160101", periods=3), np.dtype("=M8[ns]")),
        (
            date_range("20160101", periods=3, tz="US/Eastern"),
            "datetime64[ns, US/Eastern]",
        ),
        (Series([1.0, 2, 3]), np.float64),
        (Series(list("abc")), np.object_),
        (
            Series(date_range("20160101", periods=3, tz="US/Eastern")),
            "datetime64[ns, US/Eastern]",
        ),
    ],
)
def test_infer_dtype_from_array(arr, expected, using_infer_string):
    dtype, _ = infer_dtype_from_array(arr)
    if (
        using_infer_string
        and isinstance(arr, Series)
        and arr.tolist() == ["a", "b", "c"]
    ):
        expected = "string"
    assert is_dtype_equal(dtype, expected)


@pytest.mark.parametrize("cls", [np.datetime64, np.timedelta64])
def test_infer_dtype_from_scalar_zerodim_datetimelike(cls):
    # ndarray.item() can incorrectly return int instead of td64/dt64
    val = cls(1234, "ns")
    arr = np.array(val)

    dtype, res = infer_dtype_from_scalar(arr)
    assert dtype.type is cls
    assert isinstance(res, cls)

    dtype, res = infer_dtype_from(arr)
    assert dtype.type is cls
