import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays.sparse import SparseArray


class TestSparseArrayConcat:
    @pytest.mark.parametrize("kind", ["integer", "block"])
    def test_basic(self, kind):
        a = SparseArray([1, 0, 0, 2], kind=kind)
        b = SparseArray([1, 0, 2, 2], kind=kind)

        result = SparseArray._concat_same_type([a, b])
        # Can't make any assertions about the sparse index itself
        # since we aren't don't merge sparse blocs across arrays
        # in to_concat
        expected = np.array([1, 2, 1, 2, 2], dtype="int64")
        tm.assert_numpy_array_equal(result.sp_values, expected)
        assert result.kind == kind

    @pytest.mark.parametrize("kind", ["integer", "block"])
    def test_uses_first_kind(self, kind):
        other = "integer" if kind == "block" else "block"
        a = SparseArray([1, 0, 0, 2], kind=kind)
        b = SparseArray([1, 0, 2, 2], kind=other)

        result = SparseArray._concat_same_type([a, b])
        expected = np.array([1, 2, 1, 2, 2], dtype="int64")
        tm.assert_numpy_array_equal(result.sp_values, expected)
        assert result.kind == kind


@pytest.mark.parametrize(
    "other, expected_dtype",
    [
        # compatible dtype -> preserve sparse
        (pd.Series([3, 4, 5], dtype="int64"), pd.SparseDtype("int64", 0)),
        # (pd.Series([3, 4, 5], dtype="Int64"), pd.SparseDtype("int64", 0)),
        # incompatible dtype -> Sparse[common dtype]
        (pd.Series([1.5, 2.5, 3.5], dtype="float64"), pd.SparseDtype("float64", 0)),
        # incompatible dtype -> Sparse[object] dtype
        (pd.Series(["a", "b", "c"], dtype=object), pd.SparseDtype(object, 0)),
        # categorical with compatible categories -> dtype of the categories
        (pd.Series([3, 4, 5], dtype="category"), np.dtype("int64")),
        (pd.Series([1.5, 2.5, 3.5], dtype="category"), np.dtype("float64")),
        # categorical with incompatible categories -> object dtype
        (pd.Series(["a", "b", "c"], dtype="category"), np.dtype(object)),
    ],
)
def test_concat_with_non_sparse(other, expected_dtype):
    # https://github.com/pandas-dev/pandas/issues/34336
    s_sparse = pd.Series([1, 0, 2], dtype=pd.SparseDtype("int64", 0))

    result = pd.concat([s_sparse, other], ignore_index=True)
    expected = pd.Series(list(s_sparse) + list(other)).astype(expected_dtype)
    tm.assert_series_equal(result, expected)

    result = pd.concat([other, s_sparse], ignore_index=True)
    expected = pd.Series(list(other) + list(s_sparse)).astype(expected_dtype)
    tm.assert_series_equal(result, expected)
