import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays import FloatingArray


@pytest.mark.parametrize("box", [True, False], ids=["series", "array"])
def test_to_numpy(box):
    con = pd.Series if box else pd.array

    # default (with or without missing values) -> object dtype
    arr = con([0.1, 0.2, 0.3], dtype="Float64")
    result = arr.to_numpy()
    expected = np.array([0.1, 0.2, 0.3], dtype="float64")
    tm.assert_numpy_array_equal(result, expected)

    arr = con([0.1, 0.2, None], dtype="Float64")
    result = arr.to_numpy()
    expected = np.array([0.1, 0.2, np.nan], dtype="float64")
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("box", [True, False], ids=["series", "array"])
def test_to_numpy_float(box):
    con = pd.Series if box else pd.array

    # no missing values -> can convert to float, otherwise raises
    arr = con([0.1, 0.2, 0.3], dtype="Float64")
    result = arr.to_numpy(dtype="float64")
    expected = np.array([0.1, 0.2, 0.3], dtype="float64")
    tm.assert_numpy_array_equal(result, expected)

    arr = con([0.1, 0.2, None], dtype="Float64")
    result = arr.to_numpy(dtype="float64")
    expected = np.array([0.1, 0.2, np.nan], dtype="float64")
    tm.assert_numpy_array_equal(result, expected)

    result = arr.to_numpy(dtype="float64", na_value=np.nan)
    expected = np.array([0.1, 0.2, np.nan], dtype="float64")
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("box", [True, False], ids=["series", "array"])
def test_to_numpy_int(box):
    con = pd.Series if box else pd.array

    # no missing values -> can convert to int, otherwise raises
    arr = con([1.0, 2.0, 3.0], dtype="Float64")
    result = arr.to_numpy(dtype="int64")
    expected = np.array([1, 2, 3], dtype="int64")
    tm.assert_numpy_array_equal(result, expected)

    arr = con([1.0, 2.0, None], dtype="Float64")
    with pytest.raises(ValueError, match="cannot convert to 'int64'-dtype"):
        result = arr.to_numpy(dtype="int64")

    # automatic casting (floors the values)
    arr = con([0.1, 0.9, 1.1], dtype="Float64")
    result = arr.to_numpy(dtype="int64")
    expected = np.array([0, 0, 1], dtype="int64")
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("box", [True, False], ids=["series", "array"])
def test_to_numpy_na_value(box):
    con = pd.Series if box else pd.array

    arr = con([0.0, 1.0, None], dtype="Float64")
    result = arr.to_numpy(dtype=object, na_value=None)
    expected = np.array([0.0, 1.0, None], dtype="object")
    tm.assert_numpy_array_equal(result, expected)

    result = arr.to_numpy(dtype=bool, na_value=False)
    expected = np.array([False, True, False], dtype="bool")
    tm.assert_numpy_array_equal(result, expected)

    result = arr.to_numpy(dtype="int64", na_value=-99)
    expected = np.array([0, 1, -99], dtype="int64")
    tm.assert_numpy_array_equal(result, expected)


def test_to_numpy_na_value_with_nan():
    # array with both NaN and NA -> only fill NA with `na_value`
    arr = FloatingArray(np.array([0.0, np.nan, 0.0]), np.array([False, False, True]))
    result = arr.to_numpy(dtype="float64", na_value=-1)
    expected = np.array([0.0, np.nan, -1.0], dtype="float64")
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("dtype", ["float64", "float32", "int32", "int64", "bool"])
@pytest.mark.parametrize("box", [True, False], ids=["series", "array"])
def test_to_numpy_dtype(box, dtype):
    con = pd.Series if box else pd.array
    arr = con([0.0, 1.0], dtype="Float64")

    result = arr.to_numpy(dtype=dtype)
    expected = np.array([0, 1], dtype=dtype)
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("dtype", ["int32", "int64", "bool"])
@pytest.mark.parametrize("box", [True, False], ids=["series", "array"])
def test_to_numpy_na_raises(box, dtype):
    con = pd.Series if box else pd.array
    arr = con([0.0, 1.0, None], dtype="Float64")
    with pytest.raises(ValueError, match=dtype):
        arr.to_numpy(dtype=dtype)


@pytest.mark.parametrize("box", [True, False], ids=["series", "array"])
def test_to_numpy_string(box, dtype):
    con = pd.Series if box else pd.array
    arr = con([0.0, 1.0, None], dtype="Float64")

    result = arr.to_numpy(dtype="str")
    expected = np.array([0.0, 1.0, pd.NA], dtype=f"{tm.ENDIAN}U32")
    tm.assert_numpy_array_equal(result, expected)


def test_to_numpy_copy():
    # to_numpy can be zero-copy if no missing values
    arr = pd.array([0.1, 0.2, 0.3], dtype="Float64")
    result = arr.to_numpy(dtype="float64")
    result[0] = 10
    tm.assert_extension_array_equal(arr, pd.array([10, 0.2, 0.3], dtype="Float64"))

    arr = pd.array([0.1, 0.2, 0.3], dtype="Float64")
    result = arr.to_numpy(dtype="float64", copy=True)
    result[0] = 10
    tm.assert_extension_array_equal(arr, pd.array([0.1, 0.2, 0.3], dtype="Float64"))
