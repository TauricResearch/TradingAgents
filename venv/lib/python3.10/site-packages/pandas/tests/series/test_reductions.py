import numpy as np
import pytest

import pandas as pd
from pandas import Series
import pandas._testing as tm


@pytest.mark.parametrize("operation, expected", [("min", "a"), ("max", "b")])
def test_reductions_series_strings(operation, expected):
    # GH#31746
    ser = Series(["a", "b"], dtype="string")
    res_operation_serie = getattr(ser, operation)()
    assert res_operation_serie == expected


@pytest.mark.parametrize("as_period", [True, False])
def test_mode_extension_dtype(as_period):
    # GH#41927 preserve dt64tz dtype
    ser = Series([pd.Timestamp(1979, 4, n) for n in range(1, 5)])

    if as_period:
        ser = ser.dt.to_period("D")
    else:
        ser = ser.dt.tz_localize("US/Central")

    res = ser.mode()
    assert res.dtype == ser.dtype
    tm.assert_series_equal(res, ser)


def test_mode_nullable_dtype(any_numeric_ea_dtype):
    # GH#55340
    ser = Series([1, 3, 2, pd.NA, 3, 2, pd.NA], dtype=any_numeric_ea_dtype)
    result = ser.mode(dropna=False)
    expected = Series([2, 3, pd.NA], dtype=any_numeric_ea_dtype)
    tm.assert_series_equal(result, expected)

    result = ser.mode(dropna=True)
    expected = Series([2, 3], dtype=any_numeric_ea_dtype)
    tm.assert_series_equal(result, expected)

    ser[-1] = pd.NA

    result = ser.mode(dropna=True)
    expected = Series([2, 3], dtype=any_numeric_ea_dtype)
    tm.assert_series_equal(result, expected)

    result = ser.mode(dropna=False)
    expected = Series([pd.NA], dtype=any_numeric_ea_dtype)
    tm.assert_series_equal(result, expected)


def test_mode_infer_string():
    # GH#56183
    pytest.importorskip("pyarrow")
    ser = Series(["a", "b"], dtype=object)
    with pd.option_context("future.infer_string", True):
        result = ser.mode()
    expected = Series(["a", "b"], dtype=object)
    tm.assert_series_equal(result, expected)


def test_reductions_td64_with_nat():
    # GH#8617
    ser = Series([0, pd.NaT], dtype="m8[ns]")
    exp = ser[0]
    assert ser.median() == exp
    assert ser.min() == exp
    assert ser.max() == exp


@pytest.mark.parametrize("skipna", [True, False])
def test_td64_sum_empty(skipna):
    # GH#37151
    ser = Series([], dtype="timedelta64[ns]")

    result = ser.sum(skipna=skipna)
    assert isinstance(result, pd.Timedelta)
    assert result == pd.Timedelta(0)


def test_td64_summation_overflow():
    # GH#9442
    ser = Series(pd.date_range("20130101", periods=100000, freq="h"))
    ser[0] += pd.Timedelta("1s 1ms")

    # mean
    result = (ser - ser.min()).mean()
    expected = pd.Timedelta((pd.TimedeltaIndex(ser - ser.min()).asi8 / len(ser)).sum())

    # the computation is converted to float so
    # might be some loss of precision
    assert np.allclose(result._value / 1000, expected._value / 1000)

    # sum
    msg = "overflow in timedelta operation"
    with pytest.raises(ValueError, match=msg):
        (ser - ser.min()).sum()

    s1 = ser[0:10000]
    with pytest.raises(ValueError, match=msg):
        (s1 - s1.min()).sum()
    s2 = ser[0:1000]
    (s2 - s2.min()).sum()


def test_prod_numpy16_bug():
    ser = Series([1.0, 1.0, 1.0], index=range(3))
    result = ser.prod()

    assert not isinstance(result, Series)


@pytest.mark.parametrize("func", [np.any, np.all])
@pytest.mark.parametrize("kwargs", [{"keepdims": True}, {"out": object()}])
def test_validate_any_all_out_keepdims_raises(kwargs, func):
    ser = Series([1, 2])
    param = next(iter(kwargs))
    name = func.__name__

    msg = (
        f"the '{param}' parameter is not "
        "supported in the pandas "
        rf"implementation of {name}\(\)"
    )
    with pytest.raises(ValueError, match=msg):
        func(ser, **kwargs)


def test_validate_sum_initial():
    ser = Series([1, 2])
    msg = (
        r"the 'initial' parameter is not "
        r"supported in the pandas "
        r"implementation of sum\(\)"
    )
    with pytest.raises(ValueError, match=msg):
        np.sum(ser, initial=10)


def test_validate_median_initial():
    ser = Series([1, 2])
    msg = (
        r"the 'overwrite_input' parameter is not "
        r"supported in the pandas "
        r"implementation of median\(\)"
    )
    with pytest.raises(ValueError, match=msg):
        # It seems like np.median doesn't dispatch, so we use the
        # method instead of the ufunc.
        ser.median(overwrite_input=True)


def test_validate_stat_keepdims():
    ser = Series([1, 2])
    msg = (
        r"the 'keepdims' parameter is not "
        r"supported in the pandas "
        r"implementation of sum\(\)"
    )
    with pytest.raises(ValueError, match=msg):
        np.sum(ser, keepdims=True)


def test_mean_with_convertible_string_raises(using_array_manager, using_infer_string):
    # GH#44008
    ser = Series(["1", "2"])
    assert ser.sum() == "12"

    msg = "Could not convert string '12' to numeric|does not support|Cannot perform"
    with pytest.raises(TypeError, match=msg):
        ser.mean()

    df = ser.to_frame()
    if not using_array_manager:
        msg = r"Could not convert \['12'\] to numeric|does not support|Cannot perform"
    with pytest.raises(TypeError, match=msg):
        df.mean()


def test_mean_dont_convert_j_to_complex(using_array_manager):
    # GH#36703
    df = pd.DataFrame([{"db": "J", "numeric": 123}])
    if using_array_manager:
        msg = "Could not convert string 'J' to numeric"
    else:
        msg = r"Could not convert \['J'\] to numeric|does not support|Cannot perform"
    with pytest.raises(TypeError, match=msg):
        df.mean()

    with pytest.raises(TypeError, match=msg):
        df.agg("mean")

    msg = "Could not convert string 'J' to numeric|does not support|Cannot perform"
    with pytest.raises(TypeError, match=msg):
        df["db"].mean()
    msg = "Could not convert string 'J' to numeric|ufunc 'divide'|Cannot perform"
    with pytest.raises(TypeError, match=msg):
        np.mean(df["db"].astype("string").array)


def test_median_with_convertible_string_raises(using_array_manager):
    # GH#34671 this _could_ return a string "2", but definitely not float 2.0
    msg = r"Cannot convert \['1' '2' '3'\] to numeric|does not support|Cannot perform"
    ser = Series(["1", "2", "3"])
    with pytest.raises(TypeError, match=msg):
        ser.median()

    if not using_array_manager:
        msg = (
            r"Cannot convert \[\['1' '2' '3'\]\] to numeric|does not support"
            "|Cannot perform"
        )
    df = ser.to_frame()
    with pytest.raises(TypeError, match=msg):
        df.median()
