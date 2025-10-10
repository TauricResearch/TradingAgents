import numpy as np
import pytest

from pandas import (
    DatetimeIndex,
    IntervalIndex,
    MultiIndex,
    Series,
)
import pandas._testing as tm


@pytest.fixture(params=["quicksort", "mergesort", "heapsort", "stable"])
def sort_kind(request):
    return request.param


class TestSeriesSortIndex:
    def test_sort_index_name(self, datetime_series):
        result = datetime_series.sort_index(ascending=False)
        assert result.name == datetime_series.name

    def test_sort_index(self, datetime_series):
        datetime_series.index = datetime_series.index._with_freq(None)

        rindex = list(datetime_series.index)
        np.random.default_rng(2).shuffle(rindex)

        random_order = datetime_series.reindex(rindex)
        sorted_series = random_order.sort_index()
        tm.assert_series_equal(sorted_series, datetime_series)

        # descending
        sorted_series = random_order.sort_index(ascending=False)
        tm.assert_series_equal(
            sorted_series, datetime_series.reindex(datetime_series.index[::-1])
        )

        # compat on level
        sorted_series = random_order.sort_index(level=0)
        tm.assert_series_equal(sorted_series, datetime_series)

        # compat on axis
        sorted_series = random_order.sort_index(axis=0)
        tm.assert_series_equal(sorted_series, datetime_series)

        msg = "No axis named 1 for object type Series"
        with pytest.raises(ValueError, match=msg):
            random_order.sort_values(axis=1)

        sorted_series = random_order.sort_index(level=0, axis=0)
        tm.assert_series_equal(sorted_series, datetime_series)

        with pytest.raises(ValueError, match=msg):
            random_order.sort_index(level=0, axis=1)

    def test_sort_index_inplace(self, datetime_series):
        datetime_series.index = datetime_series.index._with_freq(None)

        # For GH#11402
        rindex = list(datetime_series.index)
        np.random.default_rng(2).shuffle(rindex)

        # descending
        random_order = datetime_series.reindex(rindex)
        result = random_order.sort_index(ascending=False, inplace=True)

        assert result is None
        expected = datetime_series.reindex(datetime_series.index[::-1])
        expected.index = expected.index._with_freq(None)
        tm.assert_series_equal(random_order, expected)

        # ascending
        random_order = datetime_series.reindex(rindex)
        result = random_order.sort_index(ascending=True, inplace=True)

        assert result is None
        expected = datetime_series.copy()
        expected.index = expected.index._with_freq(None)
        tm.assert_series_equal(random_order, expected)

    def test_sort_index_level(self):
        mi = MultiIndex.from_tuples([[1, 1, 3], [1, 1, 1]], names=list("ABC"))
        s = Series([1, 2], mi)
        backwards = s.iloc[[1, 0]]

        res = s.sort_index(level="A")
        tm.assert_series_equal(backwards, res)

        res = s.sort_index(level=["A", "B"])
        tm.assert_series_equal(backwards, res)

        res = s.sort_index(level="A", sort_remaining=False)
        tm.assert_series_equal(s, res)

        res = s.sort_index(level=["A", "B"], sort_remaining=False)
        tm.assert_series_equal(s, res)

    @pytest.mark.parametrize("level", ["A", 0])  # GH#21052
    def test_sort_index_multiindex(self, level):
        mi = MultiIndex.from_tuples([[1, 1, 3], [1, 1, 1]], names=list("ABC"))
        s = Series([1, 2], mi)
        backwards = s.iloc[[1, 0]]

        # implicit sort_remaining=True
        res = s.sort_index(level=level)
        tm.assert_series_equal(backwards, res)

        # GH#13496
        # sort has no effect without remaining lvls
        res = s.sort_index(level=level, sort_remaining=False)
        tm.assert_series_equal(s, res)

    def test_sort_index_kind(self, sort_kind):
        # GH#14444 & GH#13589:  Add support for sort algo choosing
        series = Series(index=[3, 2, 1, 4, 3], dtype=object)
        expected_series = Series(index=[1, 2, 3, 3, 4], dtype=object)

        index_sorted_series = series.sort_index(kind=sort_kind)
        tm.assert_series_equal(expected_series, index_sorted_series)

    def test_sort_index_na_position(self):
        series = Series(index=[3, 2, 1, 4, 3, np.nan], dtype=object)
        expected_series_first = Series(index=[np.nan, 1, 2, 3, 3, 4], dtype=object)

        index_sorted_series = series.sort_index(na_position="first")
        tm.assert_series_equal(expected_series_first, index_sorted_series)

        expected_series_last = Series(index=[1, 2, 3, 3, 4, np.nan], dtype=object)

        index_sorted_series = series.sort_index(na_position="last")
        tm.assert_series_equal(expected_series_last, index_sorted_series)

    def test_sort_index_intervals(self):
        s = Series(
            [np.nan, 1, 2, 3], IntervalIndex.from_arrays([0, 1, 2, 3], [1, 2, 3, 4])
        )

        result = s.sort_index()
        expected = s
        tm.assert_series_equal(result, expected)

        result = s.sort_index(ascending=False)
        expected = Series(
            [3, 2, 1, np.nan], IntervalIndex.from_arrays([3, 2, 1, 0], [4, 3, 2, 1])
        )
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("inplace", [True, False])
    @pytest.mark.parametrize(
        "original_list, sorted_list, ascending, ignore_index, output_index",
        [
            ([2, 3, 6, 1], [2, 3, 6, 1], True, True, [0, 1, 2, 3]),
            ([2, 3, 6, 1], [2, 3, 6, 1], True, False, [0, 1, 2, 3]),
            ([2, 3, 6, 1], [1, 6, 3, 2], False, True, [0, 1, 2, 3]),
            ([2, 3, 6, 1], [1, 6, 3, 2], False, False, [3, 2, 1, 0]),
        ],
    )
    def test_sort_index_ignore_index(
        self, inplace, original_list, sorted_list, ascending, ignore_index, output_index
    ):
        # GH 30114
        ser = Series(original_list)
        expected = Series(sorted_list, index=output_index)
        kwargs = {
            "ascending": ascending,
            "ignore_index": ignore_index,
            "inplace": inplace,
        }

        if inplace:
            result_ser = ser.copy()
            result_ser.sort_index(**kwargs)
        else:
            result_ser = ser.sort_index(**kwargs)

        tm.assert_series_equal(result_ser, expected)
        tm.assert_series_equal(ser, Series(original_list))

    def test_sort_index_ascending_list(self):
        # GH#16934

        # Set up a Series with a three level MultiIndex
        arrays = [
            ["bar", "bar", "baz", "baz", "foo", "foo", "qux", "qux"],
            ["one", "two", "one", "two", "one", "two", "one", "two"],
            [4, 3, 2, 1, 4, 3, 2, 1],
        ]
        tuples = zip(*arrays)
        mi = MultiIndex.from_tuples(tuples, names=["first", "second", "third"])
        ser = Series(range(8), index=mi)

        # Sort with boolean ascending
        result = ser.sort_index(level=["third", "first"], ascending=False)
        expected = ser.iloc[[4, 0, 5, 1, 6, 2, 7, 3]]
        tm.assert_series_equal(result, expected)

        # Sort with list of boolean ascending
        result = ser.sort_index(level=["third", "first"], ascending=[False, True])
        expected = ser.iloc[[0, 4, 1, 5, 2, 6, 3, 7]]
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "ascending",
        [
            None,
            (True, None),
            (False, "True"),
        ],
    )
    def test_sort_index_ascending_bad_value_raises(self, ascending):
        ser = Series(range(10), index=[0, 3, 2, 1, 4, 5, 7, 6, 8, 9])
        match = 'For argument "ascending" expected type bool'
        with pytest.raises(ValueError, match=match):
            ser.sort_index(ascending=ascending)


class TestSeriesSortIndexKey:
    def test_sort_index_multiindex_key(self):
        mi = MultiIndex.from_tuples([[1, 1, 3], [1, 1, 1]], names=list("ABC"))
        s = Series([1, 2], mi)
        backwards = s.iloc[[1, 0]]

        result = s.sort_index(level="C", key=lambda x: -x)
        tm.assert_series_equal(s, result)

        result = s.sort_index(level="C", key=lambda x: x)  # nothing happens
        tm.assert_series_equal(backwards, result)

    def test_sort_index_multiindex_key_multi_level(self):
        mi = MultiIndex.from_tuples([[1, 1, 3], [1, 1, 1]], names=list("ABC"))
        s = Series([1, 2], mi)
        backwards = s.iloc[[1, 0]]

        result = s.sort_index(level=["A", "C"], key=lambda x: -x)
        tm.assert_series_equal(s, result)

        result = s.sort_index(level=["A", "C"], key=lambda x: x)  # nothing happens
        tm.assert_series_equal(backwards, result)

    def test_sort_index_key(self):
        series = Series(np.arange(6, dtype="int64"), index=list("aaBBca"))

        result = series.sort_index()
        expected = series.iloc[[2, 3, 0, 1, 5, 4]]
        tm.assert_series_equal(result, expected)

        result = series.sort_index(key=lambda x: x.str.lower())
        expected = series.iloc[[0, 1, 5, 2, 3, 4]]
        tm.assert_series_equal(result, expected)

        result = series.sort_index(key=lambda x: x.str.lower(), ascending=False)
        expected = series.iloc[[4, 2, 3, 0, 1, 5]]
        tm.assert_series_equal(result, expected)

    def test_sort_index_key_int(self):
        series = Series(np.arange(6, dtype="int64"), index=np.arange(6, dtype="int64"))

        result = series.sort_index()
        tm.assert_series_equal(result, series)

        result = series.sort_index(key=lambda x: -x)
        expected = series.sort_index(ascending=False)
        tm.assert_series_equal(result, expected)

        result = series.sort_index(key=lambda x: 2 * x)
        tm.assert_series_equal(result, series)

    def test_sort_index_kind_key(self, sort_kind, sort_by_key):
        # GH #14444 & #13589:  Add support for sort algo choosing
        series = Series(index=[3, 2, 1, 4, 3], dtype=object)
        expected_series = Series(index=[1, 2, 3, 3, 4], dtype=object)

        index_sorted_series = series.sort_index(kind=sort_kind, key=sort_by_key)
        tm.assert_series_equal(expected_series, index_sorted_series)

    def test_sort_index_kind_neg_key(self, sort_kind):
        # GH #14444 & #13589:  Add support for sort algo choosing
        series = Series(index=[3, 2, 1, 4, 3], dtype=object)
        expected_series = Series(index=[4, 3, 3, 2, 1], dtype=object)

        index_sorted_series = series.sort_index(kind=sort_kind, key=lambda x: -x)
        tm.assert_series_equal(expected_series, index_sorted_series)

    def test_sort_index_na_position_key(self, sort_by_key):
        series = Series(index=[3, 2, 1, 4, 3, np.nan], dtype=object)
        expected_series_first = Series(index=[np.nan, 1, 2, 3, 3, 4], dtype=object)

        index_sorted_series = series.sort_index(na_position="first", key=sort_by_key)
        tm.assert_series_equal(expected_series_first, index_sorted_series)

        expected_series_last = Series(index=[1, 2, 3, 3, 4, np.nan], dtype=object)

        index_sorted_series = series.sort_index(na_position="last", key=sort_by_key)
        tm.assert_series_equal(expected_series_last, index_sorted_series)

    def test_changes_length_raises(self):
        s = Series([1, 2, 3])
        with pytest.raises(ValueError, match="change the shape"):
            s.sort_index(key=lambda x: x[:1])

    def test_sort_values_key_type(self):
        s = Series([1, 2, 3], DatetimeIndex(["2008-10-24", "2008-11-23", "2007-12-22"]))

        result = s.sort_index(key=lambda x: x.month)
        expected = s.iloc[[0, 1, 2]]
        tm.assert_series_equal(result, expected)

        result = s.sort_index(key=lambda x: x.day)
        expected = s.iloc[[2, 1, 0]]
        tm.assert_series_equal(result, expected)

        result = s.sort_index(key=lambda x: x.year)
        expected = s.iloc[[2, 0, 1]]
        tm.assert_series_equal(result, expected)

        result = s.sort_index(key=lambda x: x.month_name())
        expected = s.iloc[[2, 1, 0]]
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "ascending",
        [
            [True, False],
            [False, True],
        ],
    )
    def test_sort_index_multi_already_monotonic(self, ascending):
        # GH 56049
        mi = MultiIndex.from_product([[1, 2], [3, 4]])
        ser = Series(range(len(mi)), index=mi)
        result = ser.sort_index(ascending=ascending)
        if ascending == [True, False]:
            expected = ser.take([1, 0, 3, 2])
        elif ascending == [False, True]:
            expected = ser.take([2, 3, 0, 1])
        tm.assert_series_equal(result, expected)
