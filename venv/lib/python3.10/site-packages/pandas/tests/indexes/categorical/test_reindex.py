import numpy as np
import pytest

from pandas import (
    Categorical,
    CategoricalIndex,
    Index,
    Interval,
)
import pandas._testing as tm


class TestReindex:
    def test_reindex_list_non_unique(self):
        # GH#11586
        msg = "cannot reindex on an axis with duplicate labels"
        ci = CategoricalIndex(["a", "b", "c", "a"])
        with pytest.raises(ValueError, match=msg):
            ci.reindex(["a", "c"])

    def test_reindex_categorical_non_unique(self):
        msg = "cannot reindex on an axis with duplicate labels"
        ci = CategoricalIndex(["a", "b", "c", "a"])
        with pytest.raises(ValueError, match=msg):
            ci.reindex(Categorical(["a", "c"]))

    def test_reindex_list_non_unique_unused_category(self):
        msg = "cannot reindex on an axis with duplicate labels"
        ci = CategoricalIndex(["a", "b", "c", "a"], categories=["a", "b", "c", "d"])
        with pytest.raises(ValueError, match=msg):
            ci.reindex(["a", "c"])

    def test_reindex_categorical_non_unique_unused_category(self):
        msg = "cannot reindex on an axis with duplicate labels"
        ci = CategoricalIndex(["a", "b", "c", "a"], categories=["a", "b", "c", "d"])
        with pytest.raises(ValueError, match=msg):
            ci.reindex(Categorical(["a", "c"]))

    def test_reindex_duplicate_target(self):
        # See GH25459
        cat = CategoricalIndex(["a", "b", "c"], categories=["a", "b", "c", "d"])
        res, indexer = cat.reindex(["a", "c", "c"])
        exp = Index(["a", "c", "c"])
        tm.assert_index_equal(res, exp, exact=True)
        tm.assert_numpy_array_equal(indexer, np.array([0, 2, 2], dtype=np.intp))

        res, indexer = cat.reindex(
            CategoricalIndex(["a", "c", "c"], categories=["a", "b", "c", "d"])
        )
        exp = CategoricalIndex(["a", "c", "c"], categories=["a", "b", "c", "d"])
        tm.assert_index_equal(res, exp, exact=True)
        tm.assert_numpy_array_equal(indexer, np.array([0, 2, 2], dtype=np.intp))

    def test_reindex_empty_index(self):
        # See GH16770
        c = CategoricalIndex([])
        res, indexer = c.reindex(["a", "b"])
        tm.assert_index_equal(res, Index(["a", "b"]), exact=True)
        tm.assert_numpy_array_equal(indexer, np.array([-1, -1], dtype=np.intp))

    def test_reindex_categorical_added_category(self):
        # GH 42424
        ci = CategoricalIndex(
            [Interval(0, 1, closed="right"), Interval(1, 2, closed="right")],
            ordered=True,
        )
        ci_add = CategoricalIndex(
            [
                Interval(0, 1, closed="right"),
                Interval(1, 2, closed="right"),
                Interval(2, 3, closed="right"),
                Interval(3, 4, closed="right"),
            ],
            ordered=True,
        )
        result, _ = ci.reindex(ci_add)
        expected = ci_add
        tm.assert_index_equal(expected, result)
