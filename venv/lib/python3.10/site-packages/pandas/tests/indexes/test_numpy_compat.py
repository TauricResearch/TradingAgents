import numpy as np
import pytest

from pandas import (
    CategoricalIndex,
    DatetimeIndex,
    Index,
    PeriodIndex,
    TimedeltaIndex,
    isna,
)
import pandas._testing as tm
from pandas.api.types import (
    is_complex_dtype,
    is_numeric_dtype,
)
from pandas.core.arrays import BooleanArray
from pandas.core.indexes.datetimelike import DatetimeIndexOpsMixin


def test_numpy_ufuncs_out(index):
    result = index == index

    out = np.empty(index.shape, dtype=bool)
    np.equal(index, index, out=out)
    tm.assert_numpy_array_equal(out, result)

    if not index._is_multi:
        # same thing on the ExtensionArray
        out = np.empty(index.shape, dtype=bool)
        np.equal(index.array, index.array, out=out)
        tm.assert_numpy_array_equal(out, result)


@pytest.mark.parametrize(
    "func",
    [
        np.exp,
        np.exp2,
        np.expm1,
        np.log,
        np.log2,
        np.log10,
        np.log1p,
        np.sqrt,
        np.sin,
        np.cos,
        np.tan,
        np.arcsin,
        np.arccos,
        np.arctan,
        np.sinh,
        np.cosh,
        np.tanh,
        np.arcsinh,
        np.arccosh,
        np.arctanh,
        np.deg2rad,
        np.rad2deg,
    ],
    ids=lambda x: x.__name__,
)
def test_numpy_ufuncs_basic(index, func):
    # test ufuncs of numpy, see:
    # https://numpy.org/doc/stable/reference/ufuncs.html

    if isinstance(index, DatetimeIndexOpsMixin):
        with tm.external_error_raised((TypeError, AttributeError)):
            with np.errstate(all="ignore"):
                func(index)
    elif is_numeric_dtype(index) and not (
        is_complex_dtype(index) and func in [np.deg2rad, np.rad2deg]
    ):
        # coerces to float (e.g. np.sin)
        with np.errstate(all="ignore"):
            result = func(index)
            arr_result = func(index.values)
            if arr_result.dtype == np.float16:
                arr_result = arr_result.astype(np.float32)
            exp = Index(arr_result, name=index.name)

        tm.assert_index_equal(result, exp)
        if isinstance(index.dtype, np.dtype) and is_numeric_dtype(index):
            if is_complex_dtype(index):
                assert result.dtype == index.dtype
            elif index.dtype in ["bool", "int8", "uint8"]:
                assert result.dtype in ["float16", "float32"]
            elif index.dtype in ["int16", "uint16", "float32"]:
                assert result.dtype == "float32"
            else:
                assert result.dtype == "float64"
        else:
            # e.g. np.exp with Int64 -> Float64
            assert type(result) is Index
    # raise AttributeError or TypeError
    elif len(index) == 0:
        pass
    else:
        with tm.external_error_raised((TypeError, AttributeError)):
            with np.errstate(all="ignore"):
                func(index)


@pytest.mark.parametrize(
    "func", [np.isfinite, np.isinf, np.isnan, np.signbit], ids=lambda x: x.__name__
)
def test_numpy_ufuncs_other(index, func):
    # test ufuncs of numpy, see:
    # https://numpy.org/doc/stable/reference/ufuncs.html
    if isinstance(index, (DatetimeIndex, TimedeltaIndex)):
        if func in (np.isfinite, np.isinf, np.isnan):
            # numpy 1.18 changed isinf and isnan to not raise on dt64/td64
            result = func(index)
            assert isinstance(result, np.ndarray)

            out = np.empty(index.shape, dtype=bool)
            func(index, out=out)
            tm.assert_numpy_array_equal(out, result)
        else:
            with tm.external_error_raised(TypeError):
                func(index)

    elif isinstance(index, PeriodIndex):
        with tm.external_error_raised(TypeError):
            func(index)

    elif is_numeric_dtype(index) and not (
        is_complex_dtype(index) and func is np.signbit
    ):
        # Results in bool array
        result = func(index)
        if not isinstance(index.dtype, np.dtype):
            # e.g. Int64 we expect to get BooleanArray back
            assert isinstance(result, BooleanArray)
        else:
            assert isinstance(result, np.ndarray)

        out = np.empty(index.shape, dtype=bool)
        func(index, out=out)

        if not isinstance(index.dtype, np.dtype):
            tm.assert_numpy_array_equal(out, result._data)
        else:
            tm.assert_numpy_array_equal(out, result)

    elif len(index) == 0:
        pass
    else:
        with tm.external_error_raised(TypeError):
            func(index)


@pytest.mark.parametrize("func", [np.maximum, np.minimum])
def test_numpy_ufuncs_reductions(index, func, request):
    # TODO: overlap with tests.series.test_ufunc.test_reductions
    if len(index) == 0:
        pytest.skip("Test doesn't make sense for empty index.")

    if isinstance(index, CategoricalIndex) and index.dtype.ordered is False:
        with pytest.raises(TypeError, match="is not ordered for"):
            func.reduce(index)
        return
    else:
        result = func.reduce(index)

    if func is np.maximum:
        expected = index.max(skipna=False)
    else:
        expected = index.min(skipna=False)
        # TODO: do we have cases both with and without NAs?

    assert type(result) is type(expected)
    if isna(result):
        assert isna(expected)
    else:
        assert result == expected


@pytest.mark.parametrize("func", [np.bitwise_and, np.bitwise_or, np.bitwise_xor])
def test_numpy_ufuncs_bitwise(func):
    # https://github.com/pandas-dev/pandas/issues/46769
    idx1 = Index([1, 2, 3, 4], dtype="int64")
    idx2 = Index([3, 4, 5, 6], dtype="int64")

    with tm.assert_produces_warning(None):
        result = func(idx1, idx2)

    expected = Index(func(idx1.values, idx2.values))
    tm.assert_index_equal(result, expected)
