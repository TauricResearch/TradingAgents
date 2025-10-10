import numpy as np
import pytest

from pandas.core.dtypes import dtypes
from pandas.core.dtypes.common import is_extension_array_dtype

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays import ExtensionArray


class DummyDtype(dtypes.ExtensionDtype):
    pass


class DummyArray(ExtensionArray):
    def __init__(self, data) -> None:
        self.data = data

    def __array__(self, dtype=None, copy=None):
        return self.data

    @property
    def dtype(self):
        return DummyDtype()

    def astype(self, dtype, copy=True):
        # we don't support anything but a single dtype
        if isinstance(dtype, DummyDtype):
            if copy:
                return type(self)(self.data)
            return self
        elif not copy:
            return np.asarray(self, dtype=dtype)
        else:
            return np.array(self, dtype=dtype, copy=copy)


class TestExtensionArrayDtype:
    @pytest.mark.parametrize(
        "values",
        [
            pd.Categorical([]),
            pd.Categorical([]).dtype,
            pd.Series(pd.Categorical([])),
            DummyDtype(),
            DummyArray(np.array([1, 2])),
        ],
    )
    def test_is_extension_array_dtype(self, values):
        assert is_extension_array_dtype(values)

    @pytest.mark.parametrize("values", [np.array([]), pd.Series(np.array([]))])
    def test_is_not_extension_array_dtype(self, values):
        assert not is_extension_array_dtype(values)


def test_astype():
    arr = DummyArray(np.array([1, 2, 3]))
    expected = np.array([1, 2, 3], dtype=object)

    result = arr.astype(object)
    tm.assert_numpy_array_equal(result, expected)

    result = arr.astype("object")
    tm.assert_numpy_array_equal(result, expected)


def test_astype_no_copy():
    arr = DummyArray(np.array([1, 2, 3], dtype=np.int64))
    result = arr.astype(arr.dtype, copy=False)

    assert arr is result

    result = arr.astype(arr.dtype)
    assert arr is not result


@pytest.mark.parametrize("dtype", [dtypes.CategoricalDtype(), dtypes.IntervalDtype()])
def test_is_extension_array_dtype(dtype):
    assert isinstance(dtype, dtypes.ExtensionDtype)
    assert is_extension_array_dtype(dtype)


class CapturingStringArray(pd.arrays.StringArray):
    """Extend StringArray to capture arguments to __getitem__"""

    def __getitem__(self, item):
        self.last_item_arg = item
        return super().__getitem__(item)


def test_ellipsis_index():
    # GH#42430 1D slices over extension types turn into N-dimensional slices
    #  over ExtensionArrays
    df = pd.DataFrame(
        {"col1": CapturingStringArray(np.array(["hello", "world"], dtype=object))}
    )
    _ = df.iloc[:1]

    # String comparison because there's no native way to compare slices.
    # Before the fix for GH#42430, last_item_arg would get set to the 2D slice
    # (Ellipsis, slice(None, 1, None))
    out = df["col1"].array.last_item_arg
    assert str(out) == "slice(None, 1, None)"
