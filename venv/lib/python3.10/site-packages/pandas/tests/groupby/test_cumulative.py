import numpy as np
import pytest

from pandas.errors import UnsupportedFunctionCall
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm


@pytest.fixture(
    params=[np.int32, np.int64, np.float32, np.float64, "Int64", "Float64"],
    ids=["np.int32", "np.int64", "np.float32", "np.float64", "Int64", "Float64"],
)
def dtypes_for_minmax(request):
    """
    Fixture of dtypes with min and max values used for testing
    cummin and cummax
    """
    dtype = request.param

    np_type = dtype
    if dtype == "Int64":
        np_type = np.int64
    elif dtype == "Float64":
        np_type = np.float64

    min_val = (
        np.iinfo(np_type).min
        if np.dtype(np_type).kind == "i"
        else np.finfo(np_type).min
    )
    max_val = (
        np.iinfo(np_type).max
        if np.dtype(np_type).kind == "i"
        else np.finfo(np_type).max
    )

    return (dtype, min_val, max_val)


def test_groupby_cumprod():
    # GH 4095
    df = DataFrame({"key": ["b"] * 10, "value": 2})

    actual = df.groupby("key")["value"].cumprod()
    expected = df.groupby("key", group_keys=False)["value"].apply(lambda x: x.cumprod())
    expected.name = "value"
    tm.assert_series_equal(actual, expected)

    df = DataFrame({"key": ["b"] * 100, "value": 2})
    df["value"] = df["value"].astype(float)
    actual = df.groupby("key")["value"].cumprod()
    expected = df.groupby("key", group_keys=False)["value"].apply(lambda x: x.cumprod())
    expected.name = "value"
    tm.assert_series_equal(actual, expected)


@pytest.mark.skip_ubsan
def test_groupby_cumprod_overflow():
    # GH#37493 if we overflow we return garbage consistent with numpy
    df = DataFrame({"key": ["b"] * 4, "value": 100_000})
    actual = df.groupby("key")["value"].cumprod()
    expected = Series(
        [100_000, 10_000_000_000, 1_000_000_000_000_000, 7766279631452241920],
        name="value",
    )
    tm.assert_series_equal(actual, expected)

    numpy_result = df.groupby("key", group_keys=False)["value"].apply(
        lambda x: x.cumprod()
    )
    numpy_result.name = "value"
    tm.assert_series_equal(actual, numpy_result)


def test_groupby_cumprod_nan_influences_other_columns():
    # GH#48064
    df = DataFrame(
        {
            "a": 1,
            "b": [1, np.nan, 2],
            "c": [1, 2, 3.0],
        }
    )
    result = df.groupby("a").cumprod(numeric_only=True, skipna=False)
    expected = DataFrame({"b": [1, np.nan, np.nan], "c": [1, 2, 6.0]})
    tm.assert_frame_equal(result, expected)


def test_cummin(dtypes_for_minmax):
    dtype = dtypes_for_minmax[0]
    min_val = dtypes_for_minmax[1]

    # GH 15048
    base_df = DataFrame({"A": [1, 1, 1, 1, 2, 2, 2, 2], "B": [3, 4, 3, 2, 2, 3, 2, 1]})
    expected_mins = [3, 3, 3, 2, 2, 2, 2, 1]

    df = base_df.astype(dtype)

    expected = DataFrame({"B": expected_mins}).astype(dtype)
    result = df.groupby("A").cummin()
    tm.assert_frame_equal(result, expected)
    result = df.groupby("A", group_keys=False).B.apply(lambda x: x.cummin()).to_frame()
    tm.assert_frame_equal(result, expected)

    # Test w/ min value for dtype
    df.loc[[2, 6], "B"] = min_val
    df.loc[[1, 5], "B"] = min_val + 1
    expected.loc[[2, 3, 6, 7], "B"] = min_val
    expected.loc[[1, 5], "B"] = min_val + 1  # should not be rounded to min_val
    result = df.groupby("A").cummin()
    tm.assert_frame_equal(result, expected, check_exact=True)
    expected = (
        df.groupby("A", group_keys=False).B.apply(lambda x: x.cummin()).to_frame()
    )
    tm.assert_frame_equal(result, expected, check_exact=True)

    # Test nan in some values
    # Explicit cast to float to avoid implicit cast when setting nan
    base_df = base_df.astype({"B": "float"})
    base_df.loc[[0, 2, 4, 6], "B"] = np.nan
    expected = DataFrame({"B": [np.nan, 4, np.nan, 2, np.nan, 3, np.nan, 1]})
    result = base_df.groupby("A").cummin()
    tm.assert_frame_equal(result, expected)
    expected = (
        base_df.groupby("A", group_keys=False).B.apply(lambda x: x.cummin()).to_frame()
    )
    tm.assert_frame_equal(result, expected)

    # GH 15561
    df = DataFrame({"a": [1], "b": pd.to_datetime(["2001"])})
    expected = Series(pd.to_datetime("2001"), index=[0], name="b")

    result = df.groupby("a")["b"].cummin()
    tm.assert_series_equal(expected, result)

    # GH 15635
    df = DataFrame({"a": [1, 2, 1], "b": [1, 2, 2]})
    result = df.groupby("a").b.cummin()
    expected = Series([1, 2, 1], name="b")
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("method", ["cummin", "cummax"])
@pytest.mark.parametrize("dtype", ["UInt64", "Int64", "Float64", "float", "boolean"])
def test_cummin_max_all_nan_column(method, dtype):
    base_df = DataFrame({"A": [1, 1, 1, 1, 2, 2, 2, 2], "B": [np.nan] * 8})
    base_df["B"] = base_df["B"].astype(dtype)
    grouped = base_df.groupby("A")

    expected = DataFrame({"B": [np.nan] * 8}, dtype=dtype)
    result = getattr(grouped, method)()
    tm.assert_frame_equal(expected, result)

    result = getattr(grouped["B"], method)().to_frame()
    tm.assert_frame_equal(expected, result)


def test_cummax(dtypes_for_minmax):
    dtype = dtypes_for_minmax[0]
    max_val = dtypes_for_minmax[2]

    # GH 15048
    base_df = DataFrame({"A": [1, 1, 1, 1, 2, 2, 2, 2], "B": [3, 4, 3, 2, 2, 3, 2, 1]})
    expected_maxs = [3, 4, 4, 4, 2, 3, 3, 3]

    df = base_df.astype(dtype)

    expected = DataFrame({"B": expected_maxs}).astype(dtype)
    result = df.groupby("A").cummax()
    tm.assert_frame_equal(result, expected)
    result = df.groupby("A", group_keys=False).B.apply(lambda x: x.cummax()).to_frame()
    tm.assert_frame_equal(result, expected)

    # Test w/ max value for dtype
    df.loc[[2, 6], "B"] = max_val
    expected.loc[[2, 3, 6, 7], "B"] = max_val
    result = df.groupby("A").cummax()
    tm.assert_frame_equal(result, expected)
    expected = (
        df.groupby("A", group_keys=False).B.apply(lambda x: x.cummax()).to_frame()
    )
    tm.assert_frame_equal(result, expected)

    # Test nan in some values
    # Explicit cast to float to avoid implicit cast when setting nan
    base_df = base_df.astype({"B": "float"})
    base_df.loc[[0, 2, 4, 6], "B"] = np.nan
    expected = DataFrame({"B": [np.nan, 4, np.nan, 4, np.nan, 3, np.nan, 3]})
    result = base_df.groupby("A").cummax()
    tm.assert_frame_equal(result, expected)
    expected = (
        base_df.groupby("A", group_keys=False).B.apply(lambda x: x.cummax()).to_frame()
    )
    tm.assert_frame_equal(result, expected)

    # GH 15561
    df = DataFrame({"a": [1], "b": pd.to_datetime(["2001"])})
    expected = Series(pd.to_datetime("2001"), index=[0], name="b")

    result = df.groupby("a")["b"].cummax()
    tm.assert_series_equal(expected, result)

    # GH 15635
    df = DataFrame({"a": [1, 2, 1], "b": [2, 1, 1]})
    result = df.groupby("a").b.cummax()
    expected = Series([2, 1, 2], name="b")
    tm.assert_series_equal(result, expected)


def test_cummax_i8_at_implementation_bound():
    # the minimum value used to be treated as NPY_NAT+1 instead of NPY_NAT
    #  for int64 dtype GH#46382
    ser = Series([pd.NaT._value + n for n in range(5)])
    df = DataFrame({"A": 1, "B": ser, "C": ser._values.view("M8[ns]")})
    gb = df.groupby("A")

    res = gb.cummax()
    exp = df[["B", "C"]]
    tm.assert_frame_equal(res, exp)


@pytest.mark.parametrize("method", ["cummin", "cummax"])
@pytest.mark.parametrize("dtype", ["float", "Int64", "Float64"])
@pytest.mark.parametrize(
    "groups,expected_data",
    [
        ([1, 1, 1], [1, None, None]),
        ([1, 2, 3], [1, None, 2]),
        ([1, 3, 3], [1, None, None]),
    ],
)
def test_cummin_max_skipna(method, dtype, groups, expected_data):
    # GH-34047
    df = DataFrame({"a": Series([1, None, 2], dtype=dtype)})
    orig = df.copy()
    gb = df.groupby(groups)["a"]

    result = getattr(gb, method)(skipna=False)
    expected = Series(expected_data, dtype=dtype, name="a")

    # check we didn't accidentally alter df
    tm.assert_frame_equal(df, orig)

    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("method", ["cummin", "cummax"])
def test_cummin_max_skipna_multiple_cols(method):
    # Ensure missing value in "a" doesn't cause "b" to be nan-filled
    df = DataFrame({"a": [np.nan, 2.0, 2.0], "b": [2.0, 2.0, 2.0]})
    gb = df.groupby([1, 1, 1])[["a", "b"]]

    result = getattr(gb, method)(skipna=False)
    expected = DataFrame({"a": [np.nan, np.nan, np.nan], "b": [2.0, 2.0, 2.0]})

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("func", ["cumprod", "cumsum"])
def test_numpy_compat(func):
    # see gh-12811
    df = DataFrame({"A": [1, 2, 1], "B": [1, 2, 3]})
    g = df.groupby("A")

    msg = "numpy operations are not valid with groupby"

    with pytest.raises(UnsupportedFunctionCall, match=msg):
        getattr(g, func)(1, 2, 3)
    with pytest.raises(UnsupportedFunctionCall, match=msg):
        getattr(g, func)(foo=1)


@td.skip_if_32bit
@pytest.mark.parametrize("method", ["cummin", "cummax"])
@pytest.mark.parametrize(
    "dtype,val", [("UInt64", np.iinfo("uint64").max), ("Int64", 2**53 + 1)]
)
def test_nullable_int_not_cast_as_float(method, dtype, val):
    data = [val, pd.NA]
    df = DataFrame({"grp": [1, 1], "b": data}, dtype=dtype)
    grouped = df.groupby("grp")

    result = grouped.transform(method)
    expected = DataFrame({"b": data}, dtype=dtype)

    tm.assert_frame_equal(result, expected)


def test_cython_api2():
    # this takes the fast apply path

    # cumsum (GH5614)
    df = DataFrame([[1, 2, np.nan], [1, np.nan, 9], [3, 4, 9]], columns=["A", "B", "C"])
    expected = DataFrame([[2, np.nan], [np.nan, 9], [4, 9]], columns=["B", "C"])
    result = df.groupby("A").cumsum()
    tm.assert_frame_equal(result, expected)

    # GH 5755 - cumsum is a transformer and should ignore as_index
    result = df.groupby("A", as_index=False).cumsum()
    tm.assert_frame_equal(result, expected)

    # GH 13994
    msg = "DataFrameGroupBy.cumsum with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = df.groupby("A").cumsum(axis=1)
    expected = df.cumsum(axis=1)
    tm.assert_frame_equal(result, expected)

    msg = "DataFrameGroupBy.cumprod with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = df.groupby("A").cumprod(axis=1)
    expected = df.cumprod(axis=1)
    tm.assert_frame_equal(result, expected)
