from itertools import permutations

import numpy as np
import pytest

from pandas._libs.interval import IntervalTree
from pandas.compat import IS64

import pandas._testing as tm


def skipif_32bit(param):
    """
    Skip parameters in a parametrize on 32bit systems. Specifically used
    here to skip leaf_size parameters related to GH 23440.
    """
    marks = pytest.mark.skipif(not IS64, reason="GH 23440: int type mismatch on 32bit")
    return pytest.param(param, marks=marks)


@pytest.fixture(params=["int64", "float64", "uint64"])
def dtype(request):
    return request.param


@pytest.fixture(params=[skipif_32bit(1), skipif_32bit(2), 10])
def leaf_size(request):
    """
    Fixture to specify IntervalTree leaf_size parameter; to be used with the
    tree fixture.
    """
    return request.param


@pytest.fixture(
    params=[
        np.arange(5, dtype="int64"),
        np.arange(5, dtype="uint64"),
        np.arange(5, dtype="float64"),
        np.array([0, 1, 2, 3, 4, np.nan], dtype="float64"),
    ]
)
def tree(request, leaf_size):
    left = request.param
    return IntervalTree(left, left + 2, leaf_size=leaf_size)


class TestIntervalTree:
    def test_get_indexer(self, tree):
        result = tree.get_indexer(np.array([1.0, 5.5, 6.5]))
        expected = np.array([0, 4, -1], dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

        with pytest.raises(
            KeyError, match="'indexer does not intersect a unique set of intervals'"
        ):
            tree.get_indexer(np.array([3.0]))

    @pytest.mark.parametrize(
        "dtype, target_value, target_dtype",
        [("int64", 2**63 + 1, "uint64"), ("uint64", -1, "int64")],
    )
    def test_get_indexer_overflow(self, dtype, target_value, target_dtype):
        left, right = np.array([0, 1], dtype=dtype), np.array([1, 2], dtype=dtype)
        tree = IntervalTree(left, right)

        result = tree.get_indexer(np.array([target_value], dtype=target_dtype))
        expected = np.array([-1], dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

    def test_get_indexer_non_unique(self, tree):
        indexer, missing = tree.get_indexer_non_unique(np.array([1.0, 2.0, 6.5]))

        result = indexer[:1]
        expected = np.array([0], dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

        result = np.sort(indexer[1:3])
        expected = np.array([0, 1], dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

        result = np.sort(indexer[3:])
        expected = np.array([-1], dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

        result = missing
        expected = np.array([2], dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize(
        "dtype, target_value, target_dtype",
        [("int64", 2**63 + 1, "uint64"), ("uint64", -1, "int64")],
    )
    def test_get_indexer_non_unique_overflow(self, dtype, target_value, target_dtype):
        left, right = np.array([0, 2], dtype=dtype), np.array([1, 3], dtype=dtype)
        tree = IntervalTree(left, right)
        target = np.array([target_value], dtype=target_dtype)

        result_indexer, result_missing = tree.get_indexer_non_unique(target)
        expected_indexer = np.array([-1], dtype="intp")
        tm.assert_numpy_array_equal(result_indexer, expected_indexer)

        expected_missing = np.array([0], dtype="intp")
        tm.assert_numpy_array_equal(result_missing, expected_missing)

    def test_duplicates(self, dtype):
        left = np.array([0, 0, 0], dtype=dtype)
        tree = IntervalTree(left, left + 1)

        with pytest.raises(
            KeyError, match="'indexer does not intersect a unique set of intervals'"
        ):
            tree.get_indexer(np.array([0.5]))

        indexer, missing = tree.get_indexer_non_unique(np.array([0.5]))
        result = np.sort(indexer)
        expected = np.array([0, 1, 2], dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

        result = missing
        expected = np.array([], dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize(
        "leaf_size", [skipif_32bit(1), skipif_32bit(10), skipif_32bit(100), 10000]
    )
    def test_get_indexer_closed(self, closed, leaf_size):
        x = np.arange(1000, dtype="float64")
        found = x.astype("intp")
        not_found = (-1 * np.ones(1000)).astype("intp")

        tree = IntervalTree(x, x + 0.5, closed=closed, leaf_size=leaf_size)
        tm.assert_numpy_array_equal(found, tree.get_indexer(x + 0.25))

        expected = found if tree.closed_left else not_found
        tm.assert_numpy_array_equal(expected, tree.get_indexer(x + 0.0))

        expected = found if tree.closed_right else not_found
        tm.assert_numpy_array_equal(expected, tree.get_indexer(x + 0.5))

    @pytest.mark.parametrize(
        "left, right, expected",
        [
            (np.array([0, 1, 4], dtype="int64"), np.array([2, 3, 5]), True),
            (np.array([0, 1, 2], dtype="int64"), np.array([5, 4, 3]), True),
            (np.array([0, 1, np.nan]), np.array([5, 4, np.nan]), True),
            (np.array([0, 2, 4], dtype="int64"), np.array([1, 3, 5]), False),
            (np.array([0, 2, np.nan]), np.array([1, 3, np.nan]), False),
        ],
    )
    @pytest.mark.parametrize("order", (list(x) for x in permutations(range(3))))
    def test_is_overlapping(self, closed, order, left, right, expected):
        # GH 23309
        tree = IntervalTree(left[order], right[order], closed=closed)
        result = tree.is_overlapping
        assert result is expected

    @pytest.mark.parametrize("order", (list(x) for x in permutations(range(3))))
    def test_is_overlapping_endpoints(self, closed, order):
        """shared endpoints are marked as overlapping"""
        # GH 23309
        left, right = np.arange(3, dtype="int64"), np.arange(1, 4)
        tree = IntervalTree(left[order], right[order], closed=closed)
        result = tree.is_overlapping
        expected = closed == "both"
        assert result is expected

    @pytest.mark.parametrize(
        "left, right",
        [
            (np.array([], dtype="int64"), np.array([], dtype="int64")),
            (np.array([0], dtype="int64"), np.array([1], dtype="int64")),
            (np.array([np.nan]), np.array([np.nan])),
            (np.array([np.nan] * 3), np.array([np.nan] * 3)),
        ],
    )
    def test_is_overlapping_trivial(self, closed, left, right):
        # GH 23309
        tree = IntervalTree(left, right, closed=closed)
        assert tree.is_overlapping is False

    @pytest.mark.skipif(not IS64, reason="GH 23440")
    def test_construction_overflow(self):
        # GH 25485
        left, right = np.arange(101, dtype="int64"), [np.iinfo(np.int64).max] * 101
        tree = IntervalTree(left, right)

        # pivot should be average of left/right medians
        result = tree.root.pivot
        expected = (50 + np.iinfo(np.int64).max) / 2
        assert result == expected

    @pytest.mark.parametrize(
        "left, right, expected",
        [
            ([-np.inf, 1.0], [1.0, 2.0], 0.0),
            ([-np.inf, -2.0], [-2.0, -1.0], -2.0),
            ([-2.0, -1.0], [-1.0, np.inf], 0.0),
            ([1.0, 2.0], [2.0, np.inf], 2.0),
        ],
    )
    def test_inf_bound_infinite_recursion(self, left, right, expected):
        # GH 46658

        tree = IntervalTree(left * 101, right * 101)

        result = tree.root.pivot
        assert result == expected
