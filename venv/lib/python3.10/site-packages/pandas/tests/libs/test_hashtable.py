from collections.abc import Generator
from contextlib import contextmanager
import re
import struct
import tracemalloc

import numpy as np
import pytest

from pandas._libs import hashtable as ht

import pandas as pd
import pandas._testing as tm
from pandas.core.algorithms import isin


@contextmanager
def activated_tracemalloc() -> Generator[None, None, None]:
    tracemalloc.start()
    try:
        yield
    finally:
        tracemalloc.stop()


def get_allocated_khash_memory():
    snapshot = tracemalloc.take_snapshot()
    snapshot = snapshot.filter_traces(
        (tracemalloc.DomainFilter(True, ht.get_hashtable_trace_domain()),)
    )
    return sum(x.size for x in snapshot.traces)


@pytest.mark.parametrize(
    "table_type, dtype",
    [
        (ht.PyObjectHashTable, np.object_),
        (ht.Complex128HashTable, np.complex128),
        (ht.Int64HashTable, np.int64),
        (ht.UInt64HashTable, np.uint64),
        (ht.Float64HashTable, np.float64),
        (ht.Complex64HashTable, np.complex64),
        (ht.Int32HashTable, np.int32),
        (ht.UInt32HashTable, np.uint32),
        (ht.Float32HashTable, np.float32),
        (ht.Int16HashTable, np.int16),
        (ht.UInt16HashTable, np.uint16),
        (ht.Int8HashTable, np.int8),
        (ht.UInt8HashTable, np.uint8),
        (ht.IntpHashTable, np.intp),
    ],
)
class TestHashTable:
    def test_get_set_contains_len(self, table_type, dtype):
        index = 5
        table = table_type(55)
        assert len(table) == 0
        assert index not in table

        table.set_item(index, 42)
        assert len(table) == 1
        assert index in table
        assert table.get_item(index) == 42

        table.set_item(index + 1, 41)
        assert index in table
        assert index + 1 in table
        assert len(table) == 2
        assert table.get_item(index) == 42
        assert table.get_item(index + 1) == 41

        table.set_item(index, 21)
        assert index in table
        assert index + 1 in table
        assert len(table) == 2
        assert table.get_item(index) == 21
        assert table.get_item(index + 1) == 41
        assert index + 2 not in table

        table.set_item(index + 1, 21)
        assert index in table
        assert index + 1 in table
        assert len(table) == 2
        assert table.get_item(index) == 21
        assert table.get_item(index + 1) == 21

        with pytest.raises(KeyError, match=str(index + 2)):
            table.get_item(index + 2)

    def test_get_set_contains_len_mask(self, table_type, dtype):
        if table_type == ht.PyObjectHashTable:
            pytest.skip("Mask not supported for object")
        index = 5
        table = table_type(55, uses_mask=True)
        assert len(table) == 0
        assert index not in table

        table.set_item(index, 42)
        assert len(table) == 1
        assert index in table
        assert table.get_item(index) == 42
        with pytest.raises(KeyError, match="NA"):
            table.get_na()

        table.set_item(index + 1, 41)
        table.set_na(41)
        assert pd.NA in table
        assert index in table
        assert index + 1 in table
        assert len(table) == 3
        assert table.get_item(index) == 42
        assert table.get_item(index + 1) == 41
        assert table.get_na() == 41

        table.set_na(21)
        assert index in table
        assert index + 1 in table
        assert len(table) == 3
        assert table.get_item(index + 1) == 41
        assert table.get_na() == 21
        assert index + 2 not in table

        with pytest.raises(KeyError, match=str(index + 2)):
            table.get_item(index + 2)

    def test_map_keys_to_values(self, table_type, dtype, writable):
        # only Int64HashTable has this method
        if table_type == ht.Int64HashTable:
            N = 77
            table = table_type()
            keys = np.arange(N).astype(dtype)
            vals = np.arange(N).astype(np.int64) + N
            keys.flags.writeable = writable
            vals.flags.writeable = writable
            table.map_keys_to_values(keys, vals)
            for i in range(N):
                assert table.get_item(keys[i]) == i + N

    def test_map_locations(self, table_type, dtype, writable):
        N = 8
        table = table_type()
        keys = (np.arange(N) + N).astype(dtype)
        keys.flags.writeable = writable
        table.map_locations(keys)
        for i in range(N):
            assert table.get_item(keys[i]) == i

    def test_map_locations_mask(self, table_type, dtype, writable):
        if table_type == ht.PyObjectHashTable:
            pytest.skip("Mask not supported for object")
        N = 3
        table = table_type(uses_mask=True)
        keys = (np.arange(N) + N).astype(dtype)
        keys.flags.writeable = writable
        table.map_locations(keys, np.array([False, False, True]))
        for i in range(N - 1):
            assert table.get_item(keys[i]) == i

        with pytest.raises(KeyError, match=re.escape(str(keys[N - 1]))):
            table.get_item(keys[N - 1])

        assert table.get_na() == 2

    def test_lookup(self, table_type, dtype, writable):
        N = 3
        table = table_type()
        keys = (np.arange(N) + N).astype(dtype)
        keys.flags.writeable = writable
        table.map_locations(keys)
        result = table.lookup(keys)
        expected = np.arange(N)
        tm.assert_numpy_array_equal(result.astype(np.int64), expected.astype(np.int64))

    def test_lookup_wrong(self, table_type, dtype):
        if dtype in (np.int8, np.uint8):
            N = 100
        else:
            N = 512
        table = table_type()
        keys = (np.arange(N) + N).astype(dtype)
        table.map_locations(keys)
        wrong_keys = np.arange(N).astype(dtype)
        result = table.lookup(wrong_keys)
        assert np.all(result == -1)

    def test_lookup_mask(self, table_type, dtype, writable):
        if table_type == ht.PyObjectHashTable:
            pytest.skip("Mask not supported for object")
        N = 3
        table = table_type(uses_mask=True)
        keys = (np.arange(N) + N).astype(dtype)
        mask = np.array([False, True, False])
        keys.flags.writeable = writable
        table.map_locations(keys, mask)
        result = table.lookup(keys, mask)
        expected = np.arange(N)
        tm.assert_numpy_array_equal(result.astype(np.int64), expected.astype(np.int64))

        result = table.lookup(np.array([1 + N]).astype(dtype), np.array([False]))
        tm.assert_numpy_array_equal(
            result.astype(np.int64), np.array([-1], dtype=np.int64)
        )

    def test_unique(self, table_type, dtype, writable):
        if dtype in (np.int8, np.uint8):
            N = 88
        else:
            N = 1000
        table = table_type()
        expected = (np.arange(N) + N).astype(dtype)
        keys = np.repeat(expected, 5)
        keys.flags.writeable = writable
        unique = table.unique(keys)
        tm.assert_numpy_array_equal(unique, expected)

    def test_tracemalloc_works(self, table_type, dtype):
        if dtype in (np.int8, np.uint8):
            N = 256
        else:
            N = 30000
        keys = np.arange(N).astype(dtype)
        with activated_tracemalloc():
            table = table_type()
            table.map_locations(keys)
            used = get_allocated_khash_memory()
            my_size = table.sizeof()
            assert used == my_size
            del table
            assert get_allocated_khash_memory() == 0

    def test_tracemalloc_for_empty(self, table_type, dtype):
        with activated_tracemalloc():
            table = table_type()
            used = get_allocated_khash_memory()
            my_size = table.sizeof()
            assert used == my_size
            del table
            assert get_allocated_khash_memory() == 0

    def test_get_state(self, table_type, dtype):
        table = table_type(1000)
        state = table.get_state()
        assert state["size"] == 0
        assert state["n_occupied"] == 0
        assert "n_buckets" in state
        assert "upper_bound" in state

    @pytest.mark.parametrize("N", range(1, 110))
    def test_no_reallocation(self, table_type, dtype, N):
        keys = np.arange(N).astype(dtype)
        preallocated_table = table_type(N)
        n_buckets_start = preallocated_table.get_state()["n_buckets"]
        preallocated_table.map_locations(keys)
        n_buckets_end = preallocated_table.get_state()["n_buckets"]
        # original number of buckets was enough:
        assert n_buckets_start == n_buckets_end
        # check with clean table (not too much preallocated)
        clean_table = table_type()
        clean_table.map_locations(keys)
        assert n_buckets_start == clean_table.get_state()["n_buckets"]


class TestHashTableUnsorted:
    # TODO: moved from test_algos; may be redundancies with other tests
    def test_string_hashtable_set_item_signature(self):
        # GH#30419 fix typing in StringHashTable.set_item to prevent segfault
        tbl = ht.StringHashTable()

        tbl.set_item("key", 1)
        assert tbl.get_item("key") == 1

        with pytest.raises(TypeError, match="'key' has incorrect type"):
            # key arg typed as string, not object
            tbl.set_item(4, 6)
        with pytest.raises(TypeError, match="'val' has incorrect type"):
            tbl.get_item(4)

    def test_lookup_nan(self, writable):
        # GH#21688 ensure we can deal with readonly memory views
        xs = np.array([2.718, 3.14, np.nan, -7, 5, 2, 3])
        xs.setflags(write=writable)
        m = ht.Float64HashTable()
        m.map_locations(xs)
        tm.assert_numpy_array_equal(m.lookup(xs), np.arange(len(xs), dtype=np.intp))

    def test_add_signed_zeros(self):
        # GH#21866 inconsistent hash-function for float64
        # default hash-function would lead to different hash-buckets
        # for 0.0 and -0.0 if there are more than 2^30 hash-buckets
        # but this would mean 16GB
        N = 4  # 12 * 10**8 would trigger the error, if you have enough memory
        m = ht.Float64HashTable(N)
        m.set_item(0.0, 0)
        m.set_item(-0.0, 0)
        assert len(m) == 1  # 0.0 and -0.0 are equivalent

    def test_add_different_nans(self):
        # GH#21866 inconsistent hash-function for float64
        # create different nans from bit-patterns:
        NAN1 = struct.unpack("d", struct.pack("=Q", 0x7FF8000000000000))[0]
        NAN2 = struct.unpack("d", struct.pack("=Q", 0x7FF8000000000001))[0]
        assert NAN1 != NAN1
        assert NAN2 != NAN2
        # default hash function would lead to different hash-buckets
        # for NAN1 and NAN2 even if there are only 4 buckets:
        m = ht.Float64HashTable()
        m.set_item(NAN1, 0)
        m.set_item(NAN2, 0)
        assert len(m) == 1  # NAN1 and NAN2 are equivalent

    def test_lookup_overflow(self, writable):
        xs = np.array([1, 2, 2**63], dtype=np.uint64)
        # GH 21688 ensure we can deal with readonly memory views
        xs.setflags(write=writable)
        m = ht.UInt64HashTable()
        m.map_locations(xs)
        tm.assert_numpy_array_equal(m.lookup(xs), np.arange(len(xs), dtype=np.intp))

    @pytest.mark.parametrize("nvals", [0, 10])  # resizing to 0 is special case
    @pytest.mark.parametrize(
        "htable, uniques, dtype, safely_resizes",
        [
            (ht.PyObjectHashTable, ht.ObjectVector, "object", False),
            (ht.StringHashTable, ht.ObjectVector, "object", True),
            (ht.Float64HashTable, ht.Float64Vector, "float64", False),
            (ht.Int64HashTable, ht.Int64Vector, "int64", False),
            (ht.Int32HashTable, ht.Int32Vector, "int32", False),
            (ht.UInt64HashTable, ht.UInt64Vector, "uint64", False),
        ],
    )
    def test_vector_resize(
        self, writable, htable, uniques, dtype, safely_resizes, nvals
    ):
        # Test for memory errors after internal vector
        # reallocations (GH 7157)
        # Changed from using np.random.default_rng(2).rand to range
        # which could cause flaky CI failures when safely_resizes=False
        vals = np.array(range(1000), dtype=dtype)

        # GH 21688 ensures we can deal with read-only memory views
        vals.setflags(write=writable)

        # initialise instances; cannot initialise in parametrization,
        # as otherwise external views would be held on the array (which is
        # one of the things this test is checking)
        htable = htable()
        uniques = uniques()

        # get_labels may append to uniques
        htable.get_labels(vals[:nvals], uniques, 0, -1)
        # to_array() sets an external_view_exists flag on uniques.
        tmp = uniques.to_array()
        oldshape = tmp.shape

        # subsequent get_labels() calls can no longer append to it
        # (except for StringHashTables + ObjectVector)
        if safely_resizes:
            htable.get_labels(vals, uniques, 0, -1)
        else:
            with pytest.raises(ValueError, match="external reference.*"):
                htable.get_labels(vals, uniques, 0, -1)

        uniques.to_array()  # should not raise here
        assert tmp.shape == oldshape

    @pytest.mark.parametrize(
        "hashtable",
        [
            ht.PyObjectHashTable,
            ht.StringHashTable,
            ht.Float64HashTable,
            ht.Int64HashTable,
            ht.Int32HashTable,
            ht.UInt64HashTable,
        ],
    )
    def test_hashtable_large_sizehint(self, hashtable):
        # GH#22729 smoketest for not raising when passing a large size_hint
        size_hint = np.iinfo(np.uint32).max + 1
        hashtable(size_hint=size_hint)


class TestPyObjectHashTableWithNans:
    def test_nan_float(self):
        nan1 = float("nan")
        nan2 = float("nan")
        assert nan1 is not nan2
        table = ht.PyObjectHashTable()
        table.set_item(nan1, 42)
        assert table.get_item(nan2) == 42

    def test_nan_complex_both(self):
        nan1 = complex(float("nan"), float("nan"))
        nan2 = complex(float("nan"), float("nan"))
        assert nan1 is not nan2
        table = ht.PyObjectHashTable()
        table.set_item(nan1, 42)
        assert table.get_item(nan2) == 42

    def test_nan_complex_real(self):
        nan1 = complex(float("nan"), 1)
        nan2 = complex(float("nan"), 1)
        other = complex(float("nan"), 2)
        assert nan1 is not nan2
        table = ht.PyObjectHashTable()
        table.set_item(nan1, 42)
        assert table.get_item(nan2) == 42
        with pytest.raises(KeyError, match=None) as error:
            table.get_item(other)
        assert str(error.value) == str(other)

    def test_nan_complex_imag(self):
        nan1 = complex(1, float("nan"))
        nan2 = complex(1, float("nan"))
        other = complex(2, float("nan"))
        assert nan1 is not nan2
        table = ht.PyObjectHashTable()
        table.set_item(nan1, 42)
        assert table.get_item(nan2) == 42
        with pytest.raises(KeyError, match=None) as error:
            table.get_item(other)
        assert str(error.value) == str(other)

    def test_nan_in_tuple(self):
        nan1 = (float("nan"),)
        nan2 = (float("nan"),)
        assert nan1[0] is not nan2[0]
        table = ht.PyObjectHashTable()
        table.set_item(nan1, 42)
        assert table.get_item(nan2) == 42

    def test_nan_in_nested_tuple(self):
        nan1 = (1, (2, (float("nan"),)))
        nan2 = (1, (2, (float("nan"),)))
        other = (1, 2)
        table = ht.PyObjectHashTable()
        table.set_item(nan1, 42)
        assert table.get_item(nan2) == 42
        with pytest.raises(KeyError, match=None) as error:
            table.get_item(other)
        assert str(error.value) == str(other)


def test_hash_equal_tuple_with_nans():
    a = (float("nan"), (float("nan"), float("nan")))
    b = (float("nan"), (float("nan"), float("nan")))
    assert ht.object_hash(a) == ht.object_hash(b)
    assert ht.objects_are_equal(a, b)


def test_get_labels_groupby_for_Int64(writable):
    table = ht.Int64HashTable()
    vals = np.array([1, 2, -1, 2, 1, -1], dtype=np.int64)
    vals.flags.writeable = writable
    arr, unique = table.get_labels_groupby(vals)
    expected_arr = np.array([0, 1, -1, 1, 0, -1], dtype=np.intp)
    expected_unique = np.array([1, 2], dtype=np.int64)
    tm.assert_numpy_array_equal(arr, expected_arr)
    tm.assert_numpy_array_equal(unique, expected_unique)


def test_tracemalloc_works_for_StringHashTable():
    N = 1000
    keys = np.arange(N).astype(np.str_).astype(np.object_)
    with activated_tracemalloc():
        table = ht.StringHashTable()
        table.map_locations(keys)
        used = get_allocated_khash_memory()
        my_size = table.sizeof()
        assert used == my_size
        del table
        assert get_allocated_khash_memory() == 0


def test_tracemalloc_for_empty_StringHashTable():
    with activated_tracemalloc():
        table = ht.StringHashTable()
        used = get_allocated_khash_memory()
        my_size = table.sizeof()
        assert used == my_size
        del table
        assert get_allocated_khash_memory() == 0


@pytest.mark.parametrize("N", range(1, 110))
def test_no_reallocation_StringHashTable(N):
    keys = np.arange(N).astype(np.str_).astype(np.object_)
    preallocated_table = ht.StringHashTable(N)
    n_buckets_start = preallocated_table.get_state()["n_buckets"]
    preallocated_table.map_locations(keys)
    n_buckets_end = preallocated_table.get_state()["n_buckets"]
    # original number of buckets was enough:
    assert n_buckets_start == n_buckets_end
    # check with clean table (not too much preallocated)
    clean_table = ht.StringHashTable()
    clean_table.map_locations(keys)
    assert n_buckets_start == clean_table.get_state()["n_buckets"]


@pytest.mark.parametrize(
    "table_type, dtype",
    [
        (ht.Float64HashTable, np.float64),
        (ht.Float32HashTable, np.float32),
        (ht.Complex128HashTable, np.complex128),
        (ht.Complex64HashTable, np.complex64),
    ],
)
class TestHashTableWithNans:
    def test_get_set_contains_len(self, table_type, dtype):
        index = float("nan")
        table = table_type()
        assert index not in table

        table.set_item(index, 42)
        assert len(table) == 1
        assert index in table
        assert table.get_item(index) == 42

        table.set_item(index, 41)
        assert len(table) == 1
        assert index in table
        assert table.get_item(index) == 41

    def test_map_locations(self, table_type, dtype):
        N = 10
        table = table_type()
        keys = np.full(N, np.nan, dtype=dtype)
        table.map_locations(keys)
        assert len(table) == 1
        assert table.get_item(np.nan) == N - 1

    def test_unique(self, table_type, dtype):
        N = 1020
        table = table_type()
        keys = np.full(N, np.nan, dtype=dtype)
        unique = table.unique(keys)
        assert np.all(np.isnan(unique)) and len(unique) == 1


def test_unique_for_nan_objects_floats():
    table = ht.PyObjectHashTable()
    keys = np.array([float("nan") for i in range(50)], dtype=np.object_)
    unique = table.unique(keys)
    assert len(unique) == 1


def test_unique_for_nan_objects_complex():
    table = ht.PyObjectHashTable()
    keys = np.array([complex(float("nan"), 1.0) for i in range(50)], dtype=np.object_)
    unique = table.unique(keys)
    assert len(unique) == 1


def test_unique_for_nan_objects_tuple():
    table = ht.PyObjectHashTable()
    keys = np.array(
        [1] + [(1.0, (float("nan"), 1.0)) for i in range(50)], dtype=np.object_
    )
    unique = table.unique(keys)
    assert len(unique) == 2


@pytest.mark.parametrize(
    "dtype",
    [
        np.object_,
        np.complex128,
        np.int64,
        np.uint64,
        np.float64,
        np.complex64,
        np.int32,
        np.uint32,
        np.float32,
        np.int16,
        np.uint16,
        np.int8,
        np.uint8,
        np.intp,
    ],
)
class TestHelpFunctions:
    def test_value_count(self, dtype, writable):
        N = 43
        expected = (np.arange(N) + N).astype(dtype)
        values = np.repeat(expected, 5)
        values.flags.writeable = writable
        keys, counts, _ = ht.value_count(values, False)
        tm.assert_numpy_array_equal(np.sort(keys), expected)
        assert np.all(counts == 5)

    def test_value_count_mask(self, dtype):
        if dtype == np.object_:
            pytest.skip("mask not implemented for object dtype")
        values = np.array([1] * 5, dtype=dtype)
        mask = np.zeros((5,), dtype=np.bool_)
        mask[1] = True
        mask[4] = True
        keys, counts, na_counter = ht.value_count(values, False, mask=mask)
        assert len(keys) == 2
        assert na_counter == 2

    def test_value_count_stable(self, dtype, writable):
        # GH12679
        values = np.array([2, 1, 5, 22, 3, -1, 8]).astype(dtype)
        values.flags.writeable = writable
        keys, counts, _ = ht.value_count(values, False)
        tm.assert_numpy_array_equal(keys, values)
        assert np.all(counts == 1)

    def test_duplicated_first(self, dtype, writable):
        N = 100
        values = np.repeat(np.arange(N).astype(dtype), 5)
        values.flags.writeable = writable
        result = ht.duplicated(values)
        expected = np.ones_like(values, dtype=np.bool_)
        expected[::5] = False
        tm.assert_numpy_array_equal(result, expected)

    def test_ismember_yes(self, dtype, writable):
        N = 127
        arr = np.arange(N).astype(dtype)
        values = np.arange(N).astype(dtype)
        arr.flags.writeable = writable
        values.flags.writeable = writable
        result = ht.ismember(arr, values)
        expected = np.ones_like(values, dtype=np.bool_)
        tm.assert_numpy_array_equal(result, expected)

    def test_ismember_no(self, dtype):
        N = 17
        arr = np.arange(N).astype(dtype)
        values = (np.arange(N) + N).astype(dtype)
        result = ht.ismember(arr, values)
        expected = np.zeros_like(values, dtype=np.bool_)
        tm.assert_numpy_array_equal(result, expected)

    def test_mode(self, dtype, writable):
        if dtype in (np.int8, np.uint8):
            N = 53
        else:
            N = 11111
        values = np.repeat(np.arange(N).astype(dtype), 5)
        values[0] = 42
        values.flags.writeable = writable
        result = ht.mode(values, False)[0]
        assert result == 42

    def test_mode_stable(self, dtype, writable):
        values = np.array([2, 1, 5, 22, 3, -1, 8]).astype(dtype)
        values.flags.writeable = writable
        keys = ht.mode(values, False)[0]
        tm.assert_numpy_array_equal(keys, values)


def test_modes_with_nans():
    # GH42688, nans aren't mangled
    nulls = [pd.NA, np.nan, pd.NaT, None]
    values = np.array([True] + nulls * 2, dtype=np.object_)
    modes = ht.mode(values, False)[0]
    assert modes.size == len(nulls)


def test_unique_label_indices_intp(writable):
    keys = np.array([1, 2, 2, 2, 1, 3], dtype=np.intp)
    keys.flags.writeable = writable
    result = ht.unique_label_indices(keys)
    expected = np.array([0, 1, 5], dtype=np.intp)
    tm.assert_numpy_array_equal(result, expected)


def test_unique_label_indices():
    a = np.random.default_rng(2).integers(1, 1 << 10, 1 << 15).astype(np.intp)

    left = ht.unique_label_indices(a)
    right = np.unique(a, return_index=True)[1]

    tm.assert_numpy_array_equal(left, right, check_dtype=False)

    a[np.random.default_rng(2).choice(len(a), 10)] = -1
    left = ht.unique_label_indices(a)
    right = np.unique(a, return_index=True)[1][1:]
    tm.assert_numpy_array_equal(left, right, check_dtype=False)


@pytest.mark.parametrize(
    "dtype",
    [
        np.float64,
        np.float32,
        np.complex128,
        np.complex64,
    ],
)
class TestHelpFunctionsWithNans:
    def test_value_count(self, dtype):
        values = np.array([np.nan, np.nan, np.nan], dtype=dtype)
        keys, counts, _ = ht.value_count(values, True)
        assert len(keys) == 0
        keys, counts, _ = ht.value_count(values, False)
        assert len(keys) == 1 and np.all(np.isnan(keys))
        assert counts[0] == 3

    def test_duplicated_first(self, dtype):
        values = np.array([np.nan, np.nan, np.nan], dtype=dtype)
        result = ht.duplicated(values)
        expected = np.array([False, True, True])
        tm.assert_numpy_array_equal(result, expected)

    def test_ismember_yes(self, dtype):
        arr = np.array([np.nan, np.nan, np.nan], dtype=dtype)
        values = np.array([np.nan, np.nan], dtype=dtype)
        result = ht.ismember(arr, values)
        expected = np.array([True, True, True], dtype=np.bool_)
        tm.assert_numpy_array_equal(result, expected)

    def test_ismember_no(self, dtype):
        arr = np.array([np.nan, np.nan, np.nan], dtype=dtype)
        values = np.array([1], dtype=dtype)
        result = ht.ismember(arr, values)
        expected = np.array([False, False, False], dtype=np.bool_)
        tm.assert_numpy_array_equal(result, expected)

    def test_mode(self, dtype):
        values = np.array([42, np.nan, np.nan, np.nan], dtype=dtype)
        assert ht.mode(values, True)[0] == 42
        assert np.isnan(ht.mode(values, False)[0])


def test_ismember_tuple_with_nans():
    # GH-41836
    values = [("a", float("nan")), ("b", 1)]
    comps = [("a", float("nan"))]

    msg = "isin with argument that is not not a Series"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = isin(values, comps)
    expected = np.array([True, False], dtype=np.bool_)
    tm.assert_numpy_array_equal(result, expected)


def test_float_complex_int_are_equal_as_objects():
    values = ["a", 5, 5.0, 5.0 + 0j]
    comps = list(range(129))
    result = isin(np.array(values, dtype=object), np.asarray(comps))
    expected = np.array([False, True, True, True], dtype=np.bool_)
    tm.assert_numpy_array_equal(result, expected)
