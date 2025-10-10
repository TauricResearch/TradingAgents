from itertools import product
from string import ascii_lowercase

import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Period,
    Series,
    Timedelta,
    Timestamp,
    date_range,
)
import pandas._testing as tm


class TestCounting:
    def test_cumcount(self):
        df = DataFrame([["a"], ["a"], ["a"], ["b"], ["a"]], columns=["A"])
        g = df.groupby("A")
        sg = g.A

        expected = Series([0, 1, 2, 0, 3])

        tm.assert_series_equal(expected, g.cumcount())
        tm.assert_series_equal(expected, sg.cumcount())

    def test_cumcount_empty(self):
        ge = DataFrame().groupby(level=0)
        se = Series(dtype=object).groupby(level=0)

        # edge case, as this is usually considered float
        e = Series(dtype="int64")

        tm.assert_series_equal(e, ge.cumcount())
        tm.assert_series_equal(e, se.cumcount())

    def test_cumcount_dupe_index(self):
        df = DataFrame(
            [["a"], ["a"], ["a"], ["b"], ["a"]], columns=["A"], index=[0] * 5
        )
        g = df.groupby("A")
        sg = g.A

        expected = Series([0, 1, 2, 0, 3], index=[0] * 5)

        tm.assert_series_equal(expected, g.cumcount())
        tm.assert_series_equal(expected, sg.cumcount())

    def test_cumcount_mi(self):
        mi = MultiIndex.from_tuples([[0, 1], [1, 2], [2, 2], [2, 2], [1, 0]])
        df = DataFrame([["a"], ["a"], ["a"], ["b"], ["a"]], columns=["A"], index=mi)
        g = df.groupby("A")
        sg = g.A

        expected = Series([0, 1, 2, 0, 3], index=mi)

        tm.assert_series_equal(expected, g.cumcount())
        tm.assert_series_equal(expected, sg.cumcount())

    def test_cumcount_groupby_not_col(self):
        df = DataFrame(
            [["a"], ["a"], ["a"], ["b"], ["a"]], columns=["A"], index=[0] * 5
        )
        g = df.groupby([0, 0, 0, 1, 0])
        sg = g.A

        expected = Series([0, 1, 2, 0, 3], index=[0] * 5)

        tm.assert_series_equal(expected, g.cumcount())
        tm.assert_series_equal(expected, sg.cumcount())

    def test_ngroup(self):
        df = DataFrame({"A": list("aaaba")})
        g = df.groupby("A")
        sg = g.A

        expected = Series([0, 0, 0, 1, 0])

        tm.assert_series_equal(expected, g.ngroup())
        tm.assert_series_equal(expected, sg.ngroup())

    def test_ngroup_distinct(self):
        df = DataFrame({"A": list("abcde")})
        g = df.groupby("A")
        sg = g.A

        expected = Series(range(5), dtype="int64")

        tm.assert_series_equal(expected, g.ngroup())
        tm.assert_series_equal(expected, sg.ngroup())

    def test_ngroup_one_group(self):
        df = DataFrame({"A": [0] * 5})
        g = df.groupby("A")
        sg = g.A

        expected = Series([0] * 5)

        tm.assert_series_equal(expected, g.ngroup())
        tm.assert_series_equal(expected, sg.ngroup())

    def test_ngroup_empty(self):
        ge = DataFrame().groupby(level=0)
        se = Series(dtype=object).groupby(level=0)

        # edge case, as this is usually considered float
        e = Series(dtype="int64")

        tm.assert_series_equal(e, ge.ngroup())
        tm.assert_series_equal(e, se.ngroup())

    def test_ngroup_series_matches_frame(self):
        df = DataFrame({"A": list("aaaba")})
        s = Series(list("aaaba"))

        tm.assert_series_equal(df.groupby(s).ngroup(), s.groupby(s).ngroup())

    def test_ngroup_dupe_index(self):
        df = DataFrame({"A": list("aaaba")}, index=[0] * 5)
        g = df.groupby("A")
        sg = g.A

        expected = Series([0, 0, 0, 1, 0], index=[0] * 5)

        tm.assert_series_equal(expected, g.ngroup())
        tm.assert_series_equal(expected, sg.ngroup())

    def test_ngroup_mi(self):
        mi = MultiIndex.from_tuples([[0, 1], [1, 2], [2, 2], [2, 2], [1, 0]])
        df = DataFrame({"A": list("aaaba")}, index=mi)
        g = df.groupby("A")
        sg = g.A
        expected = Series([0, 0, 0, 1, 0], index=mi)

        tm.assert_series_equal(expected, g.ngroup())
        tm.assert_series_equal(expected, sg.ngroup())

    def test_ngroup_groupby_not_col(self):
        df = DataFrame({"A": list("aaaba")}, index=[0] * 5)
        g = df.groupby([0, 0, 0, 1, 0])
        sg = g.A

        expected = Series([0, 0, 0, 1, 0], index=[0] * 5)

        tm.assert_series_equal(expected, g.ngroup())
        tm.assert_series_equal(expected, sg.ngroup())

    def test_ngroup_descending(self):
        df = DataFrame(["a", "a", "b", "a", "b"], columns=["A"])
        g = df.groupby(["A"])

        ascending = Series([0, 0, 1, 0, 1])
        descending = Series([1, 1, 0, 1, 0])

        tm.assert_series_equal(descending, (g.ngroups - 1) - ascending)
        tm.assert_series_equal(ascending, g.ngroup(ascending=True))
        tm.assert_series_equal(descending, g.ngroup(ascending=False))

    def test_ngroup_matches_cumcount(self):
        # verify one manually-worked out case works
        df = DataFrame(
            [["a", "x"], ["a", "y"], ["b", "x"], ["a", "x"], ["b", "y"]],
            columns=["A", "X"],
        )
        g = df.groupby(["A", "X"])
        g_ngroup = g.ngroup()
        g_cumcount = g.cumcount()
        expected_ngroup = Series([0, 1, 2, 0, 3])
        expected_cumcount = Series([0, 0, 0, 1, 0])

        tm.assert_series_equal(g_ngroup, expected_ngroup)
        tm.assert_series_equal(g_cumcount, expected_cumcount)

    def test_ngroup_cumcount_pair(self):
        # brute force comparison for all small series
        for p in product(range(3), repeat=4):
            df = DataFrame({"a": p})
            g = df.groupby(["a"])

            order = sorted(set(p))
            ngroupd = [order.index(val) for val in p]
            cumcounted = [p[:i].count(val) for i, val in enumerate(p)]

            tm.assert_series_equal(g.ngroup(), Series(ngroupd))
            tm.assert_series_equal(g.cumcount(), Series(cumcounted))

    def test_ngroup_respects_groupby_order(self, sort):
        df = DataFrame({"a": np.random.default_rng(2).choice(list("abcdef"), 100)})
        g = df.groupby("a", sort=sort)
        df["group_id"] = -1
        df["group_index"] = -1

        for i, (_, group) in enumerate(g):
            df.loc[group.index, "group_id"] = i
            for j, ind in enumerate(group.index):
                df.loc[ind, "group_index"] = j

        tm.assert_series_equal(Series(df["group_id"].values), g.ngroup())
        tm.assert_series_equal(Series(df["group_index"].values), g.cumcount())

    @pytest.mark.parametrize(
        "datetimelike",
        [
            [Timestamp(f"2016-05-{i:02d} 20:09:25+00:00") for i in range(1, 4)],
            [Timestamp(f"2016-05-{i:02d} 20:09:25") for i in range(1, 4)],
            [Timestamp(f"2016-05-{i:02d} 20:09:25", tz="UTC") for i in range(1, 4)],
            [Timedelta(x, unit="h") for x in range(1, 4)],
            [Period(freq="2W", year=2017, month=x) for x in range(1, 4)],
        ],
    )
    def test_count_with_datetimelike(self, datetimelike):
        # test for #13393, where DataframeGroupBy.count() fails
        # when counting a datetimelike column.

        df = DataFrame({"x": ["a", "a", "b"], "y": datetimelike})
        res = df.groupby("x").count()
        expected = DataFrame({"y": [2, 1]}, index=["a", "b"])
        expected.index.name = "x"
        tm.assert_frame_equal(expected, res)

    def test_count_with_only_nans_in_first_group(self):
        # GH21956
        df = DataFrame({"A": [np.nan, np.nan], "B": ["a", "b"], "C": [1, 2]})
        result = df.groupby(["A", "B"]).C.count()
        mi = MultiIndex(levels=[[], ["a", "b"]], codes=[[], []], names=["A", "B"])
        expected = Series([], index=mi, dtype=np.int64, name="C")
        tm.assert_series_equal(result, expected, check_index_type=False)

    def test_count_groupby_column_with_nan_in_groupby_column(self):
        # https://github.com/pandas-dev/pandas/issues/32841
        df = DataFrame({"A": [1, 1, 1, 1, 1], "B": [5, 4, np.nan, 3, 0]})
        res = df.groupby(["B"]).count()
        expected = DataFrame(
            index=Index([0.0, 3.0, 4.0, 5.0], name="B"), data={"A": [1, 1, 1, 1]}
        )
        tm.assert_frame_equal(expected, res)

    def test_groupby_count_dateparseerror(self):
        dr = date_range(start="1/1/2012", freq="5min", periods=10)

        # BAD Example, datetimes first
        ser = Series(np.arange(10), index=[dr, np.arange(10)])
        grouped = ser.groupby(lambda x: x[1] % 2 == 0)
        result = grouped.count()

        ser = Series(np.arange(10), index=[np.arange(10), dr])
        grouped = ser.groupby(lambda x: x[0] % 2 == 0)
        expected = grouped.count()

        tm.assert_series_equal(result, expected)


def test_groupby_timedelta_cython_count():
    df = DataFrame(
        {"g": list("ab" * 2), "delta": np.arange(4).astype("timedelta64[ns]")}
    )
    expected = Series([2, 2], index=Index(["a", "b"], name="g"), name="delta")
    result = df.groupby("g").delta.count()
    tm.assert_series_equal(expected, result)


def test_count():
    n = 1 << 15
    dr = date_range("2015-08-30", periods=n // 10, freq="min")

    df = DataFrame(
        {
            "1st": np.random.default_rng(2).choice(list(ascii_lowercase), n),
            "2nd": np.random.default_rng(2).integers(0, 5, n),
            "3rd": np.random.default_rng(2).standard_normal(n).round(3),
            "4th": np.random.default_rng(2).integers(-10, 10, n),
            "5th": np.random.default_rng(2).choice(dr, n),
            "6th": np.random.default_rng(2).standard_normal(n).round(3),
            "7th": np.random.default_rng(2).standard_normal(n).round(3),
            "8th": np.random.default_rng(2).choice(dr, n)
            - np.random.default_rng(2).choice(dr, 1),
            "9th": np.random.default_rng(2).choice(list(ascii_lowercase), n),
        }
    )

    for col in df.columns.drop(["1st", "2nd", "4th"]):
        df.loc[np.random.default_rng(2).choice(n, n // 10), col] = np.nan

    df["9th"] = df["9th"].astype("category")

    for key in ["1st", "2nd", ["1st", "2nd"]]:
        left = df.groupby(key).count()
        msg = "DataFrameGroupBy.apply operated on the grouping columns"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            right = df.groupby(key).apply(DataFrame.count).drop(key, axis=1)
        tm.assert_frame_equal(left, right)


def test_count_non_nulls():
    # GH#5610
    # count counts non-nulls
    df = DataFrame(
        [[1, 2, "foo"], [1, np.nan, "bar"], [3, np.nan, np.nan]],
        columns=["A", "B", "C"],
    )

    count_as = df.groupby("A").count()
    count_not_as = df.groupby("A", as_index=False).count()

    expected = DataFrame([[1, 2], [0, 0]], columns=["B", "C"], index=[1, 3])
    expected.index.name = "A"
    tm.assert_frame_equal(count_not_as, expected.reset_index())
    tm.assert_frame_equal(count_as, expected)

    count_B = df.groupby("A")["B"].count()
    tm.assert_series_equal(count_B, expected["B"])


def test_count_object():
    df = DataFrame({"a": ["a"] * 3 + ["b"] * 3, "c": [2] * 3 + [3] * 3})
    result = df.groupby("c").a.count()
    expected = Series([3, 3], index=Index([2, 3], name="c"), name="a")
    tm.assert_series_equal(result, expected)

    df = DataFrame({"a": ["a", np.nan, np.nan] + ["b"] * 3, "c": [2] * 3 + [3] * 3})
    result = df.groupby("c").a.count()
    expected = Series([1, 3], index=Index([2, 3], name="c"), name="a")
    tm.assert_series_equal(result, expected)


def test_count_cross_type():
    # GH8169
    # Set float64 dtype to avoid upcast when setting nan below
    vals = np.hstack(
        (
            np.random.default_rng(2).integers(0, 5, (100, 2)),
            np.random.default_rng(2).integers(0, 2, (100, 2)),
        )
    ).astype("float64")

    df = DataFrame(vals, columns=["a", "b", "c", "d"])
    df[df == 2] = np.nan
    expected = df.groupby(["c", "d"]).count()

    for t in ["float32", "object"]:
        df["a"] = df["a"].astype(t)
        df["b"] = df["b"].astype(t)
        result = df.groupby(["c", "d"]).count()
        tm.assert_frame_equal(result, expected)


def test_lower_int_prec_count():
    df = DataFrame(
        {
            "a": np.array([0, 1, 2, 100], np.int8),
            "b": np.array([1, 2, 3, 6], np.uint32),
            "c": np.array([4, 5, 6, 8], np.int16),
            "grp": list("ab" * 2),
        }
    )
    result = df.groupby("grp").count()
    expected = DataFrame(
        {"a": [2, 2], "b": [2, 2], "c": [2, 2]}, index=Index(list("ab"), name="grp")
    )
    tm.assert_frame_equal(result, expected)


def test_count_uses_size_on_exception():
    class RaisingObjectException(Exception):
        pass

    class RaisingObject:
        def __init__(self, msg="I will raise inside Cython") -> None:
            super().__init__()
            self.msg = msg

        def __eq__(self, other):
            # gets called in Cython to check that raising calls the method
            raise RaisingObjectException(self.msg)

    df = DataFrame({"a": [RaisingObject() for _ in range(4)], "grp": list("ab" * 2)})
    result = df.groupby("grp").count()
    expected = DataFrame({"a": [2, 2]}, index=Index(list("ab"), name="grp"))
    tm.assert_frame_equal(result, expected)


def test_count_arrow_string_array(any_string_dtype):
    # GH#54751
    pytest.importorskip("pyarrow")
    df = DataFrame(
        {"a": [1, 2, 3], "b": Series(["a", "b", "a"], dtype=any_string_dtype)}
    )
    result = df.groupby("a").count()
    expected = DataFrame({"b": 1}, index=Index([1, 2, 3], name="a"))
    tm.assert_frame_equal(result, expected)
