import numpy as np
import pytest

from pandas import (
    DataFrame,
    DatetimeIndex,
    Index,
    MultiIndex,
    Series,
    concat,
    date_range,
)
import pandas._testing as tm


class TestSeriesConcat:
    def test_concat_series(self):
        ts = Series(
            np.arange(20, dtype=np.float64),
            index=date_range("2020-01-01", periods=20),
            name="foo",
        )
        ts.name = "foo"

        pieces = [ts[:5], ts[5:15], ts[15:]]

        result = concat(pieces)
        tm.assert_series_equal(result, ts)
        assert result.name == ts.name

        result = concat(pieces, keys=[0, 1, 2])
        expected = ts.copy()

        ts.index = DatetimeIndex(np.array(ts.index.values, dtype="M8[ns]"))

        exp_codes = [np.repeat([0, 1, 2], [len(x) for x in pieces]), np.arange(len(ts))]
        exp_index = MultiIndex(levels=[[0, 1, 2], ts.index], codes=exp_codes)
        expected.index = exp_index
        tm.assert_series_equal(result, expected)

    def test_concat_empty_and_non_empty_series_regression(self):
        # GH 18187 regression test
        s1 = Series([1])
        s2 = Series([], dtype=object)

        expected = s1
        msg = "The behavior of array concatenation with empty entries is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = concat([s1, s2])
        tm.assert_series_equal(result, expected)

    def test_concat_series_axis1(self):
        ts = Series(
            np.arange(10, dtype=np.float64), index=date_range("2020-01-01", periods=10)
        )

        pieces = [ts[:-2], ts[2:], ts[2:-2]]

        result = concat(pieces, axis=1)
        expected = DataFrame(pieces).T
        tm.assert_frame_equal(result, expected)

        result = concat(pieces, keys=["A", "B", "C"], axis=1)
        expected = DataFrame(pieces, index=["A", "B", "C"]).T
        tm.assert_frame_equal(result, expected)

    def test_concat_series_axis1_preserves_series_names(self):
        # preserve series names, #2489
        s = Series(np.random.default_rng(2).standard_normal(5), name="A")
        s2 = Series(np.random.default_rng(2).standard_normal(5), name="B")

        result = concat([s, s2], axis=1)
        expected = DataFrame({"A": s, "B": s2})
        tm.assert_frame_equal(result, expected)

        s2.name = None
        result = concat([s, s2], axis=1)
        tm.assert_index_equal(result.columns, Index(["A", 0], dtype="object"))

    def test_concat_series_axis1_with_reindex(self, sort):
        # must reindex, #2603
        s = Series(
            np.random.default_rng(2).standard_normal(3), index=["c", "a", "b"], name="A"
        )
        s2 = Series(
            np.random.default_rng(2).standard_normal(4),
            index=["d", "a", "b", "c"],
            name="B",
        )
        result = concat([s, s2], axis=1, sort=sort)
        expected = DataFrame({"A": s, "B": s2}, index=["c", "a", "b", "d"])
        if sort:
            expected = expected.sort_index()
        tm.assert_frame_equal(result, expected)

    def test_concat_series_axis1_names_applied(self):
        # ensure names argument is not ignored on axis=1, #23490
        s = Series([1, 2, 3])
        s2 = Series([4, 5, 6])
        result = concat([s, s2], axis=1, keys=["a", "b"], names=["A"])
        expected = DataFrame(
            [[1, 4], [2, 5], [3, 6]], columns=Index(["a", "b"], name="A")
        )
        tm.assert_frame_equal(result, expected)

        result = concat([s, s2], axis=1, keys=[("a", 1), ("b", 2)], names=["A", "B"])
        expected = DataFrame(
            [[1, 4], [2, 5], [3, 6]],
            columns=MultiIndex.from_tuples([("a", 1), ("b", 2)], names=["A", "B"]),
        )
        tm.assert_frame_equal(result, expected)

    def test_concat_series_axis1_same_names_ignore_index(self):
        dates = date_range("01-Jan-2013", "01-Jan-2014", freq="MS")[0:-1]
        s1 = Series(
            np.random.default_rng(2).standard_normal(len(dates)),
            index=dates,
            name="value",
        )
        s2 = Series(
            np.random.default_rng(2).standard_normal(len(dates)),
            index=dates,
            name="value",
        )

        result = concat([s1, s2], axis=1, ignore_index=True)
        expected = Index(range(2))

        tm.assert_index_equal(result.columns, expected, exact=True)

    @pytest.mark.parametrize(
        "s1name,s2name", [(np.int64(190), (43, 0)), (190, (43, 0))]
    )
    def test_concat_series_name_npscalar_tuple(self, s1name, s2name):
        # GH21015
        s1 = Series({"a": 1, "b": 2}, name=s1name)
        s2 = Series({"c": 5, "d": 6}, name=s2name)
        result = concat([s1, s2])
        expected = Series({"a": 1, "b": 2, "c": 5, "d": 6})
        tm.assert_series_equal(result, expected)

    def test_concat_series_partial_columns_names(self):
        # GH10698
        named_series = Series([1, 2], name="foo")
        unnamed_series1 = Series([1, 2])
        unnamed_series2 = Series([4, 5])

        result = concat([named_series, unnamed_series1, unnamed_series2], axis=1)
        expected = DataFrame(
            {"foo": [1, 2], 0: [1, 2], 1: [4, 5]}, columns=["foo", 0, 1]
        )
        tm.assert_frame_equal(result, expected)

        result = concat(
            [named_series, unnamed_series1, unnamed_series2],
            axis=1,
            keys=["red", "blue", "yellow"],
        )
        expected = DataFrame(
            {"red": [1, 2], "blue": [1, 2], "yellow": [4, 5]},
            columns=["red", "blue", "yellow"],
        )
        tm.assert_frame_equal(result, expected)

        result = concat(
            [named_series, unnamed_series1, unnamed_series2], axis=1, ignore_index=True
        )
        expected = DataFrame({0: [1, 2], 1: [1, 2], 2: [4, 5]})
        tm.assert_frame_equal(result, expected)

    def test_concat_series_length_one_reversed(self, frame_or_series):
        # GH39401
        obj = frame_or_series([100])
        result = concat([obj.iloc[::-1]])
        tm.assert_equal(result, obj)
