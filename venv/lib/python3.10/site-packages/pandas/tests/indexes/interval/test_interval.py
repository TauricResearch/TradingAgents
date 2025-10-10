from itertools import permutations
import re

import numpy as np
import pytest

import pandas as pd
from pandas import (
    Index,
    Interval,
    IntervalIndex,
    Timedelta,
    Timestamp,
    date_range,
    interval_range,
    isna,
    notna,
    timedelta_range,
)
import pandas._testing as tm
import pandas.core.common as com


@pytest.fixture(params=[None, "foo"])
def name(request):
    return request.param


class TestIntervalIndex:
    index = IntervalIndex.from_arrays([0, 1], [1, 2])

    def create_index(self, closed="right"):
        return IntervalIndex.from_breaks(range(11), closed=closed)

    def create_index_with_nan(self, closed="right"):
        mask = [True, False] + [True] * 8
        return IntervalIndex.from_arrays(
            np.where(mask, np.arange(10), np.nan),
            np.where(mask, np.arange(1, 11), np.nan),
            closed=closed,
        )

    def test_properties(self, closed):
        index = self.create_index(closed=closed)
        assert len(index) == 10
        assert index.size == 10
        assert index.shape == (10,)

        tm.assert_index_equal(index.left, Index(np.arange(10, dtype=np.int64)))
        tm.assert_index_equal(index.right, Index(np.arange(1, 11, dtype=np.int64)))
        tm.assert_index_equal(index.mid, Index(np.arange(0.5, 10.5, dtype=np.float64)))

        assert index.closed == closed

        ivs = [
            Interval(left, right, closed)
            for left, right in zip(range(10), range(1, 11))
        ]
        expected = np.array(ivs, dtype=object)
        tm.assert_numpy_array_equal(np.asarray(index), expected)

        # with nans
        index = self.create_index_with_nan(closed=closed)
        assert len(index) == 10
        assert index.size == 10
        assert index.shape == (10,)

        expected_left = Index([0, np.nan, 2, 3, 4, 5, 6, 7, 8, 9])
        expected_right = expected_left + 1
        expected_mid = expected_left + 0.5
        tm.assert_index_equal(index.left, expected_left)
        tm.assert_index_equal(index.right, expected_right)
        tm.assert_index_equal(index.mid, expected_mid)

        assert index.closed == closed

        ivs = [
            Interval(left, right, closed) if notna(left) else np.nan
            for left, right in zip(expected_left, expected_right)
        ]
        expected = np.array(ivs, dtype=object)
        tm.assert_numpy_array_equal(np.asarray(index), expected)

    @pytest.mark.parametrize(
        "breaks",
        [
            [1, 1, 2, 5, 15, 53, 217, 1014, 5335, 31240, 201608],
            [-np.inf, -100, -10, 0.5, 1, 1.5, 3.8, 101, 202, np.inf],
            date_range("2017-01-01", "2017-01-04"),
            pytest.param(
                date_range("2017-01-01", "2017-01-04", unit="s"),
                marks=pytest.mark.xfail(reason="mismatched result unit"),
            ),
            pd.to_timedelta(["1ns", "2ms", "3s", "4min", "5h", "6D"]),
        ],
    )
    def test_length(self, closed, breaks):
        # GH 18789
        index = IntervalIndex.from_breaks(breaks, closed=closed)
        result = index.length
        expected = Index(iv.length for iv in index)
        tm.assert_index_equal(result, expected)

        # with NA
        index = index.insert(1, np.nan)
        result = index.length
        expected = Index(iv.length if notna(iv) else iv for iv in index)
        tm.assert_index_equal(result, expected)

    def test_with_nans(self, closed):
        index = self.create_index(closed=closed)
        assert index.hasnans is False

        result = index.isna()
        expected = np.zeros(len(index), dtype=bool)
        tm.assert_numpy_array_equal(result, expected)

        result = index.notna()
        expected = np.ones(len(index), dtype=bool)
        tm.assert_numpy_array_equal(result, expected)

        index = self.create_index_with_nan(closed=closed)
        assert index.hasnans is True

        result = index.isna()
        expected = np.array([False, True] + [False] * (len(index) - 2))
        tm.assert_numpy_array_equal(result, expected)

        result = index.notna()
        expected = np.array([True, False] + [True] * (len(index) - 2))
        tm.assert_numpy_array_equal(result, expected)

    def test_copy(self, closed):
        expected = self.create_index(closed=closed)

        result = expected.copy()
        assert result.equals(expected)

        result = expected.copy(deep=True)
        assert result.equals(expected)
        assert result.left is not expected.left

    def test_ensure_copied_data(self, closed):
        # exercise the copy flag in the constructor

        # not copying
        index = self.create_index(closed=closed)
        result = IntervalIndex(index, copy=False)
        tm.assert_numpy_array_equal(
            index.left.values, result.left.values, check_same="same"
        )
        tm.assert_numpy_array_equal(
            index.right.values, result.right.values, check_same="same"
        )

        # by-definition make a copy
        result = IntervalIndex(np.array(index), copy=False)
        tm.assert_numpy_array_equal(
            index.left.values, result.left.values, check_same="copy"
        )
        tm.assert_numpy_array_equal(
            index.right.values, result.right.values, check_same="copy"
        )

    def test_delete(self, closed):
        breaks = np.arange(1, 11, dtype=np.int64)
        expected = IntervalIndex.from_breaks(breaks, closed=closed)
        result = self.create_index(closed=closed).delete(0)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "data",
        [
            interval_range(0, periods=10, closed="neither"),
            interval_range(1.7, periods=8, freq=2.5, closed="both"),
            interval_range(Timestamp("20170101"), periods=12, closed="left"),
            interval_range(Timedelta("1 day"), periods=6, closed="right"),
        ],
    )
    def test_insert(self, data):
        item = data[0]
        idx_item = IntervalIndex([item])

        # start
        expected = idx_item.append(data)
        result = data.insert(0, item)
        tm.assert_index_equal(result, expected)

        # end
        expected = data.append(idx_item)
        result = data.insert(len(data), item)
        tm.assert_index_equal(result, expected)

        # mid
        expected = data[:3].append(idx_item).append(data[3:])
        result = data.insert(3, item)
        tm.assert_index_equal(result, expected)

        # invalid type
        res = data.insert(1, "foo")
        expected = data.astype(object).insert(1, "foo")
        tm.assert_index_equal(res, expected)

        msg = "can only insert Interval objects and NA into an IntervalArray"
        with pytest.raises(TypeError, match=msg):
            data._data.insert(1, "foo")

        # invalid closed
        msg = "'value.closed' is 'left', expected 'right'."
        for closed in {"left", "right", "both", "neither"} - {item.closed}:
            msg = f"'value.closed' is '{closed}', expected '{item.closed}'."
            bad_item = Interval(item.left, item.right, closed=closed)
            res = data.insert(1, bad_item)
            expected = data.astype(object).insert(1, bad_item)
            tm.assert_index_equal(res, expected)
            with pytest.raises(ValueError, match=msg):
                data._data.insert(1, bad_item)

        # GH 18295 (test missing)
        na_idx = IntervalIndex([np.nan], closed=data.closed)
        for na in [np.nan, None, pd.NA]:
            expected = data[:1].append(na_idx).append(data[1:])
            result = data.insert(1, na)
            tm.assert_index_equal(result, expected)

        if data.left.dtype.kind not in ["m", "M"]:
            # trying to insert pd.NaT into a numeric-dtyped Index should cast
            expected = data.astype(object).insert(1, pd.NaT)

            msg = "can only insert Interval objects and NA into an IntervalArray"
            with pytest.raises(TypeError, match=msg):
                data._data.insert(1, pd.NaT)

        result = data.insert(1, pd.NaT)
        tm.assert_index_equal(result, expected)

    def test_is_unique_interval(self, closed):
        """
        Interval specific tests for is_unique in addition to base class tests
        """
        # unique overlapping - distinct endpoints
        idx = IntervalIndex.from_tuples([(0, 1), (0.5, 1.5)], closed=closed)
        assert idx.is_unique is True

        # unique overlapping - shared endpoints
        idx = IntervalIndex.from_tuples([(1, 2), (1, 3), (2, 3)], closed=closed)
        assert idx.is_unique is True

        # unique nested
        idx = IntervalIndex.from_tuples([(-1, 1), (-2, 2)], closed=closed)
        assert idx.is_unique is True

        # unique NaN
        idx = IntervalIndex.from_tuples([(np.nan, np.nan)], closed=closed)
        assert idx.is_unique is True

        # non-unique NaN
        idx = IntervalIndex.from_tuples(
            [(np.nan, np.nan), (np.nan, np.nan)], closed=closed
        )
        assert idx.is_unique is False

    def test_monotonic(self, closed):
        # increasing non-overlapping
        idx = IntervalIndex.from_tuples([(0, 1), (2, 3), (4, 5)], closed=closed)
        assert idx.is_monotonic_increasing is True
        assert idx._is_strictly_monotonic_increasing is True
        assert idx.is_monotonic_decreasing is False
        assert idx._is_strictly_monotonic_decreasing is False

        # decreasing non-overlapping
        idx = IntervalIndex.from_tuples([(4, 5), (2, 3), (1, 2)], closed=closed)
        assert idx.is_monotonic_increasing is False
        assert idx._is_strictly_monotonic_increasing is False
        assert idx.is_monotonic_decreasing is True
        assert idx._is_strictly_monotonic_decreasing is True

        # unordered non-overlapping
        idx = IntervalIndex.from_tuples([(0, 1), (4, 5), (2, 3)], closed=closed)
        assert idx.is_monotonic_increasing is False
        assert idx._is_strictly_monotonic_increasing is False
        assert idx.is_monotonic_decreasing is False
        assert idx._is_strictly_monotonic_decreasing is False

        # increasing overlapping
        idx = IntervalIndex.from_tuples([(0, 2), (0.5, 2.5), (1, 3)], closed=closed)
        assert idx.is_monotonic_increasing is True
        assert idx._is_strictly_monotonic_increasing is True
        assert idx.is_monotonic_decreasing is False
        assert idx._is_strictly_monotonic_decreasing is False

        # decreasing overlapping
        idx = IntervalIndex.from_tuples([(1, 3), (0.5, 2.5), (0, 2)], closed=closed)
        assert idx.is_monotonic_increasing is False
        assert idx._is_strictly_monotonic_increasing is False
        assert idx.is_monotonic_decreasing is True
        assert idx._is_strictly_monotonic_decreasing is True

        # unordered overlapping
        idx = IntervalIndex.from_tuples([(0.5, 2.5), (0, 2), (1, 3)], closed=closed)
        assert idx.is_monotonic_increasing is False
        assert idx._is_strictly_monotonic_increasing is False
        assert idx.is_monotonic_decreasing is False
        assert idx._is_strictly_monotonic_decreasing is False

        # increasing overlapping shared endpoints
        idx = IntervalIndex.from_tuples([(1, 2), (1, 3), (2, 3)], closed=closed)
        assert idx.is_monotonic_increasing is True
        assert idx._is_strictly_monotonic_increasing is True
        assert idx.is_monotonic_decreasing is False
        assert idx._is_strictly_monotonic_decreasing is False

        # decreasing overlapping shared endpoints
        idx = IntervalIndex.from_tuples([(2, 3), (1, 3), (1, 2)], closed=closed)
        assert idx.is_monotonic_increasing is False
        assert idx._is_strictly_monotonic_increasing is False
        assert idx.is_monotonic_decreasing is True
        assert idx._is_strictly_monotonic_decreasing is True

        # stationary
        idx = IntervalIndex.from_tuples([(0, 1), (0, 1)], closed=closed)
        assert idx.is_monotonic_increasing is True
        assert idx._is_strictly_monotonic_increasing is False
        assert idx.is_monotonic_decreasing is True
        assert idx._is_strictly_monotonic_decreasing is False

        # empty
        idx = IntervalIndex([], closed=closed)
        assert idx.is_monotonic_increasing is True
        assert idx._is_strictly_monotonic_increasing is True
        assert idx.is_monotonic_decreasing is True
        assert idx._is_strictly_monotonic_decreasing is True

    def test_is_monotonic_with_nans(self):
        # GH#41831
        index = IntervalIndex([np.nan, np.nan])

        assert not index.is_monotonic_increasing
        assert not index._is_strictly_monotonic_increasing
        assert not index.is_monotonic_increasing
        assert not index._is_strictly_monotonic_decreasing
        assert not index.is_monotonic_decreasing

    @pytest.mark.parametrize(
        "breaks",
        [
            date_range("20180101", periods=4),
            date_range("20180101", periods=4, tz="US/Eastern"),
            timedelta_range("0 days", periods=4),
        ],
        ids=lambda x: str(x.dtype),
    )
    def test_maybe_convert_i8(self, breaks):
        # GH 20636
        index = IntervalIndex.from_breaks(breaks)

        # intervalindex
        result = index._maybe_convert_i8(index)
        expected = IntervalIndex.from_breaks(breaks.asi8)
        tm.assert_index_equal(result, expected)

        # interval
        interval = Interval(breaks[0], breaks[1])
        result = index._maybe_convert_i8(interval)
        expected = Interval(breaks[0]._value, breaks[1]._value)
        assert result == expected

        # datetimelike index
        result = index._maybe_convert_i8(breaks)
        expected = Index(breaks.asi8)
        tm.assert_index_equal(result, expected)

        # datetimelike scalar
        result = index._maybe_convert_i8(breaks[0])
        expected = breaks[0]._value
        assert result == expected

        # list-like of datetimelike scalars
        result = index._maybe_convert_i8(list(breaks))
        expected = Index(breaks.asi8)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "breaks",
        [date_range("2018-01-01", periods=5), timedelta_range("0 days", periods=5)],
    )
    def test_maybe_convert_i8_nat(self, breaks):
        # GH 20636
        index = IntervalIndex.from_breaks(breaks)

        to_convert = breaks._constructor([pd.NaT] * 3).as_unit("ns")
        expected = Index([np.nan] * 3, dtype=np.float64)
        result = index._maybe_convert_i8(to_convert)
        tm.assert_index_equal(result, expected)

        to_convert = to_convert.insert(0, breaks[0])
        expected = expected.insert(0, float(breaks[0]._value))
        result = index._maybe_convert_i8(to_convert)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "make_key",
        [lambda breaks: breaks, list],
        ids=["lambda", "list"],
    )
    def test_maybe_convert_i8_numeric(self, make_key, any_real_numpy_dtype):
        # GH 20636
        breaks = np.arange(5, dtype=any_real_numpy_dtype)
        index = IntervalIndex.from_breaks(breaks)
        key = make_key(breaks)

        result = index._maybe_convert_i8(key)
        kind = breaks.dtype.kind
        expected_dtype = {"i": np.int64, "u": np.uint64, "f": np.float64}[kind]
        expected = Index(key, dtype=expected_dtype)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "make_key",
        [
            IntervalIndex.from_breaks,
            lambda breaks: Interval(breaks[0], breaks[1]),
            lambda breaks: breaks[0],
        ],
        ids=["IntervalIndex", "Interval", "scalar"],
    )
    def test_maybe_convert_i8_numeric_identical(self, make_key, any_real_numpy_dtype):
        # GH 20636
        breaks = np.arange(5, dtype=any_real_numpy_dtype)
        index = IntervalIndex.from_breaks(breaks)
        key = make_key(breaks)

        # test if _maybe_convert_i8 won't change key if an Interval or IntervalIndex
        result = index._maybe_convert_i8(key)
        assert result is key

    @pytest.mark.parametrize(
        "breaks1, breaks2",
        permutations(
            [
                date_range("20180101", periods=4),
                date_range("20180101", periods=4, tz="US/Eastern"),
                timedelta_range("0 days", periods=4),
            ],
            2,
        ),
        ids=lambda x: str(x.dtype),
    )
    @pytest.mark.parametrize(
        "make_key",
        [
            IntervalIndex.from_breaks,
            lambda breaks: Interval(breaks[0], breaks[1]),
            lambda breaks: breaks,
            lambda breaks: breaks[0],
            list,
        ],
        ids=["IntervalIndex", "Interval", "Index", "scalar", "list"],
    )
    def test_maybe_convert_i8_errors(self, breaks1, breaks2, make_key):
        # GH 20636
        index = IntervalIndex.from_breaks(breaks1)
        key = make_key(breaks2)

        msg = (
            f"Cannot index an IntervalIndex of subtype {breaks1.dtype} with "
            f"values of dtype {breaks2.dtype}"
        )
        msg = re.escape(msg)
        with pytest.raises(ValueError, match=msg):
            index._maybe_convert_i8(key)

    def test_contains_method(self):
        # can select values that are IN the range of a value
        i = IntervalIndex.from_arrays([0, 1], [1, 2])

        expected = np.array([False, False], dtype="bool")
        actual = i.contains(0)
        tm.assert_numpy_array_equal(actual, expected)
        actual = i.contains(3)
        tm.assert_numpy_array_equal(actual, expected)

        expected = np.array([True, False], dtype="bool")
        actual = i.contains(0.5)
        tm.assert_numpy_array_equal(actual, expected)
        actual = i.contains(1)
        tm.assert_numpy_array_equal(actual, expected)

        # __contains__ not implemented for "interval in interval", follow
        # that for the contains method for now
        with pytest.raises(
            NotImplementedError, match="contains not implemented for two"
        ):
            i.contains(Interval(0, 1))

    def test_dropna(self, closed):
        expected = IntervalIndex.from_tuples([(0.0, 1.0), (1.0, 2.0)], closed=closed)

        ii = IntervalIndex.from_tuples([(0, 1), (1, 2), np.nan], closed=closed)
        result = ii.dropna()
        tm.assert_index_equal(result, expected)

        ii = IntervalIndex.from_arrays([0, 1, np.nan], [1, 2, np.nan], closed=closed)
        result = ii.dropna()
        tm.assert_index_equal(result, expected)

    def test_non_contiguous(self, closed):
        index = IntervalIndex.from_tuples([(0, 1), (2, 3)], closed=closed)
        target = [0.5, 1.5, 2.5]
        actual = index.get_indexer(target)
        expected = np.array([0, -1, 1], dtype="intp")
        tm.assert_numpy_array_equal(actual, expected)

        assert 1.5 not in index

    def test_isin(self, closed):
        index = self.create_index(closed=closed)

        expected = np.array([True] + [False] * (len(index) - 1))
        result = index.isin(index[:1])
        tm.assert_numpy_array_equal(result, expected)

        result = index.isin([index[0]])
        tm.assert_numpy_array_equal(result, expected)

        other = IntervalIndex.from_breaks(np.arange(-2, 10), closed=closed)
        expected = np.array([True] * (len(index) - 1) + [False])
        result = index.isin(other)
        tm.assert_numpy_array_equal(result, expected)

        result = index.isin(other.tolist())
        tm.assert_numpy_array_equal(result, expected)

        for other_closed in ["right", "left", "both", "neither"]:
            other = self.create_index(closed=other_closed)
            expected = np.repeat(closed == other_closed, len(index))
            result = index.isin(other)
            tm.assert_numpy_array_equal(result, expected)

            result = index.isin(other.tolist())
            tm.assert_numpy_array_equal(result, expected)

    def test_comparison(self):
        actual = Interval(0, 1) < self.index
        expected = np.array([False, True])
        tm.assert_numpy_array_equal(actual, expected)

        actual = Interval(0.5, 1.5) < self.index
        expected = np.array([False, True])
        tm.assert_numpy_array_equal(actual, expected)
        actual = self.index > Interval(0.5, 1.5)
        tm.assert_numpy_array_equal(actual, expected)

        actual = self.index == self.index
        expected = np.array([True, True])
        tm.assert_numpy_array_equal(actual, expected)
        actual = self.index <= self.index
        tm.assert_numpy_array_equal(actual, expected)
        actual = self.index >= self.index
        tm.assert_numpy_array_equal(actual, expected)

        actual = self.index < self.index
        expected = np.array([False, False])
        tm.assert_numpy_array_equal(actual, expected)
        actual = self.index > self.index
        tm.assert_numpy_array_equal(actual, expected)

        actual = self.index == IntervalIndex.from_breaks([0, 1, 2], "left")
        tm.assert_numpy_array_equal(actual, expected)

        actual = self.index == self.index.values
        tm.assert_numpy_array_equal(actual, np.array([True, True]))
        actual = self.index.values == self.index
        tm.assert_numpy_array_equal(actual, np.array([True, True]))
        actual = self.index <= self.index.values
        tm.assert_numpy_array_equal(actual, np.array([True, True]))
        actual = self.index != self.index.values
        tm.assert_numpy_array_equal(actual, np.array([False, False]))
        actual = self.index > self.index.values
        tm.assert_numpy_array_equal(actual, np.array([False, False]))
        actual = self.index.values > self.index
        tm.assert_numpy_array_equal(actual, np.array([False, False]))

        # invalid comparisons
        actual = self.index == 0
        tm.assert_numpy_array_equal(actual, np.array([False, False]))
        actual = self.index == self.index.left
        tm.assert_numpy_array_equal(actual, np.array([False, False]))

        msg = "|".join(
            [
                "not supported between instances of 'int' and '.*.Interval'",
                r"Invalid comparison between dtype=interval\[int64, right\] and ",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            self.index > 0
        with pytest.raises(TypeError, match=msg):
            self.index <= 0
        with pytest.raises(TypeError, match=msg):
            self.index > np.arange(2)

        msg = "Lengths must match to compare"
        with pytest.raises(ValueError, match=msg):
            self.index > np.arange(3)

    def test_missing_values(self, closed):
        idx = Index(
            [np.nan, Interval(0, 1, closed=closed), Interval(1, 2, closed=closed)]
        )
        idx2 = IntervalIndex.from_arrays([np.nan, 0, 1], [np.nan, 1, 2], closed=closed)
        assert idx.equals(idx2)

        msg = (
            "missing values must be missing in the same location both left "
            "and right sides"
        )
        with pytest.raises(ValueError, match=msg):
            IntervalIndex.from_arrays(
                [np.nan, 0, 1], np.array([0, 1, 2]), closed=closed
            )

        tm.assert_numpy_array_equal(isna(idx), np.array([True, False, False]))

    def test_sort_values(self, closed):
        index = self.create_index(closed=closed)

        result = index.sort_values()
        tm.assert_index_equal(result, index)

        result = index.sort_values(ascending=False)
        tm.assert_index_equal(result, index[::-1])

        # with nan
        index = IntervalIndex([Interval(1, 2), np.nan, Interval(0, 1)])

        result = index.sort_values()
        expected = IntervalIndex([Interval(0, 1), Interval(1, 2), np.nan])
        tm.assert_index_equal(result, expected)

        result = index.sort_values(ascending=False, na_position="first")
        expected = IntervalIndex([np.nan, Interval(1, 2), Interval(0, 1)])
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("tz", [None, "US/Eastern"])
    def test_datetime(self, tz):
        start = Timestamp("2000-01-01", tz=tz)
        dates = date_range(start=start, periods=10)
        index = IntervalIndex.from_breaks(dates)

        # test mid
        start = Timestamp("2000-01-01T12:00", tz=tz)
        expected = date_range(start=start, periods=9)
        tm.assert_index_equal(index.mid, expected)

        # __contains__ doesn't check individual points
        assert Timestamp("2000-01-01", tz=tz) not in index
        assert Timestamp("2000-01-01T12", tz=tz) not in index
        assert Timestamp("2000-01-02", tz=tz) not in index
        iv_true = Interval(
            Timestamp("2000-01-02", tz=tz), Timestamp("2000-01-03", tz=tz)
        )
        iv_false = Interval(
            Timestamp("1999-12-31", tz=tz), Timestamp("2000-01-01", tz=tz)
        )
        assert iv_true in index
        assert iv_false not in index

        # .contains does check individual points
        assert not index.contains(Timestamp("2000-01-01", tz=tz)).any()
        assert index.contains(Timestamp("2000-01-01T12", tz=tz)).any()
        assert index.contains(Timestamp("2000-01-02", tz=tz)).any()

        # test get_indexer
        start = Timestamp("1999-12-31T12:00", tz=tz)
        target = date_range(start=start, periods=7, freq="12h")
        actual = index.get_indexer(target)
        expected = np.array([-1, -1, 0, 0, 1, 1, 2], dtype="intp")
        tm.assert_numpy_array_equal(actual, expected)

        start = Timestamp("2000-01-08T18:00", tz=tz)
        target = date_range(start=start, periods=7, freq="6h")
        actual = index.get_indexer(target)
        expected = np.array([7, 7, 8, 8, 8, 8, -1], dtype="intp")
        tm.assert_numpy_array_equal(actual, expected)

    def test_append(self, closed):
        index1 = IntervalIndex.from_arrays([0, 1], [1, 2], closed=closed)
        index2 = IntervalIndex.from_arrays([1, 2], [2, 3], closed=closed)

        result = index1.append(index2)
        expected = IntervalIndex.from_arrays([0, 1, 1, 2], [1, 2, 2, 3], closed=closed)
        tm.assert_index_equal(result, expected)

        result = index1.append([index1, index2])
        expected = IntervalIndex.from_arrays(
            [0, 1, 0, 1, 1, 2], [1, 2, 1, 2, 2, 3], closed=closed
        )
        tm.assert_index_equal(result, expected)

        for other_closed in {"left", "right", "both", "neither"} - {closed}:
            index_other_closed = IntervalIndex.from_arrays(
                [0, 1], [1, 2], closed=other_closed
            )
            result = index1.append(index_other_closed)
            expected = index1.astype(object).append(index_other_closed.astype(object))
            tm.assert_index_equal(result, expected)

    def test_is_non_overlapping_monotonic(self, closed):
        # Should be True in all cases
        tpls = [(0, 1), (2, 3), (4, 5), (6, 7)]
        idx = IntervalIndex.from_tuples(tpls, closed=closed)
        assert idx.is_non_overlapping_monotonic is True

        idx = IntervalIndex.from_tuples(tpls[::-1], closed=closed)
        assert idx.is_non_overlapping_monotonic is True

        # Should be False in all cases (overlapping)
        tpls = [(0, 2), (1, 3), (4, 5), (6, 7)]
        idx = IntervalIndex.from_tuples(tpls, closed=closed)
        assert idx.is_non_overlapping_monotonic is False

        idx = IntervalIndex.from_tuples(tpls[::-1], closed=closed)
        assert idx.is_non_overlapping_monotonic is False

        # Should be False in all cases (non-monotonic)
        tpls = [(0, 1), (2, 3), (6, 7), (4, 5)]
        idx = IntervalIndex.from_tuples(tpls, closed=closed)
        assert idx.is_non_overlapping_monotonic is False

        idx = IntervalIndex.from_tuples(tpls[::-1], closed=closed)
        assert idx.is_non_overlapping_monotonic is False

        # Should be False for closed='both', otherwise True (GH16560)
        if closed == "both":
            idx = IntervalIndex.from_breaks(range(4), closed=closed)
            assert idx.is_non_overlapping_monotonic is False
        else:
            idx = IntervalIndex.from_breaks(range(4), closed=closed)
            assert idx.is_non_overlapping_monotonic is True

    @pytest.mark.parametrize(
        "start, shift, na_value",
        [
            (0, 1, np.nan),
            (Timestamp("2018-01-01"), Timedelta("1 day"), pd.NaT),
            (Timedelta("0 days"), Timedelta("1 day"), pd.NaT),
        ],
    )
    def test_is_overlapping(self, start, shift, na_value, closed):
        # GH 23309
        # see test_interval_tree.py for extensive tests; interface tests here

        # non-overlapping
        tuples = [(start + n * shift, start + (n + 1) * shift) for n in (0, 2, 4)]
        index = IntervalIndex.from_tuples(tuples, closed=closed)
        assert index.is_overlapping is False

        # non-overlapping with NA
        tuples = [(na_value, na_value)] + tuples + [(na_value, na_value)]
        index = IntervalIndex.from_tuples(tuples, closed=closed)
        assert index.is_overlapping is False

        # overlapping
        tuples = [(start + n * shift, start + (n + 2) * shift) for n in range(3)]
        index = IntervalIndex.from_tuples(tuples, closed=closed)
        assert index.is_overlapping is True

        # overlapping with NA
        tuples = [(na_value, na_value)] + tuples + [(na_value, na_value)]
        index = IntervalIndex.from_tuples(tuples, closed=closed)
        assert index.is_overlapping is True

        # common endpoints
        tuples = [(start + n * shift, start + (n + 1) * shift) for n in range(3)]
        index = IntervalIndex.from_tuples(tuples, closed=closed)
        result = index.is_overlapping
        expected = closed == "both"
        assert result is expected

        # common endpoints with NA
        tuples = [(na_value, na_value)] + tuples + [(na_value, na_value)]
        index = IntervalIndex.from_tuples(tuples, closed=closed)
        result = index.is_overlapping
        assert result is expected

        # intervals with duplicate left values
        a = [10, 15, 20, 25, 30, 35, 40, 45, 45, 50, 55, 60, 65, 70, 75, 80, 85]
        b = [15, 20, 25, 30, 35, 40, 45, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90]
        index = IntervalIndex.from_arrays(a, b, closed="right")
        result = index.is_overlapping
        assert result is False

    @pytest.mark.parametrize(
        "tuples",
        [
            list(zip(range(10), range(1, 11))),
            list(
                zip(
                    date_range("20170101", periods=10),
                    date_range("20170101", periods=10),
                )
            ),
            list(
                zip(
                    timedelta_range("0 days", periods=10),
                    timedelta_range("1 day", periods=10),
                )
            ),
        ],
    )
    def test_to_tuples(self, tuples):
        # GH 18756
        idx = IntervalIndex.from_tuples(tuples)
        result = idx.to_tuples()
        expected = Index(com.asarray_tuplesafe(tuples))
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "tuples",
        [
            list(zip(range(10), range(1, 11))) + [np.nan],
            list(
                zip(
                    date_range("20170101", periods=10),
                    date_range("20170101", periods=10),
                )
            )
            + [np.nan],
            list(
                zip(
                    timedelta_range("0 days", periods=10),
                    timedelta_range("1 day", periods=10),
                )
            )
            + [np.nan],
        ],
    )
    @pytest.mark.parametrize("na_tuple", [True, False])
    def test_to_tuples_na(self, tuples, na_tuple):
        # GH 18756
        idx = IntervalIndex.from_tuples(tuples)
        result = idx.to_tuples(na_tuple=na_tuple)

        # check the non-NA portion
        expected_notna = Index(com.asarray_tuplesafe(tuples[:-1]))
        result_notna = result[:-1]
        tm.assert_index_equal(result_notna, expected_notna)

        # check the NA portion
        result_na = result[-1]
        if na_tuple:
            assert isinstance(result_na, tuple)
            assert len(result_na) == 2
            assert all(isna(x) for x in result_na)
        else:
            assert isna(result_na)

    def test_nbytes(self):
        # GH 19209
        left = np.arange(0, 4, dtype="i8")
        right = np.arange(1, 5, dtype="i8")

        result = IntervalIndex.from_arrays(left, right).nbytes
        expected = 64  # 4 * 8 * 2
        assert result == expected

    @pytest.mark.parametrize("new_closed", ["left", "right", "both", "neither"])
    def test_set_closed(self, name, closed, new_closed):
        # GH 21670
        index = interval_range(0, 5, closed=closed, name=name)
        result = index.set_closed(new_closed)
        expected = interval_range(0, 5, closed=new_closed, name=name)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("bad_closed", ["foo", 10, "LEFT", True, False])
    def test_set_closed_errors(self, bad_closed):
        # GH 21670
        index = interval_range(0, 5)
        msg = f"invalid option for 'closed': {bad_closed}"
        with pytest.raises(ValueError, match=msg):
            index.set_closed(bad_closed)

    def test_is_all_dates(self):
        # GH 23576
        year_2017 = Interval(
            Timestamp("2017-01-01 00:00:00"), Timestamp("2018-01-01 00:00:00")
        )
        year_2017_index = IntervalIndex([year_2017])
        assert not year_2017_index._is_all_dates


def test_dir():
    # GH#27571 dir(interval_index) should not raise
    index = IntervalIndex.from_arrays([0, 1], [1, 2])
    result = dir(index)
    assert "str" not in result


def test_searchsorted_different_argument_classes(listlike_box):
    # https://github.com/pandas-dev/pandas/issues/32762
    values = IntervalIndex([Interval(0, 1), Interval(1, 2)])
    result = values.searchsorted(listlike_box(values))
    expected = np.array([0, 1], dtype=result.dtype)
    tm.assert_numpy_array_equal(result, expected)

    result = values._data.searchsorted(listlike_box(values))
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize(
    "arg", [[1, 2], ["a", "b"], [Timestamp("2020-01-01", tz="Europe/London")] * 2]
)
def test_searchsorted_invalid_argument(arg):
    values = IntervalIndex([Interval(0, 1), Interval(1, 2)])
    msg = "'<' not supported between instances of 'pandas._libs.interval.Interval' and "
    with pytest.raises(TypeError, match=msg):
        values.searchsorted(arg)
