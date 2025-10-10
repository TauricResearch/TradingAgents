import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    Series,
    concat,
)
import pandas._testing as tm


class TestDataFrameConcat:
    def test_concat_multiple_frames_dtypes(self):
        # GH#2759
        df1 = DataFrame(data=np.ones((10, 2)), columns=["foo", "bar"], dtype=np.float64)
        df2 = DataFrame(data=np.ones((10, 2)), dtype=np.float32)
        results = concat((df1, df2), axis=1).dtypes
        expected = Series(
            [np.dtype("float64")] * 2 + [np.dtype("float32")] * 2,
            index=["foo", "bar", 0, 1],
        )
        tm.assert_series_equal(results, expected)

    def test_concat_tuple_keys(self):
        # GH#14438
        df1 = DataFrame(np.ones((2, 2)), columns=list("AB"))
        df2 = DataFrame(np.ones((3, 2)) * 2, columns=list("AB"))
        results = concat((df1, df2), keys=[("bee", "bah"), ("bee", "boo")])
        expected = DataFrame(
            {
                "A": {
                    ("bee", "bah", 0): 1.0,
                    ("bee", "bah", 1): 1.0,
                    ("bee", "boo", 0): 2.0,
                    ("bee", "boo", 1): 2.0,
                    ("bee", "boo", 2): 2.0,
                },
                "B": {
                    ("bee", "bah", 0): 1.0,
                    ("bee", "bah", 1): 1.0,
                    ("bee", "boo", 0): 2.0,
                    ("bee", "boo", 1): 2.0,
                    ("bee", "boo", 2): 2.0,
                },
            }
        )
        tm.assert_frame_equal(results, expected)

    def test_concat_named_keys(self):
        # GH#14252
        df = DataFrame({"foo": [1, 2], "bar": [0.1, 0.2]})
        index = Index(["a", "b"], name="baz")
        concatted_named_from_keys = concat([df, df], keys=index)
        expected_named = DataFrame(
            {"foo": [1, 2, 1, 2], "bar": [0.1, 0.2, 0.1, 0.2]},
            index=pd.MultiIndex.from_product((["a", "b"], [0, 1]), names=["baz", None]),
        )
        tm.assert_frame_equal(concatted_named_from_keys, expected_named)

        index_no_name = Index(["a", "b"], name=None)
        concatted_named_from_names = concat([df, df], keys=index_no_name, names=["baz"])
        tm.assert_frame_equal(concatted_named_from_names, expected_named)

        concatted_unnamed = concat([df, df], keys=index_no_name)
        expected_unnamed = DataFrame(
            {"foo": [1, 2, 1, 2], "bar": [0.1, 0.2, 0.1, 0.2]},
            index=pd.MultiIndex.from_product((["a", "b"], [0, 1]), names=[None, None]),
        )
        tm.assert_frame_equal(concatted_unnamed, expected_unnamed)

    def test_concat_axis_parameter(self):
        # GH#14369
        df1 = DataFrame({"A": [0.1, 0.2]}, index=range(2))
        df2 = DataFrame({"A": [0.3, 0.4]}, index=range(2))

        # Index/row/0 DataFrame
        expected_index = DataFrame({"A": [0.1, 0.2, 0.3, 0.4]}, index=[0, 1, 0, 1])

        concatted_index = concat([df1, df2], axis="index")
        tm.assert_frame_equal(concatted_index, expected_index)

        concatted_row = concat([df1, df2], axis="rows")
        tm.assert_frame_equal(concatted_row, expected_index)

        concatted_0 = concat([df1, df2], axis=0)
        tm.assert_frame_equal(concatted_0, expected_index)

        # Columns/1 DataFrame
        expected_columns = DataFrame(
            [[0.1, 0.3], [0.2, 0.4]], index=[0, 1], columns=["A", "A"]
        )

        concatted_columns = concat([df1, df2], axis="columns")
        tm.assert_frame_equal(concatted_columns, expected_columns)

        concatted_1 = concat([df1, df2], axis=1)
        tm.assert_frame_equal(concatted_1, expected_columns)

        series1 = Series([0.1, 0.2])
        series2 = Series([0.3, 0.4])

        # Index/row/0 Series
        expected_index_series = Series([0.1, 0.2, 0.3, 0.4], index=[0, 1, 0, 1])

        concatted_index_series = concat([series1, series2], axis="index")
        tm.assert_series_equal(concatted_index_series, expected_index_series)

        concatted_row_series = concat([series1, series2], axis="rows")
        tm.assert_series_equal(concatted_row_series, expected_index_series)

        concatted_0_series = concat([series1, series2], axis=0)
        tm.assert_series_equal(concatted_0_series, expected_index_series)

        # Columns/1 Series
        expected_columns_series = DataFrame(
            [[0.1, 0.3], [0.2, 0.4]], index=[0, 1], columns=[0, 1]
        )

        concatted_columns_series = concat([series1, series2], axis="columns")
        tm.assert_frame_equal(concatted_columns_series, expected_columns_series)

        concatted_1_series = concat([series1, series2], axis=1)
        tm.assert_frame_equal(concatted_1_series, expected_columns_series)

        # Testing ValueError
        with pytest.raises(ValueError, match="No axis named"):
            concat([series1, series2], axis="something")

    def test_concat_numerical_names(self):
        # GH#15262, GH#12223
        df = DataFrame(
            {"col": range(9)},
            dtype="int32",
            index=(
                pd.MultiIndex.from_product(
                    [["A0", "A1", "A2"], ["B0", "B1", "B2"]], names=[1, 2]
                )
            ),
        )
        result = concat((df.iloc[:2, :], df.iloc[-2:, :]))
        expected = DataFrame(
            {"col": [0, 1, 7, 8]},
            dtype="int32",
            index=pd.MultiIndex.from_tuples(
                [("A0", "B0"), ("A0", "B1"), ("A2", "B1"), ("A2", "B2")], names=[1, 2]
            ),
        )
        tm.assert_frame_equal(result, expected)

    def test_concat_astype_dup_col(self):
        # GH#23049
        df = DataFrame([{"a": "b"}])
        df = concat([df, df], axis=1)

        result = df.astype("category")
        expected = DataFrame(
            np.array(["b", "b"]).reshape(1, 2), columns=["a", "a"]
        ).astype("category")
        tm.assert_frame_equal(result, expected)

    def test_concat_dataframe_keys_bug(self, sort):
        t1 = DataFrame(
            {"value": Series([1, 2, 3], index=Index(["a", "b", "c"], name="id"))}
        )
        t2 = DataFrame({"value": Series([7, 8], index=Index(["a", "b"], name="id"))})

        # it works
        result = concat([t1, t2], axis=1, keys=["t1", "t2"], sort=sort)
        assert list(result.columns) == [("t1", "value"), ("t2", "value")]

    def test_concat_bool_with_int(self):
        # GH#42092 we may want to change this to return object, but that
        #  would need a deprecation
        df1 = DataFrame(Series([True, False, True, True], dtype="bool"))
        df2 = DataFrame(Series([1, 0, 1], dtype="int64"))

        result = concat([df1, df2])
        expected = concat([df1.astype("int64"), df2])
        tm.assert_frame_equal(result, expected)

    def test_concat_duplicates_in_index_with_keys(self):
        # GH#42651
        index = [1, 1, 3]
        data = [1, 2, 3]

        df = DataFrame(data=data, index=index)
        result = concat([df], keys=["A"], names=["ID", "date"])
        mi = pd.MultiIndex.from_product([["A"], index], names=["ID", "date"])
        expected = DataFrame(data=data, index=mi)
        tm.assert_frame_equal(result, expected)
        tm.assert_index_equal(result.index.levels[1], Index([1, 3], name="date"))

    @pytest.mark.parametrize("ignore_index", [True, False])
    @pytest.mark.parametrize("order", ["C", "F"])
    @pytest.mark.parametrize("axis", [0, 1])
    def test_concat_copies(self, axis, order, ignore_index, using_copy_on_write):
        # based on asv ConcatDataFrames
        df = DataFrame(np.zeros((10, 5), dtype=np.float32, order=order))

        res = concat([df] * 5, axis=axis, ignore_index=ignore_index, copy=True)

        if not using_copy_on_write:
            for arr in res._iter_column_arrays():
                for arr2 in df._iter_column_arrays():
                    assert not np.shares_memory(arr, arr2)

    def test_outer_sort_columns(self):
        # GH#47127
        df1 = DataFrame({"A": [0], "B": [1], 0: 1})
        df2 = DataFrame({"A": [100]})
        result = concat([df1, df2], ignore_index=True, join="outer", sort=True)
        expected = DataFrame({0: [1.0, np.nan], "A": [0, 100], "B": [1.0, np.nan]})
        tm.assert_frame_equal(result, expected)

    def test_inner_sort_columns(self):
        # GH#47127
        df1 = DataFrame({"A": [0], "B": [1], 0: 1})
        df2 = DataFrame({"A": [100], 0: 2})
        result = concat([df1, df2], ignore_index=True, join="inner", sort=True)
        expected = DataFrame({0: [1, 2], "A": [0, 100]})
        tm.assert_frame_equal(result, expected)

    def test_sort_columns_one_df(self):
        # GH#47127
        df1 = DataFrame({"A": [100], 0: 2})
        result = concat([df1], ignore_index=True, join="inner", sort=True)
        expected = DataFrame({0: [2], "A": [100]})
        tm.assert_frame_equal(result, expected)
