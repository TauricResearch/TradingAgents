import numpy as np
import pytest

from pandas._libs.parsers import (
    _maybe_upcast,
    na_values,
)

import pandas as pd
from pandas import NA
import pandas._testing as tm
from pandas.core.arrays import (
    ArrowStringArray,
    BooleanArray,
    FloatingArray,
    IntegerArray,
    StringArray,
)


def test_maybe_upcast(any_real_numpy_dtype):
    # GH#36712

    dtype = np.dtype(any_real_numpy_dtype)
    na_value = na_values[dtype]
    arr = np.array([1, 2, na_value], dtype=dtype)
    result = _maybe_upcast(arr, use_dtype_backend=True)

    expected_mask = np.array([False, False, True])
    if issubclass(dtype.type, np.integer):
        expected = IntegerArray(arr, mask=expected_mask)
    else:
        expected = FloatingArray(arr, mask=expected_mask)

    tm.assert_extension_array_equal(result, expected)


def test_maybe_upcast_no_na(any_real_numpy_dtype):
    # GH#36712
    arr = np.array([1, 2, 3], dtype=any_real_numpy_dtype)
    result = _maybe_upcast(arr, use_dtype_backend=True)

    expected_mask = np.array([False, False, False])
    if issubclass(np.dtype(any_real_numpy_dtype).type, np.integer):
        expected = IntegerArray(arr, mask=expected_mask)
    else:
        expected = FloatingArray(arr, mask=expected_mask)

    tm.assert_extension_array_equal(result, expected)


def test_maybe_upcaste_bool():
    # GH#36712
    dtype = np.bool_
    na_value = na_values[dtype]
    arr = np.array([True, False, na_value], dtype="uint8").view(dtype)
    result = _maybe_upcast(arr, use_dtype_backend=True)

    expected_mask = np.array([False, False, True])
    expected = BooleanArray(arr, mask=expected_mask)
    tm.assert_extension_array_equal(result, expected)


def test_maybe_upcaste_bool_no_nan():
    # GH#36712
    dtype = np.bool_
    arr = np.array([True, False, False], dtype="uint8").view(dtype)
    result = _maybe_upcast(arr, use_dtype_backend=True)

    expected_mask = np.array([False, False, False])
    expected = BooleanArray(arr, mask=expected_mask)
    tm.assert_extension_array_equal(result, expected)


def test_maybe_upcaste_all_nan():
    # GH#36712
    dtype = np.int64
    na_value = na_values[dtype]
    arr = np.array([na_value, na_value], dtype=dtype)
    result = _maybe_upcast(arr, use_dtype_backend=True)

    expected_mask = np.array([True, True])
    expected = IntegerArray(arr, mask=expected_mask)
    tm.assert_extension_array_equal(result, expected)


@pytest.mark.parametrize("val", [na_values[np.object_], "c"])
def test_maybe_upcast_object(val, string_storage):
    # GH#36712
    pa = pytest.importorskip("pyarrow")

    with pd.option_context("mode.string_storage", string_storage):
        arr = np.array(["a", "b", val], dtype=np.object_)
        result = _maybe_upcast(arr, use_dtype_backend=True)

        if string_storage == "python":
            exp_val = "c" if val == "c" else NA
            expected = StringArray(np.array(["a", "b", exp_val], dtype=np.object_))
        else:
            exp_val = "c" if val == "c" else None
            expected = ArrowStringArray(pa.array(["a", "b", exp_val]))
        tm.assert_extension_array_equal(result, expected)
