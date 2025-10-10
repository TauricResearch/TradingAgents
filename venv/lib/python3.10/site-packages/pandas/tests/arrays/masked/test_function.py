import numpy as np
import pytest

from pandas.core.dtypes.common import is_integer_dtype

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays import BaseMaskedArray

arrays = [pd.array([1, 2, 3, None], dtype=dtype) for dtype in tm.ALL_INT_EA_DTYPES]
arrays += [
    pd.array([0.141, -0.268, 5.895, None], dtype=dtype) for dtype in tm.FLOAT_EA_DTYPES
]


@pytest.fixture(params=arrays, ids=[a.dtype.name for a in arrays])
def data(request):
    """
    Fixture returning parametrized 'data' array with different integer and
    floating point types
    """
    return request.param


@pytest.fixture()
def numpy_dtype(data):
    """
    Fixture returning numpy dtype from 'data' input array.
    """
    # For integer dtype, the numpy conversion must be done to float
    if is_integer_dtype(data):
        numpy_dtype = float
    else:
        numpy_dtype = data.dtype.type
    return numpy_dtype


def test_round(data, numpy_dtype):
    # No arguments
    result = data.round()
    expected = pd.array(
        np.round(data.to_numpy(dtype=numpy_dtype, na_value=None)), dtype=data.dtype
    )
    tm.assert_extension_array_equal(result, expected)

    # Decimals argument
    result = data.round(decimals=2)
    expected = pd.array(
        np.round(data.to_numpy(dtype=numpy_dtype, na_value=None), decimals=2),
        dtype=data.dtype,
    )
    tm.assert_extension_array_equal(result, expected)


def test_tolist(data):
    result = data.tolist()
    expected = list(data)
    tm.assert_equal(result, expected)


def test_to_numpy():
    # GH#56991

    class MyStringArray(BaseMaskedArray):
        dtype = pd.StringDtype()
        _dtype_cls = pd.StringDtype
        _internal_fill_value = pd.NA

    arr = MyStringArray(
        values=np.array(["a", "b", "c"]), mask=np.array([False, True, False])
    )
    result = arr.to_numpy()
    expected = np.array(["a", pd.NA, "c"])
    tm.assert_numpy_array_equal(result, expected)
