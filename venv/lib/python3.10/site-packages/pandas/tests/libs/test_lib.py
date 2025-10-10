import pickle

import numpy as np
import pytest

from pandas._libs import (
    Timedelta,
    lib,
    writers as libwriters,
)
from pandas.compat import IS64

from pandas import Index
import pandas._testing as tm


class TestMisc:
    def test_max_len_string_array(self):
        arr = a = np.array(["foo", "b", np.nan], dtype="object")
        assert libwriters.max_len_string_array(arr) == 3

        # unicode
        arr = a.astype("U").astype(object)
        assert libwriters.max_len_string_array(arr) == 3

        # bytes for python3
        arr = a.astype("S").astype(object)
        assert libwriters.max_len_string_array(arr) == 3

        # raises
        msg = "No matching signature found"
        with pytest.raises(TypeError, match=msg):
            libwriters.max_len_string_array(arr.astype("U"))

    def test_fast_unique_multiple_list_gen_sort(self):
        keys = [["p", "a"], ["n", "d"], ["a", "s"]]

        gen = (key for key in keys)
        expected = np.array(["a", "d", "n", "p", "s"])
        out = lib.fast_unique_multiple_list_gen(gen, sort=True)
        tm.assert_numpy_array_equal(np.array(out), expected)

        gen = (key for key in keys)
        expected = np.array(["p", "a", "n", "d", "s"])
        out = lib.fast_unique_multiple_list_gen(gen, sort=False)
        tm.assert_numpy_array_equal(np.array(out), expected)

    def test_fast_multiget_timedelta_resos(self):
        # This will become relevant for test_constructor_dict_timedelta64_index
        #  once Timedelta constructor preserves reso when passed a
        #  np.timedelta64 object
        td = Timedelta(days=1)

        mapping1 = {td: 1}
        mapping2 = {td.as_unit("s"): 1}

        oindex = Index([td * n for n in range(3)])._values.astype(object)

        expected = lib.fast_multiget(mapping1, oindex)
        result = lib.fast_multiget(mapping2, oindex)
        tm.assert_numpy_array_equal(result, expected)

        # case that can't be cast to td64ns
        td = Timedelta(np.timedelta64(146000, "D"))
        assert hash(td) == hash(td.as_unit("ms"))
        assert hash(td) == hash(td.as_unit("us"))
        mapping1 = {td: 1}
        mapping2 = {td.as_unit("ms"): 1}

        oindex = Index([td * n for n in range(3)])._values.astype(object)

        expected = lib.fast_multiget(mapping1, oindex)
        result = lib.fast_multiget(mapping2, oindex)
        tm.assert_numpy_array_equal(result, expected)


class TestIndexing:
    def test_maybe_indices_to_slice_left_edge(self):
        target = np.arange(100)

        # slice
        indices = np.array([], dtype=np.intp)
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))

        assert isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(target[indices], target[maybe_slice])

    @pytest.mark.parametrize("end", [1, 2, 5, 20, 99])
    @pytest.mark.parametrize("step", [1, 2, 4])
    def test_maybe_indices_to_slice_left_edge_not_slice_end_steps(self, end, step):
        target = np.arange(100)
        indices = np.arange(0, end, step, dtype=np.intp)
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))

        assert isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(target[indices], target[maybe_slice])

        # reverse
        indices = indices[::-1]
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))

        assert isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(target[indices], target[maybe_slice])

    @pytest.mark.parametrize(
        "case", [[2, 1, 2, 0], [2, 2, 1, 0], [0, 1, 2, 1], [-2, 0, 2], [2, 0, -2]]
    )
    def test_maybe_indices_to_slice_left_edge_not_slice(self, case):
        # not slice
        target = np.arange(100)
        indices = np.array(case, dtype=np.intp)
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))

        assert not isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(maybe_slice, indices)
        tm.assert_numpy_array_equal(target[indices], target[maybe_slice])

    @pytest.mark.parametrize("start", [0, 2, 5, 20, 97, 98])
    @pytest.mark.parametrize("step", [1, 2, 4])
    def test_maybe_indices_to_slice_right_edge(self, start, step):
        target = np.arange(100)

        # slice
        indices = np.arange(start, 99, step, dtype=np.intp)
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))

        assert isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(target[indices], target[maybe_slice])

        # reverse
        indices = indices[::-1]
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))

        assert isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(target[indices], target[maybe_slice])

    def test_maybe_indices_to_slice_right_edge_not_slice(self):
        # not slice
        target = np.arange(100)
        indices = np.array([97, 98, 99, 100], dtype=np.intp)
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))

        assert not isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(maybe_slice, indices)

        msg = "index 100 is out of bounds for axis (0|1) with size 100"

        with pytest.raises(IndexError, match=msg):
            target[indices]
        with pytest.raises(IndexError, match=msg):
            target[maybe_slice]

        indices = np.array([100, 99, 98, 97], dtype=np.intp)
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))

        assert not isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(maybe_slice, indices)

        with pytest.raises(IndexError, match=msg):
            target[indices]
        with pytest.raises(IndexError, match=msg):
            target[maybe_slice]

    @pytest.mark.parametrize(
        "case", [[99, 97, 99, 96], [99, 99, 98, 97], [98, 98, 97, 96]]
    )
    def test_maybe_indices_to_slice_right_edge_cases(self, case):
        target = np.arange(100)
        indices = np.array(case, dtype=np.intp)
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))

        assert not isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(maybe_slice, indices)
        tm.assert_numpy_array_equal(target[indices], target[maybe_slice])

    @pytest.mark.parametrize("step", [1, 2, 4, 5, 8, 9])
    def test_maybe_indices_to_slice_both_edges(self, step):
        target = np.arange(10)

        # slice
        indices = np.arange(0, 9, step, dtype=np.intp)
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))
        assert isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(target[indices], target[maybe_slice])

        # reverse
        indices = indices[::-1]
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))
        assert isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(target[indices], target[maybe_slice])

    @pytest.mark.parametrize("case", [[4, 2, 0, -2], [2, 2, 1, 0], [0, 1, 2, 1]])
    def test_maybe_indices_to_slice_both_edges_not_slice(self, case):
        # not slice
        target = np.arange(10)
        indices = np.array(case, dtype=np.intp)
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))
        assert not isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(maybe_slice, indices)
        tm.assert_numpy_array_equal(target[indices], target[maybe_slice])

    @pytest.mark.parametrize("start, end", [(2, 10), (5, 25), (65, 97)])
    @pytest.mark.parametrize("step", [1, 2, 4, 20])
    def test_maybe_indices_to_slice_middle(self, start, end, step):
        target = np.arange(100)

        # slice
        indices = np.arange(start, end, step, dtype=np.intp)
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))

        assert isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(target[indices], target[maybe_slice])

        # reverse
        indices = indices[::-1]
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))

        assert isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(target[indices], target[maybe_slice])

    @pytest.mark.parametrize(
        "case", [[14, 12, 10, 12], [12, 12, 11, 10], [10, 11, 12, 11]]
    )
    def test_maybe_indices_to_slice_middle_not_slice(self, case):
        # not slice
        target = np.arange(100)
        indices = np.array(case, dtype=np.intp)
        maybe_slice = lib.maybe_indices_to_slice(indices, len(target))

        assert not isinstance(maybe_slice, slice)
        tm.assert_numpy_array_equal(maybe_slice, indices)
        tm.assert_numpy_array_equal(target[indices], target[maybe_slice])

    def test_maybe_booleans_to_slice(self):
        arr = np.array([0, 0, 1, 1, 1, 0, 1], dtype=np.uint8)
        result = lib.maybe_booleans_to_slice(arr)
        assert result.dtype == np.bool_

        result = lib.maybe_booleans_to_slice(arr[:0])
        assert result == slice(0, 0)

    def test_get_reverse_indexer(self):
        indexer = np.array([-1, -1, 1, 2, 0, -1, 3, 4], dtype=np.intp)
        result = lib.get_reverse_indexer(indexer, 5)
        expected = np.array([4, 2, 3, 6, 7], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize("dtype", ["int64", "int32"])
    def test_is_range_indexer(self, dtype):
        # GH#50592
        left = np.arange(0, 100, dtype=dtype)
        assert lib.is_range_indexer(left, 100)

    @pytest.mark.skipif(
        not IS64,
        reason="2**31 is too big for Py_ssize_t on 32-bit. "
        "It doesn't matter though since you cannot create an array that long on 32-bit",
    )
    @pytest.mark.parametrize("dtype", ["int64", "int32"])
    def test_is_range_indexer_big_n(self, dtype):
        # GH53616
        left = np.arange(0, 100, dtype=dtype)

        assert not lib.is_range_indexer(left, 2**31)

    @pytest.mark.parametrize("dtype", ["int64", "int32"])
    def test_is_range_indexer_not_equal(self, dtype):
        # GH#50592
        left = np.array([1, 2], dtype=dtype)
        assert not lib.is_range_indexer(left, 2)

    @pytest.mark.parametrize("dtype", ["int64", "int32"])
    def test_is_range_indexer_not_equal_shape(self, dtype):
        # GH#50592
        left = np.array([0, 1, 2], dtype=dtype)
        assert not lib.is_range_indexer(left, 2)


def test_cache_readonly_preserve_docstrings():
    # GH18197
    assert Index.hasnans.__doc__ is not None


def test_no_default_pickle():
    # GH#40397
    obj = tm.round_trip_pickle(lib.no_default)
    assert obj is lib.no_default


def test_ensure_string_array_copy():
    # ensure the original array is not modified in case of copy=False with
    # pickle-roundtripped object dtype array
    # https://github.com/pandas-dev/pandas/issues/54654
    arr = np.array(["a", None], dtype=object)
    arr = pickle.loads(pickle.dumps(arr))
    result = lib.ensure_string_array(arr, copy=False)
    assert not np.shares_memory(arr, result)
    assert arr[1] is None
    assert result[1] is np.nan
