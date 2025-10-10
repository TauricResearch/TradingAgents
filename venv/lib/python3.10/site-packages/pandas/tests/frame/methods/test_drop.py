import re

import numpy as np
import pytest

from pandas.errors import PerformanceWarning

import pandas as pd
from pandas import (
    DataFrame,
    DatetimeIndex,
    Index,
    MultiIndex,
    Series,
    Timestamp,
)
import pandas._testing as tm


@pytest.mark.parametrize(
    "msg,labels,level",
    [
        (r"labels \[4\] not found in level", 4, "a"),
        (r"labels \[7\] not found in level", 7, "b"),
    ],
)
def test_drop_raise_exception_if_labels_not_in_level(msg, labels, level):
    # GH 8594
    mi = MultiIndex.from_arrays([[1, 2, 3], [4, 5, 6]], names=["a", "b"])
    s = Series([10, 20, 30], index=mi)
    df = DataFrame([10, 20, 30], index=mi)

    with pytest.raises(KeyError, match=msg):
        s.drop(labels, level=level)
    with pytest.raises(KeyError, match=msg):
        df.drop(labels, level=level)


@pytest.mark.parametrize("labels,level", [(4, "a"), (7, "b")])
def test_drop_errors_ignore(labels, level):
    # GH 8594
    mi = MultiIndex.from_arrays([[1, 2, 3], [4, 5, 6]], names=["a", "b"])
    s = Series([10, 20, 30], index=mi)
    df = DataFrame([10, 20, 30], index=mi)

    expected_s = s.drop(labels, level=level, errors="ignore")
    tm.assert_series_equal(s, expected_s)

    expected_df = df.drop(labels, level=level, errors="ignore")
    tm.assert_frame_equal(df, expected_df)


def test_drop_with_non_unique_datetime_index_and_invalid_keys():
    # GH 30399

    # define dataframe with unique datetime index
    df = DataFrame(
        np.random.default_rng(2).standard_normal((5, 3)),
        columns=["a", "b", "c"],
        index=pd.date_range("2012", freq="h", periods=5),
    )
    # create dataframe with non-unique datetime index
    df = df.iloc[[0, 2, 2, 3]].copy()

    with pytest.raises(KeyError, match="not found in axis"):
        df.drop(["a", "b"])  # Dropping with labels not exist in the index


class TestDataFrameDrop:
    def test_drop_names(self):
        df = DataFrame(
            [[1, 2, 3], [3, 4, 5], [5, 6, 7]],
            index=["a", "b", "c"],
            columns=["d", "e", "f"],
        )
        df.index.name, df.columns.name = "first", "second"
        df_dropped_b = df.drop("b")
        df_dropped_e = df.drop("e", axis=1)
        df_inplace_b, df_inplace_e = df.copy(), df.copy()
        return_value = df_inplace_b.drop("b", inplace=True)
        assert return_value is None
        return_value = df_inplace_e.drop("e", axis=1, inplace=True)
        assert return_value is None
        for obj in (df_dropped_b, df_dropped_e, df_inplace_b, df_inplace_e):
            assert obj.index.name == "first"
            assert obj.columns.name == "second"
        assert list(df.columns) == ["d", "e", "f"]

        msg = r"\['g'\] not found in axis"
        with pytest.raises(KeyError, match=msg):
            df.drop(["g"])
        with pytest.raises(KeyError, match=msg):
            df.drop(["g"], axis=1)

        # errors = 'ignore'
        dropped = df.drop(["g"], errors="ignore")
        expected = Index(["a", "b", "c"], name="first")
        tm.assert_index_equal(dropped.index, expected)

        dropped = df.drop(["b", "g"], errors="ignore")
        expected = Index(["a", "c"], name="first")
        tm.assert_index_equal(dropped.index, expected)

        dropped = df.drop(["g"], axis=1, errors="ignore")
        expected = Index(["d", "e", "f"], name="second")
        tm.assert_index_equal(dropped.columns, expected)

        dropped = df.drop(["d", "g"], axis=1, errors="ignore")
        expected = Index(["e", "f"], name="second")
        tm.assert_index_equal(dropped.columns, expected)

        # GH 16398
        dropped = df.drop([], errors="ignore")
        expected = Index(["a", "b", "c"], name="first")
        tm.assert_index_equal(dropped.index, expected)

    def test_drop(self):
        simple = DataFrame({"A": [1, 2, 3, 4], "B": [0, 1, 2, 3]})
        tm.assert_frame_equal(simple.drop("A", axis=1), simple[["B"]])
        tm.assert_frame_equal(simple.drop(["A", "B"], axis="columns"), simple[[]])
        tm.assert_frame_equal(simple.drop([0, 1, 3], axis=0), simple.loc[[2], :])
        tm.assert_frame_equal(simple.drop([0, 3], axis="index"), simple.loc[[1, 2], :])

        with pytest.raises(KeyError, match=r"\[5\] not found in axis"):
            simple.drop(5)
        with pytest.raises(KeyError, match=r"\['C'\] not found in axis"):
            simple.drop("C", axis=1)
        with pytest.raises(KeyError, match=r"\[5\] not found in axis"):
            simple.drop([1, 5])
        with pytest.raises(KeyError, match=r"\['C'\] not found in axis"):
            simple.drop(["A", "C"], axis=1)

        # GH 42881
        with pytest.raises(KeyError, match=r"\['C', 'D', 'F'\] not found in axis"):
            simple.drop(["C", "D", "F"], axis=1)

        # errors = 'ignore'
        tm.assert_frame_equal(simple.drop(5, errors="ignore"), simple)
        tm.assert_frame_equal(
            simple.drop([0, 5], errors="ignore"), simple.loc[[1, 2, 3], :]
        )
        tm.assert_frame_equal(simple.drop("C", axis=1, errors="ignore"), simple)
        tm.assert_frame_equal(
            simple.drop(["A", "C"], axis=1, errors="ignore"), simple[["B"]]
        )

        # non-unique - wheee!
        nu_df = DataFrame(
            list(zip(range(3), range(-3, 1), list("abc"))), columns=["a", "a", "b"]
        )
        tm.assert_frame_equal(nu_df.drop("a", axis=1), nu_df[["b"]])
        tm.assert_frame_equal(nu_df.drop("b", axis="columns"), nu_df["a"])
        tm.assert_frame_equal(nu_df.drop([]), nu_df)  # GH 16398

        nu_df = nu_df.set_index(Index(["X", "Y", "X"]))
        nu_df.columns = list("abc")
        tm.assert_frame_equal(nu_df.drop("X", axis="rows"), nu_df.loc[["Y"], :])
        tm.assert_frame_equal(nu_df.drop(["X", "Y"], axis=0), nu_df.loc[[], :])

        # inplace cache issue
        # GH#5628
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 3)), columns=list("abc")
        )
        expected = df[~(df.b > 0)]
        return_value = df.drop(labels=df[df.b > 0].index, inplace=True)
        assert return_value is None
        tm.assert_frame_equal(df, expected)

    def test_drop_multiindex_not_lexsorted(self):
        # GH#11640

        # define the lexsorted version
        lexsorted_mi = MultiIndex.from_tuples(
            [("a", ""), ("b1", "c1"), ("b2", "c2")], names=["b", "c"]
        )
        lexsorted_df = DataFrame([[1, 3, 4]], columns=lexsorted_mi)
        assert lexsorted_df.columns._is_lexsorted()

        # define the non-lexsorted version
        not_lexsorted_df = DataFrame(
            columns=["a", "b", "c", "d"], data=[[1, "b1", "c1", 3], [1, "b2", "c2", 4]]
        )
        not_lexsorted_df = not_lexsorted_df.pivot_table(
            index="a", columns=["b", "c"], values="d"
        )
        not_lexsorted_df = not_lexsorted_df.reset_index()
        assert not not_lexsorted_df.columns._is_lexsorted()

        expected = lexsorted_df.drop("a", axis=1).astype(float)
        with tm.assert_produces_warning(PerformanceWarning):
            result = not_lexsorted_df.drop("a", axis=1)

        tm.assert_frame_equal(result, expected)

    def test_drop_api_equivalence(self):
        # equivalence of the labels/axis and index/columns API's (GH#12392)
        df = DataFrame(
            [[1, 2, 3], [3, 4, 5], [5, 6, 7]],
            index=["a", "b", "c"],
            columns=["d", "e", "f"],
        )

        res1 = df.drop("a")
        res2 = df.drop(index="a")
        tm.assert_frame_equal(res1, res2)

        res1 = df.drop("d", axis=1)
        res2 = df.drop(columns="d")
        tm.assert_frame_equal(res1, res2)

        res1 = df.drop(labels="e", axis=1)
        res2 = df.drop(columns="e")
        tm.assert_frame_equal(res1, res2)

        res1 = df.drop(["a"], axis=0)
        res2 = df.drop(index=["a"])
        tm.assert_frame_equal(res1, res2)

        res1 = df.drop(["a"], axis=0).drop(["d"], axis=1)
        res2 = df.drop(index=["a"], columns=["d"])
        tm.assert_frame_equal(res1, res2)

        msg = "Cannot specify both 'labels' and 'index'/'columns'"
        with pytest.raises(ValueError, match=msg):
            df.drop(labels="a", index="b")

        with pytest.raises(ValueError, match=msg):
            df.drop(labels="a", columns="b")

        msg = "Need to specify at least one of 'labels', 'index' or 'columns'"
        with pytest.raises(ValueError, match=msg):
            df.drop(axis=1)

    data = [[1, 2, 3], [1, 2, 3]]

    @pytest.mark.parametrize(
        "actual",
        [
            DataFrame(data=data, index=["a", "a"]),
            DataFrame(data=data, index=["a", "b"]),
            DataFrame(data=data, index=["a", "b"]).set_index([0, 1]),
            DataFrame(data=data, index=["a", "a"]).set_index([0, 1]),
        ],
    )
    def test_raise_on_drop_duplicate_index(self, actual):
        # GH#19186
        level = 0 if isinstance(actual.index, MultiIndex) else None
        msg = re.escape("\"['c'] not found in axis\"")
        with pytest.raises(KeyError, match=msg):
            actual.drop("c", level=level, axis=0)
        with pytest.raises(KeyError, match=msg):
            actual.T.drop("c", level=level, axis=1)
        expected_no_err = actual.drop("c", axis=0, level=level, errors="ignore")
        tm.assert_frame_equal(expected_no_err, actual)
        expected_no_err = actual.T.drop("c", axis=1, level=level, errors="ignore")
        tm.assert_frame_equal(expected_no_err.T, actual)

    @pytest.mark.parametrize("index", [[1, 2, 3], [1, 1, 2]])
    @pytest.mark.parametrize("drop_labels", [[], [1], [2]])
    def test_drop_empty_list(self, index, drop_labels):
        # GH#21494
        expected_index = [i for i in index if i not in drop_labels]
        frame = DataFrame(index=index).drop(drop_labels)
        tm.assert_frame_equal(frame, DataFrame(index=expected_index))

    @pytest.mark.parametrize("index", [[1, 2, 3], [1, 2, 2]])
    @pytest.mark.parametrize("drop_labels", [[1, 4], [4, 5]])
    def test_drop_non_empty_list(self, index, drop_labels):
        # GH# 21494
        with pytest.raises(KeyError, match="not found in axis"):
            DataFrame(index=index).drop(drop_labels)

    @pytest.mark.parametrize(
        "empty_listlike",
        [
            [],
            {},
            np.array([]),
            Series([], dtype="datetime64[ns]"),
            Index([]),
            DatetimeIndex([]),
        ],
    )
    def test_drop_empty_listlike_non_unique_datetime_index(self, empty_listlike):
        # GH#27994
        data = {"column_a": [5, 10], "column_b": ["one", "two"]}
        index = [Timestamp("2021-01-01"), Timestamp("2021-01-01")]
        df = DataFrame(data, index=index)

        # Passing empty list-like should return the same DataFrame.
        expected = df.copy()
        result = df.drop(empty_listlike)
        tm.assert_frame_equal(result, expected)

    def test_mixed_depth_drop(self):
        arrays = [
            ["a", "top", "top", "routine1", "routine1", "routine2"],
            ["", "OD", "OD", "result1", "result2", "result1"],
            ["", "wx", "wy", "", "", ""],
        ]

        tuples = sorted(zip(*arrays))
        index = MultiIndex.from_tuples(tuples)
        df = DataFrame(np.random.default_rng(2).standard_normal((4, 6)), columns=index)

        result = df.drop("a", axis=1)
        expected = df.drop([("a", "", "")], axis=1)
        tm.assert_frame_equal(expected, result)

        result = df.drop(["top"], axis=1)
        expected = df.drop([("top", "OD", "wx")], axis=1)
        expected = expected.drop([("top", "OD", "wy")], axis=1)
        tm.assert_frame_equal(expected, result)

        result = df.drop(("top", "OD", "wx"), axis=1)
        expected = df.drop([("top", "OD", "wx")], axis=1)
        tm.assert_frame_equal(expected, result)

        expected = df.drop([("top", "OD", "wy")], axis=1)
        expected = df.drop("top", axis=1)

        result = df.drop("result1", level=1, axis=1)
        expected = df.drop(
            [("routine1", "result1", ""), ("routine2", "result1", "")], axis=1
        )
        tm.assert_frame_equal(expected, result)

    def test_drop_multiindex_other_level_nan(self):
        # GH#12754
        df = (
            DataFrame(
                {
                    "A": ["one", "one", "two", "two"],
                    "B": [np.nan, 0.0, 1.0, 2.0],
                    "C": ["a", "b", "c", "c"],
                    "D": [1, 2, 3, 4],
                }
            )
            .set_index(["A", "B", "C"])
            .sort_index()
        )
        result = df.drop("c", level="C")
        expected = DataFrame(
            [2, 1],
            columns=["D"],
            index=MultiIndex.from_tuples(
                [("one", 0.0, "b"), ("one", np.nan, "a")], names=["A", "B", "C"]
            ),
        )
        tm.assert_frame_equal(result, expected)

    def test_drop_nonunique(self):
        df = DataFrame(
            [
                ["x-a", "x", "a", 1.5],
                ["x-a", "x", "a", 1.2],
                ["z-c", "z", "c", 3.1],
                ["x-a", "x", "a", 4.1],
                ["x-b", "x", "b", 5.1],
                ["x-b", "x", "b", 4.1],
                ["x-b", "x", "b", 2.2],
                ["y-a", "y", "a", 1.2],
                ["z-b", "z", "b", 2.1],
            ],
            columns=["var1", "var2", "var3", "var4"],
        )

        grp_size = df.groupby("var1").size()
        drop_idx = grp_size.loc[grp_size == 1]

        idf = df.set_index(["var1", "var2", "var3"])

        # it works! GH#2101
        result = idf.drop(drop_idx.index, level=0).reset_index()
        expected = df[-df.var1.isin(drop_idx.index)]

        result.index = expected.index

        tm.assert_frame_equal(result, expected)

    def test_drop_level(self, multiindex_dataframe_random_data):
        frame = multiindex_dataframe_random_data

        result = frame.drop(["bar", "qux"], level="first")
        expected = frame.iloc[[0, 1, 2, 5, 6]]
        tm.assert_frame_equal(result, expected)

        result = frame.drop(["two"], level="second")
        expected = frame.iloc[[0, 2, 3, 6, 7, 9]]
        tm.assert_frame_equal(result, expected)

        result = frame.T.drop(["bar", "qux"], axis=1, level="first")
        expected = frame.iloc[[0, 1, 2, 5, 6]].T
        tm.assert_frame_equal(result, expected)

        result = frame.T.drop(["two"], axis=1, level="second")
        expected = frame.iloc[[0, 2, 3, 6, 7, 9]].T
        tm.assert_frame_equal(result, expected)

    def test_drop_level_nonunique_datetime(self):
        # GH#12701
        idx = Index([2, 3, 4, 4, 5], name="id")
        idxdt = pd.to_datetime(
            [
                "2016-03-23 14:00",
                "2016-03-23 15:00",
                "2016-03-23 16:00",
                "2016-03-23 16:00",
                "2016-03-23 17:00",
            ]
        )
        df = DataFrame(np.arange(10).reshape(5, 2), columns=list("ab"), index=idx)
        df["tstamp"] = idxdt
        df = df.set_index("tstamp", append=True)
        ts = Timestamp("201603231600")
        assert df.index.is_unique is False

        result = df.drop(ts, level="tstamp")
        expected = df.loc[idx != 4]
        tm.assert_frame_equal(result, expected)

    def test_drop_tz_aware_timestamp_across_dst(self, frame_or_series):
        # GH#21761
        start = Timestamp("2017-10-29", tz="Europe/Berlin")
        end = Timestamp("2017-10-29 04:00:00", tz="Europe/Berlin")
        index = pd.date_range(start, end, freq="15min")
        data = frame_or_series(data=[1] * len(index), index=index)
        result = data.drop(start)
        expected_start = Timestamp("2017-10-29 00:15:00", tz="Europe/Berlin")
        expected_idx = pd.date_range(expected_start, end, freq="15min")
        expected = frame_or_series(data=[1] * len(expected_idx), index=expected_idx)
        tm.assert_equal(result, expected)

    def test_drop_preserve_names(self):
        index = MultiIndex.from_arrays(
            [[0, 0, 0, 1, 1, 1], [1, 2, 3, 1, 2, 3]], names=["one", "two"]
        )

        df = DataFrame(np.random.default_rng(2).standard_normal((6, 3)), index=index)

        result = df.drop([(0, 2)])
        assert result.index.names == ("one", "two")

    @pytest.mark.parametrize(
        "operation", ["__iadd__", "__isub__", "__imul__", "__ipow__"]
    )
    @pytest.mark.parametrize("inplace", [False, True])
    def test_inplace_drop_and_operation(self, operation, inplace):
        # GH#30484
        df = DataFrame({"x": range(5)})
        expected = df.copy()
        df["y"] = range(5)
        y = df["y"]

        with tm.assert_produces_warning(None):
            if inplace:
                df.drop("y", axis=1, inplace=inplace)
            else:
                df = df.drop("y", axis=1, inplace=inplace)

            # Perform operation and check result
            getattr(y, operation)(1)
            tm.assert_frame_equal(df, expected)

    def test_drop_with_non_unique_multiindex(self):
        # GH#36293
        mi = MultiIndex.from_arrays([["x", "y", "x"], ["i", "j", "i"]])
        df = DataFrame([1, 2, 3], index=mi)
        result = df.drop(index="x")
        expected = DataFrame([2], index=MultiIndex.from_arrays([["y"], ["j"]]))
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("indexer", [("a", "a"), [("a", "a")]])
    def test_drop_tuple_with_non_unique_multiindex(self, indexer):
        # GH#42771
        idx = MultiIndex.from_product([["a", "b"], ["a", "a"]])
        df = DataFrame({"x": range(len(idx))}, index=idx)
        result = df.drop(index=[("a", "a")])
        expected = DataFrame(
            {"x": [2, 3]}, index=MultiIndex.from_tuples([("b", "a"), ("b", "a")])
        )
        tm.assert_frame_equal(result, expected)

    def test_drop_with_duplicate_columns(self):
        df = DataFrame(
            [[1, 5, 7.0], [1, 5, 7.0], [1, 5, 7.0]], columns=["bar", "a", "a"]
        )
        result = df.drop(["a"], axis=1)
        expected = DataFrame([[1], [1], [1]], columns=["bar"])
        tm.assert_frame_equal(result, expected)
        result = df.drop("a", axis=1)
        tm.assert_frame_equal(result, expected)

    def test_drop_with_duplicate_columns2(self):
        # drop buggy GH#6240
        df = DataFrame(
            {
                "A": np.random.default_rng(2).standard_normal(5),
                "B": np.random.default_rng(2).standard_normal(5),
                "C": np.random.default_rng(2).standard_normal(5),
                "D": ["a", "b", "c", "d", "e"],
            }
        )

        expected = df.take([0, 1, 1], axis=1)
        df2 = df.take([2, 0, 1, 2, 1], axis=1)
        result = df2.drop("C", axis=1)
        tm.assert_frame_equal(result, expected)

    def test_drop_inplace_no_leftover_column_reference(self):
        # GH 13934
        df = DataFrame({"a": [1, 2, 3]}, columns=Index(["a"], dtype="object"))
        a = df.a
        df.drop(["a"], axis=1, inplace=True)
        tm.assert_index_equal(df.columns, Index([], dtype="object"))
        a -= a.mean()
        tm.assert_index_equal(df.columns, Index([], dtype="object"))

    def test_drop_level_missing_label_multiindex(self):
        # GH 18561
        df = DataFrame(index=MultiIndex.from_product([range(3), range(3)]))
        with pytest.raises(KeyError, match="labels \\[5\\] not found in level"):
            df.drop(5, level=0)

    @pytest.mark.parametrize("idx, level", [(["a", "b"], 0), (["a"], None)])
    def test_drop_index_ea_dtype(self, any_numeric_ea_dtype, idx, level):
        # GH#45860
        df = DataFrame(
            {"a": [1, 2, 2, pd.NA], "b": 100}, dtype=any_numeric_ea_dtype
        ).set_index(idx)
        result = df.drop(Index([2, pd.NA]), level=level)
        expected = DataFrame(
            {"a": [1], "b": 100}, dtype=any_numeric_ea_dtype
        ).set_index(idx)
        tm.assert_frame_equal(result, expected)

    def test_drop_parse_strings_datetime_index(self):
        # GH #5355
        df = DataFrame(
            {"a": [1, 2], "b": [1, 2]},
            index=[Timestamp("2000-01-03"), Timestamp("2000-01-04")],
        )
        result = df.drop("2000-01-03", axis=0)
        expected = DataFrame({"a": [2], "b": [2]}, index=[Timestamp("2000-01-04")])
        tm.assert_frame_equal(result, expected)
