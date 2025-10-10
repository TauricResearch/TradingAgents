"""
Additional tests for NumpyExtensionArray that aren't covered by
the interface tests.
"""
import numpy as np
import pytest

from pandas.core.dtypes.dtypes import NumpyEADtype

import pandas as pd
import pandas._testing as tm
from pandas.arrays import NumpyExtensionArray


@pytest.fixture(
    params=[
        np.array(["a", "b"], dtype=object),
        np.array([0, 1], dtype=float),
        np.array([0, 1], dtype=int),
        np.array([0, 1 + 2j], dtype=complex),
        np.array([True, False], dtype=bool),
        np.array([0, 1], dtype="datetime64[ns]"),
        np.array([0, 1], dtype="timedelta64[ns]"),
    ],
)
def any_numpy_array(request):
    """
    Parametrized fixture for NumPy arrays with different dtypes.

    This excludes string and bytes.
    """
    return request.param.copy()


# ----------------------------------------------------------------------------
# NumpyEADtype


@pytest.mark.parametrize(
    "dtype, expected",
    [
        ("bool", True),
        ("int", True),
        ("uint", True),
        ("float", True),
        ("complex", True),
        ("str", False),
        ("bytes", False),
        ("datetime64[ns]", False),
        ("object", False),
        ("void", False),
    ],
)
def test_is_numeric(dtype, expected):
    dtype = NumpyEADtype(dtype)
    assert dtype._is_numeric is expected


@pytest.mark.parametrize(
    "dtype, expected",
    [
        ("bool", True),
        ("int", False),
        ("uint", False),
        ("float", False),
        ("complex", False),
        ("str", False),
        ("bytes", False),
        ("datetime64[ns]", False),
        ("object", False),
        ("void", False),
    ],
)
def test_is_boolean(dtype, expected):
    dtype = NumpyEADtype(dtype)
    assert dtype._is_boolean is expected


def test_repr():
    dtype = NumpyEADtype(np.dtype("int64"))
    assert repr(dtype) == "NumpyEADtype('int64')"


def test_constructor_from_string():
    result = NumpyEADtype.construct_from_string("int64")
    expected = NumpyEADtype(np.dtype("int64"))
    assert result == expected


def test_dtype_idempotent(any_numpy_dtype):
    dtype = NumpyEADtype(any_numpy_dtype)

    result = NumpyEADtype(dtype)
    assert result == dtype


# ----------------------------------------------------------------------------
# Construction


def test_constructor_no_coercion():
    with pytest.raises(ValueError, match="NumPy array"):
        NumpyExtensionArray([1, 2, 3])


def test_series_constructor_with_copy():
    ndarray = np.array([1, 2, 3])
    ser = pd.Series(NumpyExtensionArray(ndarray), copy=True)

    assert ser.values is not ndarray


def test_series_constructor_with_astype():
    ndarray = np.array([1, 2, 3])
    result = pd.Series(NumpyExtensionArray(ndarray), dtype="float64")
    expected = pd.Series([1.0, 2.0, 3.0], dtype="float64")
    tm.assert_series_equal(result, expected)


def test_from_sequence_dtype():
    arr = np.array([1, 2, 3], dtype="int64")
    result = NumpyExtensionArray._from_sequence(arr, dtype="uint64")
    expected = NumpyExtensionArray(np.array([1, 2, 3], dtype="uint64"))
    tm.assert_extension_array_equal(result, expected)


def test_constructor_copy():
    arr = np.array([0, 1])
    result = NumpyExtensionArray(arr, copy=True)

    assert not tm.shares_memory(result, arr)


def test_constructor_with_data(any_numpy_array):
    nparr = any_numpy_array
    arr = NumpyExtensionArray(nparr)
    assert arr.dtype.numpy_dtype == nparr.dtype


# ----------------------------------------------------------------------------
# Conversion


def test_to_numpy():
    arr = NumpyExtensionArray(np.array([1, 2, 3]))
    result = arr.to_numpy()
    assert result is arr._ndarray

    result = arr.to_numpy(copy=True)
    assert result is not arr._ndarray

    result = arr.to_numpy(dtype="f8")
    expected = np.array([1, 2, 3], dtype="f8")
    tm.assert_numpy_array_equal(result, expected)


# ----------------------------------------------------------------------------
# Setitem


def test_setitem_series():
    ser = pd.Series([1, 2, 3])
    ser.array[0] = 10
    expected = pd.Series([10, 2, 3])
    tm.assert_series_equal(ser, expected)


def test_setitem(any_numpy_array):
    nparr = any_numpy_array
    arr = NumpyExtensionArray(nparr, copy=True)

    arr[0] = arr[1]
    nparr[0] = nparr[1]

    tm.assert_numpy_array_equal(arr.to_numpy(), nparr)


# ----------------------------------------------------------------------------
# Reductions


def test_bad_reduce_raises():
    arr = np.array([1, 2, 3], dtype="int64")
    arr = NumpyExtensionArray(arr)
    msg = "cannot perform not_a_method with type int"
    with pytest.raises(TypeError, match=msg):
        arr._reduce(msg)


def test_validate_reduction_keyword_args():
    arr = NumpyExtensionArray(np.array([1, 2, 3]))
    msg = "the 'keepdims' parameter is not supported .*all"
    with pytest.raises(ValueError, match=msg):
        arr.all(keepdims=True)


def test_np_max_nested_tuples():
    # case where checking in ufunc.nout works while checking for tuples
    #  does not
    vals = [
        (("j", "k"), ("l", "m")),
        (("l", "m"), ("o", "p")),
        (("o", "p"), ("j", "k")),
    ]
    ser = pd.Series(vals)
    arr = ser.array

    assert arr.max() is arr[2]
    assert ser.max() is arr[2]

    result = np.maximum.reduce(arr)
    assert result == arr[2]

    result = np.maximum.reduce(ser)
    assert result == arr[2]


def test_np_reduce_2d():
    raw = np.arange(12).reshape(4, 3)
    arr = NumpyExtensionArray(raw)

    res = np.maximum.reduce(arr, axis=0)
    tm.assert_extension_array_equal(res, arr[-1])

    alt = arr.max(axis=0)
    tm.assert_extension_array_equal(alt, arr[-1])


# ----------------------------------------------------------------------------
# Ops


@pytest.mark.parametrize("ufunc", [np.abs, np.negative, np.positive])
def test_ufunc_unary(ufunc):
    arr = NumpyExtensionArray(np.array([-1.0, 0.0, 1.0]))
    result = ufunc(arr)
    expected = NumpyExtensionArray(ufunc(arr._ndarray))
    tm.assert_extension_array_equal(result, expected)

    # same thing but with the 'out' keyword
    out = NumpyExtensionArray(np.array([-9.0, -9.0, -9.0]))
    ufunc(arr, out=out)
    tm.assert_extension_array_equal(out, expected)


def test_ufunc():
    arr = NumpyExtensionArray(np.array([-1.0, 0.0, 1.0]))

    r1, r2 = np.divmod(arr, np.add(arr, 2))
    e1, e2 = np.divmod(arr._ndarray, np.add(arr._ndarray, 2))
    e1 = NumpyExtensionArray(e1)
    e2 = NumpyExtensionArray(e2)
    tm.assert_extension_array_equal(r1, e1)
    tm.assert_extension_array_equal(r2, e2)


def test_basic_binop():
    # Just a basic smoke test. The EA interface tests exercise this
    # more thoroughly.
    x = NumpyExtensionArray(np.array([1, 2, 3]))
    result = x + x
    expected = NumpyExtensionArray(np.array([2, 4, 6]))
    tm.assert_extension_array_equal(result, expected)


@pytest.mark.parametrize("dtype", [None, object])
def test_setitem_object_typecode(dtype):
    arr = NumpyExtensionArray(np.array(["a", "b", "c"], dtype=dtype))
    arr[0] = "t"
    expected = NumpyExtensionArray(np.array(["t", "b", "c"], dtype=dtype))
    tm.assert_extension_array_equal(arr, expected)


def test_setitem_no_coercion():
    # https://github.com/pandas-dev/pandas/issues/28150
    arr = NumpyExtensionArray(np.array([1, 2, 3]))
    with pytest.raises(ValueError, match="int"):
        arr[0] = "a"

    # With a value that we do coerce, check that we coerce the value
    #  and not the underlying array.
    arr[0] = 2.5
    assert isinstance(arr[0], (int, np.integer)), type(arr[0])


def test_setitem_preserves_views():
    # GH#28150, see also extension test of the same name
    arr = NumpyExtensionArray(np.array([1, 2, 3]))
    view1 = arr.view()
    view2 = arr[:]
    view3 = np.asarray(arr)

    arr[0] = 9
    assert view1[0] == 9
    assert view2[0] == 9
    assert view3[0] == 9

    arr[-1] = 2.5
    view1[-1] = 5
    assert arr[-1] == 5


@pytest.mark.parametrize("dtype", [np.int64, np.uint64])
def test_quantile_empty(dtype):
    # we should get back np.nans, not -1s
    arr = NumpyExtensionArray(np.array([], dtype=dtype))
    idx = pd.Index([0.0, 0.5])

    result = arr._quantile(idx, interpolation="linear")
    expected = NumpyExtensionArray(np.array([np.nan, np.nan]))
    tm.assert_extension_array_equal(result, expected)


def test_factorize_unsigned():
    # don't raise when calling factorize on unsigned int NumpyExtensionArray
    arr = np.array([1, 2, 3], dtype=np.uint64)
    obj = NumpyExtensionArray(arr)

    res_codes, res_unique = obj.factorize()
    exp_codes, exp_unique = pd.factorize(arr)

    tm.assert_numpy_array_equal(res_codes, exp_codes)

    tm.assert_extension_array_equal(res_unique, NumpyExtensionArray(exp_unique))


# ----------------------------------------------------------------------------
# Output formatting


def test_array_repr(any_numpy_array):
    # GH#61085
    nparray = any_numpy_array
    arr = NumpyExtensionArray(nparray)
    if nparray.dtype == "object":
        values = "['a', 'b']"
    elif nparray.dtype == "float64":
        values = "[0.0, 1.0]"
    elif str(nparray.dtype).startswith("int"):
        values = "[0, 1]"
    elif nparray.dtype == "complex128":
        values = "[0j, (1+2j)]"
    elif nparray.dtype == "bool":
        values = "[True, False]"
    elif nparray.dtype == "datetime64[ns]":
        values = "[1970-01-01T00:00:00.000000000, 1970-01-01T00:00:00.000000001]"
    elif nparray.dtype == "timedelta64[ns]":
        values = "[0 nanoseconds, 1 nanoseconds]"
    expected = f"<NumpyExtensionArray>\n{values}\nLength: 2, dtype: {nparray.dtype}"
    result = repr(arr)
    assert result == expected, f"{result} vs {expected}"
