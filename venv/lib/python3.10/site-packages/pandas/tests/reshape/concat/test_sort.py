import numpy as np
import pytest

import pandas as pd
from pandas import DataFrame
import pandas._testing as tm


class TestConcatSort:
    def test_concat_sorts_columns(self, sort):
        # GH-4588
        df1 = DataFrame({"a": [1, 2], "b": [1, 2]}, columns=["b", "a"])
        df2 = DataFrame({"a": [3, 4], "c": [5, 6]})

        # for sort=True/None
        expected = DataFrame(
            {"a": [1, 2, 3, 4], "b": [1, 2, None, None], "c": [None, None, 5, 6]},
            columns=["a", "b", "c"],
        )

        if sort is False:
            expected = expected[["b", "a", "c"]]

        # default
        with tm.assert_produces_warning(None):
            result = pd.concat([df1, df2], ignore_index=True, sort=sort)
        tm.assert_frame_equal(result, expected)

    def test_concat_sorts_index(self, sort):
        df1 = DataFrame({"a": [1, 2, 3]}, index=["c", "a", "b"])
        df2 = DataFrame({"b": [1, 2]}, index=["a", "b"])

        # For True/None
        expected = DataFrame(
            {"a": [2, 3, 1], "b": [1, 2, None]},
            index=["a", "b", "c"],
            columns=["a", "b"],
        )
        if sort is False:
            expected = expected.loc[["c", "a", "b"]]

        # Warn and sort by default
        with tm.assert_produces_warning(None):
            result = pd.concat([df1, df2], axis=1, sort=sort)
        tm.assert_frame_equal(result, expected)

    def test_concat_inner_sort(self, sort):
        # https://github.com/pandas-dev/pandas/pull/20613
        df1 = DataFrame(
            {"a": [1, 2], "b": [1, 2], "c": [1, 2]}, columns=["b", "a", "c"]
        )
        df2 = DataFrame({"a": [1, 2], "b": [3, 4]}, index=[3, 4])

        with tm.assert_produces_warning(None):
            # unset sort should *not* warn for inner join
            # since that never sorted
            result = pd.concat([df1, df2], sort=sort, join="inner", ignore_index=True)

        expected = DataFrame({"b": [1, 2, 3, 4], "a": [1, 2, 1, 2]}, columns=["b", "a"])
        if sort is True:
            expected = expected[["a", "b"]]
        tm.assert_frame_equal(result, expected)

    def test_concat_aligned_sort(self):
        # GH-4588
        df = DataFrame({"c": [1, 2], "b": [3, 4], "a": [5, 6]}, columns=["c", "b", "a"])
        result = pd.concat([df, df], sort=True, ignore_index=True)
        expected = DataFrame(
            {"a": [5, 6, 5, 6], "b": [3, 4, 3, 4], "c": [1, 2, 1, 2]},
            columns=["a", "b", "c"],
        )
        tm.assert_frame_equal(result, expected)

        result = pd.concat(
            [df, df[["c", "b"]]], join="inner", sort=True, ignore_index=True
        )
        expected = expected[["b", "c"]]
        tm.assert_frame_equal(result, expected)

    def test_concat_aligned_sort_does_not_raise(self):
        # GH-4588
        # We catch TypeErrors from sorting internally and do not re-raise.
        df = DataFrame({1: [1, 2], "a": [3, 4]}, columns=[1, "a"])
        expected = DataFrame({1: [1, 2, 1, 2], "a": [3, 4, 3, 4]}, columns=[1, "a"])
        result = pd.concat([df, df], ignore_index=True, sort=True)
        tm.assert_frame_equal(result, expected)

    def test_concat_frame_with_sort_false(self):
        # GH 43375
        result = pd.concat(
            [DataFrame({i: i}, index=[i]) for i in range(2, 0, -1)], sort=False
        )
        expected = DataFrame([[2, np.nan], [np.nan, 1]], index=[2, 1], columns=[2, 1])

        tm.assert_frame_equal(result, expected)

        # GH 37937
        df1 = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]}, index=[1, 2, 3])
        df2 = DataFrame({"c": [7, 8, 9], "d": [10, 11, 12]}, index=[3, 1, 6])
        result = pd.concat([df2, df1], axis=1, sort=False)
        expected = DataFrame(
            [
                [7.0, 10.0, 3.0, 6.0],
                [8.0, 11.0, 1.0, 4.0],
                [9.0, 12.0, np.nan, np.nan],
                [np.nan, np.nan, 2.0, 5.0],
            ],
            index=[3, 1, 6, 2],
            columns=["c", "d", "a", "b"],
        )
        tm.assert_frame_equal(result, expected)

    def test_concat_sort_none_raises(self):
        # GH#41518
        df = DataFrame({1: [1, 2], "a": [3, 4]})
        msg = "The 'sort' keyword only accepts boolean values; None was passed."
        with pytest.raises(ValueError, match=msg):
            pd.concat([df, df], sort=None)
