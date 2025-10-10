import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    MultiIndex,
    Series,
)
import pandas._testing as tm


class TestDataFrameIsIn:
    def test_isin(self):
        # GH#4211
        df = DataFrame(
            {
                "vals": [1, 2, 3, 4],
                "ids": ["a", "b", "f", "n"],
                "ids2": ["a", "n", "c", "n"],
            },
            index=["foo", "bar", "baz", "qux"],
        )
        other = ["a", "b", "c"]

        result = df.isin(other)
        expected = DataFrame([df.loc[s].isin(other) for s in df.index])
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("empty", [[], Series(dtype=object), np.array([])])
    def test_isin_empty(self, empty):
        # GH#16991
        df = DataFrame({"A": ["a", "b", "c"], "B": ["a", "e", "f"]})
        expected = DataFrame(False, df.index, df.columns)

        result = df.isin(empty)
        tm.assert_frame_equal(result, expected)

    def test_isin_dict(self):
        df = DataFrame({"A": ["a", "b", "c"], "B": ["a", "e", "f"]})
        d = {"A": ["a"]}

        expected = DataFrame(False, df.index, df.columns)
        expected.loc[0, "A"] = True

        result = df.isin(d)
        tm.assert_frame_equal(result, expected)

        # non unique columns
        df = DataFrame({"A": ["a", "b", "c"], "B": ["a", "e", "f"]})
        df.columns = ["A", "A"]
        expected = DataFrame(False, df.index, df.columns)
        expected.loc[0, "A"] = True
        result = df.isin(d)
        tm.assert_frame_equal(result, expected)

    def test_isin_with_string_scalar(self):
        # GH#4763
        df = DataFrame(
            {
                "vals": [1, 2, 3, 4],
                "ids": ["a", "b", "f", "n"],
                "ids2": ["a", "n", "c", "n"],
            },
            index=["foo", "bar", "baz", "qux"],
        )
        msg = (
            r"only list-like or dict-like objects are allowed "
            r"to be passed to DataFrame.isin\(\), you passed a 'str'"
        )
        with pytest.raises(TypeError, match=msg):
            df.isin("a")

        with pytest.raises(TypeError, match=msg):
            df.isin("aaa")

    def test_isin_df(self):
        df1 = DataFrame({"A": [1, 2, 3, 4], "B": [2, np.nan, 4, 4]})
        df2 = DataFrame({"A": [0, 2, 12, 4], "B": [2, np.nan, 4, 5]})
        expected = DataFrame(False, df1.index, df1.columns)
        result = df1.isin(df2)
        expected.loc[[1, 3], "A"] = True
        expected.loc[[0, 2], "B"] = True
        tm.assert_frame_equal(result, expected)

        # partial overlapping columns
        df2.columns = ["A", "C"]
        result = df1.isin(df2)
        expected["B"] = False
        tm.assert_frame_equal(result, expected)

    def test_isin_tuples(self):
        # GH#16394
        df = DataFrame({"A": [1, 2, 3], "B": ["a", "b", "f"]})
        df["C"] = list(zip(df["A"], df["B"]))
        result = df["C"].isin([(1, "a")])
        tm.assert_series_equal(result, Series([True, False, False], name="C"))

    def test_isin_df_dupe_values(self):
        df1 = DataFrame({"A": [1, 2, 3, 4], "B": [2, np.nan, 4, 4]})
        # just cols duped
        df2 = DataFrame([[0, 2], [12, 4], [2, np.nan], [4, 5]], columns=["B", "B"])
        msg = r"cannot compute isin with a duplicate axis\."
        with pytest.raises(ValueError, match=msg):
            df1.isin(df2)

        # just index duped
        df2 = DataFrame(
            [[0, 2], [12, 4], [2, np.nan], [4, 5]],
            columns=["A", "B"],
            index=[0, 0, 1, 1],
        )
        with pytest.raises(ValueError, match=msg):
            df1.isin(df2)

        # cols and index:
        df2.columns = ["B", "B"]
        with pytest.raises(ValueError, match=msg):
            df1.isin(df2)

    def test_isin_dupe_self(self):
        other = DataFrame({"A": [1, 0, 1, 0], "B": [1, 1, 0, 0]})
        df = DataFrame([[1, 1], [1, 0], [0, 0]], columns=["A", "A"])
        result = df.isin(other)
        expected = DataFrame(False, index=df.index, columns=df.columns)
        expected.loc[0] = True
        expected.iloc[1, 1] = True
        tm.assert_frame_equal(result, expected)

    def test_isin_against_series(self):
        df = DataFrame(
            {"A": [1, 2, 3, 4], "B": [2, np.nan, 4, 4]}, index=["a", "b", "c", "d"]
        )
        s = Series([1, 3, 11, 4], index=["a", "b", "c", "d"])
        expected = DataFrame(False, index=df.index, columns=df.columns)
        expected.loc["a", "A"] = True
        expected.loc["d"] = True
        result = df.isin(s)
        tm.assert_frame_equal(result, expected)

    def test_isin_multiIndex(self):
        idx = MultiIndex.from_tuples(
            [
                (0, "a", "foo"),
                (0, "a", "bar"),
                (0, "b", "bar"),
                (0, "b", "baz"),
                (2, "a", "foo"),
                (2, "a", "bar"),
                (2, "c", "bar"),
                (2, "c", "baz"),
                (1, "b", "foo"),
                (1, "b", "bar"),
                (1, "c", "bar"),
                (1, "c", "baz"),
            ]
        )
        df1 = DataFrame({"A": np.ones(12), "B": np.zeros(12)}, index=idx)
        df2 = DataFrame(
            {
                "A": [1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
                "B": [1, 1, 0, 1, 1, 0, 0, 1, 1, 1, 1, 1],
            }
        )
        # against regular index
        expected = DataFrame(False, index=df1.index, columns=df1.columns)
        result = df1.isin(df2)
        tm.assert_frame_equal(result, expected)

        df2.index = idx
        expected = df2.values.astype(bool)
        expected[:, 1] = ~expected[:, 1]
        expected = DataFrame(expected, columns=["A", "B"], index=idx)

        result = df1.isin(df2)
        tm.assert_frame_equal(result, expected)

    def test_isin_empty_datetimelike(self):
        # GH#15473
        df1_ts = DataFrame({"date": pd.to_datetime(["2014-01-01", "2014-01-02"])})
        df1_td = DataFrame({"date": [pd.Timedelta(1, "s"), pd.Timedelta(2, "s")]})
        df2 = DataFrame({"date": []})
        df3 = DataFrame()

        expected = DataFrame({"date": [False, False]})

        result = df1_ts.isin(df2)
        tm.assert_frame_equal(result, expected)
        result = df1_ts.isin(df3)
        tm.assert_frame_equal(result, expected)

        result = df1_td.isin(df2)
        tm.assert_frame_equal(result, expected)
        result = df1_td.isin(df3)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "values",
        [
            DataFrame({"a": [1, 2, 3]}, dtype="category"),
            Series([1, 2, 3], dtype="category"),
        ],
    )
    def test_isin_category_frame(self, values):
        # GH#34256
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        expected = DataFrame({"a": [True, True, True], "b": [False, False, False]})

        result = df.isin(values)
        tm.assert_frame_equal(result, expected)

    def test_isin_read_only(self):
        # https://github.com/pandas-dev/pandas/issues/37174
        arr = np.array([1, 2, 3])
        arr.setflags(write=False)
        df = DataFrame([1, 2, 3])
        result = df.isin(arr)
        expected = DataFrame([True, True, True])
        tm.assert_frame_equal(result, expected)

    def test_isin_not_lossy(self):
        # GH 53514
        val = 1666880195890293744
        df = DataFrame({"a": [val], "b": [1.0]})
        result = df.isin([val])
        expected = DataFrame({"a": [True], "b": [False]})
        tm.assert_frame_equal(result, expected)
