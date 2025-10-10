import re

import numpy as np
import pytest

from pandas._config import using_string_dtype

import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    Categorical,
    DataFrame,
    Index,
    MultiIndex,
    Series,
    Timestamp,
    bdate_range,
    concat,
    merge,
    option_context,
)
import pandas._testing as tm


def get_test_data(ngroups=8, n=50):
    unique_groups = list(range(ngroups))
    arr = np.asarray(np.tile(unique_groups, n // ngroups))

    if len(arr) < n:
        arr = np.asarray(list(arr) + unique_groups[: n - len(arr)])

    np.random.default_rng(2).shuffle(arr)
    return arr


class TestJoin:
    # aggregate multiple columns
    @pytest.fixture
    def df(self):
        df = DataFrame(
            {
                "key1": get_test_data(),
                "key2": get_test_data(),
                "data1": np.random.default_rng(2).standard_normal(50),
                "data2": np.random.default_rng(2).standard_normal(50),
            }
        )

        # exclude a couple keys for fun
        df = df[df["key2"] > 1]
        return df

    @pytest.fixture
    def df2(self):
        return DataFrame(
            {
                "key1": get_test_data(n=10),
                "key2": get_test_data(ngroups=4, n=10),
                "value": np.random.default_rng(2).standard_normal(10),
            }
        )

    @pytest.fixture
    def target_source(self):
        data = {
            "A": [0.0, 1.0, 2.0, 3.0, 4.0],
            "B": [0.0, 1.0, 0.0, 1.0, 0.0],
            "C": ["foo1", "foo2", "foo3", "foo4", "foo5"],
            "D": bdate_range("1/1/2009", periods=5),
        }
        target = DataFrame(data, index=Index(["a", "b", "c", "d", "e"], dtype=object))

        # Join on string value

        source = DataFrame(
            {"MergedA": data["A"], "MergedD": data["D"]}, index=data["C"]
        )
        return target, source

    def test_left_outer_join(self, df, df2):
        joined_key2 = merge(df, df2, on="key2")
        _check_join(df, df2, joined_key2, ["key2"], how="left")

        joined_both = merge(df, df2)
        _check_join(df, df2, joined_both, ["key1", "key2"], how="left")

    def test_right_outer_join(self, df, df2):
        joined_key2 = merge(df, df2, on="key2", how="right")
        _check_join(df, df2, joined_key2, ["key2"], how="right")

        joined_both = merge(df, df2, how="right")
        _check_join(df, df2, joined_both, ["key1", "key2"], how="right")

    def test_full_outer_join(self, df, df2):
        joined_key2 = merge(df, df2, on="key2", how="outer")
        _check_join(df, df2, joined_key2, ["key2"], how="outer")

        joined_both = merge(df, df2, how="outer")
        _check_join(df, df2, joined_both, ["key1", "key2"], how="outer")

    def test_inner_join(self, df, df2):
        joined_key2 = merge(df, df2, on="key2", how="inner")
        _check_join(df, df2, joined_key2, ["key2"], how="inner")

        joined_both = merge(df, df2, how="inner")
        _check_join(df, df2, joined_both, ["key1", "key2"], how="inner")

    def test_handle_overlap(self, df, df2):
        joined = merge(df, df2, on="key2", suffixes=(".foo", ".bar"))

        assert "key1.foo" in joined
        assert "key1.bar" in joined

    def test_handle_overlap_arbitrary_key(self, df, df2):
        joined = merge(
            df,
            df2,
            left_on="key2",
            right_on="key1",
            suffixes=(".foo", ".bar"),
        )
        assert "key1.foo" in joined
        assert "key2.bar" in joined

    @pytest.mark.parametrize(
        "infer_string", [False, pytest.param(True, marks=td.skip_if_no("pyarrow"))]
    )
    def test_join_on(self, target_source, infer_string):
        target, source = target_source

        merged = target.join(source, on="C")
        tm.assert_series_equal(merged["MergedA"], target["A"], check_names=False)
        tm.assert_series_equal(merged["MergedD"], target["D"], check_names=False)

        # join with duplicates (fix regression from DataFrame/Matrix merge)
        df = DataFrame({"key": ["a", "a", "b", "b", "c"]})
        df2 = DataFrame({"value": [0, 1, 2]}, index=["a", "b", "c"])
        joined = df.join(df2, on="key")
        expected = DataFrame(
            {"key": ["a", "a", "b", "b", "c"], "value": [0, 0, 1, 1, 2]}
        )
        tm.assert_frame_equal(joined, expected)

        # Test when some are missing
        df_a = DataFrame([[1], [2], [3]], index=["a", "b", "c"], columns=["one"])
        df_b = DataFrame([["foo"], ["bar"]], index=[1, 2], columns=["two"])
        df_c = DataFrame([[1], [2]], index=[1, 2], columns=["three"])
        joined = df_a.join(df_b, on="one")
        joined = joined.join(df_c, on="one")
        assert np.isnan(joined["two"]["c"])
        assert np.isnan(joined["three"]["c"])

        # merge column not p resent
        with pytest.raises(KeyError, match="^'E'$"):
            target.join(source, on="E")

        # overlap
        source_copy = source.copy()
        msg = (
            "You are trying to merge on float64 and object|str columns for key "
            "'A'. If you wish to proceed you should use pd.concat"
        )
        with pytest.raises(ValueError, match=msg):
            target.join(source_copy, on="A")

    def test_join_on_fails_with_different_right_index(self):
        df = DataFrame(
            {
                "a": np.random.default_rng(2).choice(["m", "f"], size=3),
                "b": np.random.default_rng(2).standard_normal(3),
            }
        )
        df2 = DataFrame(
            {
                "a": np.random.default_rng(2).choice(["m", "f"], size=10),
                "b": np.random.default_rng(2).standard_normal(10),
            },
            index=MultiIndex.from_product([range(5), ["A", "B"]]),
        )
        msg = r'len\(left_on\) must equal the number of levels in the index of "right"'
        with pytest.raises(ValueError, match=msg):
            merge(df, df2, left_on="a", right_index=True)

    def test_join_on_fails_with_different_left_index(self):
        df = DataFrame(
            {
                "a": np.random.default_rng(2).choice(["m", "f"], size=3),
                "b": np.random.default_rng(2).standard_normal(3),
            },
            index=MultiIndex.from_arrays([range(3), list("abc")]),
        )
        df2 = DataFrame(
            {
                "a": np.random.default_rng(2).choice(["m", "f"], size=10),
                "b": np.random.default_rng(2).standard_normal(10),
            }
        )
        msg = r'len\(right_on\) must equal the number of levels in the index of "left"'
        with pytest.raises(ValueError, match=msg):
            merge(df, df2, right_on="b", left_index=True)

    def test_join_on_fails_with_different_column_counts(self):
        df = DataFrame(
            {
                "a": np.random.default_rng(2).choice(["m", "f"], size=3),
                "b": np.random.default_rng(2).standard_normal(3),
            }
        )
        df2 = DataFrame(
            {
                "a": np.random.default_rng(2).choice(["m", "f"], size=10),
                "b": np.random.default_rng(2).standard_normal(10),
            },
            index=MultiIndex.from_product([range(5), ["A", "B"]]),
        )
        msg = r"len\(right_on\) must equal len\(left_on\)"
        with pytest.raises(ValueError, match=msg):
            merge(df, df2, right_on="a", left_on=["a", "b"])

    @pytest.mark.parametrize("wrong_type", [2, "str", None, np.array([0, 1])])
    def test_join_on_fails_with_wrong_object_type(self, wrong_type):
        # GH12081 - original issue

        # GH21220 - merging of Series and DataFrame is now allowed
        # Edited test to remove the Series object from test parameters

        df = DataFrame({"a": [1, 1]})
        msg = (
            "Can only merge Series or DataFrame objects, "
            f"a {type(wrong_type)} was passed"
        )
        with pytest.raises(TypeError, match=msg):
            merge(wrong_type, df, left_on="a", right_on="a")
        with pytest.raises(TypeError, match=msg):
            merge(df, wrong_type, left_on="a", right_on="a")

    def test_join_on_pass_vector(self, target_source):
        target, source = target_source
        expected = target.join(source, on="C")
        expected = expected.rename(columns={"C": "key_0"})
        expected = expected[["key_0", "A", "B", "D", "MergedA", "MergedD"]]

        join_col = target.pop("C")
        result = target.join(source, on=join_col)
        tm.assert_frame_equal(result, expected)

    def test_join_with_len0(self, target_source):
        # nothing to merge
        target, source = target_source
        merged = target.join(source.reindex([]), on="C")
        for col in source:
            assert col in merged
            assert merged[col].isna().all()

        merged2 = target.join(source.reindex([]), on="C", how="inner")
        tm.assert_index_equal(merged2.columns, merged.columns)
        assert len(merged2) == 0

    def test_join_on_inner(self):
        df = DataFrame({"key": ["a", "a", "d", "b", "b", "c"]})
        df2 = DataFrame({"value": [0, 1]}, index=["a", "b"])

        joined = df.join(df2, on="key", how="inner")

        expected = df.join(df2, on="key")
        expected = expected[expected["value"].notna()]
        tm.assert_series_equal(joined["key"], expected["key"])
        tm.assert_series_equal(joined["value"], expected["value"], check_dtype=False)
        tm.assert_index_equal(joined.index, expected.index)

    def test_join_on_singlekey_list(self):
        df = DataFrame({"key": ["a", "a", "b", "b", "c"]})
        df2 = DataFrame({"value": [0, 1, 2]}, index=["a", "b", "c"])

        # corner cases
        joined = df.join(df2, on=["key"])
        expected = df.join(df2, on="key")

        tm.assert_frame_equal(joined, expected)

    def test_join_on_series(self, target_source):
        target, source = target_source
        result = target.join(source["MergedA"], on="C")
        expected = target.join(source[["MergedA"]], on="C")
        tm.assert_frame_equal(result, expected)

    def test_join_on_series_buglet(self):
        # GH #638
        df = DataFrame({"a": [1, 1]})
        ds = Series([2], index=[1], name="b")
        result = df.join(ds, on="a")
        expected = DataFrame({"a": [1, 1], "b": [2, 2]}, index=df.index)
        tm.assert_frame_equal(result, expected)

    def test_join_index_mixed(self, join_type):
        # no overlapping blocks
        df1 = DataFrame(index=np.arange(10))
        df1["bool"] = True
        df1["string"] = "foo"

        df2 = DataFrame(index=np.arange(5, 15))
        df2["int"] = 1
        df2["float"] = 1.0

        joined = df1.join(df2, how=join_type)
        expected = _join_by_hand(df1, df2, how=join_type)
        tm.assert_frame_equal(joined, expected)

        joined = df2.join(df1, how=join_type)
        expected = _join_by_hand(df2, df1, how=join_type)
        tm.assert_frame_equal(joined, expected)

    def test_join_index_mixed_overlap(self):
        df1 = DataFrame(
            {"A": 1.0, "B": 2, "C": "foo", "D": True},
            index=np.arange(10),
            columns=["A", "B", "C", "D"],
        )
        assert df1["B"].dtype == np.int64
        assert df1["D"].dtype == np.bool_

        df2 = DataFrame(
            {"A": 1.0, "B": 2, "C": "foo", "D": True},
            index=np.arange(0, 10, 2),
            columns=["A", "B", "C", "D"],
        )

        # overlap
        joined = df1.join(df2, lsuffix="_one", rsuffix="_two")
        expected_columns = [
            "A_one",
            "B_one",
            "C_one",
            "D_one",
            "A_two",
            "B_two",
            "C_two",
            "D_two",
        ]
        df1.columns = expected_columns[:4]
        df2.columns = expected_columns[4:]
        expected = _join_by_hand(df1, df2)
        tm.assert_frame_equal(joined, expected)

    # triggers warning about empty entries
    @pytest.mark.xfail(using_string_dtype(), reason="TODO(infer_string)")
    def test_join_empty_bug(self):
        # generated an exception in 0.4.3
        x = DataFrame()
        x.join(DataFrame([3], index=[0], columns=["A"]), how="outer")

    def test_join_unconsolidated(self):
        # GH #331
        a = DataFrame(
            np.random.default_rng(2).standard_normal((30, 2)), columns=["a", "b"]
        )
        c = Series(np.random.default_rng(2).standard_normal(30))
        a["c"] = c
        d = DataFrame(np.random.default_rng(2).standard_normal((30, 1)), columns=["q"])

        # it works!
        a.join(d)
        d.join(a)

    def test_join_multiindex(self):
        index1 = MultiIndex.from_arrays(
            [["a", "a", "a", "b", "b", "b"], [1, 2, 3, 1, 2, 3]],
            names=["first", "second"],
        )

        index2 = MultiIndex.from_arrays(
            [["b", "b", "b", "c", "c", "c"], [1, 2, 3, 1, 2, 3]],
            names=["first", "second"],
        )

        df1 = DataFrame(
            data=np.random.default_rng(2).standard_normal(6),
            index=index1,
            columns=["var X"],
        )
        df2 = DataFrame(
            data=np.random.default_rng(2).standard_normal(6),
            index=index2,
            columns=["var Y"],
        )

        df1 = df1.sort_index(level=0)
        df2 = df2.sort_index(level=0)

        joined = df1.join(df2, how="outer")
        ex_index = Index(index1.values).union(Index(index2.values))
        expected = df1.reindex(ex_index).join(df2.reindex(ex_index))
        expected.index.names = index1.names
        tm.assert_frame_equal(joined, expected)
        assert joined.index.names == index1.names

        df1 = df1.sort_index(level=1)
        df2 = df2.sort_index(level=1)

        joined = df1.join(df2, how="outer").sort_index(level=0)
        ex_index = Index(index1.values).union(Index(index2.values))
        expected = df1.reindex(ex_index).join(df2.reindex(ex_index))
        expected.index.names = index1.names

        tm.assert_frame_equal(joined, expected)
        assert joined.index.names == index1.names

    def test_join_inner_multiindex(self, lexsorted_two_level_string_multiindex):
        key1 = ["bar", "bar", "bar", "foo", "foo", "baz", "baz", "qux", "qux", "snap"]
        key2 = [
            "two",
            "one",
            "three",
            "one",
            "two",
            "one",
            "two",
            "two",
            "three",
            "one",
        ]

        data = np.random.default_rng(2).standard_normal(len(key1))
        data = DataFrame({"key1": key1, "key2": key2, "data": data})

        index = lexsorted_two_level_string_multiindex
        to_join = DataFrame(
            np.random.default_rng(2).standard_normal((10, 3)),
            index=index,
            columns=["j_one", "j_two", "j_three"],
        )

        joined = data.join(to_join, on=["key1", "key2"], how="inner")
        expected = merge(
            data,
            to_join.reset_index(),
            left_on=["key1", "key2"],
            right_on=["first", "second"],
            how="inner",
            sort=False,
        )

        expected2 = merge(
            to_join,
            data,
            right_on=["key1", "key2"],
            left_index=True,
            how="inner",
            sort=False,
        )
        tm.assert_frame_equal(joined, expected2.reindex_like(joined))

        expected2 = merge(
            to_join,
            data,
            right_on=["key1", "key2"],
            left_index=True,
            how="inner",
            sort=False,
        )

        expected = expected.drop(["first", "second"], axis=1)
        expected.index = joined.index

        assert joined.index.is_monotonic_increasing
        tm.assert_frame_equal(joined, expected)

        # _assert_same_contents(expected, expected2.loc[:, expected.columns])

    def test_join_hierarchical_mixed_raises(self):
        # GH 2024
        # GH 40993: For raising, enforced in 2.0
        df = DataFrame([(1, 2, 3), (4, 5, 6)], columns=["a", "b", "c"])
        new_df = df.groupby(["a"]).agg({"b": ["mean", "sum"]})
        other_df = DataFrame([(1, 2, 3), (7, 10, 6)], columns=["a", "b", "d"])
        other_df.set_index("a", inplace=True)
        # GH 9455, 12219
        with pytest.raises(
            pd.errors.MergeError, match="Not allowed to merge between different levels"
        ):
            merge(new_df, other_df, left_index=True, right_index=True)

    def test_join_float64_float32(self):
        a = DataFrame(
            np.random.default_rng(2).standard_normal((10, 2)),
            columns=["a", "b"],
            dtype=np.float64,
        )
        b = DataFrame(
            np.random.default_rng(2).standard_normal((10, 1)),
            columns=["c"],
            dtype=np.float32,
        )
        joined = a.join(b)
        assert joined.dtypes["a"] == "float64"
        assert joined.dtypes["b"] == "float64"
        assert joined.dtypes["c"] == "float32"

        a = np.random.default_rng(2).integers(0, 5, 100).astype("int64")
        b = np.random.default_rng(2).random(100).astype("float64")
        c = np.random.default_rng(2).random(100).astype("float32")
        df = DataFrame({"a": a, "b": b, "c": c})
        xpdf = DataFrame({"a": a, "b": b, "c": c})
        s = DataFrame(
            np.random.default_rng(2).random(5).astype("float32"), columns=["md"]
        )
        rs = df.merge(s, left_on="a", right_index=True)
        assert rs.dtypes["a"] == "int64"
        assert rs.dtypes["b"] == "float64"
        assert rs.dtypes["c"] == "float32"
        assert rs.dtypes["md"] == "float32"

        xp = xpdf.merge(s, left_on="a", right_index=True)
        tm.assert_frame_equal(rs, xp)

    def test_join_many_non_unique_index(self):
        df1 = DataFrame({"a": [1, 1], "b": [1, 1], "c": [10, 20]})
        df2 = DataFrame({"a": [1, 1], "b": [1, 2], "d": [100, 200]})
        df3 = DataFrame({"a": [1, 1], "b": [1, 2], "e": [1000, 2000]})
        idf1 = df1.set_index(["a", "b"])
        idf2 = df2.set_index(["a", "b"])
        idf3 = df3.set_index(["a", "b"])

        result = idf1.join([idf2, idf3], how="outer")

        df_partially_merged = merge(df1, df2, on=["a", "b"], how="outer")
        expected = merge(df_partially_merged, df3, on=["a", "b"], how="outer")

        result = result.reset_index()
        expected = expected[result.columns]
        expected["a"] = expected.a.astype("int64")
        expected["b"] = expected.b.astype("int64")
        tm.assert_frame_equal(result, expected)

        df1 = DataFrame({"a": [1, 1, 1], "b": [1, 1, 1], "c": [10, 20, 30]})
        df2 = DataFrame({"a": [1, 1, 1], "b": [1, 1, 2], "d": [100, 200, 300]})
        df3 = DataFrame({"a": [1, 1, 1], "b": [1, 1, 2], "e": [1000, 2000, 3000]})
        idf1 = df1.set_index(["a", "b"])
        idf2 = df2.set_index(["a", "b"])
        idf3 = df3.set_index(["a", "b"])
        result = idf1.join([idf2, idf3], how="inner")

        df_partially_merged = merge(df1, df2, on=["a", "b"], how="inner")
        expected = merge(df_partially_merged, df3, on=["a", "b"], how="inner")

        result = result.reset_index()

        tm.assert_frame_equal(result, expected.loc[:, result.columns])

        # GH 11519
        df = DataFrame(
            {
                "A": ["foo", "bar", "foo", "bar", "foo", "bar", "foo", "foo"],
                "B": ["one", "one", "two", "three", "two", "two", "one", "three"],
                "C": np.random.default_rng(2).standard_normal(8),
                "D": np.random.default_rng(2).standard_normal(8),
            }
        )
        s = Series(
            np.repeat(np.arange(8), 2), index=np.repeat(np.arange(8), 2), name="TEST"
        )
        inner = df.join(s, how="inner")
        outer = df.join(s, how="outer")
        left = df.join(s, how="left")
        right = df.join(s, how="right")
        tm.assert_frame_equal(inner, outer)
        tm.assert_frame_equal(inner, left)
        tm.assert_frame_equal(inner, right)

    @pytest.mark.parametrize(
        "infer_string", [False, pytest.param(True, marks=td.skip_if_no("pyarrow"))]
    )
    def test_join_sort(self, infer_string):
        with option_context("future.infer_string", infer_string):
            left = DataFrame(
                {"key": ["foo", "bar", "baz", "foo"], "value": [1, 2, 3, 4]}
            )
            right = DataFrame({"value2": ["a", "b", "c"]}, index=["bar", "baz", "foo"])

            joined = left.join(right, on="key", sort=True)
            expected = DataFrame(
                {
                    "key": ["bar", "baz", "foo", "foo"],
                    "value": [2, 3, 1, 4],
                    "value2": ["a", "b", "c", "c"],
                },
                index=[1, 2, 0, 3],
            )
            tm.assert_frame_equal(joined, expected)

            # smoke test
            joined = left.join(right, on="key", sort=False)
            tm.assert_index_equal(joined.index, Index(range(4)), exact=True)

    def test_join_mixed_non_unique_index(self):
        # GH 12814, unorderable types in py3 with a non-unique index
        df1 = DataFrame({"a": [1, 2, 3, 4]}, index=[1, 2, 3, "a"])
        df2 = DataFrame({"b": [5, 6, 7, 8]}, index=[1, 3, 3, 4])
        result = df1.join(df2)
        expected = DataFrame(
            {"a": [1, 2, 3, 3, 4], "b": [5, np.nan, 6, 7, np.nan]},
            index=[1, 2, 3, 3, "a"],
        )
        tm.assert_frame_equal(result, expected)

        df3 = DataFrame({"a": [1, 2, 3, 4]}, index=[1, 2, 2, "a"])
        df4 = DataFrame({"b": [5, 6, 7, 8]}, index=[1, 2, 3, 4])
        result = df3.join(df4)
        expected = DataFrame(
            {"a": [1, 2, 3, 4], "b": [5, 6, 6, np.nan]}, index=[1, 2, 2, "a"]
        )
        tm.assert_frame_equal(result, expected)

    def test_join_non_unique_period_index(self):
        # GH #16871
        index = pd.period_range("2016-01-01", periods=16, freq="M")
        df = DataFrame(list(range(len(index))), index=index, columns=["pnum"])
        df2 = concat([df, df])
        result = df.join(df2, how="inner", rsuffix="_df2")
        expected = DataFrame(
            np.tile(np.arange(16, dtype=np.int64).repeat(2).reshape(-1, 1), 2),
            columns=["pnum", "pnum_df2"],
            index=df2.sort_index().index,
        )
        tm.assert_frame_equal(result, expected)

    def test_mixed_type_join_with_suffix(self, using_infer_string):
        # GH #916
        df = DataFrame(
            np.random.default_rng(2).standard_normal((20, 6)),
            columns=["a", "b", "c", "d", "e", "f"],
        )
        df.insert(0, "id", 0)
        df.insert(5, "dt", "foo")

        grouped = df.groupby("id")
        msg = re.escape("agg function failed [how->mean,dtype->")
        if using_infer_string:
            msg = "dtype 'str' does not support operation 'mean'"
        with pytest.raises(TypeError, match=msg):
            grouped.mean()
        mn = grouped.mean(numeric_only=True)
        cn = grouped.count()

        # it works!
        mn.join(cn, rsuffix="_right")

    def test_join_many(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 6)), columns=list("abcdef")
        )
        df_list = [df[["a", "b"]], df[["c", "d"]], df[["e", "f"]]]

        joined = df_list[0].join(df_list[1:])
        tm.assert_frame_equal(joined, df)

        df_list = [df[["a", "b"]][:-2], df[["c", "d"]][2:], df[["e", "f"]][1:9]]

        def _check_diff_index(df_list, result, exp_index):
            reindexed = [x.reindex(exp_index) for x in df_list]
            expected = reindexed[0].join(reindexed[1:])
            tm.assert_frame_equal(result, expected)

        # different join types
        joined = df_list[0].join(df_list[1:], how="outer")
        _check_diff_index(df_list, joined, df.index)

        joined = df_list[0].join(df_list[1:])
        _check_diff_index(df_list, joined, df_list[0].index)

        joined = df_list[0].join(df_list[1:], how="inner")
        _check_diff_index(df_list, joined, df.index[2:8])

        msg = "Joining multiple DataFrames only supported for joining on index"
        with pytest.raises(ValueError, match=msg):
            df_list[0].join(df_list[1:], on="a")

    def test_join_many_mixed(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((8, 4)),
            columns=["A", "B", "C", "D"],
        )
        df["key"] = ["foo", "bar"] * 4
        df1 = df.loc[:, ["A", "B"]]
        df2 = df.loc[:, ["C", "D"]]
        df3 = df.loc[:, ["key"]]

        result = df1.join([df2, df3])
        tm.assert_frame_equal(result, df)

    def test_join_dups(self):
        # joining dups
        df = concat(
            [
                DataFrame(
                    np.random.default_rng(2).standard_normal((10, 4)),
                    columns=["A", "A", "B", "B"],
                ),
                DataFrame(
                    np.random.default_rng(2).integers(0, 10, size=20).reshape(10, 2),
                    columns=["A", "C"],
                ),
            ],
            axis=1,
        )

        expected = concat([df, df], axis=1)
        result = df.join(df, rsuffix="_2")
        result.columns = expected.columns
        tm.assert_frame_equal(result, expected)

        # GH 4975, invalid join on dups
        w = DataFrame(
            np.random.default_rng(2).standard_normal((4, 2)), columns=["x", "y"]
        )
        x = DataFrame(
            np.random.default_rng(2).standard_normal((4, 2)), columns=["x", "y"]
        )
        y = DataFrame(
            np.random.default_rng(2).standard_normal((4, 2)), columns=["x", "y"]
        )
        z = DataFrame(
            np.random.default_rng(2).standard_normal((4, 2)), columns=["x", "y"]
        )

        dta = x.merge(y, left_index=True, right_index=True).merge(
            z, left_index=True, right_index=True, how="outer"
        )
        # GH 40991: As of 2.0 causes duplicate columns
        with pytest.raises(
            pd.errors.MergeError,
            match="Passing 'suffixes' which cause duplicate columns",
        ):
            dta.merge(w, left_index=True, right_index=True)

    def test_join_multi_to_multi(self, join_type):
        # GH 20475
        leftindex = MultiIndex.from_product(
            [list("abc"), list("xy"), [1, 2]], names=["abc", "xy", "num"]
        )
        left = DataFrame({"v1": range(12)}, index=leftindex)

        rightindex = MultiIndex.from_product(
            [list("abc"), list("xy")], names=["abc", "xy"]
        )
        right = DataFrame({"v2": [100 * i for i in range(1, 7)]}, index=rightindex)

        result = left.join(right, on=["abc", "xy"], how=join_type)
        expected = (
            left.reset_index()
            .merge(right.reset_index(), on=["abc", "xy"], how=join_type)
            .set_index(["abc", "xy", "num"])
        )
        tm.assert_frame_equal(expected, result)

        msg = r'len\(left_on\) must equal the number of levels in the index of "right"'
        with pytest.raises(ValueError, match=msg):
            left.join(right, on="xy", how=join_type)

        with pytest.raises(ValueError, match=msg):
            right.join(left, on=["abc", "xy"], how=join_type)

    def test_join_on_tz_aware_datetimeindex(self):
        # GH 23931, 26335
        df1 = DataFrame(
            {
                "date": pd.date_range(
                    start="2018-01-01", periods=5, tz="America/Chicago"
                ),
                "vals": list("abcde"),
            }
        )

        df2 = DataFrame(
            {
                "date": pd.date_range(
                    start="2018-01-03", periods=5, tz="America/Chicago"
                ),
                "vals_2": list("tuvwx"),
            }
        )
        result = df1.join(df2.set_index("date"), on="date")
        expected = df1.copy()
        expected["vals_2"] = Series([np.nan] * 2 + list("tuv"))
        tm.assert_frame_equal(result, expected)

    def test_join_datetime_string(self):
        # GH 5647
        dfa = DataFrame(
            [
                ["2012-08-02", "L", 10],
                ["2012-08-02", "J", 15],
                ["2013-04-06", "L", 20],
                ["2013-04-06", "J", 25],
            ],
            columns=["x", "y", "a"],
        )
        dfa["x"] = pd.to_datetime(dfa["x"]).astype("M8[ns]")
        dfb = DataFrame(
            [["2012-08-02", "J", 1], ["2013-04-06", "L", 2]],
            columns=["x", "y", "z"],
            index=[2, 4],
        )
        dfb["x"] = pd.to_datetime(dfb["x"]).astype("M8[ns]")
        result = dfb.join(dfa.set_index(["x", "y"]), on=["x", "y"])
        expected = DataFrame(
            [
                [Timestamp("2012-08-02 00:00:00"), "J", 1, 15],
                [Timestamp("2013-04-06 00:00:00"), "L", 2, 20],
            ],
            index=[2, 4],
            columns=["x", "y", "z", "a"],
        )
        expected["x"] = expected["x"].astype("M8[ns]")
        tm.assert_frame_equal(result, expected)

    def test_join_with_categorical_index(self):
        # GH47812
        ix = ["a", "b"]
        id1 = pd.CategoricalIndex(ix, categories=ix)
        id2 = pd.CategoricalIndex(reversed(ix), categories=reversed(ix))

        df1 = DataFrame({"c1": ix}, index=id1)
        df2 = DataFrame({"c2": reversed(ix)}, index=id2)
        result = df1.join(df2)
        expected = DataFrame(
            {"c1": ["a", "b"], "c2": ["a", "b"]},
            index=pd.CategoricalIndex(["a", "b"], categories=["a", "b"]),
        )
        tm.assert_frame_equal(result, expected)


def _check_join(left, right, result, join_col, how="left", lsuffix="_x", rsuffix="_y"):
    # some smoke tests
    for c in join_col:
        assert result[c].notna().all()

    left_grouped = left.groupby(join_col)
    right_grouped = right.groupby(join_col)

    for group_key, group in result.groupby(join_col):
        l_joined = _restrict_to_columns(group, left.columns, lsuffix)
        r_joined = _restrict_to_columns(group, right.columns, rsuffix)

        try:
            lgroup = left_grouped.get_group(group_key)
        except KeyError as err:
            if how in ("left", "inner"):
                raise AssertionError(
                    f"key {group_key} should not have been in the join"
                ) from err

            _assert_all_na(l_joined, left.columns, join_col)
        else:
            _assert_same_contents(l_joined, lgroup)

        try:
            rgroup = right_grouped.get_group(group_key)
        except KeyError as err:
            if how in ("right", "inner"):
                raise AssertionError(
                    f"key {group_key} should not have been in the join"
                ) from err

            _assert_all_na(r_joined, right.columns, join_col)
        else:
            _assert_same_contents(r_joined, rgroup)


def _restrict_to_columns(group, columns, suffix):
    found = [
        c for c in group.columns if c in columns or c.replace(suffix, "") in columns
    ]

    # filter
    group = group.loc[:, found]

    # get rid of suffixes, if any
    group = group.rename(columns=lambda x: x.replace(suffix, ""))

    # put in the right order...
    group = group.loc[:, columns]

    return group


def _assert_same_contents(join_chunk, source):
    NA_SENTINEL = -1234567  # drop_duplicates not so NA-friendly...

    jvalues = join_chunk.fillna(NA_SENTINEL).drop_duplicates().values
    svalues = source.fillna(NA_SENTINEL).drop_duplicates().values

    rows = {tuple(row) for row in jvalues}
    assert len(rows) == len(source)
    assert all(tuple(row) in rows for row in svalues)


def _assert_all_na(join_chunk, source_columns, join_col):
    for c in source_columns:
        if c in join_col:
            continue
        assert join_chunk[c].isna().all()


def _join_by_hand(a, b, how="left"):
    join_index = a.index.join(b.index, how=how)

    a_re = a.reindex(join_index)
    b_re = b.reindex(join_index)

    result_columns = a.columns.append(b.columns)

    for col, s in b_re.items():
        a_re[col] = s
    return a_re.reindex(columns=result_columns)


def test_join_inner_multiindex_deterministic_order():
    # GH: 36910
    left = DataFrame(
        data={"e": 5},
        index=MultiIndex.from_tuples([(1, 2, 4)], names=("a", "b", "d")),
    )
    right = DataFrame(
        data={"f": 6}, index=MultiIndex.from_tuples([(2, 3)], names=("b", "c"))
    )
    result = left.join(right, how="inner")
    expected = DataFrame(
        {"e": [5], "f": [6]},
        index=MultiIndex.from_tuples([(1, 2, 4, 3)], names=("a", "b", "d", "c")),
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    ("input_col", "output_cols"), [("b", ["a", "b"]), ("a", ["a_x", "a_y"])]
)
def test_join_cross(input_col, output_cols):
    # GH#5401
    left = DataFrame({"a": [1, 3]})
    right = DataFrame({input_col: [3, 4]})
    result = left.join(right, how="cross", lsuffix="_x", rsuffix="_y")
    expected = DataFrame({output_cols[0]: [1, 1, 3, 3], output_cols[1]: [3, 4, 3, 4]})
    tm.assert_frame_equal(result, expected)


def test_join_multiindex_one_level(join_type):
    # GH#36909
    left = DataFrame(
        data={"c": 3}, index=MultiIndex.from_tuples([(1, 2)], names=("a", "b"))
    )
    right = DataFrame(data={"d": 4}, index=MultiIndex.from_tuples([(2,)], names=("b",)))
    result = left.join(right, how=join_type)
    if join_type == "right":
        expected = DataFrame(
            {"c": [3], "d": [4]},
            index=MultiIndex.from_tuples([(2, 1)], names=["b", "a"]),
        )
    else:
        expected = DataFrame(
            {"c": [3], "d": [4]},
            index=MultiIndex.from_tuples([(1, 2)], names=["a", "b"]),
        )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "categories, values",
    [
        (["Y", "X"], ["Y", "X", "X"]),
        ([2, 1], [2, 1, 1]),
        ([2.5, 1.5], [2.5, 1.5, 1.5]),
        (
            [Timestamp("2020-12-31"), Timestamp("2019-12-31")],
            [Timestamp("2020-12-31"), Timestamp("2019-12-31"), Timestamp("2019-12-31")],
        ),
    ],
)
def test_join_multiindex_not_alphabetical_categorical(categories, values):
    # GH#38502
    left = DataFrame(
        {
            "first": ["A", "A"],
            "second": Categorical(categories, categories=categories),
            "value": [1, 2],
        }
    ).set_index(["first", "second"])
    right = DataFrame(
        {
            "first": ["A", "A", "B"],
            "second": Categorical(values, categories=categories),
            "value": [3, 4, 5],
        }
    ).set_index(["first", "second"])
    result = left.join(right, lsuffix="_left", rsuffix="_right")

    expected = DataFrame(
        {
            "first": ["A", "A"],
            "second": Categorical(categories, categories=categories),
            "value_left": [1, 2],
            "value_right": [3, 4],
        }
    ).set_index(["first", "second"])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "left_empty, how, exp",
    [
        (False, "left", "left"),
        (False, "right", "empty"),
        (False, "inner", "empty"),
        (False, "outer", "left"),
        (False, "cross", "empty"),
        (True, "left", "empty"),
        (True, "right", "right"),
        (True, "inner", "empty"),
        (True, "outer", "right"),
        (True, "cross", "empty"),
    ],
)
def test_join_empty(left_empty, how, exp):
    left = DataFrame({"A": [2, 1], "B": [3, 4]}, dtype="int64").set_index("A")
    right = DataFrame({"A": [1], "C": [5]}, dtype="int64").set_index("A")

    if left_empty:
        left = left.head(0)
    else:
        right = right.head(0)

    result = left.join(right, how=how)

    if exp == "left":
        expected = DataFrame({"A": [2, 1], "B": [3, 4], "C": [np.nan, np.nan]})
        expected = expected.set_index("A")
    elif exp == "right":
        expected = DataFrame({"B": [np.nan], "A": [1], "C": [5]})
        expected = expected.set_index("A")
    elif exp == "empty":
        expected = DataFrame(columns=["B", "C"], dtype="int64")
        if how != "cross":
            expected = expected.rename_axis("A")
    if how == "outer":
        expected = expected.sort_index()

    tm.assert_frame_equal(result, expected)


def test_join_empty_uncomparable_columns():
    # GH 57048
    df1 = DataFrame()
    df2 = DataFrame(columns=["test"])
    df3 = DataFrame(columns=["foo", ("bar", "baz")])

    result = df1 + df2
    expected = DataFrame(columns=["test"])
    tm.assert_frame_equal(result, expected)

    result = df2 + df3
    expected = DataFrame(columns=[("bar", "baz"), "foo", "test"])
    tm.assert_frame_equal(result, expected)

    result = df1 + df3
    expected = DataFrame(columns=[("bar", "baz"), "foo"])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "how, values",
    [
        ("inner", [0, 1, 2]),
        ("outer", [0, 1, 2]),
        ("left", [0, 1, 2]),
        ("right", [0, 2, 1]),
    ],
)
def test_join_multiindex_categorical_output_index_dtype(how, values):
    # GH#50906
    df1 = DataFrame(
        {
            "a": Categorical([0, 1, 2]),
            "b": Categorical([0, 1, 2]),
            "c": [0, 1, 2],
        }
    ).set_index(["a", "b"])

    df2 = DataFrame(
        {
            "a": Categorical([0, 2, 1]),
            "b": Categorical([0, 2, 1]),
            "d": [0, 2, 1],
        }
    ).set_index(["a", "b"])

    expected = DataFrame(
        {
            "a": Categorical(values),
            "b": Categorical(values),
            "c": values,
            "d": values,
        }
    ).set_index(["a", "b"])

    result = df1.join(df2, how=how)
    tm.assert_frame_equal(result, expected)
