import numpy as np
import pytest

from pandas.core.dtypes.generic import ABCIndex

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays.integer import (
    Int8Dtype,
    UInt32Dtype,
)


def test_dtypes(dtype):
    # smoke tests on auto dtype construction

    if dtype.is_signed_integer:
        assert np.dtype(dtype.type).kind == "i"
    else:
        assert np.dtype(dtype.type).kind == "u"
    assert dtype.name is not None


@pytest.mark.parametrize("op", ["sum", "min", "max", "prod"])
def test_preserve_dtypes(op):
    # for ops that enable (mean would actually work here
    # but generally it is a float return value)
    df = pd.DataFrame(
        {
            "A": ["a", "b", "b"],
            "B": [1, None, 3],
            "C": pd.array([1, None, 3], dtype="Int64"),
        }
    )

    # op
    result = getattr(df.C, op)()
    if op in {"sum", "prod", "min", "max"}:
        assert isinstance(result, np.int64)
    else:
        assert isinstance(result, int)

    # groupby
    result = getattr(df.groupby("A"), op)()

    expected = pd.DataFrame(
        {"B": np.array([1.0, 3.0]), "C": pd.array([1, 3], dtype="Int64")},
        index=pd.Index(["a", "b"], name="A"),
    )
    tm.assert_frame_equal(result, expected)


def test_astype_nansafe():
    # see gh-22343
    arr = pd.array([np.nan, 1, 2], dtype="Int8")
    msg = "cannot convert NA to integer"

    with pytest.raises(ValueError, match=msg):
        arr.astype("uint32")


@pytest.mark.parametrize("dropna", [True, False])
def test_construct_index(all_data, dropna):
    # ensure that we do not coerce to different Index dtype or non-index

    all_data = all_data[:10]
    if dropna:
        other = np.array(all_data[~all_data.isna()])
    else:
        other = all_data

    result = pd.Index(pd.array(other, dtype=all_data.dtype))
    expected = pd.Index(other, dtype=all_data.dtype)
    assert all_data.dtype == expected.dtype  # dont coerce to object

    tm.assert_index_equal(result, expected)


@pytest.mark.parametrize("dropna", [True, False])
def test_astype_index(all_data, dropna):
    # as an int/uint index to Index

    all_data = all_data[:10]
    if dropna:
        other = all_data[~all_data.isna()]
    else:
        other = all_data

    dtype = all_data.dtype
    idx = pd.Index(np.array(other))
    assert isinstance(idx, ABCIndex)

    result = idx.astype(dtype)
    expected = idx.astype(object).astype(dtype)
    tm.assert_index_equal(result, expected)


def test_astype(all_data):
    all_data = all_data[:10]

    ints = all_data[~all_data.isna()]
    mixed = all_data
    dtype = Int8Dtype()

    # coerce to same type - ints
    s = pd.Series(ints)
    result = s.astype(all_data.dtype)
    expected = pd.Series(ints)
    tm.assert_series_equal(result, expected)

    # coerce to same other - ints
    s = pd.Series(ints)
    result = s.astype(dtype)
    expected = pd.Series(ints, dtype=dtype)
    tm.assert_series_equal(result, expected)

    # coerce to same numpy_dtype - ints
    s = pd.Series(ints)
    result = s.astype(all_data.dtype.numpy_dtype)
    expected = pd.Series(ints._data.astype(all_data.dtype.numpy_dtype))
    tm.assert_series_equal(result, expected)

    # coerce to same type - mixed
    s = pd.Series(mixed)
    result = s.astype(all_data.dtype)
    expected = pd.Series(mixed)
    tm.assert_series_equal(result, expected)

    # coerce to same other - mixed
    s = pd.Series(mixed)
    result = s.astype(dtype)
    expected = pd.Series(mixed, dtype=dtype)
    tm.assert_series_equal(result, expected)

    # coerce to same numpy_dtype - mixed
    s = pd.Series(mixed)
    msg = "cannot convert NA to integer"
    with pytest.raises(ValueError, match=msg):
        s.astype(all_data.dtype.numpy_dtype)

    # coerce to object
    s = pd.Series(mixed)
    result = s.astype("object")
    expected = pd.Series(np.asarray(mixed, dtype=object))
    tm.assert_series_equal(result, expected)


def test_astype_copy():
    arr = pd.array([1, 2, 3, None], dtype="Int64")
    orig = pd.array([1, 2, 3, None], dtype="Int64")

    # copy=True -> ensure both data and mask are actual copies
    result = arr.astype("Int64", copy=True)
    assert result is not arr
    assert not tm.shares_memory(result, arr)
    result[0] = 10
    tm.assert_extension_array_equal(arr, orig)
    result[0] = pd.NA
    tm.assert_extension_array_equal(arr, orig)

    # copy=False
    result = arr.astype("Int64", copy=False)
    assert result is arr
    assert np.shares_memory(result._data, arr._data)
    assert np.shares_memory(result._mask, arr._mask)
    result[0] = 10
    assert arr[0] == 10
    result[0] = pd.NA
    assert arr[0] is pd.NA

    # astype to different dtype -> always needs a copy -> even with copy=False
    # we need to ensure that also the mask is actually copied
    arr = pd.array([1, 2, 3, None], dtype="Int64")
    orig = pd.array([1, 2, 3, None], dtype="Int64")

    result = arr.astype("Int32", copy=False)
    assert not tm.shares_memory(result, arr)
    result[0] = 10
    tm.assert_extension_array_equal(arr, orig)
    result[0] = pd.NA
    tm.assert_extension_array_equal(arr, orig)


def test_astype_to_larger_numpy():
    a = pd.array([1, 2], dtype="Int32")
    result = a.astype("int64")
    expected = np.array([1, 2], dtype="int64")
    tm.assert_numpy_array_equal(result, expected)

    a = pd.array([1, 2], dtype="UInt32")
    result = a.astype("uint64")
    expected = np.array([1, 2], dtype="uint64")
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("dtype", [Int8Dtype(), "Int8", UInt32Dtype(), "UInt32"])
def test_astype_specific_casting(dtype):
    s = pd.Series([1, 2, 3], dtype="Int64")
    result = s.astype(dtype)
    expected = pd.Series([1, 2, 3], dtype=dtype)
    tm.assert_series_equal(result, expected)

    s = pd.Series([1, 2, 3, None], dtype="Int64")
    result = s.astype(dtype)
    expected = pd.Series([1, 2, 3, None], dtype=dtype)
    tm.assert_series_equal(result, expected)


def test_astype_floating():
    arr = pd.array([1, 2, None], dtype="Int64")
    result = arr.astype("Float64")
    expected = pd.array([1.0, 2.0, None], dtype="Float64")
    tm.assert_extension_array_equal(result, expected)


def test_astype_dt64():
    # GH#32435
    arr = pd.array([1, 2, 3, pd.NA]) * 10**9

    result = arr.astype("datetime64[ns]")

    expected = np.array([1, 2, 3, "NaT"], dtype="M8[s]").astype("M8[ns]")
    tm.assert_numpy_array_equal(result, expected)


def test_construct_cast_invalid(dtype):
    msg = "cannot safely"
    arr = [1.2, 2.3, 3.7]
    with pytest.raises(TypeError, match=msg):
        pd.array(arr, dtype=dtype)

    with pytest.raises(TypeError, match=msg):
        pd.Series(arr).astype(dtype)

    arr = [1.2, 2.3, 3.7, np.nan]
    with pytest.raises(TypeError, match=msg):
        pd.array(arr, dtype=dtype)

    with pytest.raises(TypeError, match=msg):
        pd.Series(arr).astype(dtype)


@pytest.mark.parametrize("in_series", [True, False])
def test_to_numpy_na_nan(in_series):
    a = pd.array([0, 1, None], dtype="Int64")
    if in_series:
        a = pd.Series(a)

    result = a.to_numpy(dtype="float64", na_value=np.nan)
    expected = np.array([0.0, 1.0, np.nan], dtype="float64")
    tm.assert_numpy_array_equal(result, expected)

    result = a.to_numpy(dtype="int64", na_value=-1)
    expected = np.array([0, 1, -1], dtype="int64")
    tm.assert_numpy_array_equal(result, expected)

    result = a.to_numpy(dtype="bool", na_value=False)
    expected = np.array([False, True, False], dtype="bool")
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("in_series", [True, False])
@pytest.mark.parametrize("dtype", ["int32", "int64", "bool"])
def test_to_numpy_dtype(dtype, in_series):
    a = pd.array([0, 1], dtype="Int64")
    if in_series:
        a = pd.Series(a)

    result = a.to_numpy(dtype=dtype)
    expected = np.array([0, 1], dtype=dtype)
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("dtype", ["int64", "bool"])
def test_to_numpy_na_raises(dtype):
    a = pd.array([0, 1, None], dtype="Int64")
    with pytest.raises(ValueError, match=dtype):
        a.to_numpy(dtype=dtype)


def test_astype_str(using_infer_string):
    a = pd.array([1, 2, None], dtype="Int64")

    if using_infer_string:
        expected = pd.array(["1", "2", None], dtype=pd.StringDtype(na_value=np.nan))

        tm.assert_extension_array_equal(a.astype(str), expected)
        tm.assert_extension_array_equal(a.astype("str"), expected)
    else:
        expected = np.array(["1", "2", "<NA>"], dtype=f"{tm.ENDIAN}U21")

        tm.assert_numpy_array_equal(a.astype(str), expected)
        tm.assert_numpy_array_equal(a.astype("str"), expected)


def test_astype_boolean():
    # https://github.com/pandas-dev/pandas/issues/31102
    a = pd.array([1, 0, -1, 2, None], dtype="Int64")
    result = a.astype("boolean")
    expected = pd.array([True, False, True, True, None], dtype="boolean")
    tm.assert_extension_array_equal(result, expected)
