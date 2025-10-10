import numpy as np

from pandas.core.dtypes.common import is_scalar

import pandas as pd
import pandas._testing as tm


class TestSearchsorted:
    def test_searchsorted_string(self, string_dtype):
        arr = pd.array(["a", "b", "c"], dtype=string_dtype)

        result = arr.searchsorted("a", side="left")
        assert is_scalar(result)
        assert result == 0

        result = arr.searchsorted("a", side="right")
        assert is_scalar(result)
        assert result == 1

    def test_searchsorted_numeric_dtypes_scalar(self, any_real_numpy_dtype):
        arr = pd.array([1, 3, 90], dtype=any_real_numpy_dtype)
        result = arr.searchsorted(30)
        assert is_scalar(result)
        assert result == 2

        result = arr.searchsorted([30])
        expected = np.array([2], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

    def test_searchsorted_numeric_dtypes_vector(self, any_real_numpy_dtype):
        arr = pd.array([1, 3, 90], dtype=any_real_numpy_dtype)
        result = arr.searchsorted([2, 30])
        expected = np.array([1, 2], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

    def test_searchsorted_sorter(self, any_real_numpy_dtype):
        arr = pd.array([3, 1, 2], dtype=any_real_numpy_dtype)
        result = arr.searchsorted([0, 3], sorter=np.argsort(arr))
        expected = np.array([0, 2], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)
