import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Series,
    date_range,
)
import pandas._testing as tm


class TestDataFrameRound:
    def test_round(self):
        # GH#2665

        # Test that rounding an empty DataFrame does nothing
        df = DataFrame()
        tm.assert_frame_equal(df, df.round())

        # Here's the test frame we'll be working with
        df = DataFrame({"col1": [1.123, 2.123, 3.123], "col2": [1.234, 2.234, 3.234]})

        # Default round to integer (i.e. decimals=0)
        expected_rounded = DataFrame({"col1": [1.0, 2.0, 3.0], "col2": [1.0, 2.0, 3.0]})
        tm.assert_frame_equal(df.round(), expected_rounded)

        # Round with an integer
        decimals = 2
        expected_rounded = DataFrame(
            {"col1": [1.12, 2.12, 3.12], "col2": [1.23, 2.23, 3.23]}
        )
        tm.assert_frame_equal(df.round(decimals), expected_rounded)

        # This should also work with np.round (since np.round dispatches to
        # df.round)
        tm.assert_frame_equal(np.round(df, decimals), expected_rounded)

        # Round with a list
        round_list = [1, 2]
        msg = "decimals must be an integer, a dict-like or a Series"
        with pytest.raises(TypeError, match=msg):
            df.round(round_list)

        # Round with a dictionary
        expected_rounded = DataFrame(
            {"col1": [1.1, 2.1, 3.1], "col2": [1.23, 2.23, 3.23]}
        )
        round_dict = {"col1": 1, "col2": 2}
        tm.assert_frame_equal(df.round(round_dict), expected_rounded)

        # Incomplete dict
        expected_partially_rounded = DataFrame(
            {"col1": [1.123, 2.123, 3.123], "col2": [1.2, 2.2, 3.2]}
        )
        partial_round_dict = {"col2": 1}
        tm.assert_frame_equal(df.round(partial_round_dict), expected_partially_rounded)

        # Dict with unknown elements
        wrong_round_dict = {"col3": 2, "col2": 1}
        tm.assert_frame_equal(df.round(wrong_round_dict), expected_partially_rounded)

        # float input to `decimals`
        non_int_round_dict = {"col1": 1, "col2": 0.5}
        msg = "Values in decimals must be integers"
        with pytest.raises(TypeError, match=msg):
            df.round(non_int_round_dict)

        # String input
        non_int_round_dict = {"col1": 1, "col2": "foo"}
        with pytest.raises(TypeError, match=msg):
            df.round(non_int_round_dict)

        non_int_round_Series = Series(non_int_round_dict)
        with pytest.raises(TypeError, match=msg):
            df.round(non_int_round_Series)

        # List input
        non_int_round_dict = {"col1": 1, "col2": [1, 2]}
        with pytest.raises(TypeError, match=msg):
            df.round(non_int_round_dict)

        non_int_round_Series = Series(non_int_round_dict)
        with pytest.raises(TypeError, match=msg):
            df.round(non_int_round_Series)

        # Non integer Series inputs
        non_int_round_Series = Series(non_int_round_dict)
        with pytest.raises(TypeError, match=msg):
            df.round(non_int_round_Series)

        non_int_round_Series = Series(non_int_round_dict)
        with pytest.raises(TypeError, match=msg):
            df.round(non_int_round_Series)

        # Negative numbers
        negative_round_dict = {"col1": -1, "col2": -2}
        big_df = df * 100
        expected_neg_rounded = DataFrame(
            {"col1": [110.0, 210, 310], "col2": [100.0, 200, 300]}
        )
        tm.assert_frame_equal(big_df.round(negative_round_dict), expected_neg_rounded)

        # nan in Series round
        nan_round_Series = Series({"col1": np.nan, "col2": 1})

        with pytest.raises(TypeError, match=msg):
            df.round(nan_round_Series)

        # Make sure this doesn't break existing Series.round
        tm.assert_series_equal(df["col1"].round(1), expected_rounded["col1"])

        # named columns
        # GH#11986
        decimals = 2
        expected_rounded = DataFrame(
            {"col1": [1.12, 2.12, 3.12], "col2": [1.23, 2.23, 3.23]}
        )
        df.columns.name = "cols"
        expected_rounded.columns.name = "cols"
        tm.assert_frame_equal(df.round(decimals), expected_rounded)

        # interaction of named columns & series
        tm.assert_series_equal(df["col1"].round(decimals), expected_rounded["col1"])
        tm.assert_series_equal(df.round(decimals)["col1"], expected_rounded["col1"])

    def test_round_numpy(self):
        # GH#12600
        df = DataFrame([[1.53, 1.36], [0.06, 7.01]])
        out = np.round(df, decimals=0)
        expected = DataFrame([[2.0, 1.0], [0.0, 7.0]])
        tm.assert_frame_equal(out, expected)

        msg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=msg):
            np.round(df, decimals=0, out=df)

    def test_round_numpy_with_nan(self):
        # See GH#14197
        df = Series([1.53, np.nan, 0.06]).to_frame()
        with tm.assert_produces_warning(None):
            result = df.round()
        expected = Series([2.0, np.nan, 0.0]).to_frame()
        tm.assert_frame_equal(result, expected)

    def test_round_mixed_type(self):
        # GH#11885
        df = DataFrame(
            {
                "col1": [1.1, 2.2, 3.3, 4.4],
                "col2": ["1", "a", "c", "f"],
                "col3": date_range("20111111", periods=4),
            }
        )
        round_0 = DataFrame(
            {
                "col1": [1.0, 2.0, 3.0, 4.0],
                "col2": ["1", "a", "c", "f"],
                "col3": date_range("20111111", periods=4),
            }
        )
        tm.assert_frame_equal(df.round(), round_0)
        tm.assert_frame_equal(df.round(1), df)
        tm.assert_frame_equal(df.round({"col1": 1}), df)
        tm.assert_frame_equal(df.round({"col1": 0}), round_0)
        tm.assert_frame_equal(df.round({"col1": 0, "col2": 1}), round_0)
        tm.assert_frame_equal(df.round({"col3": 1}), df)

    def test_round_with_duplicate_columns(self):
        # GH#11611

        df = DataFrame(
            np.random.default_rng(2).random([3, 3]),
            columns=["A", "B", "C"],
            index=["first", "second", "third"],
        )

        dfs = pd.concat((df, df), axis=1)
        rounded = dfs.round()
        tm.assert_index_equal(rounded.index, dfs.index)

        decimals = Series([1, 0, 2], index=["A", "B", "A"])
        msg = "Index of decimals must be unique"
        with pytest.raises(ValueError, match=msg):
            df.round(decimals)

    def test_round_builtin(self):
        # GH#11763
        # Here's the test frame we'll be working with
        df = DataFrame({"col1": [1.123, 2.123, 3.123], "col2": [1.234, 2.234, 3.234]})

        # Default round to integer (i.e. decimals=0)
        expected_rounded = DataFrame({"col1": [1.0, 2.0, 3.0], "col2": [1.0, 2.0, 3.0]})
        tm.assert_frame_equal(round(df), expected_rounded)

    def test_round_nonunique_categorical(self):
        # See GH#21809
        idx = pd.CategoricalIndex(["low"] * 3 + ["hi"] * 3)
        df = DataFrame(np.random.default_rng(2).random((6, 3)), columns=list("abc"))

        expected = df.round(3)
        expected.index = idx

        df_categorical = df.copy().set_index(idx)
        assert df_categorical.shape == (6, 3)
        result = df_categorical.round(3)
        assert result.shape == (6, 3)

        tm.assert_frame_equal(result, expected)

    def test_round_interval_category_columns(self):
        # GH#30063
        columns = pd.CategoricalIndex(pd.interval_range(0, 2))
        df = DataFrame([[0.66, 1.1], [0.3, 0.25]], columns=columns)

        result = df.round()
        expected = DataFrame([[1.0, 1.0], [0.0, 0.0]], columns=columns)
        tm.assert_frame_equal(result, expected)

    def test_round_empty_not_input(self):
        # GH#51032
        df = DataFrame()
        result = df.round()
        tm.assert_frame_equal(df, result)
        assert df is not result
