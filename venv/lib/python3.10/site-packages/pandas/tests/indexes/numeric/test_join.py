import numpy as np
import pytest

import pandas._testing as tm
from pandas.core.indexes.api import Index


class TestJoinInt64Index:
    def test_join_non_unique(self):
        left = Index([4, 4, 3, 3])

        joined, lidx, ridx = left.join(left, return_indexers=True)

        exp_joined = Index([4, 4, 4, 4, 3, 3, 3, 3])
        tm.assert_index_equal(joined, exp_joined)

        exp_lidx = np.array([0, 0, 1, 1, 2, 2, 3, 3], dtype=np.intp)
        tm.assert_numpy_array_equal(lidx, exp_lidx)

        exp_ridx = np.array([0, 1, 0, 1, 2, 3, 2, 3], dtype=np.intp)
        tm.assert_numpy_array_equal(ridx, exp_ridx)

    def test_join_inner(self):
        index = Index(range(0, 20, 2), dtype=np.int64)
        other = Index([7, 12, 25, 1, 2, 5], dtype=np.int64)
        other_mono = Index([1, 2, 5, 7, 12, 25], dtype=np.int64)

        # not monotonic
        res, lidx, ridx = index.join(other, how="inner", return_indexers=True)

        # no guarantee of sortedness, so sort for comparison purposes
        ind = res.argsort()
        res = res.take(ind)
        lidx = lidx.take(ind)
        ridx = ridx.take(ind)

        eres = Index([2, 12], dtype=np.int64)
        elidx = np.array([1, 6], dtype=np.intp)
        eridx = np.array([4, 1], dtype=np.intp)

        assert isinstance(res, Index) and res.dtype == np.int64
        tm.assert_index_equal(res, eres)
        tm.assert_numpy_array_equal(lidx, elidx)
        tm.assert_numpy_array_equal(ridx, eridx)

        # monotonic
        res, lidx, ridx = index.join(other_mono, how="inner", return_indexers=True)

        res2 = index.intersection(other_mono)
        tm.assert_index_equal(res, res2)

        elidx = np.array([1, 6], dtype=np.intp)
        eridx = np.array([1, 4], dtype=np.intp)
        assert isinstance(res, Index) and res.dtype == np.int64
        tm.assert_index_equal(res, eres)
        tm.assert_numpy_array_equal(lidx, elidx)
        tm.assert_numpy_array_equal(ridx, eridx)

    def test_join_left(self):
        index = Index(range(0, 20, 2), dtype=np.int64)
        other = Index([7, 12, 25, 1, 2, 5], dtype=np.int64)
        other_mono = Index([1, 2, 5, 7, 12, 25], dtype=np.int64)

        # not monotonic
        res, lidx, ridx = index.join(other, how="left", return_indexers=True)
        eres = index
        eridx = np.array([-1, 4, -1, -1, -1, -1, 1, -1, -1, -1], dtype=np.intp)

        assert isinstance(res, Index) and res.dtype == np.int64
        tm.assert_index_equal(res, eres)
        assert lidx is None
        tm.assert_numpy_array_equal(ridx, eridx)

        # monotonic
        res, lidx, ridx = index.join(other_mono, how="left", return_indexers=True)
        eridx = np.array([-1, 1, -1, -1, -1, -1, 4, -1, -1, -1], dtype=np.intp)
        assert isinstance(res, Index) and res.dtype == np.int64
        tm.assert_index_equal(res, eres)
        assert lidx is None
        tm.assert_numpy_array_equal(ridx, eridx)

        # non-unique
        idx = Index([1, 1, 2, 5])
        idx2 = Index([1, 2, 5, 7, 9])
        res, lidx, ridx = idx2.join(idx, how="left", return_indexers=True)
        eres = Index([1, 1, 2, 5, 7, 9])  # 1 is in idx2, so it should be x2
        eridx = np.array([0, 1, 2, 3, -1, -1], dtype=np.intp)
        elidx = np.array([0, 0, 1, 2, 3, 4], dtype=np.intp)
        tm.assert_index_equal(res, eres)
        tm.assert_numpy_array_equal(lidx, elidx)
        tm.assert_numpy_array_equal(ridx, eridx)

    def test_join_right(self):
        index = Index(range(0, 20, 2), dtype=np.int64)
        other = Index([7, 12, 25, 1, 2, 5], dtype=np.int64)
        other_mono = Index([1, 2, 5, 7, 12, 25], dtype=np.int64)

        # not monotonic
        res, lidx, ridx = index.join(other, how="right", return_indexers=True)
        eres = other
        elidx = np.array([-1, 6, -1, -1, 1, -1], dtype=np.intp)

        assert isinstance(other, Index) and other.dtype == np.int64
        tm.assert_index_equal(res, eres)
        tm.assert_numpy_array_equal(lidx, elidx)
        assert ridx is None

        # monotonic
        res, lidx, ridx = index.join(other_mono, how="right", return_indexers=True)
        eres = other_mono
        elidx = np.array([-1, 1, -1, -1, 6, -1], dtype=np.intp)
        assert isinstance(other, Index) and other.dtype == np.int64
        tm.assert_index_equal(res, eres)
        tm.assert_numpy_array_equal(lidx, elidx)
        assert ridx is None

        # non-unique
        idx = Index([1, 1, 2, 5])
        idx2 = Index([1, 2, 5, 7, 9])
        res, lidx, ridx = idx.join(idx2, how="right", return_indexers=True)
        eres = Index([1, 1, 2, 5, 7, 9])  # 1 is in idx2, so it should be x2
        elidx = np.array([0, 1, 2, 3, -1, -1], dtype=np.intp)
        eridx = np.array([0, 0, 1, 2, 3, 4], dtype=np.intp)
        tm.assert_index_equal(res, eres)
        tm.assert_numpy_array_equal(lidx, elidx)
        tm.assert_numpy_array_equal(ridx, eridx)

    def test_join_non_int_index(self):
        index = Index(range(0, 20, 2), dtype=np.int64)
        other = Index([3, 6, 7, 8, 10], dtype=object)

        outer = index.join(other, how="outer")
        outer2 = other.join(index, how="outer")
        expected = Index([0, 2, 3, 4, 6, 7, 8, 10, 12, 14, 16, 18])
        tm.assert_index_equal(outer, outer2)
        tm.assert_index_equal(outer, expected)

        inner = index.join(other, how="inner")
        inner2 = other.join(index, how="inner")
        expected = Index([6, 8, 10])
        tm.assert_index_equal(inner, inner2)
        tm.assert_index_equal(inner, expected)

        left = index.join(other, how="left")
        tm.assert_index_equal(left, index.astype(object))

        left2 = other.join(index, how="left")
        tm.assert_index_equal(left2, other)

        right = index.join(other, how="right")
        tm.assert_index_equal(right, other)

        right2 = other.join(index, how="right")
        tm.assert_index_equal(right2, index.astype(object))

    def test_join_outer(self):
        index = Index(range(0, 20, 2), dtype=np.int64)
        other = Index([7, 12, 25, 1, 2, 5], dtype=np.int64)
        other_mono = Index([1, 2, 5, 7, 12, 25], dtype=np.int64)

        # not monotonic
        # guarantee of sortedness
        res, lidx, ridx = index.join(other, how="outer", return_indexers=True)
        noidx_res = index.join(other, how="outer")
        tm.assert_index_equal(res, noidx_res)

        eres = Index([0, 1, 2, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 25], dtype=np.int64)
        elidx = np.array([0, -1, 1, 2, -1, 3, -1, 4, 5, 6, 7, 8, 9, -1], dtype=np.intp)
        eridx = np.array(
            [-1, 3, 4, -1, 5, -1, 0, -1, -1, 1, -1, -1, -1, 2], dtype=np.intp
        )

        assert isinstance(res, Index) and res.dtype == np.int64
        tm.assert_index_equal(res, eres)
        tm.assert_numpy_array_equal(lidx, elidx)
        tm.assert_numpy_array_equal(ridx, eridx)

        # monotonic
        res, lidx, ridx = index.join(other_mono, how="outer", return_indexers=True)
        noidx_res = index.join(other_mono, how="outer")
        tm.assert_index_equal(res, noidx_res)

        elidx = np.array([0, -1, 1, 2, -1, 3, -1, 4, 5, 6, 7, 8, 9, -1], dtype=np.intp)
        eridx = np.array(
            [-1, 0, 1, -1, 2, -1, 3, -1, -1, 4, -1, -1, -1, 5], dtype=np.intp
        )
        assert isinstance(res, Index) and res.dtype == np.int64
        tm.assert_index_equal(res, eres)
        tm.assert_numpy_array_equal(lidx, elidx)
        tm.assert_numpy_array_equal(ridx, eridx)


class TestJoinUInt64Index:
    @pytest.fixture
    def index_large(self):
        # large values used in TestUInt64Index where no compat needed with int64/float64
        large = [2**63, 2**63 + 10, 2**63 + 15, 2**63 + 20, 2**63 + 25]
        return Index(large, dtype=np.uint64)

    def test_join_inner(self, index_large):
        other = Index(2**63 + np.array([7, 12, 25, 1, 2, 10], dtype="uint64"))
        other_mono = Index(2**63 + np.array([1, 2, 7, 10, 12, 25], dtype="uint64"))

        # not monotonic
        res, lidx, ridx = index_large.join(other, how="inner", return_indexers=True)

        # no guarantee of sortedness, so sort for comparison purposes
        ind = res.argsort()
        res = res.take(ind)
        lidx = lidx.take(ind)
        ridx = ridx.take(ind)

        eres = Index(2**63 + np.array([10, 25], dtype="uint64"))
        elidx = np.array([1, 4], dtype=np.intp)
        eridx = np.array([5, 2], dtype=np.intp)

        assert isinstance(res, Index) and res.dtype == np.uint64
        tm.assert_index_equal(res, eres)
        tm.assert_numpy_array_equal(lidx, elidx)
        tm.assert_numpy_array_equal(ridx, eridx)

        # monotonic
        res, lidx, ridx = index_large.join(
            other_mono, how="inner", return_indexers=True
        )

        res2 = index_large.intersection(other_mono)
        tm.assert_index_equal(res, res2)

        elidx = np.array([1, 4], dtype=np.intp)
        eridx = np.array([3, 5], dtype=np.intp)

        assert isinstance(res, Index) and res.dtype == np.uint64
        tm.assert_index_equal(res, eres)
        tm.assert_numpy_array_equal(lidx, elidx)
        tm.assert_numpy_array_equal(ridx, eridx)

    def test_join_left(self, index_large):
        other = Index(2**63 + np.array([7, 12, 25, 1, 2, 10], dtype="uint64"))
        other_mono = Index(2**63 + np.array([1, 2, 7, 10, 12, 25], dtype="uint64"))

        # not monotonic
        res, lidx, ridx = index_large.join(other, how="left", return_indexers=True)
        eres = index_large
        eridx = np.array([-1, 5, -1, -1, 2], dtype=np.intp)

        assert isinstance(res, Index) and res.dtype == np.uint64
        tm.assert_index_equal(res, eres)
        assert lidx is None
        tm.assert_numpy_array_equal(ridx, eridx)

        # monotonic
        res, lidx, ridx = index_large.join(other_mono, how="left", return_indexers=True)
        eridx = np.array([-1, 3, -1, -1, 5], dtype=np.intp)

        assert isinstance(res, Index) and res.dtype == np.uint64
        tm.assert_index_equal(res, eres)
        assert lidx is None
        tm.assert_numpy_array_equal(ridx, eridx)

        # non-unique
        idx = Index(2**63 + np.array([1, 1, 2, 5], dtype="uint64"))
        idx2 = Index(2**63 + np.array([1, 2, 5, 7, 9], dtype="uint64"))
        res, lidx, ridx = idx2.join(idx, how="left", return_indexers=True)

        # 1 is in idx2, so it should be x2
        eres = Index(2**63 + np.array([1, 1, 2, 5, 7, 9], dtype="uint64"))
        eridx = np.array([0, 1, 2, 3, -1, -1], dtype=np.intp)
        elidx = np.array([0, 0, 1, 2, 3, 4], dtype=np.intp)

        tm.assert_index_equal(res, eres)
        tm.assert_numpy_array_equal(lidx, elidx)
        tm.assert_numpy_array_equal(ridx, eridx)

    def test_join_right(self, index_large):
        other = Index(2**63 + np.array([7, 12, 25, 1, 2, 10], dtype="uint64"))
        other_mono = Index(2**63 + np.array([1, 2, 7, 10, 12, 25], dtype="uint64"))

        # not monotonic
        res, lidx, ridx = index_large.join(other, how="right", return_indexers=True)
        eres = other
        elidx = np.array([-1, -1, 4, -1, -1, 1], dtype=np.intp)

        tm.assert_numpy_array_equal(lidx, elidx)
        assert isinstance(other, Index) and other.dtype == np.uint64
        tm.assert_index_equal(res, eres)
        assert ridx is None

        # monotonic
        res, lidx, ridx = index_large.join(
            other_mono, how="right", return_indexers=True
        )
        eres = other_mono
        elidx = np.array([-1, -1, -1, 1, -1, 4], dtype=np.intp)

        assert isinstance(other, Index) and other.dtype == np.uint64
        tm.assert_numpy_array_equal(lidx, elidx)
        tm.assert_index_equal(res, eres)
        assert ridx is None

        # non-unique
        idx = Index(2**63 + np.array([1, 1, 2, 5], dtype="uint64"))
        idx2 = Index(2**63 + np.array([1, 2, 5, 7, 9], dtype="uint64"))
        res, lidx, ridx = idx.join(idx2, how="right", return_indexers=True)

        # 1 is in idx2, so it should be x2
        eres = Index(2**63 + np.array([1, 1, 2, 5, 7, 9], dtype="uint64"))
        elidx = np.array([0, 1, 2, 3, -1, -1], dtype=np.intp)
        eridx = np.array([0, 0, 1, 2, 3, 4], dtype=np.intp)

        tm.assert_index_equal(res, eres)
        tm.assert_numpy_array_equal(lidx, elidx)
        tm.assert_numpy_array_equal(ridx, eridx)

    def test_join_non_int_index(self, index_large):
        other = Index(
            2**63 + np.array([1, 5, 7, 10, 20], dtype="uint64"), dtype=object
        )

        outer = index_large.join(other, how="outer")
        outer2 = other.join(index_large, how="outer")
        expected = Index(
            2**63 + np.array([0, 1, 5, 7, 10, 15, 20, 25], dtype="uint64")
        )
        tm.assert_index_equal(outer, outer2)
        tm.assert_index_equal(outer, expected)

        inner = index_large.join(other, how="inner")
        inner2 = other.join(index_large, how="inner")
        expected = Index(2**63 + np.array([10, 20], dtype="uint64"))
        tm.assert_index_equal(inner, inner2)
        tm.assert_index_equal(inner, expected)

        left = index_large.join(other, how="left")
        tm.assert_index_equal(left, index_large.astype(object))

        left2 = other.join(index_large, how="left")
        tm.assert_index_equal(left2, other)

        right = index_large.join(other, how="right")
        tm.assert_index_equal(right, other)

        right2 = other.join(index_large, how="right")
        tm.assert_index_equal(right2, index_large.astype(object))

    def test_join_outer(self, index_large):
        other = Index(2**63 + np.array([7, 12, 25, 1, 2, 10], dtype="uint64"))
        other_mono = Index(2**63 + np.array([1, 2, 7, 10, 12, 25], dtype="uint64"))

        # not monotonic
        # guarantee of sortedness
        res, lidx, ridx = index_large.join(other, how="outer", return_indexers=True)
        noidx_res = index_large.join(other, how="outer")
        tm.assert_index_equal(res, noidx_res)

        eres = Index(
            2**63 + np.array([0, 1, 2, 7, 10, 12, 15, 20, 25], dtype="uint64")
        )
        elidx = np.array([0, -1, -1, -1, 1, -1, 2, 3, 4], dtype=np.intp)
        eridx = np.array([-1, 3, 4, 0, 5, 1, -1, -1, 2], dtype=np.intp)

        assert isinstance(res, Index) and res.dtype == np.uint64
        tm.assert_index_equal(res, eres)
        tm.assert_numpy_array_equal(lidx, elidx)
        tm.assert_numpy_array_equal(ridx, eridx)

        # monotonic
        res, lidx, ridx = index_large.join(
            other_mono, how="outer", return_indexers=True
        )
        noidx_res = index_large.join(other_mono, how="outer")
        tm.assert_index_equal(res, noidx_res)

        elidx = np.array([0, -1, -1, -1, 1, -1, 2, 3, 4], dtype=np.intp)
        eridx = np.array([-1, 0, 1, 2, 3, 4, -1, -1, 5], dtype=np.intp)

        assert isinstance(res, Index) and res.dtype == np.uint64
        tm.assert_index_equal(res, eres)
        tm.assert_numpy_array_equal(lidx, elidx)
        tm.assert_numpy_array_equal(ridx, eridx)
