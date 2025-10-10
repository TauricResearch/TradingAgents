import re

import numpy as np
import pytest

from pandas._libs.sparse import IntIndex
from pandas.compat.numpy import np_version_gt2

import pandas as pd
from pandas import (
    SparseDtype,
    isna,
)
import pandas._testing as tm
from pandas.core.arrays.sparse import SparseArray


@pytest.fixture
def arr_data():
    """Fixture returning numpy array with valid and missing entries"""
    return np.array([np.nan, np.nan, 1, 2, 3, np.nan, 4, 5, np.nan, 6])


@pytest.fixture
def arr(arr_data):
    """Fixture returning SparseArray from 'arr_data'"""
    return SparseArray(arr_data)


@pytest.fixture
def zarr():
    """Fixture returning SparseArray with integer entries and 'fill_value=0'"""
    return SparseArray([0, 0, 1, 2, 3, 0, 4, 5, 0, 6], fill_value=0)


class TestSparseArray:
    @pytest.mark.parametrize("fill_value", [0, None, np.nan])
    def test_shift_fill_value(self, fill_value):
        # GH #24128
        sparse = SparseArray(np.array([1, 0, 0, 3, 0]), fill_value=8.0)
        res = sparse.shift(1, fill_value=fill_value)
        if isna(fill_value):
            fill_value = res.dtype.na_value
        exp = SparseArray(np.array([fill_value, 1, 0, 0, 3]), fill_value=8.0)
        tm.assert_sp_array_equal(res, exp)

    def test_set_fill_value(self):
        arr = SparseArray([1.0, np.nan, 2.0], fill_value=np.nan)
        arr.fill_value = 2
        assert arr.fill_value == 2

        arr = SparseArray([1, 0, 2], fill_value=0, dtype=np.int64)
        arr.fill_value = 2
        assert arr.fill_value == 2

        msg = "Allowing arbitrary scalar fill_value in SparseDtype is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            arr.fill_value = 3.1
        assert arr.fill_value == 3.1

        arr.fill_value = np.nan
        assert np.isnan(arr.fill_value)

        arr = SparseArray([True, False, True], fill_value=False, dtype=np.bool_)
        arr.fill_value = True
        assert arr.fill_value is True

        with tm.assert_produces_warning(FutureWarning, match=msg):
            arr.fill_value = 0

        arr.fill_value = np.nan
        assert np.isnan(arr.fill_value)

    @pytest.mark.parametrize("val", [[1, 2, 3], np.array([1, 2]), (1, 2, 3)])
    def test_set_fill_invalid_non_scalar(self, val):
        arr = SparseArray([True, False, True], fill_value=False, dtype=np.bool_)
        msg = "fill_value must be a scalar"

        with pytest.raises(ValueError, match=msg):
            arr.fill_value = val

    def test_copy(self, arr):
        arr2 = arr.copy()
        assert arr2.sp_values is not arr.sp_values
        assert arr2.sp_index is arr.sp_index

    def test_values_asarray(self, arr_data, arr):
        tm.assert_almost_equal(arr.to_dense(), arr_data)

    @pytest.mark.parametrize(
        "data,shape,dtype",
        [
            ([0, 0, 0, 0, 0], (5,), None),
            ([], (0,), None),
            ([0], (1,), None),
            (["A", "A", np.nan, "B"], (4,), object),
        ],
    )
    def test_shape(self, data, shape, dtype):
        # GH 21126
        out = SparseArray(data, dtype=dtype)
        assert out.shape == shape

    @pytest.mark.parametrize(
        "vals",
        [
            [np.nan, np.nan, np.nan, np.nan, np.nan],
            [1, np.nan, np.nan, 3, np.nan],
            [1, np.nan, 0, 3, 0],
        ],
    )
    @pytest.mark.parametrize("fill_value", [None, 0])
    def test_dense_repr(self, vals, fill_value):
        vals = np.array(vals)
        arr = SparseArray(vals, fill_value=fill_value)

        res = arr.to_dense()
        tm.assert_numpy_array_equal(res, vals)

    @pytest.mark.parametrize("fix", ["arr", "zarr"])
    def test_pickle(self, fix, request):
        obj = request.getfixturevalue(fix)
        unpickled = tm.round_trip_pickle(obj)
        tm.assert_sp_array_equal(unpickled, obj)

    def test_generator_warnings(self):
        sp_arr = SparseArray([1, 2, 3])
        with tm.assert_produces_warning(None):
            for _ in sp_arr:
                pass

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

    def test_fillna(self):
        s = SparseArray([1, np.nan, np.nan, 3, np.nan])
        res = s.fillna(-1)
        exp = SparseArray([1, -1, -1, 3, -1], fill_value=-1, dtype=np.float64)
        tm.assert_sp_array_equal(res, exp)

        s = SparseArray([1, np.nan, np.nan, 3, np.nan], fill_value=0)
        res = s.fillna(-1)
        exp = SparseArray([1, -1, -1, 3, -1], fill_value=0, dtype=np.float64)
        tm.assert_sp_array_equal(res, exp)

        s = SparseArray([1, np.nan, 0, 3, 0])
        res = s.fillna(-1)
        exp = SparseArray([1, -1, 0, 3, 0], fill_value=-1, dtype=np.float64)
        tm.assert_sp_array_equal(res, exp)

        s = SparseArray([1, np.nan, 0, 3, 0], fill_value=0)
        res = s.fillna(-1)
        exp = SparseArray([1, -1, 0, 3, 0], fill_value=0, dtype=np.float64)
        tm.assert_sp_array_equal(res, exp)

        s = SparseArray([np.nan, np.nan, np.nan, np.nan])
        res = s.fillna(-1)
        exp = SparseArray([-1, -1, -1, -1], fill_value=-1, dtype=np.float64)
        tm.assert_sp_array_equal(res, exp)

        s = SparseArray([np.nan, np.nan, np.nan, np.nan], fill_value=0)
        res = s.fillna(-1)
        exp = SparseArray([-1, -1, -1, -1], fill_value=0, dtype=np.float64)
        tm.assert_sp_array_equal(res, exp)

        # float dtype's fill_value is np.nan, replaced by -1
        s = SparseArray([0.0, 0.0, 0.0, 0.0])
        res = s.fillna(-1)
        exp = SparseArray([0.0, 0.0, 0.0, 0.0], fill_value=-1)
        tm.assert_sp_array_equal(res, exp)

        # int dtype shouldn't have missing. No changes.
        s = SparseArray([0, 0, 0, 0])
        assert s.dtype == SparseDtype(np.int64)
        assert s.fill_value == 0
        res = s.fillna(-1)
        tm.assert_sp_array_equal(res, s)

        s = SparseArray([0, 0, 0, 0], fill_value=0)
        assert s.dtype == SparseDtype(np.int64)
        assert s.fill_value == 0
        res = s.fillna(-1)
        exp = SparseArray([0, 0, 0, 0], fill_value=0)
        tm.assert_sp_array_equal(res, exp)

        # fill_value can be nan if there is no missing hole.
        # only fill_value will be changed
        s = SparseArray([0, 0, 0, 0], fill_value=np.nan)
        assert s.dtype == SparseDtype(np.int64, fill_value=np.nan)
        assert np.isnan(s.fill_value)
        res = s.fillna(-1)
        exp = SparseArray([0, 0, 0, 0], fill_value=-1)
        tm.assert_sp_array_equal(res, exp)

    def test_fillna_overlap(self):
        s = SparseArray([1, np.nan, np.nan, 3, np.nan])
        # filling with existing value doesn't replace existing value with
        # fill_value, i.e. existing 3 remains in sp_values
        res = s.fillna(3)
        exp = np.array([1, 3, 3, 3, 3], dtype=np.float64)
        tm.assert_numpy_array_equal(res.to_dense(), exp)

        s = SparseArray([1, np.nan, np.nan, 3, np.nan], fill_value=0)
        res = s.fillna(3)
        exp = SparseArray([1, 3, 3, 3, 3], fill_value=0, dtype=np.float64)
        tm.assert_sp_array_equal(res, exp)

    def test_nonzero(self):
        # Tests regression #21172.
        sa = SparseArray([float("nan"), float("nan"), 1, 0, 0, 2, 0, 0, 0, 3, 0, 0])
        expected = np.array([2, 5, 9], dtype=np.int32)
        (result,) = sa.nonzero()
        tm.assert_numpy_array_equal(expected, result)

        sa = SparseArray([0, 0, 1, 0, 0, 2, 0, 0, 0, 3, 0, 0])
        (result,) = sa.nonzero()
        tm.assert_numpy_array_equal(expected, result)


class TestSparseArrayAnalytics:
    @pytest.mark.parametrize(
        "data,expected",
        [
            (
                np.array([1, 2, 3, 4, 5], dtype=float),  # non-null data
                SparseArray(np.array([1.0, 3.0, 6.0, 10.0, 15.0])),
            ),
            (
                np.array([1, 2, np.nan, 4, 5], dtype=float),  # null data
                SparseArray(np.array([1.0, 3.0, np.nan, 7.0, 12.0])),
            ),
        ],
    )
    @pytest.mark.parametrize("numpy", [True, False])
    def test_cumsum(self, data, expected, numpy):
        cumsum = np.cumsum if numpy else lambda s: s.cumsum()

        out = cumsum(SparseArray(data))
        tm.assert_sp_array_equal(out, expected)

        out = cumsum(SparseArray(data, fill_value=np.nan))
        tm.assert_sp_array_equal(out, expected)

        out = cumsum(SparseArray(data, fill_value=2))
        tm.assert_sp_array_equal(out, expected)

        if numpy:  # numpy compatibility checks.
            msg = "the 'dtype' parameter is not supported"
            with pytest.raises(ValueError, match=msg):
                np.cumsum(SparseArray(data), dtype=np.int64)

            msg = "the 'out' parameter is not supported"
            with pytest.raises(ValueError, match=msg):
                np.cumsum(SparseArray(data), out=out)
        else:
            axis = 1  # SparseArray currently 1-D, so only axis = 0 is valid.
            msg = re.escape(f"axis(={axis}) out of bounds")
            with pytest.raises(ValueError, match=msg):
                SparseArray(data).cumsum(axis=axis)

    def test_ufunc(self):
        # GH 13853 make sure ufunc is applied to fill_value
        sparse = SparseArray([1, np.nan, 2, np.nan, -2])
        result = SparseArray([1, np.nan, 2, np.nan, 2])
        tm.assert_sp_array_equal(abs(sparse), result)
        tm.assert_sp_array_equal(np.abs(sparse), result)

        sparse = SparseArray([1, -1, 2, -2], fill_value=1)
        result = SparseArray([1, 2, 2], sparse_index=sparse.sp_index, fill_value=1)
        tm.assert_sp_array_equal(abs(sparse), result)
        tm.assert_sp_array_equal(np.abs(sparse), result)

        sparse = SparseArray([1, -1, 2, -2], fill_value=-1)
        exp = SparseArray([1, 1, 2, 2], fill_value=1)
        tm.assert_sp_array_equal(abs(sparse), exp)
        tm.assert_sp_array_equal(np.abs(sparse), exp)

        sparse = SparseArray([1, np.nan, 2, np.nan, -2])
        result = SparseArray(np.sin([1, np.nan, 2, np.nan, -2]))
        tm.assert_sp_array_equal(np.sin(sparse), result)

        sparse = SparseArray([1, -1, 2, -2], fill_value=1)
        result = SparseArray(np.sin([1, -1, 2, -2]), fill_value=np.sin(1))
        tm.assert_sp_array_equal(np.sin(sparse), result)

        sparse = SparseArray([1, -1, 0, -2], fill_value=0)
        result = SparseArray(np.sin([1, -1, 0, -2]), fill_value=np.sin(0))
        tm.assert_sp_array_equal(np.sin(sparse), result)

    def test_ufunc_args(self):
        # GH 13853 make sure ufunc is applied to fill_value, including its arg
        sparse = SparseArray([1, np.nan, 2, np.nan, -2])
        result = SparseArray([2, np.nan, 3, np.nan, -1])
        tm.assert_sp_array_equal(np.add(sparse, 1), result)

        sparse = SparseArray([1, -1, 2, -2], fill_value=1)
        result = SparseArray([2, 0, 3, -1], fill_value=2)
        tm.assert_sp_array_equal(np.add(sparse, 1), result)

        sparse = SparseArray([1, -1, 0, -2], fill_value=0)
        result = SparseArray([2, 0, 1, -1], fill_value=1)
        tm.assert_sp_array_equal(np.add(sparse, 1), result)

    @pytest.mark.parametrize("fill_value", [0.0, np.nan])
    def test_modf(self, fill_value):
        # https://github.com/pandas-dev/pandas/issues/26946
        sparse = SparseArray([fill_value] * 10 + [1.1, 2.2], fill_value=fill_value)
        r1, r2 = np.modf(sparse)
        e1, e2 = np.modf(np.asarray(sparse))
        tm.assert_sp_array_equal(r1, SparseArray(e1, fill_value=fill_value))
        tm.assert_sp_array_equal(r2, SparseArray(e2, fill_value=fill_value))

    def test_nbytes_integer(self):
        arr = SparseArray([1, 0, 0, 0, 2], kind="integer")
        result = arr.nbytes
        # (2 * 8) + 2 * 4
        assert result == 24

    def test_nbytes_block(self):
        arr = SparseArray([1, 2, 0, 0, 0], kind="block")
        result = arr.nbytes
        # (2 * 8) + 4 + 4
        # sp_values, blocs, blengths
        assert result == 24

    def test_asarray_datetime64(self):
        s = SparseArray(pd.to_datetime(["2012", None, None, "2013"]))
        np.asarray(s)

    def test_density(self):
        arr = SparseArray([0, 1])
        assert arr.density == 0.5

    def test_npoints(self):
        arr = SparseArray([0, 1])
        assert arr.npoints == 1


def test_setting_fill_value_fillna_still_works():
    # This is why letting users update fill_value / dtype is bad
    # astype has the same problem.
    arr = SparseArray([1.0, np.nan, 1.0], fill_value=0.0)
    arr.fill_value = np.nan
    result = arr.isna()
    # Can't do direct comparison, since the sp_index will be different
    # So let's convert to ndarray and check there.
    result = np.asarray(result)

    expected = np.array([False, True, False])
    tm.assert_numpy_array_equal(result, expected)


def test_setting_fill_value_updates():
    arr = SparseArray([0.0, np.nan], fill_value=0)
    arr.fill_value = np.nan
    # use private constructor to get the index right
    # otherwise both nans would be un-stored.
    expected = SparseArray._simple_new(
        sparse_array=np.array([np.nan]),
        sparse_index=IntIndex(2, [1]),
        dtype=SparseDtype(float, np.nan),
    )
    tm.assert_sp_array_equal(arr, expected)


@pytest.mark.parametrize(
    "arr,fill_value,loc",
    [
        ([None, 1, 2], None, 0),
        ([0, None, 2], None, 1),
        ([0, 1, None], None, 2),
        ([0, 1, 1, None, None], None, 3),
        ([1, 1, 1, 2], None, -1),
        ([], None, -1),
        ([None, 1, 0, 0, None, 2], None, 0),
        ([None, 1, 0, 0, None, 2], 1, 1),
        ([None, 1, 0, 0, None, 2], 2, 5),
        ([None, 1, 0, 0, None, 2], 3, -1),
        ([None, 0, 0, 1, 2, 1], 0, 1),
        ([None, 0, 0, 1, 2, 1], 1, 3),
    ],
)
def test_first_fill_value_loc(arr, fill_value, loc):
    result = SparseArray(arr, fill_value=fill_value)._first_fill_value_loc()
    assert result == loc


@pytest.mark.parametrize(
    "arr",
    [
        [1, 2, np.nan, np.nan],
        [1, np.nan, 2, np.nan],
        [1, 2, np.nan],
        [np.nan, 1, 0, 0, np.nan, 2],
        [np.nan, 0, 0, 1, 2, 1],
    ],
)
@pytest.mark.parametrize("fill_value", [np.nan, 0, 1])
def test_unique_na_fill(arr, fill_value):
    a = SparseArray(arr, fill_value=fill_value).unique()
    b = pd.Series(arr).unique()
    assert isinstance(a, SparseArray)
    a = np.asarray(a)
    tm.assert_numpy_array_equal(a, b)


def test_unique_all_sparse():
    # https://github.com/pandas-dev/pandas/issues/23168
    arr = SparseArray([0, 0])
    result = arr.unique()
    expected = SparseArray([0])
    tm.assert_sp_array_equal(result, expected)


def test_map():
    arr = SparseArray([0, 1, 2])
    expected = SparseArray([10, 11, 12], fill_value=10)

    # dict
    result = arr.map({0: 10, 1: 11, 2: 12})
    tm.assert_sp_array_equal(result, expected)

    # series
    result = arr.map(pd.Series({0: 10, 1: 11, 2: 12}))
    tm.assert_sp_array_equal(result, expected)

    # function
    result = arr.map(pd.Series({0: 10, 1: 11, 2: 12}))
    expected = SparseArray([10, 11, 12], fill_value=10)
    tm.assert_sp_array_equal(result, expected)


def test_map_missing():
    arr = SparseArray([0, 1, 2])
    expected = SparseArray([10, 11, None], fill_value=10)

    result = arr.map({0: 10, 1: 11})
    tm.assert_sp_array_equal(result, expected)


@pytest.mark.parametrize("fill_value", [np.nan, 1])
def test_dropna(fill_value):
    # GH-28287
    arr = SparseArray([np.nan, 1], fill_value=fill_value)
    exp = SparseArray([1.0], fill_value=fill_value)
    tm.assert_sp_array_equal(arr.dropna(), exp)

    df = pd.DataFrame({"a": [0, 1], "b": arr})
    expected_df = pd.DataFrame({"a": [1], "b": exp}, index=pd.Index([1]))
    tm.assert_equal(df.dropna(), expected_df)


def test_drop_duplicates_fill_value():
    # GH 11726
    df = pd.DataFrame(np.zeros((5, 5))).apply(lambda x: SparseArray(x, fill_value=0))
    result = df.drop_duplicates()
    expected = pd.DataFrame({i: SparseArray([0.0], fill_value=0) for i in range(5)})
    tm.assert_frame_equal(result, expected)


def test_zero_sparse_column():
    # GH 27781
    df1 = pd.DataFrame({"A": SparseArray([0, 0, 0]), "B": [1, 2, 3]})
    df2 = pd.DataFrame({"A": SparseArray([0, 1, 0]), "B": [1, 2, 3]})
    result = df1.loc[df1["B"] != 2]
    expected = df2.loc[df2["B"] != 2]
    tm.assert_frame_equal(result, expected)

    expected = pd.DataFrame({"A": SparseArray([0, 0]), "B": [1, 3]}, index=[0, 2])
    tm.assert_frame_equal(result, expected)


def test_array_interface(arr_data, arr):
    # https://github.com/pandas-dev/pandas/pull/60046
    result = np.asarray(arr)
    tm.assert_numpy_array_equal(result, arr_data)

    # it always gives a copy by default
    result_copy1 = np.asarray(arr)
    result_copy2 = np.asarray(arr)
    assert not np.may_share_memory(result_copy1, result_copy2)

    # or with explicit copy=True
    result_copy1 = np.array(arr, copy=True)
    result_copy2 = np.array(arr, copy=True)
    assert not np.may_share_memory(result_copy1, result_copy2)

    if not np_version_gt2:
        # copy=False semantics are only supported in NumPy>=2.
        return

    msg = "Starting with NumPy 2.0, the behavior of the 'copy' keyword has changed"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        np.array(arr, copy=False)

    # except when there are actually no sparse filled values
    arr2 = SparseArray(np.array([1, 2, 3]))
    result_nocopy1 = np.array(arr2, copy=False)
    result_nocopy2 = np.array(arr2, copy=False)
    assert np.may_share_memory(result_nocopy1, result_nocopy2)
