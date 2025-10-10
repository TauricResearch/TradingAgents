import numpy as np
import pytest

from pandas._libs.sparse import IntIndex

import pandas as pd
from pandas import (
    SparseDtype,
    isna,
)
import pandas._testing as tm
from pandas.core.arrays.sparse import SparseArray


class TestConstructors:
    def test_constructor_dtype(self):
        arr = SparseArray([np.nan, 1, 2, np.nan])
        assert arr.dtype == SparseDtype(np.float64, np.nan)
        assert arr.dtype.subtype == np.float64
        assert np.isnan(arr.fill_value)

        arr = SparseArray([np.nan, 1, 2, np.nan], fill_value=0)
        assert arr.dtype == SparseDtype(np.float64, 0)
        assert arr.fill_value == 0

        arr = SparseArray([0, 1, 2, 4], dtype=np.float64)
        assert arr.dtype == SparseDtype(np.float64, np.nan)
        assert np.isnan(arr.fill_value)

        arr = SparseArray([0, 1, 2, 4], dtype=np.int64)
        assert arr.dtype == SparseDtype(np.int64, 0)
        assert arr.fill_value == 0

        arr = SparseArray([0, 1, 2, 4], fill_value=0, dtype=np.int64)
        assert arr.dtype == SparseDtype(np.int64, 0)
        assert arr.fill_value == 0

        arr = SparseArray([0, 1, 2, 4], dtype=None)
        assert arr.dtype == SparseDtype(np.int64, 0)
        assert arr.fill_value == 0

        arr = SparseArray([0, 1, 2, 4], fill_value=0, dtype=None)
        assert arr.dtype == SparseDtype(np.int64, 0)
        assert arr.fill_value == 0

    def test_constructor_dtype_str(self):
        result = SparseArray([1, 2, 3], dtype="int")
        expected = SparseArray([1, 2, 3], dtype=int)
        tm.assert_sp_array_equal(result, expected)

    def test_constructor_sparse_dtype(self):
        result = SparseArray([1, 0, 0, 1], dtype=SparseDtype("int64", -1))
        expected = SparseArray([1, 0, 0, 1], fill_value=-1, dtype=np.int64)
        tm.assert_sp_array_equal(result, expected)
        assert result.sp_values.dtype == np.dtype("int64")

    def test_constructor_sparse_dtype_str(self):
        result = SparseArray([1, 0, 0, 1], dtype="Sparse[int32]")
        expected = SparseArray([1, 0, 0, 1], dtype=np.int32)
        tm.assert_sp_array_equal(result, expected)
        assert result.sp_values.dtype == np.dtype("int32")

    def test_constructor_object_dtype(self):
        # GH#11856
        arr = SparseArray(["A", "A", np.nan, "B"], dtype=object)
        assert arr.dtype == SparseDtype(object)
        assert np.isnan(arr.fill_value)

        arr = SparseArray(["A", "A", np.nan, "B"], dtype=object, fill_value="A")
        assert arr.dtype == SparseDtype(object, "A")
        assert arr.fill_value == "A"

    def test_constructor_object_dtype_bool_fill(self):
        # GH#17574
        data = [False, 0, 100.0, 0.0]
        arr = SparseArray(data, dtype=object, fill_value=False)
        assert arr.dtype == SparseDtype(object, False)
        assert arr.fill_value is False
        arr_expected = np.array(data, dtype=object)
        it = (type(x) == type(y) and x == y for x, y in zip(arr, arr_expected))
        assert np.fromiter(it, dtype=np.bool_).all()

    @pytest.mark.parametrize("dtype", [SparseDtype(int, 0), int])
    def test_constructor_na_dtype(self, dtype):
        with pytest.raises(ValueError, match="Cannot convert"):
            SparseArray([0, 1, np.nan], dtype=dtype)

    def test_constructor_warns_when_losing_timezone(self):
        # GH#32501 warn when losing timezone information
        dti = pd.date_range("2016-01-01", periods=3, tz="US/Pacific")

        expected = SparseArray(np.asarray(dti, dtype="datetime64[ns]"))

        with tm.assert_produces_warning(UserWarning):
            result = SparseArray(dti)

        tm.assert_sp_array_equal(result, expected)

        with tm.assert_produces_warning(UserWarning):
            result = SparseArray(pd.Series(dti))

        tm.assert_sp_array_equal(result, expected)

    def test_constructor_spindex_dtype(self):
        arr = SparseArray(data=[1, 2], sparse_index=IntIndex(4, [1, 2]))
        # TODO: actionable?
        # XXX: Behavior change: specifying SparseIndex no longer changes the
        # fill_value
        expected = SparseArray([0, 1, 2, 0], kind="integer")
        tm.assert_sp_array_equal(arr, expected)
        assert arr.dtype == SparseDtype(np.int64)
        assert arr.fill_value == 0

        arr = SparseArray(
            data=[1, 2, 3],
            sparse_index=IntIndex(4, [1, 2, 3]),
            dtype=np.int64,
            fill_value=0,
        )
        exp = SparseArray([0, 1, 2, 3], dtype=np.int64, fill_value=0)
        tm.assert_sp_array_equal(arr, exp)
        assert arr.dtype == SparseDtype(np.int64)
        assert arr.fill_value == 0

        arr = SparseArray(
            data=[1, 2], sparse_index=IntIndex(4, [1, 2]), fill_value=0, dtype=np.int64
        )
        exp = SparseArray([0, 1, 2, 0], fill_value=0, dtype=np.int64)
        tm.assert_sp_array_equal(arr, exp)
        assert arr.dtype == SparseDtype(np.int64)
        assert arr.fill_value == 0

        arr = SparseArray(
            data=[1, 2, 3],
            sparse_index=IntIndex(4, [1, 2, 3]),
            dtype=None,
            fill_value=0,
        )
        exp = SparseArray([0, 1, 2, 3], dtype=None)
        tm.assert_sp_array_equal(arr, exp)
        assert arr.dtype == SparseDtype(np.int64)
        assert arr.fill_value == 0

    @pytest.mark.parametrize("sparse_index", [None, IntIndex(1, [0])])
    def test_constructor_spindex_dtype_scalar(self, sparse_index):
        # scalar input
        msg = "Constructing SparseArray with scalar data is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            arr = SparseArray(data=1, sparse_index=sparse_index, dtype=None)
        exp = SparseArray([1], dtype=None)
        tm.assert_sp_array_equal(arr, exp)
        assert arr.dtype == SparseDtype(np.int64)
        assert arr.fill_value == 0

        with tm.assert_produces_warning(FutureWarning, match=msg):
            arr = SparseArray(data=1, sparse_index=IntIndex(1, [0]), dtype=None)
        exp = SparseArray([1], dtype=None)
        tm.assert_sp_array_equal(arr, exp)
        assert arr.dtype == SparseDtype(np.int64)
        assert arr.fill_value == 0

    def test_constructor_spindex_dtype_scalar_broadcasts(self):
        arr = SparseArray(
            data=[1, 2], sparse_index=IntIndex(4, [1, 2]), fill_value=0, dtype=None
        )
        exp = SparseArray([0, 1, 2, 0], fill_value=0, dtype=None)
        tm.assert_sp_array_equal(arr, exp)
        assert arr.dtype == SparseDtype(np.int64)
        assert arr.fill_value == 0

    @pytest.mark.parametrize(
        "data, fill_value",
        [
            (np.array([1, 2]), 0),
            (np.array([1.0, 2.0]), np.nan),
            ([True, False], False),
            ([pd.Timestamp("2017-01-01")], pd.NaT),
        ],
    )
    def test_constructor_inferred_fill_value(self, data, fill_value):
        result = SparseArray(data).fill_value

        if isna(fill_value):
            assert isna(result)
        else:
            assert result == fill_value

    @pytest.mark.parametrize("format", ["coo", "csc", "csr"])
    @pytest.mark.parametrize("size", [0, 10])
    def test_from_spmatrix(self, size, format):
        sp_sparse = pytest.importorskip("scipy.sparse")

        mat = sp_sparse.random(size, 1, density=0.5, format=format)
        result = SparseArray.from_spmatrix(mat)

        result = np.asarray(result)
        expected = mat.toarray().ravel()
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize("format", ["coo", "csc", "csr"])
    def test_from_spmatrix_including_explicit_zero(self, format):
        sp_sparse = pytest.importorskip("scipy.sparse")

        mat = sp_sparse.random(10, 1, density=0.5, format=format)
        mat.data[0] = 0
        result = SparseArray.from_spmatrix(mat)

        result = np.asarray(result)
        expected = mat.toarray().ravel()
        tm.assert_numpy_array_equal(result, expected)

    def test_from_spmatrix_raises(self):
        sp_sparse = pytest.importorskip("scipy.sparse")

        mat = sp_sparse.eye(5, 4, format="csc")

        with pytest.raises(ValueError, match="not '4'"):
            SparseArray.from_spmatrix(mat)

    def test_constructor_from_too_large_array(self):
        with pytest.raises(TypeError, match="expected dimension <= 1 data"):
            SparseArray(np.arange(10).reshape((2, 5)))

    def test_constructor_from_sparse(self):
        zarr = SparseArray([0, 0, 1, 2, 3, 0, 4, 5, 0, 6], fill_value=0)
        res = SparseArray(zarr)
        assert res.fill_value == 0
        tm.assert_almost_equal(res.sp_values, zarr.sp_values)

    def test_constructor_copy(self):
        arr_data = np.array([np.nan, np.nan, 1, 2, 3, np.nan, 4, 5, np.nan, 6])
        arr = SparseArray(arr_data)

        cp = SparseArray(arr, copy=True)
        cp.sp_values[:3] = 0
        assert not (arr.sp_values[:3] == 0).any()

        not_copy = SparseArray(arr)
        not_copy.sp_values[:3] = 0
        assert (arr.sp_values[:3] == 0).all()

    def test_constructor_bool(self):
        # GH#10648
        data = np.array([False, False, True, True, False, False])
        arr = SparseArray(data, fill_value=False, dtype=bool)

        assert arr.dtype == SparseDtype(bool)
        tm.assert_numpy_array_equal(arr.sp_values, np.array([True, True]))
        # Behavior change: np.asarray densifies.
        # tm.assert_numpy_array_equal(arr.sp_values, np.asarray(arr))
        tm.assert_numpy_array_equal(arr.sp_index.indices, np.array([2, 3], np.int32))

        dense = arr.to_dense()
        assert dense.dtype == bool
        tm.assert_numpy_array_equal(dense, data)

    def test_constructor_bool_fill_value(self):
        arr = SparseArray([True, False, True], dtype=None)
        assert arr.dtype == SparseDtype(np.bool_)
        assert not arr.fill_value

        arr = SparseArray([True, False, True], dtype=np.bool_)
        assert arr.dtype == SparseDtype(np.bool_)
        assert not arr.fill_value

        arr = SparseArray([True, False, True], dtype=np.bool_, fill_value=True)
        assert arr.dtype == SparseDtype(np.bool_, True)
        assert arr.fill_value

    def test_constructor_float32(self):
        # GH#10648
        data = np.array([1.0, np.nan, 3], dtype=np.float32)
        arr = SparseArray(data, dtype=np.float32)

        assert arr.dtype == SparseDtype(np.float32)
        tm.assert_numpy_array_equal(arr.sp_values, np.array([1, 3], dtype=np.float32))
        # Behavior change: np.asarray densifies.
        # tm.assert_numpy_array_equal(arr.sp_values, np.asarray(arr))
        tm.assert_numpy_array_equal(
            arr.sp_index.indices, np.array([0, 2], dtype=np.int32)
        )

        dense = arr.to_dense()
        assert dense.dtype == np.float32
        tm.assert_numpy_array_equal(dense, data)
