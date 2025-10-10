import numpy as np
import pytest

import pandas as pd
from pandas.core.arrays.floating import (
    Float32Dtype,
    Float64Dtype,
)


def test_dtypes(dtype):
    # smoke tests on auto dtype construction

    np.dtype(dtype.type).kind == "f"
    assert dtype.name is not None


@pytest.mark.parametrize(
    "dtype, expected",
    [(Float32Dtype(), "Float32Dtype()"), (Float64Dtype(), "Float64Dtype()")],
)
def test_repr_dtype(dtype, expected):
    assert repr(dtype) == expected


def test_repr_array():
    result = repr(pd.array([1.0, None, 3.0]))
    expected = "<FloatingArray>\n[1.0, <NA>, 3.0]\nLength: 3, dtype: Float64"
    assert result == expected


def test_repr_array_long():
    data = pd.array([1.0, 2.0, None] * 1000)
    expected = """<FloatingArray>
[ 1.0,  2.0, <NA>,  1.0,  2.0, <NA>,  1.0,  2.0, <NA>,  1.0,
 ...
 <NA>,  1.0,  2.0, <NA>,  1.0,  2.0, <NA>,  1.0,  2.0, <NA>]
Length: 3000, dtype: Float64"""
    result = repr(data)
    assert result == expected


def test_frame_repr(data_missing):
    df = pd.DataFrame({"A": data_missing})
    result = repr(df)
    expected = "      A\n0  <NA>\n1   0.1"
    assert result == expected
