import numpy as np
import pytest

import pandas as pd
from pandas import SparseDtype
import pandas._testing as tm
from pandas.core.arrays.sparse import SparseArray


@pytest.fixture
def arr_data():
    return np.array([np.nan, np.nan, 1, 2, 3, np.nan, 4, 5, np.nan, 6])


@pytest.fixture
def arr(arr_data):
    return SparseArray(arr_data)


class TestGetitem:
    def test_getitem(self, arr):
        dense = arr.to_dense()
        for i, value in enumerate(arr):
            tm.assert_almost_equal(value, dense[i])
            tm.assert_almost_equal(arr[-i], dense[-i])

    def test_getitem_arraylike_mask(self, arr):
        arr = SparseArray([0, 1, 2])
        result = arr[[True, False, True]]
        expected = SparseArray([0, 2])
        tm.assert_sp_array_equal(result, expected)

    @pytest.mark.parametrize(
        "slc",
        [
            np.s_[:],
            np.s_[1:10],
            np.s_[1:100],
            np.s_[10:1],
            np.s_[:-3],
            np.s_[-5:-4],
            np.s_[:-12],
            np.s_[-12:],
            np.s_[2:],
            np.s_[2::3],
            np.s_[::2],
            np.s_[::-1],
            np.s_[::-2],
            np.s_[1:6:2],
            np.s_[:-6:-2],
        ],
    )
    @pytest.mark.parametrize(
        "as_dense", [[np.nan] * 10, [1] * 10, [np.nan] * 5 + [1] * 5, []]
    )
    def test_getslice(self, slc, as_dense):
        as_dense = np.array(as_dense)
        arr = SparseArray(as_dense)

        result = arr[slc]
        expected = SparseArray(as_dense[slc])

        tm.assert_sp_array_equal(result, expected)

    def test_getslice_tuple(self):
        dense = np.array([np.nan, 0, 3, 4, 0, 5, np.nan, np.nan, 0])

        sparse = SparseArray(dense)
        res = sparse[(slice(4, None),)]
        exp = SparseArray(dense[4:])
        tm.assert_sp_array_equal(res, exp)

        sparse = SparseArray(dense, fill_value=0)
        res = sparse[(slice(4, None),)]
        exp = SparseArray(dense[4:], fill_value=0)
        tm.assert_sp_array_equal(res, exp)

        msg = "too many indices for array"
        with pytest.raises(IndexError, match=msg):
            sparse[4:, :]

        with pytest.raises(IndexError, match=msg):
            # check numpy compat
            dense[4:, :]

    def test_boolean_slice_empty(self):
        arr = SparseArray([0, 1, 2])
        res = arr[[False, False, False]]
        assert res.dtype == arr.dtype

    def test_getitem_bool_sparse_array(self, arr):
        # GH 23122
        spar_bool = SparseArray([False, True] * 5, dtype=np.bool_, fill_value=True)
        exp = SparseArray([np.nan, 2, np.nan, 5, 6])
        tm.assert_sp_array_equal(arr[spar_bool], exp)

        spar_bool = ~spar_bool
        res = arr[spar_bool]
        exp = SparseArray([np.nan, 1, 3, 4, np.nan])
        tm.assert_sp_array_equal(res, exp)

        spar_bool = SparseArray(
            [False, True, np.nan] * 3, dtype=np.bool_, fill_value=np.nan
        )
        res = arr[spar_bool]
        exp = SparseArray([np.nan, 3, 5])
        tm.assert_sp_array_equal(res, exp)

    def test_getitem_bool_sparse_array_as_comparison(self):
        # GH 45110
        arr = SparseArray([1, 2, 3, 4, np.nan, np.nan], fill_value=np.nan)
        res = arr[arr > 2]
        exp = SparseArray([3.0, 4.0], fill_value=np.nan)
        tm.assert_sp_array_equal(res, exp)

    def test_get_item(self, arr):
        zarr = SparseArray([0, 0, 1, 2, 3, 0, 4, 5, 0, 6], fill_value=0)

        assert np.isnan(arr[1])
        assert arr[2] == 1
        assert arr[7] == 5

        assert zarr[0] == 0
        assert zarr[2] == 1
        assert zarr[7] == 5

        errmsg = "must be an integer between -10 and 10"

        with pytest.raises(IndexError, match=errmsg):
            arr[11]

        with pytest.raises(IndexError, match=errmsg):
            arr[-11]

        assert arr[-1] == arr[len(arr) - 1]


class TestSetitem:
    def test_set_item(self, arr_data):
        arr = SparseArray(arr_data).copy()

        def setitem():
            arr[5] = 3

        def setslice():
            arr[1:5] = 2

        with pytest.raises(TypeError, match="assignment via setitem"):
            setitem()

        with pytest.raises(TypeError, match="assignment via setitem"):
            setslice()


class TestTake:
    def test_take_scalar_raises(self, arr):
        msg = "'indices' must be an array, not a scalar '2'."
        with pytest.raises(ValueError, match=msg):
            arr.take(2)

    def test_take(self, arr_data, arr):
        exp = SparseArray(np.take(arr_data, [2, 3]))
        tm.assert_sp_array_equal(arr.take([2, 3]), exp)

        exp = SparseArray(np.take(arr_data, [0, 1, 2]))
        tm.assert_sp_array_equal(arr.take([0, 1, 2]), exp)

    def test_take_all_empty(self):
        sparse = pd.array([0, 0], dtype=SparseDtype("int64"))
        result = sparse.take([0, 1], allow_fill=True, fill_value=np.nan)
        tm.assert_sp_array_equal(sparse, result)

    def test_take_different_fill_value(self):
        # Take with a different fill value shouldn't overwrite the original
        sparse = pd.array([0.0], dtype=SparseDtype("float64", fill_value=0.0))
        result = sparse.take([0, -1], allow_fill=True, fill_value=np.nan)
        expected = pd.array([0, np.nan], dtype=sparse.dtype)
        tm.assert_sp_array_equal(expected, result)

    def test_take_fill_value(self):
        data = np.array([1, np.nan, 0, 3, 0])
        sparse = SparseArray(data, fill_value=0)

        exp = SparseArray(np.take(data, [0]), fill_value=0)
        tm.assert_sp_array_equal(sparse.take([0]), exp)

        exp = SparseArray(np.take(data, [1, 3, 4]), fill_value=0)
        tm.assert_sp_array_equal(sparse.take([1, 3, 4]), exp)

    def test_take_negative(self, arr_data, arr):
        exp = SparseArray(np.take(arr_data, [-1]))
        tm.assert_sp_array_equal(arr.take([-1]), exp)

        exp = SparseArray(np.take(arr_data, [-4, -3, -2]))
        tm.assert_sp_array_equal(arr.take([-4, -3, -2]), exp)

    def test_bad_take(self, arr):
        with pytest.raises(IndexError, match="bounds"):
            arr.take([11])

    def test_take_filling(self):
        # similar tests as GH 12631
        sparse = SparseArray([np.nan, np.nan, 1, np.nan, 4])
        result = sparse.take(np.array([1, 0, -1]))
        expected = SparseArray([np.nan, np.nan, 4])
        tm.assert_sp_array_equal(result, expected)

        # TODO: actionable?
        # XXX: test change: fill_value=True -> allow_fill=True
        result = sparse.take(np.array([1, 0, -1]), allow_fill=True)
        expected = SparseArray([np.nan, np.nan, np.nan])
        tm.assert_sp_array_equal(result, expected)

        # allow_fill=False
        result = sparse.take(np.array([1, 0, -1]), allow_fill=False, fill_value=True)
        expected = SparseArray([np.nan, np.nan, 4])
        tm.assert_sp_array_equal(result, expected)

        msg = "Invalid value in 'indices'"
        with pytest.raises(ValueError, match=msg):
            sparse.take(np.array([1, 0, -2]), allow_fill=True)

        with pytest.raises(ValueError, match=msg):
            sparse.take(np.array([1, 0, -5]), allow_fill=True)

        msg = "out of bounds value in 'indices'"
        with pytest.raises(IndexError, match=msg):
            sparse.take(np.array([1, -6]))
        with pytest.raises(IndexError, match=msg):
            sparse.take(np.array([1, 5]))
        with pytest.raises(IndexError, match=msg):
            sparse.take(np.array([1, 5]), allow_fill=True)

    def test_take_filling_fill_value(self):
        # same tests as GH#12631
        sparse = SparseArray([np.nan, 0, 1, 0, 4], fill_value=0)
        result = sparse.take(np.array([1, 0, -1]))
        expected = SparseArray([0, np.nan, 4], fill_value=0)
        tm.assert_sp_array_equal(result, expected)

        # fill_value
        result = sparse.take(np.array([1, 0, -1]), allow_fill=True)
        # TODO: actionable?
        # XXX: behavior change.
        # the old way of filling self.fill_value doesn't follow EA rules.
        # It's supposed to be self.dtype.na_value (nan in this case)
        expected = SparseArray([0, np.nan, np.nan], fill_value=0)
        tm.assert_sp_array_equal(result, expected)

        # allow_fill=False
        result = sparse.take(np.array([1, 0, -1]), allow_fill=False, fill_value=True)
        expected = SparseArray([0, np.nan, 4], fill_value=0)
        tm.assert_sp_array_equal(result, expected)

        msg = "Invalid value in 'indices'."
        with pytest.raises(ValueError, match=msg):
            sparse.take(np.array([1, 0, -2]), allow_fill=True)
        with pytest.raises(ValueError, match=msg):
            sparse.take(np.array([1, 0, -5]), allow_fill=True)

        msg = "out of bounds value in 'indices'"
        with pytest.raises(IndexError, match=msg):
            sparse.take(np.array([1, -6]))
        with pytest.raises(IndexError, match=msg):
            sparse.take(np.array([1, 5]))
        with pytest.raises(IndexError, match=msg):
            sparse.take(np.array([1, 5]), fill_value=True)

    @pytest.mark.parametrize("kind", ["block", "integer"])
    def test_take_filling_all_nan(self, kind):
        sparse = SparseArray([np.nan, np.nan, np.nan, np.nan, np.nan], kind=kind)
        result = sparse.take(np.array([1, 0, -1]))
        expected = SparseArray([np.nan, np.nan, np.nan], kind=kind)
        tm.assert_sp_array_equal(result, expected)

        result = sparse.take(np.array([1, 0, -1]), fill_value=True)
        expected = SparseArray([np.nan, np.nan, np.nan], kind=kind)
        tm.assert_sp_array_equal(result, expected)

        msg = "out of bounds value in 'indices'"
        with pytest.raises(IndexError, match=msg):
            sparse.take(np.array([1, -6]))
        with pytest.raises(IndexError, match=msg):
            sparse.take(np.array([1, 5]))
        with pytest.raises(IndexError, match=msg):
            sparse.take(np.array([1, 5]), fill_value=True)


class TestWhere:
    def test_where_retain_fill_value(self):
        # GH#45691 don't lose fill_value on _where
        arr = SparseArray([np.nan, 1.0], fill_value=0)

        mask = np.array([True, False])

        res = arr._where(~mask, 1)
        exp = SparseArray([1, 1.0], fill_value=0)
        tm.assert_sp_array_equal(res, exp)

        ser = pd.Series(arr)
        res = ser.where(~mask, 1)
        tm.assert_series_equal(res, pd.Series(exp))
