import numpy as np
import pytest

import pandas as pd
from pandas import (
    CategoricalDtype,
    CategoricalIndex,
    DataFrame,
    IntervalIndex,
    MultiIndex,
    RangeIndex,
    Series,
    Timestamp,
)
import pandas._testing as tm


class TestDataFrameSortIndex:
    def test_sort_index_and_reconstruction_doc_example(self):
        # doc example
        df = DataFrame(
            {"value": [1, 2, 3, 4]},
            index=MultiIndex(
                levels=[["a", "b"], ["bb", "aa"]], codes=[[0, 0, 1, 1], [0, 1, 0, 1]]
            ),
        )
        assert df.index._is_lexsorted()
        assert not df.index.is_monotonic_increasing

        # sort it
        expected = DataFrame(
            {"value": [2, 1, 4, 3]},
            index=MultiIndex(
                levels=[["a", "b"], ["aa", "bb"]], codes=[[0, 0, 1, 1], [0, 1, 0, 1]]
            ),
        )
        result = df.sort_index()
        assert result.index.is_monotonic_increasing
        tm.assert_frame_equal(result, expected)

        # reconstruct
        result = df.sort_index().copy()
        result.index = result.index._sort_levels_monotonic()
        assert result.index.is_monotonic_increasing
        tm.assert_frame_equal(result, expected)

    def test_sort_index_non_existent_label_multiindex(self):
        # GH#12261
        df = DataFrame(0, columns=[], index=MultiIndex.from_product([[], []]))
        with tm.assert_produces_warning(None):
            df.loc["b", "2"] = 1
            df.loc["a", "3"] = 1
        result = df.sort_index().index.is_monotonic_increasing
        assert result is True

    def test_sort_index_reorder_on_ops(self):
        # GH#15687
        df = DataFrame(
            np.random.default_rng(2).standard_normal((8, 2)),
            index=MultiIndex.from_product(
                [["a", "b"], ["big", "small"], ["red", "blu"]],
                names=["letter", "size", "color"],
            ),
            columns=["near", "far"],
        )
        df = df.sort_index()

        def my_func(group):
            group.index = ["newz", "newa"]
            return group

        result = df.groupby(level=["letter", "size"]).apply(my_func).sort_index()
        expected = MultiIndex.from_product(
            [["a", "b"], ["big", "small"], ["newa", "newz"]],
            names=["letter", "size", None],
        )

        tm.assert_index_equal(result.index, expected)

    def test_sort_index_nan_multiindex(self):
        # GH#14784
        # incorrect sorting w.r.t. nans
        tuples = [[12, 13], [np.nan, np.nan], [np.nan, 3], [1, 2]]
        mi = MultiIndex.from_tuples(tuples)

        df = DataFrame(np.arange(16).reshape(4, 4), index=mi, columns=list("ABCD"))
        s = Series(np.arange(4), index=mi)

        df2 = DataFrame(
            {
                "date": pd.DatetimeIndex(
                    [
                        "20121002",
                        "20121007",
                        "20130130",
                        "20130202",
                        "20130305",
                        "20121002",
                        "20121207",
                        "20130130",
                        "20130202",
                        "20130305",
                        "20130202",
                        "20130305",
                    ]
                ),
                "user_id": [1, 1, 1, 1, 1, 3, 3, 3, 5, 5, 5, 5],
                "whole_cost": [
                    1790,
                    np.nan,
                    280,
                    259,
                    np.nan,
                    623,
                    90,
                    312,
                    np.nan,
                    301,
                    359,
                    801,
                ],
                "cost": [12, 15, 10, 24, 39, 1, 0, np.nan, 45, 34, 1, 12],
            }
        ).set_index(["date", "user_id"])

        # sorting frame, default nan position is last
        result = df.sort_index()
        expected = df.iloc[[3, 0, 2, 1], :]
        tm.assert_frame_equal(result, expected)

        # sorting frame, nan position last
        result = df.sort_index(na_position="last")
        expected = df.iloc[[3, 0, 2, 1], :]
        tm.assert_frame_equal(result, expected)

        # sorting frame, nan position first
        result = df.sort_index(na_position="first")
        expected = df.iloc[[1, 2, 3, 0], :]
        tm.assert_frame_equal(result, expected)

        # sorting frame with removed rows
        result = df2.dropna().sort_index()
        expected = df2.sort_index().dropna()
        tm.assert_frame_equal(result, expected)

        # sorting series, default nan position is last
        result = s.sort_index()
        expected = s.iloc[[3, 0, 2, 1]]
        tm.assert_series_equal(result, expected)

        # sorting series, nan position last
        result = s.sort_index(na_position="last")
        expected = s.iloc[[3, 0, 2, 1]]
        tm.assert_series_equal(result, expected)

        # sorting series, nan position first
        result = s.sort_index(na_position="first")
        expected = s.iloc[[1, 2, 3, 0]]
        tm.assert_series_equal(result, expected)

    def test_sort_index_nan(self):
        # GH#3917

        # Test DataFrame with nan label
        df = DataFrame(
            {"A": [1, 2, np.nan, 1, 6, 8, 4], "B": [9, np.nan, 5, 2, 5, 4, 5]},
            index=[1, 2, 3, 4, 5, 6, np.nan],
        )

        # NaN label, ascending=True, na_position='last'
        sorted_df = df.sort_index(kind="quicksort", ascending=True, na_position="last")
        expected = DataFrame(
            {"A": [1, 2, np.nan, 1, 6, 8, 4], "B": [9, np.nan, 5, 2, 5, 4, 5]},
            index=[1, 2, 3, 4, 5, 6, np.nan],
        )
        tm.assert_frame_equal(sorted_df, expected)

        # NaN label, ascending=True, na_position='first'
        sorted_df = df.sort_index(na_position="first")
        expected = DataFrame(
            {"A": [4, 1, 2, np.nan, 1, 6, 8], "B": [5, 9, np.nan, 5, 2, 5, 4]},
            index=[np.nan, 1, 2, 3, 4, 5, 6],
        )
        tm.assert_frame_equal(sorted_df, expected)

        # NaN label, ascending=False, na_position='last'
        sorted_df = df.sort_index(kind="quicksort", ascending=False)
        expected = DataFrame(
            {"A": [8, 6, 1, np.nan, 2, 1, 4], "B": [4, 5, 2, 5, np.nan, 9, 5]},
            index=[6, 5, 4, 3, 2, 1, np.nan],
        )
        tm.assert_frame_equal(sorted_df, expected)

        # NaN label, ascending=False, na_position='first'
        sorted_df = df.sort_index(
            kind="quicksort", ascending=False, na_position="first"
        )
        expected = DataFrame(
            {"A": [4, 8, 6, 1, np.nan, 2, 1], "B": [5, 4, 5, 2, 5, np.nan, 9]},
            index=[np.nan, 6, 5, 4, 3, 2, 1],
        )
        tm.assert_frame_equal(sorted_df, expected)

    def test_sort_index_multi_index(self):
        # GH#25775, testing that sorting by index works with a multi-index.
        df = DataFrame(
            {"a": [3, 1, 2], "b": [0, 0, 0], "c": [0, 1, 2], "d": list("abc")}
        )
        result = df.set_index(list("abc")).sort_index(level=list("ba"))

        expected = DataFrame(
            {"a": [1, 2, 3], "b": [0, 0, 0], "c": [1, 2, 0], "d": list("bca")}
        )
        expected = expected.set_index(list("abc"))

        tm.assert_frame_equal(result, expected)

    def test_sort_index_inplace(self):
        frame = DataFrame(
            np.random.default_rng(2).standard_normal((4, 4)),
            index=[1, 2, 3, 4],
            columns=["A", "B", "C", "D"],
        )

        # axis=0
        unordered = frame.loc[[3, 2, 4, 1]]
        a_values = unordered["A"]
        df = unordered.copy()
        return_value = df.sort_index(inplace=True)
        assert return_value is None
        expected = frame
        tm.assert_frame_equal(df, expected)
        # GH 44153 related
        # Used to be a_id != id(df["A"]), but flaky in the CI
        assert a_values is not df["A"]

        df = unordered.copy()
        return_value = df.sort_index(ascending=False, inplace=True)
        assert return_value is None
        expected = frame[::-1]
        tm.assert_frame_equal(df, expected)

        # axis=1
        unordered = frame.loc[:, ["D", "B", "C", "A"]]
        df = unordered.copy()
        return_value = df.sort_index(axis=1, inplace=True)
        assert return_value is None
        expected = frame
        tm.assert_frame_equal(df, expected)

        df = unordered.copy()
        return_value = df.sort_index(axis=1, ascending=False, inplace=True)
        assert return_value is None
        expected = frame.iloc[:, ::-1]
        tm.assert_frame_equal(df, expected)

    def test_sort_index_different_sortorder(self):
        A = np.arange(20).repeat(5)
        B = np.tile(np.arange(5), 20)

        indexer = np.random.default_rng(2).permutation(100)
        A = A.take(indexer)
        B = B.take(indexer)

        df = DataFrame(
            {"A": A, "B": B, "C": np.random.default_rng(2).standard_normal(100)}
        )

        ex_indexer = np.lexsort((df.B.max() - df.B, df.A))
        expected = df.take(ex_indexer)

        # test with multiindex, too
        idf = df.set_index(["A", "B"])

        result = idf.sort_index(ascending=[1, 0])
        expected = idf.take(ex_indexer)
        tm.assert_frame_equal(result, expected)

        # also, Series!
        result = idf["C"].sort_index(ascending=[1, 0])
        tm.assert_series_equal(result, expected["C"])

    def test_sort_index_level(self):
        mi = MultiIndex.from_tuples([[1, 1, 3], [1, 1, 1]], names=list("ABC"))
        df = DataFrame([[1, 2], [3, 4]], mi)

        result = df.sort_index(level="A", sort_remaining=False)
        expected = df
        tm.assert_frame_equal(result, expected)

        result = df.sort_index(level=["A", "B"], sort_remaining=False)
        expected = df
        tm.assert_frame_equal(result, expected)

        # Error thrown by sort_index when
        # first index is sorted last (GH#26053)
        result = df.sort_index(level=["C", "B", "A"])
        expected = df.iloc[[1, 0]]
        tm.assert_frame_equal(result, expected)

        result = df.sort_index(level=["B", "C", "A"])
        expected = df.iloc[[1, 0]]
        tm.assert_frame_equal(result, expected)

        result = df.sort_index(level=["C", "A"])
        expected = df.iloc[[1, 0]]
        tm.assert_frame_equal(result, expected)

    def test_sort_index_categorical_index(self):
        df = DataFrame(
            {
                "A": np.arange(6, dtype="int64"),
                "B": Series(list("aabbca")).astype(CategoricalDtype(list("cab"))),
            }
        ).set_index("B")

        result = df.sort_index()
        expected = df.iloc[[4, 0, 1, 5, 2, 3]]
        tm.assert_frame_equal(result, expected)

        result = df.sort_index(ascending=False)
        expected = df.iloc[[2, 3, 0, 1, 5, 4]]
        tm.assert_frame_equal(result, expected)

    def test_sort_index(self):
        # GH#13496

        frame = DataFrame(
            np.arange(16).reshape(4, 4),
            index=[1, 2, 3, 4],
            columns=["A", "B", "C", "D"],
        )

        # axis=0 : sort rows by index labels
        unordered = frame.loc[[3, 2, 4, 1]]
        result = unordered.sort_index(axis=0)
        expected = frame
        tm.assert_frame_equal(result, expected)

        result = unordered.sort_index(ascending=False)
        expected = frame[::-1]
        tm.assert_frame_equal(result, expected)

        # axis=1 : sort columns by column names
        unordered = frame.iloc[:, [2, 1, 3, 0]]
        result = unordered.sort_index(axis=1)
        tm.assert_frame_equal(result, frame)

        result = unordered.sort_index(axis=1, ascending=False)
        expected = frame.iloc[:, ::-1]
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("level", ["A", 0])  # GH#21052
    def test_sort_index_multiindex(self, level):
        # GH#13496

        # sort rows by specified level of multi-index
        mi = MultiIndex.from_tuples(
            [[2, 1, 3], [2, 1, 2], [1, 1, 1]], names=list("ABC")
        )
        df = DataFrame([[1, 2], [3, 4], [5, 6]], index=mi)

        expected_mi = MultiIndex.from_tuples(
            [[1, 1, 1], [2, 1, 2], [2, 1, 3]], names=list("ABC")
        )
        expected = DataFrame([[5, 6], [3, 4], [1, 2]], index=expected_mi)
        result = df.sort_index(level=level)
        tm.assert_frame_equal(result, expected)

        # sort_remaining=False
        expected_mi = MultiIndex.from_tuples(
            [[1, 1, 1], [2, 1, 3], [2, 1, 2]], names=list("ABC")
        )
        expected = DataFrame([[5, 6], [1, 2], [3, 4]], index=expected_mi)
        result = df.sort_index(level=level, sort_remaining=False)
        tm.assert_frame_equal(result, expected)

    def test_sort_index_intervalindex(self):
        # this is a de-facto sort via unstack
        # confirming that we sort in the order of the bins
        y = Series(np.random.default_rng(2).standard_normal(100))
        x1 = Series(np.sign(np.random.default_rng(2).standard_normal(100)))
        x2 = pd.cut(
            Series(np.random.default_rng(2).standard_normal(100)),
            bins=[-3, -0.5, 0, 0.5, 3],
        )
        model = pd.concat([y, x1, x2], axis=1, keys=["Y", "X1", "X2"])

        result = model.groupby(["X1", "X2"], observed=True).mean().unstack()
        expected = IntervalIndex.from_tuples(
            [(-3.0, -0.5), (-0.5, 0.0), (0.0, 0.5), (0.5, 3.0)], closed="right"
        )
        result = result.columns.levels[1].categories
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("inplace", [True, False])
    @pytest.mark.parametrize(
        "original_dict, sorted_dict, ascending, ignore_index, output_index",
        [
            ({"A": [1, 2, 3]}, {"A": [2, 3, 1]}, False, True, [0, 1, 2]),
            ({"A": [1, 2, 3]}, {"A": [1, 3, 2]}, True, True, [0, 1, 2]),
            ({"A": [1, 2, 3]}, {"A": [2, 3, 1]}, False, False, [5, 3, 2]),
            ({"A": [1, 2, 3]}, {"A": [1, 3, 2]}, True, False, [2, 3, 5]),
        ],
    )
    def test_sort_index_ignore_index(
        self, inplace, original_dict, sorted_dict, ascending, ignore_index, output_index
    ):
        # GH 30114
        original_index = [2, 5, 3]
        df = DataFrame(original_dict, index=original_index)
        expected_df = DataFrame(sorted_dict, index=output_index)
        kwargs = {
            "ascending": ascending,
            "ignore_index": ignore_index,
            "inplace": inplace,
        }

        if inplace:
            result_df = df.copy()
            result_df.sort_index(**kwargs)
        else:
            result_df = df.sort_index(**kwargs)

        tm.assert_frame_equal(result_df, expected_df)
        tm.assert_frame_equal(df, DataFrame(original_dict, index=original_index))

    @pytest.mark.parametrize("inplace", [True, False])
    @pytest.mark.parametrize("ignore_index", [True, False])
    def test_respect_ignore_index(self, inplace, ignore_index):
        # GH 43591
        df = DataFrame({"a": [1, 2, 3]}, index=RangeIndex(4, -1, -2))
        result = df.sort_index(
            ascending=False, ignore_index=ignore_index, inplace=inplace
        )

        if inplace:
            result = df
        if ignore_index:
            expected = DataFrame({"a": [1, 2, 3]})
        else:
            expected = DataFrame({"a": [1, 2, 3]}, index=RangeIndex(4, -1, -2))

        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("inplace", [True, False])
    @pytest.mark.parametrize(
        "original_dict, sorted_dict, ascending, ignore_index, output_index",
        [
            (
                {"M1": [1, 2], "M2": [3, 4]},
                {"M1": [1, 2], "M2": [3, 4]},
                True,
                True,
                [0, 1],
            ),
            (
                {"M1": [1, 2], "M2": [3, 4]},
                {"M1": [2, 1], "M2": [4, 3]},
                False,
                True,
                [0, 1],
            ),
            (
                {"M1": [1, 2], "M2": [3, 4]},
                {"M1": [1, 2], "M2": [3, 4]},
                True,
                False,
                MultiIndex.from_tuples([(2, 1), (3, 4)], names=list("AB")),
            ),
            (
                {"M1": [1, 2], "M2": [3, 4]},
                {"M1": [2, 1], "M2": [4, 3]},
                False,
                False,
                MultiIndex.from_tuples([(3, 4), (2, 1)], names=list("AB")),
            ),
        ],
    )
    def test_sort_index_ignore_index_multi_index(
        self, inplace, original_dict, sorted_dict, ascending, ignore_index, output_index
    ):
        # GH 30114, this is to test ignore_index on MultiIndex of index
        mi = MultiIndex.from_tuples([(2, 1), (3, 4)], names=list("AB"))
        df = DataFrame(original_dict, index=mi)
        expected_df = DataFrame(sorted_dict, index=output_index)

        kwargs = {
            "ascending": ascending,
            "ignore_index": ignore_index,
            "inplace": inplace,
        }

        if inplace:
            result_df = df.copy()
            result_df.sort_index(**kwargs)
        else:
            result_df = df.sort_index(**kwargs)

        tm.assert_frame_equal(result_df, expected_df)
        tm.assert_frame_equal(df, DataFrame(original_dict, index=mi))

    def test_sort_index_categorical_multiindex(self):
        # GH#15058
        df = DataFrame(
            {
                "a": range(6),
                "l1": pd.Categorical(
                    ["a", "a", "b", "b", "c", "c"],
                    categories=["c", "a", "b"],
                    ordered=True,
                ),
                "l2": [0, 1, 0, 1, 0, 1],
            }
        )
        result = df.set_index(["l1", "l2"]).sort_index()
        expected = DataFrame(
            [4, 5, 0, 1, 2, 3],
            columns=["a"],
            index=MultiIndex(
                levels=[
                    CategoricalIndex(
                        ["c", "a", "b"],
                        categories=["c", "a", "b"],
                        ordered=True,
                        name="l1",
                        dtype="category",
                    ),
                    [0, 1],
                ],
                codes=[[0, 0, 1, 1, 2, 2], [0, 1, 0, 1, 0, 1]],
                names=["l1", "l2"],
            ),
        )
        tm.assert_frame_equal(result, expected)

    def test_sort_index_and_reconstruction(self):
        # GH#15622
        # lexsortedness should be identical
        # across MultiIndex construction methods

        df = DataFrame([[1, 1], [2, 2]], index=list("ab"))
        expected = DataFrame(
            [[1, 1], [2, 2], [1, 1], [2, 2]],
            index=MultiIndex.from_tuples(
                [(0.5, "a"), (0.5, "b"), (0.8, "a"), (0.8, "b")]
            ),
        )
        assert expected.index._is_lexsorted()

        result = DataFrame(
            [[1, 1], [2, 2], [1, 1], [2, 2]],
            index=MultiIndex.from_product([[0.5, 0.8], list("ab")]),
        )
        result = result.sort_index()
        assert result.index.is_monotonic_increasing

        tm.assert_frame_equal(result, expected)

        result = DataFrame(
            [[1, 1], [2, 2], [1, 1], [2, 2]],
            index=MultiIndex(
                levels=[[0.5, 0.8], ["a", "b"]], codes=[[0, 0, 1, 1], [0, 1, 0, 1]]
            ),
        )
        result = result.sort_index()
        assert result.index._is_lexsorted()

        tm.assert_frame_equal(result, expected)

        concatted = pd.concat([df, df], keys=[0.8, 0.5])
        result = concatted.sort_index()

        assert result.index.is_monotonic_increasing

        tm.assert_frame_equal(result, expected)

        # GH#14015
        df = DataFrame(
            [[1, 2], [6, 7]],
            columns=MultiIndex.from_tuples(
                [(0, "20160811 12:00:00"), (0, "20160809 12:00:00")],
                names=["l1", "Date"],
            ),
        )

        df.columns = df.columns.set_levels(
            pd.to_datetime(df.columns.levels[1]), level=1
        )
        assert not df.columns.is_monotonic_increasing
        result = df.sort_index(axis=1)
        assert result.columns.is_monotonic_increasing
        result = df.sort_index(axis=1, level=1)
        assert result.columns.is_monotonic_increasing

    # TODO: better name, de-duplicate with test_sort_index_level above
    def test_sort_index_level2(self, multiindex_dataframe_random_data):
        frame = multiindex_dataframe_random_data

        df = frame.copy()
        df.index = np.arange(len(df))

        # axis=1

        # series
        a_sorted = frame["A"].sort_index(level=0)

        # preserve names
        assert a_sorted.index.names == frame.index.names

        # inplace
        rs = frame.copy()
        return_value = rs.sort_index(level=0, inplace=True)
        assert return_value is None
        tm.assert_frame_equal(rs, frame.sort_index(level=0))

    def test_sort_index_level_large_cardinality(self):
        # GH#2684 (int64)
        index = MultiIndex.from_arrays([np.arange(4000)] * 3)
        df = DataFrame(
            np.random.default_rng(2).standard_normal(4000).astype("int64"), index=index
        )

        # it works!
        result = df.sort_index(level=0)
        assert result.index._lexsort_depth == 3

        # GH#2684 (int32)
        index = MultiIndex.from_arrays([np.arange(4000)] * 3)
        df = DataFrame(
            np.random.default_rng(2).standard_normal(4000).astype("int32"), index=index
        )

        # it works!
        result = df.sort_index(level=0)
        assert (result.dtypes.values == df.dtypes.values).all()
        assert result.index._lexsort_depth == 3

    def test_sort_index_level_by_name(self, multiindex_dataframe_random_data):
        frame = multiindex_dataframe_random_data

        frame.index.names = ["first", "second"]
        result = frame.sort_index(level="second")
        expected = frame.sort_index(level=1)
        tm.assert_frame_equal(result, expected)

    def test_sort_index_level_mixed(self, multiindex_dataframe_random_data):
        frame = multiindex_dataframe_random_data

        sorted_before = frame.sort_index(level=1)

        df = frame.copy()
        df["foo"] = "bar"
        sorted_after = df.sort_index(level=1)
        tm.assert_frame_equal(sorted_before, sorted_after.drop(["foo"], axis=1))

        dft = frame.T
        sorted_before = dft.sort_index(level=1, axis=1)
        dft["foo", "three"] = "bar"

        sorted_after = dft.sort_index(level=1, axis=1)
        tm.assert_frame_equal(
            sorted_before.drop([("foo", "three")], axis=1),
            sorted_after.drop([("foo", "three")], axis=1),
        )

    def test_sort_index_preserve_levels(self, multiindex_dataframe_random_data):
        frame = multiindex_dataframe_random_data

        result = frame.sort_index()
        assert result.index.names == frame.index.names

    @pytest.mark.parametrize(
        "gen,extra",
        [
            ([1.0, 3.0, 2.0, 5.0], 4.0),
            ([1, 3, 2, 5], 4),
            (
                [
                    Timestamp("20130101"),
                    Timestamp("20130103"),
                    Timestamp("20130102"),
                    Timestamp("20130105"),
                ],
                Timestamp("20130104"),
            ),
            (["1one", "3one", "2one", "5one"], "4one"),
        ],
    )
    def test_sort_index_multilevel_repr_8017(self, gen, extra):
        data = np.random.default_rng(2).standard_normal((3, 4))

        columns = MultiIndex.from_tuples([("red", i) for i in gen])
        df = DataFrame(data, index=list("def"), columns=columns)
        df2 = pd.concat(
            [
                df,
                DataFrame(
                    "world",
                    index=list("def"),
                    columns=MultiIndex.from_tuples([("red", extra)]),
                ),
            ],
            axis=1,
        )

        # check that the repr is good
        # make sure that we have a correct sparsified repr
        # e.g. only 1 header of read
        assert str(df2).splitlines()[0].split() == ["red"]

        # GH 8017
        # sorting fails after columns added

        # construct single-dtype then sort
        result = df.copy().sort_index(axis=1)
        expected = df.iloc[:, [0, 2, 1, 3]]
        tm.assert_frame_equal(result, expected)

        result = df2.sort_index(axis=1)
        expected = df2.iloc[:, [0, 2, 1, 4, 3]]
        tm.assert_frame_equal(result, expected)

        # setitem then sort
        result = df.copy()
        result[("red", extra)] = "world"

        result = result.sort_index(axis=1)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "categories",
        [
            pytest.param(["a", "b", "c"], id="str"),
            pytest.param(
                [pd.Interval(0, 1), pd.Interval(1, 2), pd.Interval(2, 3)],
                id="pd.Interval",
            ),
        ],
    )
    def test_sort_index_with_categories(self, categories):
        # GH#23452
        df = DataFrame(
            {"foo": range(len(categories))},
            index=CategoricalIndex(
                data=categories, categories=categories, ordered=True
            ),
        )
        df.index = df.index.reorder_categories(df.index.categories[::-1])
        result = df.sort_index()
        expected = DataFrame(
            {"foo": reversed(range(len(categories)))},
            index=CategoricalIndex(
                data=categories[::-1], categories=categories[::-1], ordered=True
            ),
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "ascending",
        [
            None,
            [True, None],
            [False, "True"],
        ],
    )
    def test_sort_index_ascending_bad_value_raises(self, ascending):
        # GH 39434
        df = DataFrame(np.arange(64))
        length = len(df.index)
        df.index = [(i - length / 2) % length for i in range(length)]
        match = 'For argument "ascending" expected type bool'
        with pytest.raises(ValueError, match=match):
            df.sort_index(axis=0, ascending=ascending, na_position="first")

    def test_sort_index_use_inf_as_na(self):
        # GH 29687
        expected = DataFrame(
            {"col1": [1, 2, 3], "col2": [3, 4, 5]},
            index=pd.date_range("2020", periods=3),
        )
        msg = "use_inf_as_na option is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            with pd.option_context("mode.use_inf_as_na", True):
                result = expected.sort_index()
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "ascending",
        [(True, False), [True, False]],
    )
    def test_sort_index_ascending_tuple(self, ascending):
        df = DataFrame(
            {
                "legs": [4, 2, 4, 2, 2],
            },
            index=MultiIndex.from_tuples(
                [
                    ("mammal", "dog"),
                    ("bird", "duck"),
                    ("mammal", "horse"),
                    ("bird", "penguin"),
                    ("mammal", "kangaroo"),
                ],
                names=["class", "animal"],
            ),
        )

        # parameter `ascending`` is a tuple
        result = df.sort_index(level=(0, 1), ascending=ascending)

        expected = DataFrame(
            {
                "legs": [2, 2, 2, 4, 4],
            },
            index=MultiIndex.from_tuples(
                [
                    ("bird", "penguin"),
                    ("bird", "duck"),
                    ("mammal", "kangaroo"),
                    ("mammal", "horse"),
                    ("mammal", "dog"),
                ],
                names=["class", "animal"],
            ),
        )

        tm.assert_frame_equal(result, expected)


class TestDataFrameSortIndexKey:
    def test_sort_multi_index_key(self):
        # GH 25775, testing that sorting by index works with a multi-index.
        df = DataFrame(
            {"a": [3, 1, 2], "b": [0, 0, 0], "c": [0, 1, 2], "d": list("abc")}
        ).set_index(list("abc"))

        result = df.sort_index(level=list("ac"), key=lambda x: x)

        expected = DataFrame(
            {"a": [1, 2, 3], "b": [0, 0, 0], "c": [1, 2, 0], "d": list("bca")}
        ).set_index(list("abc"))
        tm.assert_frame_equal(result, expected)

        result = df.sort_index(level=list("ac"), key=lambda x: -x)
        expected = DataFrame(
            {"a": [3, 2, 1], "b": [0, 0, 0], "c": [0, 2, 1], "d": list("acb")}
        ).set_index(list("abc"))

        tm.assert_frame_equal(result, expected)

    def test_sort_index_key(self):  # issue 27237
        df = DataFrame(np.arange(6, dtype="int64"), index=list("aaBBca"))

        result = df.sort_index()
        expected = df.iloc[[2, 3, 0, 1, 5, 4]]
        tm.assert_frame_equal(result, expected)

        result = df.sort_index(key=lambda x: x.str.lower())
        expected = df.iloc[[0, 1, 5, 2, 3, 4]]
        tm.assert_frame_equal(result, expected)

        result = df.sort_index(key=lambda x: x.str.lower(), ascending=False)
        expected = df.iloc[[4, 2, 3, 0, 1, 5]]
        tm.assert_frame_equal(result, expected)

    def test_sort_index_key_int(self):
        df = DataFrame(np.arange(6, dtype="int64"), index=np.arange(6, dtype="int64"))

        result = df.sort_index()
        tm.assert_frame_equal(result, df)

        result = df.sort_index(key=lambda x: -x)
        expected = df.sort_index(ascending=False)
        tm.assert_frame_equal(result, expected)

        result = df.sort_index(key=lambda x: 2 * x)
        tm.assert_frame_equal(result, df)

    def test_sort_multi_index_key_str(self):
        # GH 25775, testing that sorting by index works with a multi-index.
        df = DataFrame(
            {"a": ["B", "a", "C"], "b": [0, 1, 0], "c": list("abc"), "d": [0, 1, 2]}
        ).set_index(list("abc"))

        result = df.sort_index(level="a", key=lambda x: x.str.lower())

        expected = DataFrame(
            {"a": ["a", "B", "C"], "b": [1, 0, 0], "c": list("bac"), "d": [1, 0, 2]}
        ).set_index(list("abc"))
        tm.assert_frame_equal(result, expected)

        result = df.sort_index(
            level=list("abc"),  # can refer to names
            key=lambda x: x.str.lower() if x.name in ["a", "c"] else -x,
        )

        expected = DataFrame(
            {"a": ["a", "B", "C"], "b": [1, 0, 0], "c": list("bac"), "d": [1, 0, 2]}
        ).set_index(list("abc"))
        tm.assert_frame_equal(result, expected)

    def test_changes_length_raises(self):
        df = DataFrame({"A": [1, 2, 3]})
        with pytest.raises(ValueError, match="change the shape"):
            df.sort_index(key=lambda x: x[:1])

    def test_sort_index_multiindex_sparse_column(self):
        # GH 29735, testing that sort_index on a multiindexed frame with sparse
        # columns fills with 0.
        expected = DataFrame(
            {
                i: pd.array([0.0, 0.0, 0.0, 0.0], dtype=pd.SparseDtype("float64", 0.0))
                for i in range(4)
            },
            index=MultiIndex.from_product([[1, 2], [1, 2]]),
        )

        result = expected.sort_index(level=0)

        tm.assert_frame_equal(result, expected)

    def test_sort_index_na_position(self):
        # GH#51612
        df = DataFrame([1, 2], index=MultiIndex.from_tuples([(1, 1), (1, pd.NA)]))
        expected = df.copy()
        result = df.sort_index(level=[0, 1], na_position="last")
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("ascending", [True, False])
    def test_sort_index_multiindex_sort_remaining(self, ascending):
        # GH #24247
        df = DataFrame(
            {"A": [1, 2, 3, 4, 5], "B": [10, 20, 30, 40, 50]},
            index=MultiIndex.from_tuples(
                [("a", "x"), ("a", "y"), ("b", "x"), ("b", "y"), ("c", "x")]
            ),
        )

        result = df.sort_index(level=1, sort_remaining=False, ascending=ascending)

        if ascending:
            expected = DataFrame(
                {"A": [1, 3, 5, 2, 4], "B": [10, 30, 50, 20, 40]},
                index=MultiIndex.from_tuples(
                    [("a", "x"), ("b", "x"), ("c", "x"), ("a", "y"), ("b", "y")]
                ),
            )
        else:
            expected = DataFrame(
                {"A": [2, 4, 1, 3, 5], "B": [20, 40, 10, 30, 50]},
                index=MultiIndex.from_tuples(
                    [("a", "y"), ("b", "y"), ("a", "x"), ("b", "x"), ("c", "x")]
                ),
            )

        tm.assert_frame_equal(result, expected)


def test_sort_index_with_sliced_multiindex():
    # GH 55379
    mi = MultiIndex.from_tuples(
        [
            ("a", "10"),
            ("a", "18"),
            ("a", "25"),
            ("b", "16"),
            ("b", "26"),
            ("a", "45"),
            ("b", "28"),
            ("a", "5"),
            ("a", "50"),
            ("a", "51"),
            ("b", "4"),
        ],
        names=["group", "str"],
    )

    df = DataFrame({"x": range(len(mi))}, index=mi)
    result = df.iloc[0:6].sort_index()

    expected = DataFrame(
        {"x": [0, 1, 2, 5, 3, 4]},
        index=MultiIndex.from_tuples(
            [
                ("a", "10"),
                ("a", "18"),
                ("a", "25"),
                ("a", "45"),
                ("b", "16"),
                ("b", "26"),
            ],
            names=["group", "str"],
        ),
    )
    tm.assert_frame_equal(result, expected)


def test_axis_columns_ignore_index():
    # GH 56478
    df = DataFrame([[1, 2]], columns=["d", "c"])
    result = df.sort_index(axis="columns", ignore_index=True)
    expected = DataFrame([[2, 1]])
    tm.assert_frame_equal(result, expected)


def test_sort_index_stable_sort():
    # GH 57151
    df = DataFrame(
        data=[
            (Timestamp("2024-01-30 13:00:00"), 13.0),
            (Timestamp("2024-01-30 13:00:00"), 13.1),
            (Timestamp("2024-01-30 12:00:00"), 12.0),
            (Timestamp("2024-01-30 12:00:00"), 12.1),
        ],
        columns=["dt", "value"],
    ).set_index(["dt"])
    result = df.sort_index(level="dt", kind="stable")
    expected = DataFrame(
        data=[
            (Timestamp("2024-01-30 12:00:00"), 12.0),
            (Timestamp("2024-01-30 12:00:00"), 12.1),
            (Timestamp("2024-01-30 13:00:00"), 13.0),
            (Timestamp("2024-01-30 13:00:00"), 13.1),
        ],
        columns=["dt", "value"],
    ).set_index(["dt"])
    tm.assert_frame_equal(result, expected)
