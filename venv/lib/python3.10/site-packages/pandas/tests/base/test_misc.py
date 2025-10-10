import sys

import numpy as np
import pytest

from pandas._config import using_string_dtype

from pandas.compat import PYPY

from pandas.core.dtypes.common import (
    is_dtype_equal,
    is_object_dtype,
)

import pandas as pd
from pandas import (
    Index,
    Series,
)
import pandas._testing as tm


def test_isnull_notnull_docstrings():
    # GH#41855 make sure its clear these are aliases
    doc = pd.DataFrame.notnull.__doc__
    assert doc.startswith("\nDataFrame.notnull is an alias for DataFrame.notna.\n")
    doc = pd.DataFrame.isnull.__doc__
    assert doc.startswith("\nDataFrame.isnull is an alias for DataFrame.isna.\n")

    doc = Series.notnull.__doc__
    assert doc.startswith("\nSeries.notnull is an alias for Series.notna.\n")
    doc = Series.isnull.__doc__
    assert doc.startswith("\nSeries.isnull is an alias for Series.isna.\n")


@pytest.mark.parametrize(
    "op_name, op",
    [
        ("add", "+"),
        ("sub", "-"),
        ("mul", "*"),
        ("mod", "%"),
        ("pow", "**"),
        ("truediv", "/"),
        ("floordiv", "//"),
    ],
)
def test_binary_ops_docstring(frame_or_series, op_name, op):
    # not using the all_arithmetic_functions fixture with _get_opstr
    # as _get_opstr is used internally in the dynamic implementation of the docstring
    klass = frame_or_series

    operand1 = klass.__name__.lower()
    operand2 = "other"
    expected_str = " ".join([operand1, op, operand2])
    assert expected_str in getattr(klass, op_name).__doc__

    # reverse version of the binary ops
    expected_str = " ".join([operand2, op, operand1])
    assert expected_str in getattr(klass, "r" + op_name).__doc__


def test_ndarray_compat_properties(index_or_series_obj):
    obj = index_or_series_obj

    # Check that we work.
    for p in ["shape", "dtype", "T", "nbytes"]:
        assert getattr(obj, p, None) is not None

    # deprecated properties
    for p in ["strides", "itemsize", "base", "data"]:
        assert not hasattr(obj, p)

    msg = "can only convert an array of size 1 to a Python scalar"
    with pytest.raises(ValueError, match=msg):
        obj.item()  # len > 1

    assert obj.ndim == 1
    assert obj.size == len(obj)

    assert Index([1]).item() == 1
    assert Series([1]).item() == 1


@pytest.mark.skipif(
    PYPY or using_string_dtype(),
    reason="not relevant for PyPy doesn't work properly for arrow strings",
)
def test_memory_usage(index_or_series_memory_obj):
    obj = index_or_series_memory_obj
    # Clear index caches so that len(obj) == 0 report 0 memory usage
    if isinstance(obj, Series):
        is_ser = True
        obj.index._engine.clear_mapping()
    else:
        is_ser = False
        obj._engine.clear_mapping()

    res = obj.memory_usage()
    res_deep = obj.memory_usage(deep=True)

    is_object = is_object_dtype(obj) or (is_ser and is_object_dtype(obj.index))
    is_categorical = isinstance(obj.dtype, pd.CategoricalDtype) or (
        is_ser and isinstance(obj.index.dtype, pd.CategoricalDtype)
    )
    is_object_string = is_dtype_equal(obj, "string[python]") or (
        is_ser and is_dtype_equal(obj.index.dtype, "string[python]")
    )

    if len(obj) == 0:
        expected = 0
        assert res_deep == res == expected
    elif is_object or is_categorical or is_object_string:
        # only deep will pick them up
        assert res_deep > res
    else:
        assert res == res_deep

    # sys.getsizeof will call the .memory_usage with
    # deep=True, and add on some GC overhead
    diff = res_deep - sys.getsizeof(obj)
    assert abs(diff) < 100


def test_memory_usage_components_series(series_with_simple_index):
    series = series_with_simple_index
    total_usage = series.memory_usage(index=True)
    non_index_usage = series.memory_usage(index=False)
    index_usage = series.index.memory_usage()
    assert total_usage == non_index_usage + index_usage


@pytest.mark.parametrize("dtype", tm.NARROW_NP_DTYPES)
def test_memory_usage_components_narrow_series(dtype):
    series = Series(range(5), dtype=dtype, index=[f"i-{i}" for i in range(5)], name="a")
    total_usage = series.memory_usage(index=True)
    non_index_usage = series.memory_usage(index=False)
    index_usage = series.index.memory_usage()
    assert total_usage == non_index_usage + index_usage


def test_searchsorted(request, index_or_series_obj):
    # numpy.searchsorted calls obj.searchsorted under the hood.
    # See gh-12238
    obj = index_or_series_obj

    if isinstance(obj, pd.MultiIndex):
        # See gh-14833
        request.applymarker(
            pytest.mark.xfail(
                reason="np.searchsorted doesn't work on pd.MultiIndex: GH 14833"
            )
        )
    elif obj.dtype.kind == "c" and isinstance(obj, Index):
        # TODO: Should Series cases also raise? Looks like they use numpy
        #  comparison semantics https://github.com/numpy/numpy/issues/15981
        mark = pytest.mark.xfail(reason="complex objects are not comparable")
        request.applymarker(mark)

    max_obj = max(obj, default=0)
    index = np.searchsorted(obj, max_obj)
    assert 0 <= index <= len(obj)

    index = np.searchsorted(obj, max_obj, sorter=range(len(obj)))
    assert 0 <= index <= len(obj)


@pytest.mark.filterwarnings(r"ignore:Dtype inference:FutureWarning")
def test_access_by_position(index_flat):
    index = index_flat

    if len(index) == 0:
        pytest.skip("Test doesn't make sense on empty data")

    series = Series(index)
    assert index[0] == series.iloc[0]
    assert index[5] == series.iloc[5]
    assert index[-1] == series.iloc[-1]

    size = len(index)
    assert index[-1] == index[size - 1]

    msg = f"index {size} is out of bounds for axis 0 with size {size}"
    if isinstance(index.dtype, pd.StringDtype) and index.dtype.storage == "pyarrow":
        msg = "index out of bounds"
    with pytest.raises(IndexError, match=msg):
        index[size]
    msg = "single positional indexer is out-of-bounds"
    with pytest.raises(IndexError, match=msg):
        series.iloc[size]
