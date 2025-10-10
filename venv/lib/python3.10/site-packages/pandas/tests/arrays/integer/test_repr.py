import numpy as np
import pytest

import pandas as pd
from pandas.core.arrays.integer import (
    Int8Dtype,
    Int16Dtype,
    Int32Dtype,
    Int64Dtype,
    UInt8Dtype,
    UInt16Dtype,
    UInt32Dtype,
    UInt64Dtype,
)


def test_dtypes(dtype):
    # smoke tests on auto dtype construction

    if dtype.is_signed_integer:
        assert np.dtype(dtype.type).kind == "i"
    else:
        assert np.dtype(dtype.type).kind == "u"
    assert dtype.name is not None


@pytest.mark.parametrize(
    "dtype, expected",
    [
        (Int8Dtype(), "Int8Dtype()"),
        (Int16Dtype(), "Int16Dtype()"),
        (Int32Dtype(), "Int32Dtype()"),
        (Int64Dtype(), "Int64Dtype()"),
        (UInt8Dtype(), "UInt8Dtype()"),
        (UInt16Dtype(), "UInt16Dtype()"),
        (UInt32Dtype(), "UInt32Dtype()"),
        (UInt64Dtype(), "UInt64Dtype()"),
    ],
)
def test_repr_dtype(dtype, expected):
    assert repr(dtype) == expected


def test_repr_array():
    result = repr(pd.array([1, None, 3]))
    expected = "<IntegerArray>\n[1, <NA>, 3]\nLength: 3, dtype: Int64"
    assert result == expected


def test_repr_array_long():
    data = pd.array([1, 2, None] * 1000)
    expected = (
        "<IntegerArray>\n"
        "[   1,    2, <NA>,    1,    2, <NA>,    1,    2, <NA>,    1,\n"
        " ...\n"
        " <NA>,    1,    2, <NA>,    1,    2, <NA>,    1,    2, <NA>]\n"
        "Length: 3000, dtype: Int64"
    )
    result = repr(data)
    assert result == expected


def test_frame_repr(data_missing):
    df = pd.DataFrame({"A": data_missing})
    result = repr(df)
    expected = "      A\n0  <NA>\n1     1"
    assert result == expected
