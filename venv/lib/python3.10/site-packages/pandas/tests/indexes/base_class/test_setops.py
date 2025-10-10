from datetime import datetime

import numpy as np
import pytest

import pandas as pd
from pandas import (
    Index,
    Series,
)
import pandas._testing as tm
from pandas.core.algorithms import safe_sort


def equal_contents(arr1, arr2) -> bool:
    """
    Checks if the set of unique elements of arr1 and arr2 are equivalent.
    """
    return frozenset(arr1) == frozenset(arr2)


class TestIndexSetOps:
    @pytest.mark.parametrize(
        "method", ["union", "intersection", "difference", "symmetric_difference"]
    )
    def test_setops_sort_validation(self, method):
        idx1 = Index(["a", "b"])
        idx2 = Index(["b", "c"])

        with pytest.raises(ValueError, match="The 'sort' keyword only takes"):
            getattr(idx1, method)(idx2, sort=2)

        # sort=True is supported as of GH#??
        getattr(idx1, method)(idx2, sort=True)

    def test_setops_preserve_object_dtype(self):
        idx = Index([1, 2, 3], dtype=object)
        result = idx.intersection(idx[1:])
        expected = idx[1:]
        tm.assert_index_equal(result, expected)

        # if other is not monotonic increasing, intersection goes through
        #  a different route
        result = idx.intersection(idx[1:][::-1])
        tm.assert_index_equal(result, expected)

        result = idx._union(idx[1:], sort=None)
        expected = idx
        tm.assert_numpy_array_equal(result, expected.values)

        result = idx.union(idx[1:], sort=None)
        tm.assert_index_equal(result, expected)

        # if other is not monotonic increasing, _union goes through
        #  a different route
        result = idx._union(idx[1:][::-1], sort=None)
        tm.assert_numpy_array_equal(result, expected.values)

        result = idx.union(idx[1:][::-1], sort=None)
        tm.assert_index_equal(result, expected)

    def test_union_base(self):
        index = Index([0, "a", 1, "b", 2, "c"])
        first = index[3:]
        second = index[:5]

        result = first.union(second)

        expected = Index([0, 1, 2, "a", "b", "c"])
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("klass", [np.array, Series, list])
    def test_union_different_type_base(self, klass):
        # GH 10149
        index = Index([0, "a", 1, "b", 2, "c"])
        first = index[3:]
        second = index[:5]

        result = first.union(klass(second.values))

        assert equal_contents(result, index)

    def test_union_sort_other_incomparable(self):
        # https://github.com/pandas-dev/pandas/issues/24959
        idx = Index([1, pd.Timestamp("2000")])
        # default (sort=None)
        with tm.assert_produces_warning(RuntimeWarning):
            result = idx.union(idx[:1])

        tm.assert_index_equal(result, idx)

        # sort=None
        with tm.assert_produces_warning(RuntimeWarning):
            result = idx.union(idx[:1], sort=None)
        tm.assert_index_equal(result, idx)

        # sort=False
        result = idx.union(idx[:1], sort=False)
        tm.assert_index_equal(result, idx)

    def test_union_sort_other_incomparable_true(self):
        idx = Index([1, pd.Timestamp("2000")])
        with pytest.raises(TypeError, match=".*"):
            idx.union(idx[:1], sort=True)

    def test_intersection_equal_sort_true(self):
        idx = Index(["c", "a", "b"])
        sorted_ = Index(["a", "b", "c"])
        tm.assert_index_equal(idx.intersection(idx, sort=True), sorted_)

    def test_intersection_base(self, sort):
        # (same results for py2 and py3 but sortedness not tested elsewhere)
        index = Index([0, "a", 1, "b", 2, "c"])
        first = index[:5]
        second = index[:3]

        expected = Index([0, 1, "a"]) if sort is None else Index([0, "a", 1])
        result = first.intersection(second, sort=sort)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("klass", [np.array, Series, list])
    def test_intersection_different_type_base(self, klass, sort):
        # GH 10149
        index = Index([0, "a", 1, "b", 2, "c"])
        first = index[:5]
        second = index[:3]

        result = first.intersection(klass(second.values), sort=sort)
        assert equal_contents(result, second)

    def test_intersection_nosort(self):
        result = Index(["c", "b", "a"]).intersection(["b", "a"])
        expected = Index(["b", "a"])
        tm.assert_index_equal(result, expected)

    def test_intersection_equal_sort(self):
        idx = Index(["c", "a", "b"])
        tm.assert_index_equal(idx.intersection(idx, sort=False), idx)
        tm.assert_index_equal(idx.intersection(idx, sort=None), idx)

    def test_intersection_str_dates(self, sort):
        dt_dates = [datetime(2012, 2, 9), datetime(2012, 2, 22)]

        i1 = Index(dt_dates, dtype=object)
        i2 = Index(["aa"], dtype=object)
        result = i2.intersection(i1, sort=sort)

        assert len(result) == 0

    @pytest.mark.parametrize(
        "index2,expected_arr",
        [(Index(["B", "D"]), ["B"]), (Index(["B", "D", "A"]), ["A", "B"])],
    )
    def test_intersection_non_monotonic_non_unique(self, index2, expected_arr, sort):
        # non-monotonic non-unique
        index1 = Index(["A", "B", "A", "C"])
        expected = Index(expected_arr)
        result = index1.intersection(index2, sort=sort)
        if sort is None:
            expected = expected.sort_values()
        tm.assert_index_equal(result, expected)

    def test_difference_base(self, sort):
        # (same results for py2 and py3 but sortedness not tested elsewhere)
        index = Index([0, "a", 1, "b", 2, "c"])
        first = index[:4]
        second = index[3:]

        result = first.difference(second, sort)
        expected = Index([0, "a", 1])
        if sort is None:
            expected = Index(safe_sort(expected))
        tm.assert_index_equal(result, expected)

    def test_symmetric_difference(self):
        # (same results for py2 and py3 but sortedness not tested elsewhere)
        index = Index([0, "a", 1, "b", 2, "c"])
        first = index[:4]
        second = index[3:]

        result = first.symmetric_difference(second)
        expected = Index([0, 1, 2, "a", "c"])
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "method,expected,sort",
        [
            (
                "intersection",
                np.array(
                    [(1, "A"), (2, "A"), (1, "B"), (2, "B")],
                    dtype=[("num", int), ("let", "S1")],
                ),
                False,
            ),
            (
                "intersection",
                np.array(
                    [(1, "A"), (1, "B"), (2, "A"), (2, "B")],
                    dtype=[("num", int), ("let", "S1")],
                ),
                None,
            ),
            (
                "union",
                np.array(
                    [(1, "A"), (1, "B"), (1, "C"), (2, "A"), (2, "B"), (2, "C")],
                    dtype=[("num", int), ("let", "S1")],
                ),
                None,
            ),
        ],
    )
    def test_tuple_union_bug(self, method, expected, sort):
        index1 = Index(
            np.array(
                [(1, "A"), (2, "A"), (1, "B"), (2, "B")],
                dtype=[("num", int), ("let", "S1")],
            )
        )
        index2 = Index(
            np.array(
                [(1, "A"), (2, "A"), (1, "B"), (2, "B"), (1, "C"), (2, "C")],
                dtype=[("num", int), ("let", "S1")],
            )
        )

        result = getattr(index1, method)(index2, sort=sort)
        assert result.ndim == 1

        expected = Index(expected)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("first_list", [["b", "a"], []])
    @pytest.mark.parametrize("second_list", [["a", "b"], []])
    @pytest.mark.parametrize(
        "first_name, second_name, expected_name",
        [("A", "B", None), (None, "B", None), ("A", None, None)],
    )
    def test_union_name_preservation(
        self, first_list, second_list, first_name, second_name, expected_name, sort
    ):
        first = Index(first_list, name=first_name)
        second = Index(second_list, name=second_name)
        union = first.union(second, sort=sort)

        vals = set(first_list).union(second_list)

        if sort is None and len(first_list) > 0 and len(second_list) > 0:
            expected = Index(sorted(vals), name=expected_name)
            tm.assert_index_equal(union, expected)
        else:
            expected = Index(vals, name=expected_name)
            tm.assert_index_equal(union.sort_values(), expected.sort_values())

    @pytest.mark.parametrize(
        "diff_type, expected",
        [["difference", [1, "B"]], ["symmetric_difference", [1, 2, "B", "C"]]],
    )
    def test_difference_object_type(self, diff_type, expected):
        # GH 13432
        idx1 = Index([0, 1, "A", "B"])
        idx2 = Index([0, 2, "A", "C"])
        result = getattr(idx1, diff_type)(idx2)
        expected = Index(expected)
        tm.assert_index_equal(result, expected)
