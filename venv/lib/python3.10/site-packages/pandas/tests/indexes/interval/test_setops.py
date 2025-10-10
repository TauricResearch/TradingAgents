import numpy as np
import pytest

from pandas import (
    Index,
    IntervalIndex,
    Timestamp,
    interval_range,
)
import pandas._testing as tm


def monotonic_index(start, end, dtype="int64", closed="right"):
    return IntervalIndex.from_breaks(np.arange(start, end, dtype=dtype), closed=closed)


def empty_index(dtype="int64", closed="right"):
    return IntervalIndex(np.array([], dtype=dtype), closed=closed)


class TestIntervalIndex:
    def test_union(self, closed, sort):
        index = monotonic_index(0, 11, closed=closed)
        other = monotonic_index(5, 13, closed=closed)

        expected = monotonic_index(0, 13, closed=closed)
        result = index[::-1].union(other, sort=sort)
        if sort in (None, True):
            tm.assert_index_equal(result, expected)
        else:
            tm.assert_index_equal(result.sort_values(), expected)

        result = other[::-1].union(index, sort=sort)
        if sort in (None, True):
            tm.assert_index_equal(result, expected)
        else:
            tm.assert_index_equal(result.sort_values(), expected)

        tm.assert_index_equal(index.union(index, sort=sort), index)
        tm.assert_index_equal(index.union(index[:1], sort=sort), index)

    def test_union_empty_result(self, closed, sort):
        # GH 19101: empty result, same dtype
        index = empty_index(dtype="int64", closed=closed)
        result = index.union(index, sort=sort)
        tm.assert_index_equal(result, index)

        # GH 19101: empty result, different numeric dtypes -> common dtype is f8
        other = empty_index(dtype="float64", closed=closed)
        result = index.union(other, sort=sort)
        expected = other
        tm.assert_index_equal(result, expected)

        other = index.union(index, sort=sort)
        tm.assert_index_equal(result, expected)

        other = empty_index(dtype="uint64", closed=closed)
        result = index.union(other, sort=sort)
        tm.assert_index_equal(result, expected)

        result = other.union(index, sort=sort)
        tm.assert_index_equal(result, expected)

    def test_intersection(self, closed, sort):
        index = monotonic_index(0, 11, closed=closed)
        other = monotonic_index(5, 13, closed=closed)

        expected = monotonic_index(5, 11, closed=closed)
        result = index[::-1].intersection(other, sort=sort)
        if sort in (None, True):
            tm.assert_index_equal(result, expected)
        else:
            tm.assert_index_equal(result.sort_values(), expected)

        result = other[::-1].intersection(index, sort=sort)
        if sort in (None, True):
            tm.assert_index_equal(result, expected)
        else:
            tm.assert_index_equal(result.sort_values(), expected)

        tm.assert_index_equal(index.intersection(index, sort=sort), index)

        # GH 26225: nested intervals
        index = IntervalIndex.from_tuples([(1, 2), (1, 3), (1, 4), (0, 2)])
        other = IntervalIndex.from_tuples([(1, 2), (1, 3)])
        expected = IntervalIndex.from_tuples([(1, 2), (1, 3)])
        result = index.intersection(other)
        tm.assert_index_equal(result, expected)

        # GH 26225
        index = IntervalIndex.from_tuples([(0, 3), (0, 2)])
        other = IntervalIndex.from_tuples([(0, 2), (1, 3)])
        expected = IntervalIndex.from_tuples([(0, 2)])
        result = index.intersection(other)
        tm.assert_index_equal(result, expected)

        # GH 26225: duplicate nan element
        index = IntervalIndex([np.nan, np.nan])
        other = IntervalIndex([np.nan])
        expected = IntervalIndex([np.nan])
        result = index.intersection(other)
        tm.assert_index_equal(result, expected)

    def test_intersection_empty_result(self, closed, sort):
        index = monotonic_index(0, 11, closed=closed)

        # GH 19101: empty result, same dtype
        other = monotonic_index(300, 314, closed=closed)
        expected = empty_index(dtype="int64", closed=closed)
        result = index.intersection(other, sort=sort)
        tm.assert_index_equal(result, expected)

        # GH 19101: empty result, different numeric dtypes -> common dtype is float64
        other = monotonic_index(300, 314, dtype="float64", closed=closed)
        result = index.intersection(other, sort=sort)
        expected = other[:0]
        tm.assert_index_equal(result, expected)

        other = monotonic_index(300, 314, dtype="uint64", closed=closed)
        result = index.intersection(other, sort=sort)
        tm.assert_index_equal(result, expected)

    def test_intersection_duplicates(self):
        # GH#38743
        index = IntervalIndex.from_tuples([(1, 2), (1, 2), (2, 3), (3, 4)])
        other = IntervalIndex.from_tuples([(1, 2), (2, 3)])
        expected = IntervalIndex.from_tuples([(1, 2), (2, 3)])
        result = index.intersection(other)
        tm.assert_index_equal(result, expected)

    def test_difference(self, closed, sort):
        index = IntervalIndex.from_arrays([1, 0, 3, 2], [1, 2, 3, 4], closed=closed)
        result = index.difference(index[:1], sort=sort)
        expected = index[1:]
        if sort is None:
            expected = expected.sort_values()
        tm.assert_index_equal(result, expected)

        # GH 19101: empty result, same dtype
        result = index.difference(index, sort=sort)
        expected = empty_index(dtype="int64", closed=closed)
        tm.assert_index_equal(result, expected)

        # GH 19101: empty result, different dtypes
        other = IntervalIndex.from_arrays(
            index.left.astype("float64"), index.right, closed=closed
        )
        result = index.difference(other, sort=sort)
        tm.assert_index_equal(result, expected)

    def test_symmetric_difference(self, closed, sort):
        index = monotonic_index(0, 11, closed=closed)
        result = index[1:].symmetric_difference(index[:-1], sort=sort)
        expected = IntervalIndex([index[0], index[-1]])
        if sort in (None, True):
            tm.assert_index_equal(result, expected)
        else:
            tm.assert_index_equal(result.sort_values(), expected)

        # GH 19101: empty result, same dtype
        result = index.symmetric_difference(index, sort=sort)
        expected = empty_index(dtype="int64", closed=closed)
        if sort in (None, True):
            tm.assert_index_equal(result, expected)
        else:
            tm.assert_index_equal(result.sort_values(), expected)

        # GH 19101: empty result, different dtypes
        other = IntervalIndex.from_arrays(
            index.left.astype("float64"), index.right, closed=closed
        )
        result = index.symmetric_difference(other, sort=sort)
        expected = empty_index(dtype="float64", closed=closed)
        tm.assert_index_equal(result, expected)

    @pytest.mark.filterwarnings("ignore:'<' not supported between:RuntimeWarning")
    @pytest.mark.parametrize(
        "op_name", ["union", "intersection", "difference", "symmetric_difference"]
    )
    def test_set_incompatible_types(self, closed, op_name, sort):
        index = monotonic_index(0, 11, closed=closed)
        set_op = getattr(index, op_name)

        # TODO: standardize return type of non-union setops type(self vs other)
        # non-IntervalIndex
        if op_name == "difference":
            expected = index
        else:
            expected = getattr(index.astype("O"), op_name)(Index([1, 2, 3]))
        result = set_op(Index([1, 2, 3]), sort=sort)
        tm.assert_index_equal(result, expected)

        # mixed closed -> cast to object
        for other_closed in {"right", "left", "both", "neither"} - {closed}:
            other = monotonic_index(0, 11, closed=other_closed)
            expected = getattr(index.astype(object), op_name)(other, sort=sort)
            if op_name == "difference":
                expected = index
            result = set_op(other, sort=sort)
            tm.assert_index_equal(result, expected)

        # GH 19016: incompatible dtypes -> cast to object
        other = interval_range(Timestamp("20180101"), periods=9, closed=closed)
        expected = getattr(index.astype(object), op_name)(other, sort=sort)
        if op_name == "difference":
            expected = index
        result = set_op(other, sort=sort)
        tm.assert_index_equal(result, expected)
