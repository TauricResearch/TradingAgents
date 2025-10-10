from datetime import timedelta
import re

import numpy as np
import pytest

from pandas._libs import index as libindex
from pandas.errors import (
    InvalidIndexError,
    PerformanceWarning,
)

import pandas as pd
from pandas import (
    Categorical,
    DataFrame,
    Index,
    MultiIndex,
    date_range,
)
import pandas._testing as tm


class TestSliceLocs:
    def test_slice_locs_partial(self, idx):
        sorted_idx, _ = idx.sortlevel(0)

        result = sorted_idx.slice_locs(("foo", "two"), ("qux", "one"))
        assert result == (1, 5)

        result = sorted_idx.slice_locs(None, ("qux", "one"))
        assert result == (0, 5)

        result = sorted_idx.slice_locs(("foo", "two"), None)
        assert result == (1, len(sorted_idx))

        result = sorted_idx.slice_locs("bar", "baz")
        assert result == (2, 4)

    def test_slice_locs(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((50, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=50, freq="B"),
        )
        stacked = df.stack(future_stack=True)
        idx = stacked.index

        slob = slice(*idx.slice_locs(df.index[5], df.index[15]))
        sliced = stacked[slob]
        expected = df[5:16].stack(future_stack=True)
        tm.assert_almost_equal(sliced.values, expected.values)

        slob = slice(
            *idx.slice_locs(
                df.index[5] + timedelta(seconds=30),
                df.index[15] - timedelta(seconds=30),
            )
        )
        sliced = stacked[slob]
        expected = df[6:15].stack(future_stack=True)
        tm.assert_almost_equal(sliced.values, expected.values)

    def test_slice_locs_with_type_mismatch(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        stacked = df.stack(future_stack=True)
        idx = stacked.index
        with pytest.raises(TypeError, match="^Level type mismatch"):
            idx.slice_locs((1, 3))
        with pytest.raises(TypeError, match="^Level type mismatch"):
            idx.slice_locs(df.index[5] + timedelta(seconds=30), (5, 2))
        df = DataFrame(
            np.ones((5, 5)),
            index=Index([f"i-{i}" for i in range(5)], name="a"),
            columns=Index([f"i-{i}" for i in range(5)], name="a"),
        )
        stacked = df.stack(future_stack=True)
        idx = stacked.index
        with pytest.raises(TypeError, match="^Level type mismatch"):
            idx.slice_locs(timedelta(seconds=30))
        # TODO: Try creating a UnicodeDecodeError in exception message
        with pytest.raises(TypeError, match="^Level type mismatch"):
            idx.slice_locs(df.index[1], (16, "a"))

    def test_slice_locs_not_sorted(self):
        index = MultiIndex(
            levels=[Index(np.arange(4)), Index(np.arange(4)), Index(np.arange(4))],
            codes=[
                np.array([0, 0, 1, 2, 2, 2, 3, 3]),
                np.array([0, 1, 0, 0, 0, 1, 0, 1]),
                np.array([1, 0, 1, 1, 0, 0, 1, 0]),
            ],
        )
        msg = "[Kk]ey length.*greater than MultiIndex lexsort depth"
        with pytest.raises(KeyError, match=msg):
            index.slice_locs((1, 0, 1), (2, 1, 0))

        # works
        sorted_index, _ = index.sortlevel(0)
        # should there be a test case here???
        sorted_index.slice_locs((1, 0, 1), (2, 1, 0))

    def test_slice_locs_not_contained(self):
        # some searchsorted action

        index = MultiIndex(
            levels=[[0, 2, 4, 6], [0, 2, 4]],
            codes=[[0, 0, 0, 1, 1, 2, 3, 3, 3], [0, 1, 2, 1, 2, 2, 0, 1, 2]],
        )

        result = index.slice_locs((1, 0), (5, 2))
        assert result == (3, 6)

        result = index.slice_locs(1, 5)
        assert result == (3, 6)

        result = index.slice_locs((2, 2), (5, 2))
        assert result == (3, 6)

        result = index.slice_locs(2, 5)
        assert result == (3, 6)

        result = index.slice_locs((1, 0), (6, 3))
        assert result == (3, 8)

        result = index.slice_locs(-1, 10)
        assert result == (0, len(index))

    @pytest.mark.parametrize(
        "index_arr,expected,start_idx,end_idx",
        [
            ([[np.nan, "a", "b"], ["c", "d", "e"]], (0, 3), np.nan, None),
            ([[np.nan, "a", "b"], ["c", "d", "e"]], (0, 3), np.nan, "b"),
            ([[np.nan, "a", "b"], ["c", "d", "e"]], (0, 3), np.nan, ("b", "e")),
            ([["a", "b", "c"], ["d", np.nan, "e"]], (1, 3), ("b", np.nan), None),
            ([["a", "b", "c"], ["d", np.nan, "e"]], (1, 3), ("b", np.nan), "c"),
            ([["a", "b", "c"], ["d", np.nan, "e"]], (1, 3), ("b", np.nan), ("c", "e")),
        ],
    )
    def test_slice_locs_with_missing_value(
        self, index_arr, expected, start_idx, end_idx
    ):
        # issue 19132
        idx = MultiIndex.from_arrays(index_arr)
        result = idx.slice_locs(start=start_idx, end=end_idx)
        assert result == expected


class TestPutmask:
    def test_putmask_with_wrong_mask(self, idx):
        # GH18368

        msg = "putmask: mask and data must be the same size"
        with pytest.raises(ValueError, match=msg):
            idx.putmask(np.ones(len(idx) + 1, np.bool_), 1)

        with pytest.raises(ValueError, match=msg):
            idx.putmask(np.ones(len(idx) - 1, np.bool_), 1)

        with pytest.raises(ValueError, match=msg):
            idx.putmask("foo", 1)

    def test_putmask_multiindex_other(self):
        # GH#43212 `value` is also a MultiIndex

        left = MultiIndex.from_tuples([(np.nan, 6), (np.nan, 6), ("a", 4)])
        right = MultiIndex.from_tuples([("a", 1), ("a", 1), ("d", 1)])
        mask = np.array([True, True, False])

        result = left.putmask(mask, right)

        expected = MultiIndex.from_tuples([right[0], right[1], left[2]])
        tm.assert_index_equal(result, expected)

    def test_putmask_keep_dtype(self, any_numeric_ea_dtype):
        # GH#49830
        midx = MultiIndex.from_arrays(
            [pd.Series([1, 2, 3], dtype=any_numeric_ea_dtype), [10, 11, 12]]
        )
        midx2 = MultiIndex.from_arrays(
            [pd.Series([5, 6, 7], dtype=any_numeric_ea_dtype), [-1, -2, -3]]
        )
        result = midx.putmask([True, False, False], midx2)
        expected = MultiIndex.from_arrays(
            [pd.Series([5, 2, 3], dtype=any_numeric_ea_dtype), [-1, 11, 12]]
        )
        tm.assert_index_equal(result, expected)

    def test_putmask_keep_dtype_shorter_value(self, any_numeric_ea_dtype):
        # GH#49830
        midx = MultiIndex.from_arrays(
            [pd.Series([1, 2, 3], dtype=any_numeric_ea_dtype), [10, 11, 12]]
        )
        midx2 = MultiIndex.from_arrays(
            [pd.Series([5], dtype=any_numeric_ea_dtype), [-1]]
        )
        result = midx.putmask([True, False, False], midx2)
        expected = MultiIndex.from_arrays(
            [pd.Series([5, 2, 3], dtype=any_numeric_ea_dtype), [-1, 11, 12]]
        )
        tm.assert_index_equal(result, expected)


class TestGetIndexer:
    def test_get_indexer(self):
        major_axis = Index(np.arange(4))
        minor_axis = Index(np.arange(2))

        major_codes = np.array([0, 0, 1, 2, 2, 3, 3], dtype=np.intp)
        minor_codes = np.array([0, 1, 0, 0, 1, 0, 1], dtype=np.intp)

        index = MultiIndex(
            levels=[major_axis, minor_axis], codes=[major_codes, minor_codes]
        )
        idx1 = index[:5]
        idx2 = index[[1, 3, 5]]

        r1 = idx1.get_indexer(idx2)
        tm.assert_almost_equal(r1, np.array([1, 3, -1], dtype=np.intp))

        r1 = idx2.get_indexer(idx1, method="pad")
        e1 = np.array([-1, 0, 0, 1, 1], dtype=np.intp)
        tm.assert_almost_equal(r1, e1)

        r2 = idx2.get_indexer(idx1[::-1], method="pad")
        tm.assert_almost_equal(r2, e1[::-1])

        rffill1 = idx2.get_indexer(idx1, method="ffill")
        tm.assert_almost_equal(r1, rffill1)

        r1 = idx2.get_indexer(idx1, method="backfill")
        e1 = np.array([0, 0, 1, 1, 2], dtype=np.intp)
        tm.assert_almost_equal(r1, e1)

        r2 = idx2.get_indexer(idx1[::-1], method="backfill")
        tm.assert_almost_equal(r2, e1[::-1])

        rbfill1 = idx2.get_indexer(idx1, method="bfill")
        tm.assert_almost_equal(r1, rbfill1)

        # pass non-MultiIndex
        r1 = idx1.get_indexer(idx2.values)
        rexp1 = idx1.get_indexer(idx2)
        tm.assert_almost_equal(r1, rexp1)

        r1 = idx1.get_indexer([1, 2, 3])
        assert (r1 == [-1, -1, -1]).all()

        # create index with duplicates
        idx1 = Index(list(range(10)) + list(range(10)))
        idx2 = Index(list(range(20)))

        msg = "Reindexing only valid with uniquely valued Index objects"
        with pytest.raises(InvalidIndexError, match=msg):
            idx1.get_indexer(idx2)

    def test_get_indexer_nearest(self):
        midx = MultiIndex.from_tuples([("a", 1), ("b", 2)])
        msg = (
            "method='nearest' not implemented yet for MultiIndex; "
            "see GitHub issue 9365"
        )
        with pytest.raises(NotImplementedError, match=msg):
            midx.get_indexer(["a"], method="nearest")
        msg = "tolerance not implemented yet for MultiIndex"
        with pytest.raises(NotImplementedError, match=msg):
            midx.get_indexer(["a"], method="pad", tolerance=2)

    def test_get_indexer_categorical_time(self):
        # https://github.com/pandas-dev/pandas/issues/21390
        midx = MultiIndex.from_product(
            [
                Categorical(["a", "b", "c"]),
                Categorical(date_range("2012-01-01", periods=3, freq="h")),
            ]
        )
        result = midx.get_indexer(midx)
        tm.assert_numpy_array_equal(result, np.arange(9, dtype=np.intp))

    @pytest.mark.parametrize(
        "index_arr,labels,expected",
        [
            (
                [[1, np.nan, 2], [3, 4, 5]],
                [1, np.nan, 2],
                np.array([-1, -1, -1], dtype=np.intp),
            ),
            ([[1, np.nan, 2], [3, 4, 5]], [(np.nan, 4)], np.array([1], dtype=np.intp)),
            ([[1, 2, 3], [np.nan, 4, 5]], [(1, np.nan)], np.array([0], dtype=np.intp)),
            (
                [[1, 2, 3], [np.nan, 4, 5]],
                [np.nan, 4, 5],
                np.array([-1, -1, -1], dtype=np.intp),
            ),
        ],
    )
    def test_get_indexer_with_missing_value(self, index_arr, labels, expected):
        # issue 19132
        idx = MultiIndex.from_arrays(index_arr)
        result = idx.get_indexer(labels)
        tm.assert_numpy_array_equal(result, expected)

    def test_get_indexer_methods(self):
        # https://github.com/pandas-dev/pandas/issues/29896
        # test getting an indexer for another index with different methods
        # confirms that getting an indexer without a filling method, getting an
        # indexer and backfilling, and getting an indexer and padding all behave
        # correctly in the case where all of the target values fall in between
        # several levels in the MultiIndex into which they are getting an indexer
        #
        # visually, the MultiIndexes used in this test are:
        # mult_idx_1:
        #  0: -1 0
        #  1:    2
        #  2:    3
        #  3:    4
        #  4:  0 0
        #  5:    2
        #  6:    3
        #  7:    4
        #  8:  1 0
        #  9:    2
        # 10:    3
        # 11:    4
        #
        # mult_idx_2:
        #  0: 0 1
        #  1:   3
        #  2:   4
        mult_idx_1 = MultiIndex.from_product([[-1, 0, 1], [0, 2, 3, 4]])
        mult_idx_2 = MultiIndex.from_product([[0], [1, 3, 4]])

        indexer = mult_idx_1.get_indexer(mult_idx_2)
        expected = np.array([-1, 6, 7], dtype=indexer.dtype)
        tm.assert_almost_equal(expected, indexer)

        backfill_indexer = mult_idx_1.get_indexer(mult_idx_2, method="backfill")
        expected = np.array([5, 6, 7], dtype=backfill_indexer.dtype)
        tm.assert_almost_equal(expected, backfill_indexer)

        # ensure the legacy "bfill" option functions identically to "backfill"
        backfill_indexer = mult_idx_1.get_indexer(mult_idx_2, method="bfill")
        expected = np.array([5, 6, 7], dtype=backfill_indexer.dtype)
        tm.assert_almost_equal(expected, backfill_indexer)

        pad_indexer = mult_idx_1.get_indexer(mult_idx_2, method="pad")
        expected = np.array([4, 6, 7], dtype=pad_indexer.dtype)
        tm.assert_almost_equal(expected, pad_indexer)

        # ensure the legacy "ffill" option functions identically to "pad"
        pad_indexer = mult_idx_1.get_indexer(mult_idx_2, method="ffill")
        expected = np.array([4, 6, 7], dtype=pad_indexer.dtype)
        tm.assert_almost_equal(expected, pad_indexer)

    @pytest.mark.parametrize("method", ["pad", "ffill", "backfill", "bfill", "nearest"])
    def test_get_indexer_methods_raise_for_non_monotonic(self, method):
        # 53452
        mi = MultiIndex.from_arrays([[0, 4, 2], [0, 4, 2]])
        if method == "nearest":
            err = NotImplementedError
            msg = "not implemented yet for MultiIndex"
        else:
            err = ValueError
            msg = "index must be monotonic increasing or decreasing"
        with pytest.raises(err, match=msg):
            mi.get_indexer([(1, 1)], method=method)

    def test_get_indexer_three_or_more_levels(self):
        # https://github.com/pandas-dev/pandas/issues/29896
        # tests get_indexer() on MultiIndexes with 3+ levels
        # visually, these are
        # mult_idx_1:
        #  0: 1 2 5
        #  1:     7
        #  2:   4 5
        #  3:     7
        #  4:   6 5
        #  5:     7
        #  6: 3 2 5
        #  7:     7
        #  8:   4 5
        #  9:     7
        # 10:   6 5
        # 11:     7
        #
        # mult_idx_2:
        #  0: 1 1 8
        #  1: 1 5 9
        #  2: 1 6 7
        #  3: 2 1 6
        #  4: 2 7 6
        #  5: 2 7 8
        #  6: 3 6 8
        mult_idx_1 = MultiIndex.from_product([[1, 3], [2, 4, 6], [5, 7]])
        mult_idx_2 = MultiIndex.from_tuples(
            [
                (1, 1, 8),
                (1, 5, 9),
                (1, 6, 7),
                (2, 1, 6),
                (2, 7, 7),
                (2, 7, 8),
                (3, 6, 8),
            ]
        )
        # sanity check
        assert mult_idx_1.is_monotonic_increasing
        assert mult_idx_1.is_unique
        assert mult_idx_2.is_monotonic_increasing
        assert mult_idx_2.is_unique

        # show the relationships between the two
        assert mult_idx_2[0] < mult_idx_1[0]
        assert mult_idx_1[3] < mult_idx_2[1] < mult_idx_1[4]
        assert mult_idx_1[5] == mult_idx_2[2]
        assert mult_idx_1[5] < mult_idx_2[3] < mult_idx_1[6]
        assert mult_idx_1[5] < mult_idx_2[4] < mult_idx_1[6]
        assert mult_idx_1[5] < mult_idx_2[5] < mult_idx_1[6]
        assert mult_idx_1[-1] < mult_idx_2[6]

        indexer_no_fill = mult_idx_1.get_indexer(mult_idx_2)
        expected = np.array([-1, -1, 5, -1, -1, -1, -1], dtype=indexer_no_fill.dtype)
        tm.assert_almost_equal(expected, indexer_no_fill)

        # test with backfilling
        indexer_backfilled = mult_idx_1.get_indexer(mult_idx_2, method="backfill")
        expected = np.array([0, 4, 5, 6, 6, 6, -1], dtype=indexer_backfilled.dtype)
        tm.assert_almost_equal(expected, indexer_backfilled)

        # now, the same thing, but forward-filled (aka "padded")
        indexer_padded = mult_idx_1.get_indexer(mult_idx_2, method="pad")
        expected = np.array([-1, 3, 5, 5, 5, 5, 11], dtype=indexer_padded.dtype)
        tm.assert_almost_equal(expected, indexer_padded)

        # now, do the indexing in the other direction
        assert mult_idx_2[0] < mult_idx_1[0] < mult_idx_2[1]
        assert mult_idx_2[0] < mult_idx_1[1] < mult_idx_2[1]
        assert mult_idx_2[0] < mult_idx_1[2] < mult_idx_2[1]
        assert mult_idx_2[0] < mult_idx_1[3] < mult_idx_2[1]
        assert mult_idx_2[1] < mult_idx_1[4] < mult_idx_2[2]
        assert mult_idx_2[2] == mult_idx_1[5]
        assert mult_idx_2[5] < mult_idx_1[6] < mult_idx_2[6]
        assert mult_idx_2[5] < mult_idx_1[7] < mult_idx_2[6]
        assert mult_idx_2[5] < mult_idx_1[8] < mult_idx_2[6]
        assert mult_idx_2[5] < mult_idx_1[9] < mult_idx_2[6]
        assert mult_idx_2[5] < mult_idx_1[10] < mult_idx_2[6]
        assert mult_idx_2[5] < mult_idx_1[11] < mult_idx_2[6]

        indexer = mult_idx_2.get_indexer(mult_idx_1)
        expected = np.array(
            [-1, -1, -1, -1, -1, 2, -1, -1, -1, -1, -1, -1], dtype=indexer.dtype
        )
        tm.assert_almost_equal(expected, indexer)

        backfill_indexer = mult_idx_2.get_indexer(mult_idx_1, method="bfill")
        expected = np.array(
            [1, 1, 1, 1, 2, 2, 6, 6, 6, 6, 6, 6], dtype=backfill_indexer.dtype
        )
        tm.assert_almost_equal(expected, backfill_indexer)

        pad_indexer = mult_idx_2.get_indexer(mult_idx_1, method="pad")
        expected = np.array(
            [0, 0, 0, 0, 1, 2, 5, 5, 5, 5, 5, 5], dtype=pad_indexer.dtype
        )
        tm.assert_almost_equal(expected, pad_indexer)

    def test_get_indexer_crossing_levels(self):
        # https://github.com/pandas-dev/pandas/issues/29896
        # tests a corner case with get_indexer() with MultiIndexes where, when we
        # need to "carry" across levels, proper tuple ordering is respected
        #
        # the MultiIndexes used in this test, visually, are:
        # mult_idx_1:
        #  0: 1 1 1 1
        #  1:       2
        #  2:     2 1
        #  3:       2
        #  4: 1 2 1 1
        #  5:       2
        #  6:     2 1
        #  7:       2
        #  8: 2 1 1 1
        #  9:       2
        # 10:     2 1
        # 11:       2
        # 12: 2 2 1 1
        # 13:       2
        # 14:     2 1
        # 15:       2
        #
        # mult_idx_2:
        #  0: 1 3 2 2
        #  1: 2 3 2 2
        mult_idx_1 = MultiIndex.from_product([[1, 2]] * 4)
        mult_idx_2 = MultiIndex.from_tuples([(1, 3, 2, 2), (2, 3, 2, 2)])

        # show the tuple orderings, which get_indexer() should respect
        assert mult_idx_1[7] < mult_idx_2[0] < mult_idx_1[8]
        assert mult_idx_1[-1] < mult_idx_2[1]

        indexer = mult_idx_1.get_indexer(mult_idx_2)
        expected = np.array([-1, -1], dtype=indexer.dtype)
        tm.assert_almost_equal(expected, indexer)

        backfill_indexer = mult_idx_1.get_indexer(mult_idx_2, method="bfill")
        expected = np.array([8, -1], dtype=backfill_indexer.dtype)
        tm.assert_almost_equal(expected, backfill_indexer)

        pad_indexer = mult_idx_1.get_indexer(mult_idx_2, method="ffill")
        expected = np.array([7, 15], dtype=pad_indexer.dtype)
        tm.assert_almost_equal(expected, pad_indexer)

    def test_get_indexer_kwarg_validation(self):
        # GH#41918
        mi = MultiIndex.from_product([range(3), ["A", "B"]])

        msg = "limit argument only valid if doing pad, backfill or nearest"
        with pytest.raises(ValueError, match=msg):
            mi.get_indexer(mi[:-1], limit=4)

        msg = "tolerance argument only valid if doing pad, backfill or nearest"
        with pytest.raises(ValueError, match=msg):
            mi.get_indexer(mi[:-1], tolerance="piano")

    def test_get_indexer_nan(self):
        # GH#37222
        idx1 = MultiIndex.from_product([["A"], [1.0, 2.0]], names=["id1", "id2"])
        idx2 = MultiIndex.from_product([["A"], [np.nan, 2.0]], names=["id1", "id2"])
        expected = np.array([-1, 1])
        result = idx2.get_indexer(idx1)
        tm.assert_numpy_array_equal(result, expected, check_dtype=False)
        result = idx1.get_indexer(idx2)
        tm.assert_numpy_array_equal(result, expected, check_dtype=False)


def test_getitem(idx):
    # scalar
    assert idx[2] == ("bar", "one")

    # slice
    result = idx[2:5]
    expected = idx[[2, 3, 4]]
    assert result.equals(expected)

    # boolean
    result = idx[[True, False, True, False, True, True]]
    result2 = idx[np.array([True, False, True, False, True, True])]
    expected = idx[[0, 2, 4, 5]]
    assert result.equals(expected)
    assert result2.equals(expected)


def test_getitem_group_select(idx):
    sorted_idx, _ = idx.sortlevel(0)
    assert sorted_idx.get_loc("baz") == slice(3, 4)
    assert sorted_idx.get_loc("foo") == slice(0, 2)


@pytest.mark.parametrize("ind1", [[True] * 5, Index([True] * 5)])
@pytest.mark.parametrize(
    "ind2",
    [[True, False, True, False, False], Index([True, False, True, False, False])],
)
def test_getitem_bool_index_all(ind1, ind2):
    # GH#22533
    idx = MultiIndex.from_tuples([(10, 1), (20, 2), (30, 3), (40, 4), (50, 5)])
    tm.assert_index_equal(idx[ind1], idx)

    expected = MultiIndex.from_tuples([(10, 1), (30, 3)])
    tm.assert_index_equal(idx[ind2], expected)


@pytest.mark.parametrize("ind1", [[True], Index([True])])
@pytest.mark.parametrize("ind2", [[False], Index([False])])
def test_getitem_bool_index_single(ind1, ind2):
    # GH#22533
    idx = MultiIndex.from_tuples([(10, 1)])
    tm.assert_index_equal(idx[ind1], idx)

    expected = MultiIndex(
        levels=[np.array([], dtype=np.int64), np.array([], dtype=np.int64)],
        codes=[[], []],
    )
    tm.assert_index_equal(idx[ind2], expected)


class TestGetLoc:
    def test_get_loc(self, idx):
        assert idx.get_loc(("foo", "two")) == 1
        assert idx.get_loc(("baz", "two")) == 3
        with pytest.raises(KeyError, match=r"^\('bar', 'two'\)$"):
            idx.get_loc(("bar", "two"))
        with pytest.raises(KeyError, match=r"^'quux'$"):
            idx.get_loc("quux")

        # 3 levels
        index = MultiIndex(
            levels=[Index(np.arange(4)), Index(np.arange(4)), Index(np.arange(4))],
            codes=[
                np.array([0, 0, 1, 2, 2, 2, 3, 3]),
                np.array([0, 1, 0, 0, 0, 1, 0, 1]),
                np.array([1, 0, 1, 1, 0, 0, 1, 0]),
            ],
        )
        with pytest.raises(KeyError, match=r"^\(1, 1\)$"):
            index.get_loc((1, 1))
        assert index.get_loc((2, 0)) == slice(3, 5)

    def test_get_loc_duplicates(self):
        index = Index([2, 2, 2, 2])
        result = index.get_loc(2)
        expected = slice(0, 4)
        assert result == expected

        index = Index(["c", "a", "a", "b", "b"])
        rs = index.get_loc("c")
        xp = 0
        assert rs == xp

        with pytest.raises(KeyError, match="2"):
            index.get_loc(2)

    def test_get_loc_level(self):
        index = MultiIndex(
            levels=[Index(np.arange(4)), Index(np.arange(4)), Index(np.arange(4))],
            codes=[
                np.array([0, 0, 1, 2, 2, 2, 3, 3]),
                np.array([0, 1, 0, 0, 0, 1, 0, 1]),
                np.array([1, 0, 1, 1, 0, 0, 1, 0]),
            ],
        )
        loc, new_index = index.get_loc_level((0, 1))
        expected = slice(1, 2)
        exp_index = index[expected].droplevel(0).droplevel(0)
        assert loc == expected
        assert new_index.equals(exp_index)

        loc, new_index = index.get_loc_level((0, 1, 0))
        expected = 1
        assert loc == expected
        assert new_index is None

        with pytest.raises(KeyError, match=r"^\(2, 2\)$"):
            index.get_loc_level((2, 2))
        # GH 22221: unused label
        with pytest.raises(KeyError, match=r"^2$"):
            index.drop(2).get_loc_level(2)
        # Unused label on unsorted level:
        with pytest.raises(KeyError, match=r"^2$"):
            index.drop(1, level=2).get_loc_level(2, level=2)

        index = MultiIndex(
            levels=[[2000], list(range(4))],
            codes=[np.array([0, 0, 0, 0]), np.array([0, 1, 2, 3])],
        )
        result, new_index = index.get_loc_level((2000, slice(None, None)))
        expected = slice(None, None)
        assert result == expected
        assert new_index.equals(index.droplevel(0))

    @pytest.mark.parametrize("dtype1", [int, float, bool, str])
    @pytest.mark.parametrize("dtype2", [int, float, bool, str])
    def test_get_loc_multiple_dtypes(self, dtype1, dtype2):
        # GH 18520
        levels = [np.array([0, 1]).astype(dtype1), np.array([0, 1]).astype(dtype2)]
        idx = MultiIndex.from_product(levels)
        assert idx.get_loc(idx[2]) == 2

    @pytest.mark.parametrize("level", [0, 1])
    @pytest.mark.parametrize("dtypes", [[int, float], [float, int]])
    def test_get_loc_implicit_cast(self, level, dtypes):
        # GH 18818, GH 15994 : as flat index, cast int to float and vice-versa
        levels = [["a", "b"], ["c", "d"]]
        key = ["b", "d"]
        lev_dtype, key_dtype = dtypes
        levels[level] = np.array([0, 1], dtype=lev_dtype)
        key[level] = key_dtype(1)
        idx = MultiIndex.from_product(levels)
        assert idx.get_loc(tuple(key)) == 3

    @pytest.mark.parametrize("dtype", [bool, object])
    def test_get_loc_cast_bool(self, dtype):
        # GH 19086 : int is casted to bool, but not vice-versa (for object dtype)
        #  With bool dtype, we don't cast in either direction.
        levels = [Index([False, True], dtype=dtype), np.arange(2, dtype="int64")]
        idx = MultiIndex.from_product(levels)

        if dtype is bool:
            with pytest.raises(KeyError, match=r"^\(0, 1\)$"):
                assert idx.get_loc((0, 1)) == 1
            with pytest.raises(KeyError, match=r"^\(1, 0\)$"):
                assert idx.get_loc((1, 0)) == 2
        else:
            # We use python object comparisons, which treat 0 == False and 1 == True
            assert idx.get_loc((0, 1)) == 1
            assert idx.get_loc((1, 0)) == 2

        with pytest.raises(KeyError, match=r"^\(False, True\)$"):
            idx.get_loc((False, True))
        with pytest.raises(KeyError, match=r"^\(True, False\)$"):
            idx.get_loc((True, False))

    @pytest.mark.parametrize("level", [0, 1])
    def test_get_loc_nan(self, level, nulls_fixture):
        # GH 18485 : NaN in MultiIndex
        levels = [["a", "b"], ["c", "d"]]
        key = ["b", "d"]
        levels[level] = np.array([0, nulls_fixture], dtype=type(nulls_fixture))
        key[level] = nulls_fixture
        idx = MultiIndex.from_product(levels)
        assert idx.get_loc(tuple(key)) == 3

    def test_get_loc_missing_nan(self):
        # GH 8569
        idx = MultiIndex.from_arrays([[1.0, 2.0], [3.0, 4.0]])
        assert isinstance(idx.get_loc(1), slice)
        with pytest.raises(KeyError, match=r"^3$"):
            idx.get_loc(3)
        with pytest.raises(KeyError, match=r"^nan$"):
            idx.get_loc(np.nan)
        with pytest.raises(InvalidIndexError, match=r"\[nan\]"):
            # listlike/non-hashable raises TypeError
            idx.get_loc([np.nan])

    def test_get_loc_with_values_including_missing_values(self):
        # issue 19132
        idx = MultiIndex.from_product([[np.nan, 1]] * 2)
        expected = slice(0, 2, None)
        assert idx.get_loc(np.nan) == expected

        idx = MultiIndex.from_arrays([[np.nan, 1, 2, np.nan]])
        expected = np.array([True, False, False, True])
        tm.assert_numpy_array_equal(idx.get_loc(np.nan), expected)

        idx = MultiIndex.from_product([[np.nan, 1]] * 3)
        expected = slice(2, 4, None)
        assert idx.get_loc((np.nan, 1)) == expected

    def test_get_loc_duplicates2(self):
        # TODO: de-duplicate with test_get_loc_duplicates above?
        index = MultiIndex(
            levels=[["D", "B", "C"], [0, 26, 27, 37, 57, 67, 75, 82]],
            codes=[[0, 0, 0, 1, 2, 2, 2, 2, 2, 2], [1, 3, 4, 6, 0, 2, 2, 3, 5, 7]],
            names=["tag", "day"],
        )

        assert index.get_loc("D") == slice(0, 3)

    def test_get_loc_past_lexsort_depth(self):
        # GH#30053
        idx = MultiIndex(
            levels=[["a"], [0, 7], [1]],
            codes=[[0, 0], [1, 0], [0, 0]],
            names=["x", "y", "z"],
            sortorder=0,
        )
        key = ("a", 7)

        with tm.assert_produces_warning(PerformanceWarning):
            # PerformanceWarning: indexing past lexsort depth may impact performance
            result = idx.get_loc(key)

        assert result == slice(0, 1, None)

    def test_multiindex_get_loc_list_raises(self):
        # GH#35878
        idx = MultiIndex.from_tuples([("a", 1), ("b", 2)])
        msg = r"\[\]"
        with pytest.raises(InvalidIndexError, match=msg):
            idx.get_loc([])

    def test_get_loc_nested_tuple_raises_keyerror(self):
        # raise KeyError, not TypeError
        mi = MultiIndex.from_product([range(3), range(4), range(5), range(6)])
        key = ((2, 3, 4), "foo")

        with pytest.raises(KeyError, match=re.escape(str(key))):
            mi.get_loc(key)


class TestWhere:
    def test_where(self):
        i = MultiIndex.from_tuples([("A", 1), ("A", 2)])

        msg = r"\.where is not supported for MultiIndex operations"
        with pytest.raises(NotImplementedError, match=msg):
            i.where(True)

    def test_where_array_like(self, listlike_box):
        mi = MultiIndex.from_tuples([("A", 1), ("A", 2)])
        cond = [False, True]
        msg = r"\.where is not supported for MultiIndex operations"
        with pytest.raises(NotImplementedError, match=msg):
            mi.where(listlike_box(cond))


class TestContains:
    def test_contains_top_level(self):
        midx = MultiIndex.from_product([["A", "B"], [1, 2]])
        assert "A" in midx
        assert "A" not in midx._engine

    def test_contains_with_nat(self):
        # MI with a NaT
        mi = MultiIndex(
            levels=[["C"], date_range("2012-01-01", periods=5)],
            codes=[[0, 0, 0, 0, 0, 0], [-1, 0, 1, 2, 3, 4]],
            names=[None, "B"],
        )
        assert ("C", pd.Timestamp("2012-01-01")) in mi
        for val in mi.values:
            assert val in mi

    def test_contains(self, idx):
        assert ("foo", "two") in idx
        assert ("bar", "two") not in idx
        assert None not in idx

    def test_contains_with_missing_value(self):
        # GH#19132
        idx = MultiIndex.from_arrays([[1, np.nan, 2]])
        assert np.nan in idx

        idx = MultiIndex.from_arrays([[1, 2], [np.nan, 3]])
        assert np.nan not in idx
        assert (1, np.nan) in idx

    def test_multiindex_contains_dropped(self):
        # GH#19027
        # test that dropped MultiIndex levels are not in the MultiIndex
        # despite continuing to be in the MultiIndex's levels
        idx = MultiIndex.from_product([[1, 2], [3, 4]])
        assert 2 in idx
        idx = idx.drop(2)

        # drop implementation keeps 2 in the levels
        assert 2 in idx.levels[0]
        # but it should no longer be in the index itself
        assert 2 not in idx

        # also applies to strings
        idx = MultiIndex.from_product([["a", "b"], ["c", "d"]])
        assert "a" in idx
        idx = idx.drop("a")
        assert "a" in idx.levels[0]
        assert "a" not in idx

    def test_contains_td64_level(self):
        # GH#24570
        tx = pd.timedelta_range("09:30:00", "16:00:00", freq="30 min")
        idx = MultiIndex.from_arrays([tx, np.arange(len(tx))])
        assert tx[0] in idx
        assert "element_not_exit" not in idx
        assert "0 day 09:30:00" in idx

    def test_large_mi_contains(self, monkeypatch):
        # GH#10645
        with monkeypatch.context():
            monkeypatch.setattr(libindex, "_SIZE_CUTOFF", 10)
            result = MultiIndex.from_arrays([range(10), range(10)])
            assert (10, 0) not in result


def test_timestamp_multiindex_indexer():
    # https://github.com/pandas-dev/pandas/issues/26944
    idx = MultiIndex.from_product(
        [
            date_range("2019-01-01T00:15:33", periods=100, freq="h", name="date"),
            ["x"],
            [3],
        ]
    )
    df = DataFrame({"foo": np.arange(len(idx))}, idx)
    result = df.loc[pd.IndexSlice["2019-1-2":, "x", :], "foo"]
    qidx = MultiIndex.from_product(
        [
            date_range(
                start="2019-01-02T00:15:33",
                end="2019-01-05T03:15:33",
                freq="h",
                name="date",
            ),
            ["x"],
            [3],
        ]
    )
    should_be = pd.Series(data=np.arange(24, len(qidx) + 24), index=qidx, name="foo")
    tm.assert_series_equal(result, should_be)


@pytest.mark.parametrize(
    "index_arr,expected,target,algo",
    [
        ([[np.nan, "a", "b"], ["c", "d", "e"]], 0, np.nan, "left"),
        ([[np.nan, "a", "b"], ["c", "d", "e"]], 1, (np.nan, "c"), "right"),
        ([["a", "b", "c"], ["d", np.nan, "d"]], 1, ("b", np.nan), "left"),
    ],
)
def test_get_slice_bound_with_missing_value(index_arr, expected, target, algo):
    # issue 19132
    idx = MultiIndex.from_arrays(index_arr)
    result = idx.get_slice_bound(target, side=algo)
    assert result == expected


@pytest.mark.parametrize(
    "index_arr,expected,start_idx,end_idx",
    [
        ([[np.nan, 1, 2], [3, 4, 5]], slice(0, 2, None), np.nan, 1),
        ([[np.nan, 1, 2], [3, 4, 5]], slice(0, 3, None), np.nan, (2, 5)),
        ([[1, 2, 3], [4, np.nan, 5]], slice(1, 3, None), (2, np.nan), 3),
        ([[1, 2, 3], [4, np.nan, 5]], slice(1, 3, None), (2, np.nan), (3, 5)),
    ],
)
def test_slice_indexer_with_missing_value(index_arr, expected, start_idx, end_idx):
    # issue 19132
    idx = MultiIndex.from_arrays(index_arr)
    result = idx.slice_indexer(start=start_idx, end=end_idx)
    assert result == expected


def test_pyint_engine():
    # GH#18519 : when combinations of codes cannot be represented in 64
    # bits, the index underlying the MultiIndex engine works with Python
    # integers, rather than uint64.
    N = 5
    keys = [
        tuple(arr)
        for arr in [
            [0] * 10 * N,
            [1] * 10 * N,
            [2] * 10 * N,
            [np.nan] * N + [2] * 9 * N,
            [0] * N + [2] * 9 * N,
            [np.nan] * N + [2] * 8 * N + [0] * N,
        ]
    ]
    # Each level contains 4 elements (including NaN), so it is represented
    # in 2 bits, for a total of 2*N*10 = 100 > 64 bits. If we were using a
    # 64 bit engine and truncating the first levels, the fourth and fifth
    # keys would collide; if truncating the last levels, the fifth and
    # sixth; if rotating bits rather than shifting, the third and fifth.

    for idx, key_value in enumerate(keys):
        index = MultiIndex.from_tuples(keys)
        assert index.get_loc(key_value) == idx

        expected = np.arange(idx + 1, dtype=np.intp)
        result = index.get_indexer([keys[i] for i in expected])
        tm.assert_numpy_array_equal(result, expected)

    # With missing key:
    idces = range(len(keys))
    expected = np.array([-1] + list(idces), dtype=np.intp)
    missing = tuple([0, 1] * 5 * N)
    result = index.get_indexer([missing] + [keys[i] for i in idces])
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize(
    "keys,expected",
    [
        ((slice(None), [5, 4]), [1, 0]),
        ((slice(None), [4, 5]), [0, 1]),
        (([True, False, True], [4, 6]), [0, 2]),
        (([True, False, True], [6, 4]), [0, 2]),
        ((2, [4, 5]), [0, 1]),
        ((2, [5, 4]), [1, 0]),
        (([2], [4, 5]), [0, 1]),
        (([2], [5, 4]), [1, 0]),
    ],
)
def test_get_locs_reordering(keys, expected):
    # GH48384
    idx = MultiIndex.from_arrays(
        [
            [2, 2, 1],
            [4, 5, 6],
        ]
    )
    result = idx.get_locs(keys)
    expected = np.array(expected, dtype=np.intp)
    tm.assert_numpy_array_equal(result, expected)


def test_get_indexer_for_multiindex_with_nans(nulls_fixture):
    # GH37222
    idx1 = MultiIndex.from_product([["A"], [1.0, 2.0]], names=["id1", "id2"])
    idx2 = MultiIndex.from_product([["A"], [nulls_fixture, 2.0]], names=["id1", "id2"])

    result = idx2.get_indexer(idx1)
    expected = np.array([-1, 1], dtype=np.intp)
    tm.assert_numpy_array_equal(result, expected)

    result = idx1.get_indexer(idx2)
    expected = np.array([-1, 1], dtype=np.intp)
    tm.assert_numpy_array_equal(result, expected)
