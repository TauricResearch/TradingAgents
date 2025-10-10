"""
test_insert is specifically for the DataFrame.insert method; not to be
confused with tests with "insert" in their names that are really testing
__setitem__.
"""
import numpy as np
import pytest

from pandas.errors import PerformanceWarning

from pandas import (
    DataFrame,
    Index,
)
import pandas._testing as tm


class TestDataFrameInsert:
    def test_insert(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 3)),
            index=np.arange(5),
            columns=["c", "b", "a"],
        )

        df.insert(0, "foo", df["a"])
        tm.assert_index_equal(df.columns, Index(["foo", "c", "b", "a"]))
        tm.assert_series_equal(df["a"], df["foo"], check_names=False)

        df.insert(2, "bar", df["c"])
        tm.assert_index_equal(df.columns, Index(["foo", "c", "bar", "b", "a"]))
        tm.assert_almost_equal(df["c"], df["bar"], check_names=False)

        with pytest.raises(ValueError, match="already exists"):
            df.insert(1, "a", df["b"])

        msg = "cannot insert c, already exists"
        with pytest.raises(ValueError, match=msg):
            df.insert(1, "c", df["b"])

        df.columns.name = "some_name"
        # preserve columns name field
        df.insert(0, "baz", df["c"])
        assert df.columns.name == "some_name"

    def test_insert_column_bug_4032(self):
        # GH#4032, inserting a column and renaming causing errors
        df = DataFrame({"b": [1.1, 2.2]})

        df = df.rename(columns={})
        df.insert(0, "a", [1, 2])
        result = df.rename(columns={})

        expected = DataFrame([[1, 1.1], [2, 2.2]], columns=["a", "b"])
        tm.assert_frame_equal(result, expected)

        df.insert(0, "c", [1.3, 2.3])
        result = df.rename(columns={})

        expected = DataFrame([[1.3, 1, 1.1], [2.3, 2, 2.2]], columns=["c", "a", "b"])
        tm.assert_frame_equal(result, expected)

    def test_insert_with_columns_dups(self):
        # GH#14291
        df = DataFrame()
        df.insert(0, "A", ["g", "h", "i"], allow_duplicates=True)
        df.insert(0, "A", ["d", "e", "f"], allow_duplicates=True)
        df.insert(0, "A", ["a", "b", "c"], allow_duplicates=True)
        exp = DataFrame(
            [["a", "d", "g"], ["b", "e", "h"], ["c", "f", "i"]], columns=["A", "A", "A"]
        )
        tm.assert_frame_equal(df, exp)

    def test_insert_item_cache(self, using_array_manager, using_copy_on_write):
        df = DataFrame(np.random.default_rng(2).standard_normal((4, 3)))
        ser = df[0]

        if using_array_manager:
            expected_warning = None
        else:
            # with BlockManager warn about high fragmentation of single dtype
            expected_warning = PerformanceWarning

        with tm.assert_produces_warning(expected_warning):
            for n in range(100):
                df[n + 3] = df[1] * n

        if using_copy_on_write:
            ser.iloc[0] = 99
            assert df.iloc[0, 0] == df[0][0]
            assert df.iloc[0, 0] != 99
        else:
            ser.values[0] = 99
            assert df.iloc[0, 0] == df[0][0]
            assert df.iloc[0, 0] == 99

    def test_insert_EA_no_warning(self):
        # PerformanceWarning about fragmented frame should not be raised when
        # using EAs (https://github.com/pandas-dev/pandas/issues/44098)
        df = DataFrame(
            np.random.default_rng(2).integers(0, 100, size=(3, 100)), dtype="Int64"
        )
        with tm.assert_produces_warning(None):
            df["a"] = np.array([1, 2, 3])

    def test_insert_frame(self):
        # GH#42403
        df = DataFrame({"col1": [1, 2], "col2": [3, 4]})

        msg = (
            "Expected a one-dimensional object, got a DataFrame with 2 columns instead."
        )
        with pytest.raises(ValueError, match=msg):
            df.insert(1, "newcol", df)

    def test_insert_int64_loc(self):
        # GH#53193
        df = DataFrame({"a": [1, 2]})
        df.insert(np.int64(0), "b", 0)
        tm.assert_frame_equal(df, DataFrame({"b": [0, 0], "a": [1, 2]}))
