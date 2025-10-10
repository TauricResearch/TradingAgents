"""
Tests for subclasses of NDArrayBackedExtensionArray
"""
import numpy as np

from pandas import (
    CategoricalIndex,
    date_range,
)
from pandas.core.arrays import (
    Categorical,
    DatetimeArray,
    NumpyExtensionArray,
    TimedeltaArray,
)


class TestEmpty:
    def test_empty_categorical(self):
        ci = CategoricalIndex(["a", "b", "c"], ordered=True)
        dtype = ci.dtype

        # case with int8 codes
        shape = (4,)
        result = Categorical._empty(shape, dtype=dtype)
        assert isinstance(result, Categorical)
        assert result.shape == shape
        assert result._ndarray.dtype == np.int8

        # case where repr would segfault if we didn't override base implementation
        result = Categorical._empty((4096,), dtype=dtype)
        assert isinstance(result, Categorical)
        assert result.shape == (4096,)
        assert result._ndarray.dtype == np.int8
        repr(result)

        # case with int16 codes
        ci = CategoricalIndex(list(range(512)) * 4, ordered=False)
        dtype = ci.dtype
        result = Categorical._empty(shape, dtype=dtype)
        assert isinstance(result, Categorical)
        assert result.shape == shape
        assert result._ndarray.dtype == np.int16

    def test_empty_dt64tz(self):
        dti = date_range("2016-01-01", periods=2, tz="Asia/Tokyo")
        dtype = dti.dtype

        shape = (0,)
        result = DatetimeArray._empty(shape, dtype=dtype)
        assert result.dtype == dtype
        assert isinstance(result, DatetimeArray)
        assert result.shape == shape

    def test_empty_dt64(self):
        shape = (3, 9)
        result = DatetimeArray._empty(shape, dtype="datetime64[ns]")
        assert isinstance(result, DatetimeArray)
        assert result.shape == shape

    def test_empty_td64(self):
        shape = (3, 9)
        result = TimedeltaArray._empty(shape, dtype="m8[ns]")
        assert isinstance(result, TimedeltaArray)
        assert result.shape == shape

    def test_empty_pandas_array(self):
        arr = NumpyExtensionArray(np.array([1, 2]))
        dtype = arr.dtype

        shape = (3, 9)
        result = NumpyExtensionArray._empty(shape, dtype=dtype)
        assert isinstance(result, NumpyExtensionArray)
        assert result.dtype == dtype
        assert result.shape == shape
