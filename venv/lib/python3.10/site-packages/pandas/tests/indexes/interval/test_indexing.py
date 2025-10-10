import re

import numpy as np
import pytest

from pandas.errors import InvalidIndexError

from pandas import (
    NA,
    CategoricalIndex,
    DatetimeIndex,
    Index,
    Interval,
    IntervalIndex,
    MultiIndex,
    NaT,
    Timedelta,
    Timestamp,
    array,
    date_range,
    interval_range,
    isna,
    period_range,
    timedelta_range,
)
import pandas._testing as tm


class TestGetItem:
    def test_getitem(self, closed):
        idx = IntervalIndex.from_arrays((0, 1, np.nan), (1, 2, np.nan), closed=closed)
        assert idx[0] == Interval(0.0, 1.0, closed=closed)
        assert idx[1] == Interval(1.0, 2.0, closed=closed)
        assert isna(idx[2])

        result = idx[0:1]
        expected = IntervalIndex.from_arrays((0.0,), (1.0,), closed=closed)
        tm.assert_index_equal(result, expected)

        result = idx[0:2]
        expected = IntervalIndex.from_arrays((0.0, 1), (1.0, 2.0), closed=closed)
        tm.assert_index_equal(result, expected)

        result = idx[1:3]
        expected = IntervalIndex.from_arrays(
            (1.0, np.nan), (2.0, np.nan), closed=closed
        )
        tm.assert_index_equal(result, expected)

    def test_getitem_2d_deprecated(self):
        # GH#30588 multi-dim indexing is deprecated, but raising is also acceptable
        idx = IntervalIndex.from_breaks(range(11), closed="right")
        with pytest.raises(ValueError, match="multi-dimensional indexing not allowed"):
            idx[:, None]
        with pytest.raises(ValueError, match="multi-dimensional indexing not allowed"):
            # GH#44051
            idx[True]
        with pytest.raises(ValueError, match="multi-dimensional indexing not allowed"):
            # GH#44051
            idx[False]


class TestWhere:
    def test_where(self, listlike_box):
        klass = listlike_box

        idx = IntervalIndex.from_breaks(range(11), closed="right")
        cond = [True] * len(idx)
        expected = idx
        result = expected.where(klass(cond))
        tm.assert_index_equal(result, expected)

        cond = [False] + [True] * len(idx[1:])
        expected = IntervalIndex([np.nan] + idx[1:].tolist())
        result = idx.where(klass(cond))
        tm.assert_index_equal(result, expected)


class TestTake:
    def test_take(self, closed):
        index = IntervalIndex.from_breaks(range(11), closed=closed)

        result = index.take(range(10))
        tm.assert_index_equal(result, index)

        result = index.take([0, 0, 1])
        expected = IntervalIndex.from_arrays([0, 0, 1], [1, 1, 2], closed=closed)
        tm.assert_index_equal(result, expected)


class TestGetLoc:
    @pytest.mark.parametrize("side", ["right", "left", "both", "neither"])
    def test_get_loc_interval(self, closed, side):
        idx = IntervalIndex.from_tuples([(0, 1), (2, 3)], closed=closed)

        for bound in [[0, 1], [1, 2], [2, 3], [3, 4], [0, 2], [2.5, 3], [-1, 4]]:
            # if get_loc is supplied an interval, it should only search
            # for exact matches, not overlaps or covers, else KeyError.
            msg = re.escape(f"Interval({bound[0]}, {bound[1]}, closed='{side}')")
            if closed == side:
                if bound == [0, 1]:
                    assert idx.get_loc(Interval(0, 1, closed=side)) == 0
                elif bound == [2, 3]:
                    assert idx.get_loc(Interval(2, 3, closed=side)) == 1
                else:
                    with pytest.raises(KeyError, match=msg):
                        idx.get_loc(Interval(*bound, closed=side))
            else:
                with pytest.raises(KeyError, match=msg):
                    idx.get_loc(Interval(*bound, closed=side))

    @pytest.mark.parametrize("scalar", [-0.5, 0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5])
    def test_get_loc_scalar(self, closed, scalar):
        # correct = {side: {query: answer}}.
        # If query is not in the dict, that query should raise a KeyError
        correct = {
            "right": {0.5: 0, 1: 0, 2.5: 1, 3: 1},
            "left": {0: 0, 0.5: 0, 2: 1, 2.5: 1},
            "both": {0: 0, 0.5: 0, 1: 0, 2: 1, 2.5: 1, 3: 1},
            "neither": {0.5: 0, 2.5: 1},
        }

        idx = IntervalIndex.from_tuples([(0, 1), (2, 3)], closed=closed)

        # if get_loc is supplied a scalar, it should return the index of
        # the interval which contains the scalar, or KeyError.
        if scalar in correct[closed].keys():
            assert idx.get_loc(scalar) == correct[closed][scalar]
        else:
            with pytest.raises(KeyError, match=str(scalar)):
                idx.get_loc(scalar)

    @pytest.mark.parametrize("scalar", [-1, 0, 0.5, 3, 4.5, 5, 6])
    def test_get_loc_length_one_scalar(self, scalar, closed):
        # GH 20921
        index = IntervalIndex.from_tuples([(0, 5)], closed=closed)
        if scalar in index[0]:
            result = index.get_loc(scalar)
            assert result == 0
        else:
            with pytest.raises(KeyError, match=str(scalar)):
                index.get_loc(scalar)

    @pytest.mark.parametrize("other_closed", ["left", "right", "both", "neither"])
    @pytest.mark.parametrize("left, right", [(0, 5), (-1, 4), (-1, 6), (6, 7)])
    def test_get_loc_length_one_interval(self, left, right, closed, other_closed):
        # GH 20921
        index = IntervalIndex.from_tuples([(0, 5)], closed=closed)
        interval = Interval(left, right, closed=other_closed)
        if interval == index[0]:
            result = index.get_loc(interval)
            assert result == 0
        else:
            with pytest.raises(
                KeyError,
                match=re.escape(f"Interval({left}, {right}, closed='{other_closed}')"),
            ):
                index.get_loc(interval)

    # Make consistent with test_interval_new.py (see #16316, #16386)
    @pytest.mark.parametrize(
        "breaks",
        [
            date_range("20180101", periods=4),
            date_range("20180101", periods=4, tz="US/Eastern"),
            timedelta_range("0 days", periods=4),
        ],
        ids=lambda x: str(x.dtype),
    )
    def test_get_loc_datetimelike_nonoverlapping(self, breaks):
        # GH 20636
        # nonoverlapping = IntervalIndex method and no i8 conversion
        index = IntervalIndex.from_breaks(breaks)

        value = index[0].mid
        result = index.get_loc(value)
        expected = 0
        assert result == expected

        interval = Interval(index[0].left, index[0].right)
        result = index.get_loc(interval)
        expected = 0
        assert result == expected

    @pytest.mark.parametrize(
        "arrays",
        [
            (date_range("20180101", periods=4), date_range("20180103", periods=4)),
            (
                date_range("20180101", periods=4, tz="US/Eastern"),
                date_range("20180103", periods=4, tz="US/Eastern"),
            ),
            (
                timedelta_range("0 days", periods=4),
                timedelta_range("2 days", periods=4),
            ),
        ],
        ids=lambda x: str(x[0].dtype),
    )
    def test_get_loc_datetimelike_overlapping(self, arrays):
        # GH 20636
        index = IntervalIndex.from_arrays(*arrays)

        value = index[0].mid + Timedelta("12 hours")
        result = index.get_loc(value)
        expected = slice(0, 2, None)
        assert result == expected

        interval = Interval(index[0].left, index[0].right)
        result = index.get_loc(interval)
        expected = 0
        assert result == expected

    @pytest.mark.parametrize(
        "values",
        [
            date_range("2018-01-04", periods=4, freq="-1D"),
            date_range("2018-01-04", periods=4, freq="-1D", tz="US/Eastern"),
            timedelta_range("3 days", periods=4, freq="-1D"),
            np.arange(3.0, -1.0, -1.0),
            np.arange(3, -1, -1),
        ],
        ids=lambda x: str(x.dtype),
    )
    def test_get_loc_decreasing(self, values):
        # GH 25860
        index = IntervalIndex.from_arrays(values[1:], values[:-1])
        result = index.get_loc(index[0])
        expected = 0
        assert result == expected

    @pytest.mark.parametrize("key", [[5], (2, 3)])
    def test_get_loc_non_scalar_errors(self, key):
        # GH 31117
        idx = IntervalIndex.from_tuples([(1, 3), (2, 4), (3, 5), (7, 10), (3, 10)])

        msg = str(key)
        with pytest.raises(InvalidIndexError, match=msg):
            idx.get_loc(key)

    def test_get_indexer_with_nans(self):
        # GH#41831
        index = IntervalIndex([np.nan, Interval(1, 2), np.nan])

        expected = np.array([True, False, True])
        for key in [None, np.nan, NA]:
            assert key in index
            result = index.get_loc(key)
            tm.assert_numpy_array_equal(result, expected)

        for key in [NaT, np.timedelta64("NaT", "ns"), np.datetime64("NaT", "ns")]:
            with pytest.raises(KeyError, match=str(key)):
                index.get_loc(key)


class TestGetIndexer:
    @pytest.mark.parametrize(
        "query, expected",
        [
            ([Interval(2, 4, closed="right")], [1]),
            ([Interval(2, 4, closed="left")], [-1]),
            ([Interval(2, 4, closed="both")], [-1]),
            ([Interval(2, 4, closed="neither")], [-1]),
            ([Interval(1, 4, closed="right")], [-1]),
            ([Interval(0, 4, closed="right")], [-1]),
            ([Interval(0.5, 1.5, closed="right")], [-1]),
            ([Interval(2, 4, closed="right"), Interval(0, 1, closed="right")], [1, -1]),
            ([Interval(2, 4, closed="right"), Interval(2, 4, closed="right")], [1, 1]),
            ([Interval(5, 7, closed="right"), Interval(2, 4, closed="right")], [2, 1]),
            ([Interval(2, 4, closed="right"), Interval(2, 4, closed="left")], [1, -1]),
        ],
    )
    def test_get_indexer_with_interval(self, query, expected):
        tuples = [(0, 2), (2, 4), (5, 7)]
        index = IntervalIndex.from_tuples(tuples, closed="right")

        result = index.get_indexer(query)
        expected = np.array(expected, dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize(
        "query, expected",
        [
            ([-0.5], [-1]),
            ([0], [-1]),
            ([0.5], [0]),
            ([1], [0]),
            ([1.5], [1]),
            ([2], [1]),
            ([2.5], [-1]),
            ([3], [-1]),
            ([3.5], [2]),
            ([4], [2]),
            ([4.5], [-1]),
            ([1, 2], [0, 1]),
            ([1, 2, 3], [0, 1, -1]),
            ([1, 2, 3, 4], [0, 1, -1, 2]),
            ([1, 2, 3, 4, 2], [0, 1, -1, 2, 1]),
        ],
    )
    def test_get_indexer_with_int_and_float(self, query, expected):
        tuples = [(0, 1), (1, 2), (3, 4)]
        index = IntervalIndex.from_tuples(tuples, closed="right")

        result = index.get_indexer(query)
        expected = np.array(expected, dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize("item", [[3], np.arange(0.5, 5, 0.5)])
    def test_get_indexer_length_one(self, item, closed):
        # GH 17284
        index = IntervalIndex.from_tuples([(0, 5)], closed=closed)
        result = index.get_indexer(item)
        expected = np.array([0] * len(item), dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize("size", [1, 5])
    def test_get_indexer_length_one_interval(self, size, closed):
        # GH 17284
        index = IntervalIndex.from_tuples([(0, 5)], closed=closed)
        result = index.get_indexer([Interval(0, 5, closed)] * size)
        expected = np.array([0] * size, dtype="intp")
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize(
        "target",
        [
            IntervalIndex.from_tuples([(7, 8), (1, 2), (3, 4), (0, 1)]),
            IntervalIndex.from_tuples([(0, 1), (1, 2), (3, 4), np.nan]),
            IntervalIndex.from_tuples([(0, 1), (1, 2), (3, 4)], closed="both"),
            [-1, 0, 0.5, 1, 2, 2.5, np.nan],
            ["foo", "foo", "bar", "baz"],
        ],
    )
    def test_get_indexer_categorical(self, target, ordered):
        # GH 30063: categorical and non-categorical results should be consistent
        index = IntervalIndex.from_tuples([(0, 1), (1, 2), (3, 4)])
        categorical_target = CategoricalIndex(target, ordered=ordered)

        result = index.get_indexer(categorical_target)
        expected = index.get_indexer(target)
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.filterwarnings(
        "ignore:invalid value encountered in cast:RuntimeWarning"
    )
    def test_get_indexer_categorical_with_nans(self):
        # GH#41934 nans in both index and in target
        ii = IntervalIndex.from_breaks(range(5))
        ii2 = ii.append(IntervalIndex([np.nan]))
        ci2 = CategoricalIndex(ii2)

        result = ii2.get_indexer(ci2)
        expected = np.arange(5, dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

        # not-all-matches
        result = ii2[1:].get_indexer(ci2[::-1])
        expected = np.array([3, 2, 1, 0, -1], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

        # non-unique target, non-unique nans
        result = ii2.get_indexer(ci2.append(ci2))
        expected = np.array([0, 1, 2, 3, 4, 0, 1, 2, 3, 4], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

    def test_get_indexer_datetime(self):
        ii = IntervalIndex.from_breaks(date_range("2018-01-01", periods=4))
        # TODO: with mismatched resolution get_indexer currently raises;
        #  this should probably coerce?
        target = DatetimeIndex(["2018-01-02"], dtype="M8[ns]")
        result = ii.get_indexer(target)
        expected = np.array([0], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

        result = ii.get_indexer(target.astype(str))
        tm.assert_numpy_array_equal(result, expected)

        # https://github.com/pandas-dev/pandas/issues/47772
        result = ii.get_indexer(target.asi8)
        expected = np.array([-1], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize(
        "tuples, closed",
        [
            ([(0, 2), (1, 3), (3, 4)], "neither"),
            ([(0, 5), (1, 4), (6, 7)], "left"),
            ([(0, 1), (0, 1), (1, 2)], "right"),
            ([(0, 1), (2, 3), (3, 4)], "both"),
        ],
    )
    def test_get_indexer_errors(self, tuples, closed):
        # IntervalIndex needs non-overlapping for uniqueness when querying
        index = IntervalIndex.from_tuples(tuples, closed=closed)

        msg = (
            "cannot handle overlapping indices; use "
            "IntervalIndex.get_indexer_non_unique"
        )
        with pytest.raises(InvalidIndexError, match=msg):
            index.get_indexer([0, 2])

    @pytest.mark.parametrize(
        "query, expected",
        [
            ([-0.5], ([-1], [0])),
            ([0], ([0], [])),
            ([0.5], ([0], [])),
            ([1], ([0, 1], [])),
            ([1.5], ([0, 1], [])),
            ([2], ([0, 1, 2], [])),
            ([2.5], ([1, 2], [])),
            ([3], ([2], [])),
            ([3.5], ([2], [])),
            ([4], ([-1], [0])),
            ([4.5], ([-1], [0])),
            ([1, 2], ([0, 1, 0, 1, 2], [])),
            ([1, 2, 3], ([0, 1, 0, 1, 2, 2], [])),
            ([1, 2, 3, 4], ([0, 1, 0, 1, 2, 2, -1], [3])),
            ([1, 2, 3, 4, 2], ([0, 1, 0, 1, 2, 2, -1, 0, 1, 2], [3])),
        ],
    )
    def test_get_indexer_non_unique_with_int_and_float(self, query, expected):
        tuples = [(0, 2.5), (1, 3), (2, 4)]
        index = IntervalIndex.from_tuples(tuples, closed="left")

        result_indexer, result_missing = index.get_indexer_non_unique(query)
        expected_indexer = np.array(expected[0], dtype="intp")
        expected_missing = np.array(expected[1], dtype="intp")

        tm.assert_numpy_array_equal(result_indexer, expected_indexer)
        tm.assert_numpy_array_equal(result_missing, expected_missing)

        # TODO we may also want to test get_indexer for the case when
        # the intervals are duplicated, decreasing, non-monotonic, etc..

    def test_get_indexer_non_monotonic(self):
        # GH 16410
        idx1 = IntervalIndex.from_tuples([(2, 3), (4, 5), (0, 1)])
        idx2 = IntervalIndex.from_tuples([(0, 1), (2, 3), (6, 7), (8, 9)])
        result = idx1.get_indexer(idx2)
        expected = np.array([2, 0, -1, -1], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

        result = idx1.get_indexer(idx1[1:])
        expected = np.array([1, 2], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

    def test_get_indexer_with_nans(self):
        # GH#41831
        index = IntervalIndex([np.nan, np.nan])
        other = IntervalIndex([np.nan])

        assert not index._index_as_unique

        result = index.get_indexer_for(other)
        expected = np.array([0, 1], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

    def test_get_index_non_unique_non_monotonic(self):
        # GH#44084 (root cause)
        index = IntervalIndex.from_tuples(
            [(0.0, 1.0), (1.0, 2.0), (0.0, 1.0), (1.0, 2.0)]
        )

        result, _ = index.get_indexer_non_unique([Interval(1.0, 2.0)])
        expected = np.array([1, 3], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

    def test_get_indexer_multiindex_with_intervals(self):
        # GH#44084 (MultiIndex case as reported)
        interval_index = IntervalIndex.from_tuples(
            [(2.0, 3.0), (0.0, 1.0), (1.0, 2.0)], name="interval"
        )
        foo_index = Index([1, 2, 3], name="foo")

        multi_index = MultiIndex.from_product([foo_index, interval_index])

        result = multi_index.get_level_values("interval").get_indexer_for(
            [Interval(0.0, 1.0)]
        )
        expected = np.array([1, 4, 7], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize("box", [IntervalIndex, array, list])
    def test_get_indexer_interval_index(self, box):
        # GH#30178
        rng = period_range("2022-07-01", freq="D", periods=3)
        idx = box(interval_range(Timestamp("2022-07-01"), freq="3D", periods=3))

        actual = rng.get_indexer(idx)
        expected = np.array([-1, -1, -1], dtype=np.intp)
        tm.assert_numpy_array_equal(actual, expected)

    def test_get_indexer_read_only(self):
        idx = interval_range(start=0, end=5)
        arr = np.array([1, 2])
        arr.flags.writeable = False
        result = idx.get_indexer(arr)
        expected = np.array([0, 1])
        tm.assert_numpy_array_equal(result, expected, check_dtype=False)

        result = idx.get_indexer_non_unique(arr)[0]
        tm.assert_numpy_array_equal(result, expected, check_dtype=False)


class TestSliceLocs:
    def test_slice_locs_with_interval(self):
        # increasing monotonically
        index = IntervalIndex.from_tuples([(0, 2), (1, 3), (2, 4)])

        assert index.slice_locs(start=Interval(0, 2), end=Interval(2, 4)) == (0, 3)
        assert index.slice_locs(start=Interval(0, 2)) == (0, 3)
        assert index.slice_locs(end=Interval(2, 4)) == (0, 3)
        assert index.slice_locs(end=Interval(0, 2)) == (0, 1)
        assert index.slice_locs(start=Interval(2, 4), end=Interval(0, 2)) == (2, 1)

        # decreasing monotonically
        index = IntervalIndex.from_tuples([(2, 4), (1, 3), (0, 2)])

        assert index.slice_locs(start=Interval(0, 2), end=Interval(2, 4)) == (2, 1)
        assert index.slice_locs(start=Interval(0, 2)) == (2, 3)
        assert index.slice_locs(end=Interval(2, 4)) == (0, 1)
        assert index.slice_locs(end=Interval(0, 2)) == (0, 3)
        assert index.slice_locs(start=Interval(2, 4), end=Interval(0, 2)) == (0, 3)

        # sorted duplicates
        index = IntervalIndex.from_tuples([(0, 2), (0, 2), (2, 4)])

        assert index.slice_locs(start=Interval(0, 2), end=Interval(2, 4)) == (0, 3)
        assert index.slice_locs(start=Interval(0, 2)) == (0, 3)
        assert index.slice_locs(end=Interval(2, 4)) == (0, 3)
        assert index.slice_locs(end=Interval(0, 2)) == (0, 2)
        assert index.slice_locs(start=Interval(2, 4), end=Interval(0, 2)) == (2, 2)

        # unsorted duplicates
        index = IntervalIndex.from_tuples([(0, 2), (2, 4), (0, 2)])

        with pytest.raises(
            KeyError,
            match=re.escape(
                '"Cannot get left slice bound for non-unique label: '
                "Interval(0, 2, closed='right')\""
            ),
        ):
            index.slice_locs(start=Interval(0, 2), end=Interval(2, 4))

        with pytest.raises(
            KeyError,
            match=re.escape(
                '"Cannot get left slice bound for non-unique label: '
                "Interval(0, 2, closed='right')\""
            ),
        ):
            index.slice_locs(start=Interval(0, 2))

        assert index.slice_locs(end=Interval(2, 4)) == (0, 2)

        with pytest.raises(
            KeyError,
            match=re.escape(
                '"Cannot get right slice bound for non-unique label: '
                "Interval(0, 2, closed='right')\""
            ),
        ):
            index.slice_locs(end=Interval(0, 2))

        with pytest.raises(
            KeyError,
            match=re.escape(
                '"Cannot get right slice bound for non-unique label: '
                "Interval(0, 2, closed='right')\""
            ),
        ):
            index.slice_locs(start=Interval(2, 4), end=Interval(0, 2))

        # another unsorted duplicates
        index = IntervalIndex.from_tuples([(0, 2), (0, 2), (2, 4), (1, 3)])

        assert index.slice_locs(start=Interval(0, 2), end=Interval(2, 4)) == (0, 3)
        assert index.slice_locs(start=Interval(0, 2)) == (0, 4)
        assert index.slice_locs(end=Interval(2, 4)) == (0, 3)
        assert index.slice_locs(end=Interval(0, 2)) == (0, 2)
        assert index.slice_locs(start=Interval(2, 4), end=Interval(0, 2)) == (2, 2)

    def test_slice_locs_with_ints_and_floats_succeeds(self):
        # increasing non-overlapping
        index = IntervalIndex.from_tuples([(0, 1), (1, 2), (3, 4)])

        assert index.slice_locs(0, 1) == (0, 1)
        assert index.slice_locs(0, 2) == (0, 2)
        assert index.slice_locs(0, 3) == (0, 2)
        assert index.slice_locs(3, 1) == (2, 1)
        assert index.slice_locs(3, 4) == (2, 3)
        assert index.slice_locs(0, 4) == (0, 3)

        # decreasing non-overlapping
        index = IntervalIndex.from_tuples([(3, 4), (1, 2), (0, 1)])
        assert index.slice_locs(0, 1) == (3, 3)
        assert index.slice_locs(0, 2) == (3, 2)
        assert index.slice_locs(0, 3) == (3, 1)
        assert index.slice_locs(3, 1) == (1, 3)
        assert index.slice_locs(3, 4) == (1, 1)
        assert index.slice_locs(0, 4) == (3, 1)

    @pytest.mark.parametrize("query", [[0, 1], [0, 2], [0, 3], [0, 4]])
    @pytest.mark.parametrize(
        "tuples",
        [
            [(0, 2), (1, 3), (2, 4)],
            [(2, 4), (1, 3), (0, 2)],
            [(0, 2), (0, 2), (2, 4)],
            [(0, 2), (2, 4), (0, 2)],
            [(0, 2), (0, 2), (2, 4), (1, 3)],
        ],
    )
    def test_slice_locs_with_ints_and_floats_errors(self, tuples, query):
        start, stop = query
        index = IntervalIndex.from_tuples(tuples)
        with pytest.raises(
            KeyError,
            match=(
                "'can only get slices from an IntervalIndex if bounds are "
                "non-overlapping and all monotonic increasing or decreasing'"
            ),
        ):
            index.slice_locs(start, stop)


class TestPutmask:
    @pytest.mark.parametrize("tz", ["US/Pacific", None])
    def test_putmask_dt64(self, tz):
        # GH#37968
        dti = date_range("2016-01-01", periods=9, tz=tz)
        idx = IntervalIndex.from_breaks(dti)
        mask = np.zeros(idx.shape, dtype=bool)
        mask[0:3] = True

        result = idx.putmask(mask, idx[-1])
        expected = IntervalIndex([idx[-1]] * 3 + list(idx[3:]))
        tm.assert_index_equal(result, expected)

    def test_putmask_td64(self):
        # GH#37968
        dti = date_range("2016-01-01", periods=9)
        tdi = dti - dti[0]
        idx = IntervalIndex.from_breaks(tdi)
        mask = np.zeros(idx.shape, dtype=bool)
        mask[0:3] = True

        result = idx.putmask(mask, idx[-1])
        expected = IntervalIndex([idx[-1]] * 3 + list(idx[3:]))
        tm.assert_index_equal(result, expected)


class TestContains:
    # .__contains__, not .contains

    def test_contains_dunder(self):
        index = IntervalIndex.from_arrays([0, 1], [1, 2], closed="right")

        # __contains__ requires perfect matches to intervals.
        assert 0 not in index
        assert 1 not in index
        assert 2 not in index

        assert Interval(0, 1, closed="right") in index
        assert Interval(0, 2, closed="right") not in index
        assert Interval(0, 0.5, closed="right") not in index
        assert Interval(3, 5, closed="right") not in index
        assert Interval(-1, 0, closed="left") not in index
        assert Interval(0, 1, closed="left") not in index
        assert Interval(0, 1, closed="both") not in index
