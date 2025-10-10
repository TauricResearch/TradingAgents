import numpy as np
import pytest

from pandas._libs.sparse import IntIndex

from pandas import (
    SparseDtype,
    Timestamp,
)
import pandas._testing as tm
from pandas.core.arrays.sparse import SparseArray


class TestAstype:
    def test_astype(self):
        # float -> float
        arr = SparseArray([None, None, 0, 2])
        result = arr.astype("Sparse[float32]")
        expected = SparseArray([None, None, 0, 2], dtype=np.dtype("float32"))
        tm.assert_sp_array_equal(result, expected)

        dtype = SparseDtype("float64", fill_value=0)
        result = arr.astype(dtype)
        expected = SparseArray._simple_new(
            np.array([0.0, 2.0], dtype=dtype.subtype), IntIndex(4, [2, 3]), dtype
        )
        tm.assert_sp_array_equal(result, expected)

        dtype = SparseDtype("int64", 0)
        result = arr.astype(dtype)
        expected = SparseArray._simple_new(
            np.array([0, 2], dtype=np.int64), IntIndex(4, [2, 3]), dtype
        )
        tm.assert_sp_array_equal(result, expected)

        arr = SparseArray([0, np.nan, 0, 1], fill_value=0)
        with pytest.raises(ValueError, match="NA"):
            arr.astype("Sparse[i8]")

    def test_astype_bool(self):
        a = SparseArray([1, 0, 0, 1], dtype=SparseDtype(int, 0))
        result = a.astype(bool)
        expected = np.array([1, 0, 0, 1], dtype=bool)
        tm.assert_numpy_array_equal(result, expected)

        # update fill value
        result = a.astype(SparseDtype(bool, False))
        expected = SparseArray(
            [True, False, False, True], dtype=SparseDtype(bool, False)
        )
        tm.assert_sp_array_equal(result, expected)

    def test_astype_all(self, any_real_numpy_dtype):
        vals = np.array([1, 2, 3])
        arr = SparseArray(vals, fill_value=1)
        typ = np.dtype(any_real_numpy_dtype)
        res = arr.astype(typ)
        tm.assert_numpy_array_equal(res, vals.astype(any_real_numpy_dtype))

    @pytest.mark.parametrize(
        "arr, dtype, expected",
        [
            (
                SparseArray([0, 1]),
                "float",
                SparseArray([0.0, 1.0], dtype=SparseDtype(float, 0.0)),
            ),
            (SparseArray([0, 1]), bool, SparseArray([False, True])),
            (
                SparseArray([0, 1], fill_value=1),
                bool,
                SparseArray([False, True], dtype=SparseDtype(bool, True)),
            ),
            pytest.param(
                SparseArray([0, 1]),
                "datetime64[ns]",
                SparseArray(
                    np.array([0, 1], dtype="datetime64[ns]"),
                    dtype=SparseDtype("datetime64[ns]", Timestamp("1970")),
                ),
            ),
            (
                SparseArray([0, 1, 10]),
                np.str_,
                SparseArray(["0", "1", "10"], dtype=SparseDtype(np.str_, "0")),
            ),
            (SparseArray(["10", "20"]), float, SparseArray([10.0, 20.0])),
            (
                SparseArray([0, 1, 0]),
                object,
                SparseArray([0, 1, 0], dtype=SparseDtype(object, 0)),
            ),
        ],
    )
    def test_astype_more(self, arr, dtype, expected):
        result = arr.astype(arr.dtype.update_dtype(dtype))
        tm.assert_sp_array_equal(result, expected)

    def test_astype_nan_raises(self):
        arr = SparseArray([1.0, np.nan])
        with pytest.raises(ValueError, match="Cannot convert non-finite"):
            arr.astype(int)

    def test_astype_copy_false(self):
        # GH#34456 bug caused by using .view instead of .astype in astype_nansafe
        arr = SparseArray([1, 2, 3])

        dtype = SparseDtype(float, 0)

        result = arr.astype(dtype, copy=False)
        expected = SparseArray([1.0, 2.0, 3.0], fill_value=0.0)
        tm.assert_sp_array_equal(result, expected)

    def test_astype_dt64_to_int64(self):
        # GH#49631 match non-sparse behavior
        values = np.array(["NaT", "2016-01-02", "2016-01-03"], dtype="M8[ns]")

        arr = SparseArray(values)
        result = arr.astype("int64")
        expected = values.astype("int64")
        tm.assert_numpy_array_equal(result, expected)

        # we should also be able to cast to equivalent Sparse[int64]
        dtype_int64 = SparseDtype("int64", np.iinfo(np.int64).min)
        result2 = arr.astype(dtype_int64)
        tm.assert_numpy_array_equal(result2.to_numpy(), expected)

        # GH#50087 we should match the non-sparse behavior regardless of
        #  if we have a fill_value other than NaT
        dtype = SparseDtype("datetime64[ns]", values[1])
        arr3 = SparseArray(values, dtype=dtype)
        result3 = arr3.astype("int64")
        tm.assert_numpy_array_equal(result3, expected)
