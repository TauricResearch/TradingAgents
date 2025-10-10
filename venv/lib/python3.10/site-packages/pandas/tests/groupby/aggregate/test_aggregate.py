"""
test .agg behavior / note that .apply is tested generally in test_groupby.py
"""
import datetime
import functools
from functools import partial
import re

import numpy as np
import pytest

from pandas.errors import SpecificationError

from pandas.core.dtypes.common import is_integer_dtype

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Series,
    concat,
    to_datetime,
)
import pandas._testing as tm
from pandas.core.groupby.grouper import Grouping


def test_groupby_agg_no_extra_calls():
    # GH#31760
    df = DataFrame({"key": ["a", "b", "c", "c"], "value": [1, 2, 3, 4]})
    gb = df.groupby("key")["value"]

    def dummy_func(x):
        assert len(x) != 0
        return x.sum()

    gb.agg(dummy_func)


def test_agg_regression1(tsframe):
    grouped = tsframe.groupby([lambda x: x.year, lambda x: x.month])
    result = grouped.agg("mean")
    expected = grouped.mean()
    tm.assert_frame_equal(result, expected)


def test_agg_must_agg(df):
    grouped = df.groupby("A")["C"]

    msg = "Must produce aggregated value"
    with pytest.raises(Exception, match=msg):
        grouped.agg(lambda x: x.describe())
    with pytest.raises(Exception, match=msg):
        grouped.agg(lambda x: x.index[:2])


def test_agg_ser_multi_key(df):
    f = lambda x: x.sum()
    results = df.C.groupby([df.A, df.B]).aggregate(f)
    expected = df.groupby(["A", "B"]).sum()["C"]
    tm.assert_series_equal(results, expected)


def test_groupby_aggregation_mixed_dtype():
    # GH 6212
    expected = DataFrame(
        {
            "v1": [5, 5, 7, np.nan, 3, 3, 4, 1],
            "v2": [55, 55, 77, np.nan, 33, 33, 44, 11],
        },
        index=MultiIndex.from_tuples(
            [
                (1, 95),
                (1, 99),
                (2, 95),
                (2, 99),
                ("big", "damp"),
                ("blue", "dry"),
                ("red", "red"),
                ("red", "wet"),
            ],
            names=["by1", "by2"],
        ),
    )

    df = DataFrame(
        {
            "v1": [1, 3, 5, 7, 8, 3, 5, np.nan, 4, 5, 7, 9],
            "v2": [11, 33, 55, 77, 88, 33, 55, np.nan, 44, 55, 77, 99],
            "by1": ["red", "blue", 1, 2, np.nan, "big", 1, 2, "red", 1, np.nan, 12],
            "by2": [
                "wet",
                "dry",
                99,
                95,
                np.nan,
                "damp",
                95,
                99,
                "red",
                99,
                np.nan,
                np.nan,
            ],
        }
    )

    g = df.groupby(["by1", "by2"])
    result = g[["v1", "v2"]].mean()
    tm.assert_frame_equal(result, expected)


def test_groupby_aggregation_multi_level_column():
    # GH 29772
    lst = [
        [True, True, True, False],
        [True, False, np.nan, False],
        [True, True, np.nan, False],
        [True, True, np.nan, False],
    ]
    df = DataFrame(
        data=lst,
        columns=MultiIndex.from_tuples([("A", 0), ("A", 1), ("B", 0), ("B", 1)]),
    )

    msg = "DataFrame.groupby with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        gb = df.groupby(level=1, axis=1)
    result = gb.sum(numeric_only=False)
    expected = DataFrame({0: [2.0, True, True, True], 1: [1, 0, 1, 1]})

    tm.assert_frame_equal(result, expected)


def test_agg_apply_corner(ts, tsframe):
    # nothing to group, all NA
    grouped = ts.groupby(ts * np.nan, group_keys=False)
    assert ts.dtype == np.float64

    # groupby float64 values results in a float64 Index
    exp = Series([], dtype=np.float64, index=Index([], dtype=np.float64))
    tm.assert_series_equal(grouped.sum(), exp)
    tm.assert_series_equal(grouped.agg("sum"), exp)
    tm.assert_series_equal(grouped.apply("sum"), exp, check_index_type=False)

    # DataFrame
    grouped = tsframe.groupby(tsframe["A"] * np.nan, group_keys=False)
    exp_df = DataFrame(
        columns=tsframe.columns,
        dtype=float,
        index=Index([], name="A", dtype=np.float64),
    )
    tm.assert_frame_equal(grouped.sum(), exp_df)
    tm.assert_frame_equal(grouped.agg("sum"), exp_df)

    msg = "The behavior of DataFrame.sum with axis=None is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg, check_stacklevel=False):
        res = grouped.apply(np.sum)
    tm.assert_frame_equal(res, exp_df)


def test_agg_grouping_is_list_tuple(ts):
    df = DataFrame(
        np.random.default_rng(2).standard_normal((30, 4)),
        columns=Index(list("ABCD"), dtype=object),
        index=pd.date_range("2000-01-01", periods=30, freq="B"),
    )

    grouped = df.groupby(lambda x: x.year)
    grouper = grouped._grouper.groupings[0].grouping_vector
    grouped._grouper.groupings[0] = Grouping(ts.index, list(grouper))

    result = grouped.agg("mean")
    expected = grouped.mean()
    tm.assert_frame_equal(result, expected)

    grouped._grouper.groupings[0] = Grouping(ts.index, tuple(grouper))

    result = grouped.agg("mean")
    expected = grouped.mean()
    tm.assert_frame_equal(result, expected)


def test_agg_python_multiindex(multiindex_dataframe_random_data):
    grouped = multiindex_dataframe_random_data.groupby(["A", "B"])

    result = grouped.agg("mean")
    expected = grouped.mean()
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "groupbyfunc", [lambda x: x.weekday(), [lambda x: x.month, lambda x: x.weekday()]]
)
def test_aggregate_str_func(tsframe, groupbyfunc):
    grouped = tsframe.groupby(groupbyfunc)

    # single series
    result = grouped["A"].agg("std")
    expected = grouped["A"].std()
    tm.assert_series_equal(result, expected)

    # group frame by function name
    result = grouped.aggregate("var")
    expected = grouped.var()
    tm.assert_frame_equal(result, expected)

    # group frame by function dict
    result = grouped.agg({"A": "var", "B": "std", "C": "mean", "D": "sem"})
    expected = DataFrame(
        {
            "A": grouped["A"].var(),
            "B": grouped["B"].std(),
            "C": grouped["C"].mean(),
            "D": grouped["D"].sem(),
        }
    )
    tm.assert_frame_equal(result, expected)


def test_std_masked_dtype(any_numeric_ea_dtype):
    # GH#35516
    df = DataFrame(
        {
            "a": [2, 1, 1, 1, 2, 2, 1],
            "b": Series([pd.NA, 1, 2, 1, 1, 1, 2], dtype="Float64"),
        }
    )
    result = df.groupby("a").std()
    expected = DataFrame(
        {"b": [0.57735, 0]}, index=Index([1, 2], name="a"), dtype="Float64"
    )
    tm.assert_frame_equal(result, expected)


def test_agg_str_with_kwarg_axis_1_raises(df, reduction_func):
    gb = df.groupby(level=0)
    warn_msg = f"DataFrameGroupBy.{reduction_func} with axis=1 is deprecated"
    if reduction_func in ("idxmax", "idxmin"):
        error = TypeError
        msg = "'[<>]' not supported between instances of 'float' and 'str'"
        warn = FutureWarning
    else:
        error = ValueError
        msg = f"Operation {reduction_func} does not support axis=1"
        warn = None
    with pytest.raises(error, match=msg):
        with tm.assert_produces_warning(warn, match=warn_msg):
            gb.agg(reduction_func, axis=1)


@pytest.mark.parametrize(
    "func, expected, dtype, result_dtype_dict",
    [
        ("sum", [5, 7, 9], "int64", {}),
        ("std", [4.5**0.5] * 3, int, {"i": float, "j": float, "k": float}),
        ("var", [4.5] * 3, int, {"i": float, "j": float, "k": float}),
        ("sum", [5, 7, 9], "Int64", {"j": "int64"}),
        ("std", [4.5**0.5] * 3, "Int64", {"i": float, "j": float, "k": float}),
        ("var", [4.5] * 3, "Int64", {"i": "float64", "j": "float64", "k": "float64"}),
    ],
)
def test_multiindex_groupby_mixed_cols_axis1(func, expected, dtype, result_dtype_dict):
    # GH#43209
    df = DataFrame(
        [[1, 2, 3, 4, 5, 6]] * 3,
        columns=MultiIndex.from_product([["a", "b"], ["i", "j", "k"]]),
    ).astype({("a", "j"): dtype, ("b", "j"): dtype})

    msg = "DataFrame.groupby with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        gb = df.groupby(level=1, axis=1)
    result = gb.agg(func)
    expected = DataFrame([expected] * 3, columns=["i", "j", "k"]).astype(
        result_dtype_dict
    )

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "func, expected_data, result_dtype_dict",
    [
        ("sum", [[2, 4], [10, 12], [18, 20]], {10: "int64", 20: "int64"}),
        # std should ideally return Int64 / Float64 #43330
        ("std", [[2**0.5] * 2] * 3, "float64"),
        ("var", [[2] * 2] * 3, {10: "float64", 20: "float64"}),
    ],
)
def test_groupby_mixed_cols_axis1(func, expected_data, result_dtype_dict):
    # GH#43209
    df = DataFrame(
        np.arange(12).reshape(3, 4),
        index=Index([0, 1, 0], name="y"),
        columns=Index([10, 20, 10, 20], name="x"),
        dtype="int64",
    ).astype({10: "Int64"})

    msg = "DataFrame.groupby with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        gb = df.groupby("x", axis=1)
    result = gb.agg(func)
    expected = DataFrame(
        data=expected_data,
        index=Index([0, 1, 0], name="y"),
        columns=Index([10, 20], name="x"),
    ).astype(result_dtype_dict)
    tm.assert_frame_equal(result, expected)


def test_aggregate_item_by_item(df):
    grouped = df.groupby("A")

    aggfun_0 = lambda ser: ser.size
    result = grouped.agg(aggfun_0)
    foosum = (df.A == "foo").sum()
    barsum = (df.A == "bar").sum()
    K = len(result.columns)

    # GH5782
    exp = Series(np.array([foosum] * K), index=list("BCD"), name="foo")
    tm.assert_series_equal(result.xs("foo"), exp)

    exp = Series(np.array([barsum] * K), index=list("BCD"), name="bar")
    tm.assert_almost_equal(result.xs("bar"), exp)

    def aggfun_1(ser):
        return ser.size

    result = DataFrame().groupby(df.A).agg(aggfun_1)
    assert isinstance(result, DataFrame)
    assert len(result) == 0


def test_wrap_agg_out(three_group):
    grouped = three_group.groupby(["A", "B"])

    def func(ser):
        if ser.dtype in (object, "string"):
            raise TypeError("Test error message")
        return ser.sum()

    with pytest.raises(TypeError, match="Test error message"):
        grouped.aggregate(func)
    result = grouped[["D", "E", "F"]].aggregate(func)
    exp_grouped = three_group.loc[:, ["A", "B", "D", "E", "F"]]
    expected = exp_grouped.groupby(["A", "B"]).aggregate(func)
    tm.assert_frame_equal(result, expected)


def test_agg_multiple_functions_maintain_order(df):
    # GH #610
    funcs = [("mean", np.mean), ("max", np.max), ("min", np.min)]
    msg = "is currently using SeriesGroupBy.mean"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = df.groupby("A")["C"].agg(funcs)
    exp_cols = Index(["mean", "max", "min"])

    tm.assert_index_equal(result.columns, exp_cols)


def test_series_index_name(df):
    grouped = df.loc[:, ["C"]].groupby(df["A"])
    result = grouped.agg(lambda x: x.mean())
    assert result.index.name == "A"


def test_agg_multiple_functions_same_name():
    # GH 30880
    df = DataFrame(
        np.random.default_rng(2).standard_normal((1000, 3)),
        index=pd.date_range("1/1/2012", freq="s", periods=1000),
        columns=["A", "B", "C"],
    )
    result = df.resample("3min").agg(
        {"A": [partial(np.quantile, q=0.9999), partial(np.quantile, q=0.1111)]}
    )
    expected_index = pd.date_range("1/1/2012", freq="3min", periods=6)
    expected_columns = MultiIndex.from_tuples([("A", "quantile"), ("A", "quantile")])
    expected_values = np.array(
        [df.resample("3min").A.quantile(q=q).values for q in [0.9999, 0.1111]]
    ).T
    expected = DataFrame(
        expected_values, columns=expected_columns, index=expected_index
    )
    tm.assert_frame_equal(result, expected)


def test_agg_multiple_functions_same_name_with_ohlc_present():
    # GH 30880
    # ohlc expands dimensions, so different test to the above is required.
    df = DataFrame(
        np.random.default_rng(2).standard_normal((1000, 3)),
        index=pd.date_range("1/1/2012", freq="s", periods=1000, name="dti"),
        columns=Index(["A", "B", "C"], name="alpha"),
    )
    result = df.resample("3min").agg(
        {"A": ["ohlc", partial(np.quantile, q=0.9999), partial(np.quantile, q=0.1111)]}
    )
    expected_index = pd.date_range("1/1/2012", freq="3min", periods=6, name="dti")
    expected_columns = MultiIndex.from_tuples(
        [
            ("A", "ohlc", "open"),
            ("A", "ohlc", "high"),
            ("A", "ohlc", "low"),
            ("A", "ohlc", "close"),
            ("A", "quantile", "A"),
            ("A", "quantile", "A"),
        ],
        names=["alpha", None, None],
    )
    non_ohlc_expected_values = np.array(
        [df.resample("3min").A.quantile(q=q).values for q in [0.9999, 0.1111]]
    ).T
    expected_values = np.hstack(
        [df.resample("3min").A.ohlc(), non_ohlc_expected_values]
    )
    expected = DataFrame(
        expected_values, columns=expected_columns, index=expected_index
    )
    tm.assert_frame_equal(result, expected)


def test_multiple_functions_tuples_and_non_tuples(df):
    # #1359
    # Columns B and C would cause partial failure
    df = df.drop(columns=["B", "C"])

    funcs = [("foo", "mean"), "std"]
    ex_funcs = [("foo", "mean"), ("std", "std")]

    result = df.groupby("A")["D"].agg(funcs)
    expected = df.groupby("A")["D"].agg(ex_funcs)
    tm.assert_frame_equal(result, expected)

    result = df.groupby("A").agg(funcs)
    expected = df.groupby("A").agg(ex_funcs)
    tm.assert_frame_equal(result, expected)


def test_more_flexible_frame_multi_function(df):
    grouped = df.groupby("A")

    exmean = grouped.agg({"C": "mean", "D": "mean"})
    exstd = grouped.agg({"C": "std", "D": "std"})

    expected = concat([exmean, exstd], keys=["mean", "std"], axis=1)
    expected = expected.swaplevel(0, 1, axis=1).sort_index(level=0, axis=1)

    d = {"C": ["mean", "std"], "D": ["mean", "std"]}
    result = grouped.aggregate(d)

    tm.assert_frame_equal(result, expected)

    # be careful
    result = grouped.aggregate({"C": "mean", "D": ["mean", "std"]})
    expected = grouped.aggregate({"C": "mean", "D": ["mean", "std"]})
    tm.assert_frame_equal(result, expected)

    def numpymean(x):
        return np.mean(x)

    def numpystd(x):
        return np.std(x, ddof=1)

    # this uses column selection & renaming
    msg = r"nested renamer is not supported"
    with pytest.raises(SpecificationError, match=msg):
        d = {"C": "mean", "D": {"foo": "mean", "bar": "std"}}
        grouped.aggregate(d)

    # But without renaming, these functions are OK
    d = {"C": ["mean"], "D": [numpymean, numpystd]}
    grouped.aggregate(d)


def test_multi_function_flexible_mix(df):
    # GH #1268
    grouped = df.groupby("A")

    # Expected
    d = {"C": {"foo": "mean", "bar": "std"}, "D": {"sum": "sum"}}
    # this uses column selection & renaming
    msg = r"nested renamer is not supported"
    with pytest.raises(SpecificationError, match=msg):
        grouped.aggregate(d)

    # Test 1
    d = {"C": {"foo": "mean", "bar": "std"}, "D": "sum"}
    # this uses column selection & renaming
    with pytest.raises(SpecificationError, match=msg):
        grouped.aggregate(d)

    # Test 2
    d = {"C": {"foo": "mean", "bar": "std"}, "D": "sum"}
    # this uses column selection & renaming
    with pytest.raises(SpecificationError, match=msg):
        grouped.aggregate(d)


def test_groupby_agg_coercing_bools():
    # issue 14873
    dat = DataFrame({"a": [1, 1, 2, 2], "b": [0, 1, 2, 3], "c": [None, None, 1, 1]})
    gp = dat.groupby("a")

    index = Index([1, 2], name="a")

    result = gp["b"].aggregate(lambda x: (x != 0).all())
    expected = Series([False, True], index=index, name="b")
    tm.assert_series_equal(result, expected)

    result = gp["c"].aggregate(lambda x: x.isnull().all())
    expected = Series([True, False], index=index, name="c")
    tm.assert_series_equal(result, expected)


def test_groupby_agg_dict_with_getitem():
    # issue 25471
    dat = DataFrame({"A": ["A", "A", "B", "B", "B"], "B": [1, 2, 1, 1, 2]})
    result = dat.groupby("A")[["B"]].agg({"B": "sum"})

    expected = DataFrame({"B": [3, 4]}, index=["A", "B"]).rename_axis("A", axis=0)

    tm.assert_frame_equal(result, expected)


def test_groupby_agg_dict_dup_columns():
    # GH#55006
    df = DataFrame(
        [[1, 2, 3, 4], [1, 3, 4, 5], [2, 4, 5, 6]],
        columns=["a", "b", "c", "c"],
    )
    gb = df.groupby("a")
    result = gb.agg({"b": "sum"})
    expected = DataFrame({"b": [5, 4]}, index=Index([1, 2], name="a"))
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "op",
    [
        lambda x: x.sum(),
        lambda x: x.cumsum(),
        lambda x: x.transform("sum"),
        lambda x: x.transform("cumsum"),
        lambda x: x.agg("sum"),
        lambda x: x.agg("cumsum"),
    ],
)
def test_bool_agg_dtype(op):
    # GH 7001
    # Bool sum aggregations result in int
    df = DataFrame({"a": [1, 1], "b": [False, True]})
    s = df.set_index("a")["b"]

    result = op(df.groupby("a"))["b"].dtype
    assert is_integer_dtype(result)

    result = op(s.groupby("a")).dtype
    assert is_integer_dtype(result)


@pytest.mark.parametrize(
    "keys, agg_index",
    [
        (["a"], Index([1], name="a")),
        (["a", "b"], MultiIndex([[1], [2]], [[0], [0]], names=["a", "b"])),
    ],
)
@pytest.mark.parametrize(
    "input_dtype", ["bool", "int32", "int64", "float32", "float64"]
)
@pytest.mark.parametrize(
    "result_dtype", ["bool", "int32", "int64", "float32", "float64"]
)
@pytest.mark.parametrize("method", ["apply", "aggregate", "transform"])
def test_callable_result_dtype_frame(
    keys, agg_index, input_dtype, result_dtype, method
):
    # GH 21240
    df = DataFrame({"a": [1], "b": [2], "c": [True]})
    df["c"] = df["c"].astype(input_dtype)
    op = getattr(df.groupby(keys)[["c"]], method)
    result = op(lambda x: x.astype(result_dtype).iloc[0])
    expected_index = pd.RangeIndex(0, 1) if method == "transform" else agg_index
    expected = DataFrame({"c": [df["c"].iloc[0]]}, index=expected_index).astype(
        result_dtype
    )
    if method == "apply":
        expected.columns.names = [0]
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "keys, agg_index",
    [
        (["a"], Index([1], name="a")),
        (["a", "b"], MultiIndex([[1], [2]], [[0], [0]], names=["a", "b"])),
    ],
)
@pytest.mark.parametrize("input", [True, 1, 1.0])
@pytest.mark.parametrize("dtype", [bool, int, float])
@pytest.mark.parametrize("method", ["apply", "aggregate", "transform"])
def test_callable_result_dtype_series(keys, agg_index, input, dtype, method):
    # GH 21240
    df = DataFrame({"a": [1], "b": [2], "c": [input]})
    op = getattr(df.groupby(keys)["c"], method)
    result = op(lambda x: x.astype(dtype).iloc[0])
    expected_index = pd.RangeIndex(0, 1) if method == "transform" else agg_index
    expected = Series([df["c"].iloc[0]], index=expected_index, name="c").astype(dtype)
    tm.assert_series_equal(result, expected)


def test_order_aggregate_multiple_funcs():
    # GH 25692
    df = DataFrame({"A": [1, 1, 2, 2], "B": [1, 2, 3, 4]})

    res = df.groupby("A").agg(["sum", "max", "mean", "ohlc", "min"])
    result = res.columns.levels[1]

    expected = Index(["sum", "max", "mean", "ohlc", "min"])

    tm.assert_index_equal(result, expected)


def test_ohlc_ea_dtypes(any_numeric_ea_dtype):
    # GH#37493
    df = DataFrame(
        {"a": [1, 1, 2, 3, 4, 4], "b": [22, 11, pd.NA, 10, 20, pd.NA]},
        dtype=any_numeric_ea_dtype,
    )
    gb = df.groupby("a")
    result = gb.ohlc()
    expected = DataFrame(
        [[22, 22, 11, 11], [pd.NA] * 4, [10] * 4, [20] * 4],
        columns=MultiIndex.from_product([["b"], ["open", "high", "low", "close"]]),
        index=Index([1, 2, 3, 4], dtype=any_numeric_ea_dtype, name="a"),
        dtype=any_numeric_ea_dtype,
    )
    tm.assert_frame_equal(result, expected)

    gb2 = df.groupby("a", as_index=False)
    result2 = gb2.ohlc()
    expected2 = expected.reset_index()
    tm.assert_frame_equal(result2, expected2)


@pytest.mark.parametrize("dtype", [np.int64, np.uint64])
@pytest.mark.parametrize("how", ["first", "last", "min", "max", "mean", "median"])
def test_uint64_type_handling(dtype, how):
    # GH 26310
    df = DataFrame({"x": 6903052872240755750, "y": [1, 2]})
    expected = df.groupby("y").agg({"x": how})
    df.x = df.x.astype(dtype)
    result = df.groupby("y").agg({"x": how})
    if how not in ("mean", "median"):
        # mean and median always result in floats
        result.x = result.x.astype(np.int64)
    tm.assert_frame_equal(result, expected, check_exact=True)


def test_func_duplicates_raises():
    # GH28426
    msg = "Function names"
    df = DataFrame({"A": [0, 0, 1, 1], "B": [1, 2, 3, 4]})
    with pytest.raises(SpecificationError, match=msg):
        df.groupby("A").agg(["min", "min"])


@pytest.mark.parametrize(
    "index",
    [
        pd.CategoricalIndex(list("abc")),
        pd.interval_range(0, 3),
        pd.period_range("2020", periods=3, freq="D"),
        MultiIndex.from_tuples([("a", 0), ("a", 1), ("b", 0)]),
    ],
)
def test_agg_index_has_complex_internals(index):
    # GH 31223
    df = DataFrame({"group": [1, 1, 2], "value": [0, 1, 0]}, index=index)
    result = df.groupby("group").agg({"value": Series.nunique})
    expected = DataFrame({"group": [1, 2], "value": [2, 1]}).set_index("group")
    tm.assert_frame_equal(result, expected)


def test_agg_split_block():
    # https://github.com/pandas-dev/pandas/issues/31522
    df = DataFrame(
        {
            "key1": ["a", "a", "b", "b", "a"],
            "key2": ["one", "two", "one", "two", "one"],
            "key3": ["three", "three", "three", "six", "six"],
        }
    )
    result = df.groupby("key1").min()
    expected = DataFrame(
        {"key2": ["one", "one"], "key3": ["six", "six"]},
        index=Index(["a", "b"], name="key1"),
    )
    tm.assert_frame_equal(result, expected)


def test_agg_split_object_part_datetime():
    # https://github.com/pandas-dev/pandas/pull/31616
    df = DataFrame(
        {
            "A": pd.date_range("2000", periods=4),
            "B": ["a", "b", "c", "d"],
            "C": [1, 2, 3, 4],
            "D": ["b", "c", "d", "e"],
            "E": pd.date_range("2000", periods=4),
            "F": [1, 2, 3, 4],
        }
    ).astype(object)
    result = df.groupby([0, 0, 0, 0]).min()
    expected = DataFrame(
        {
            "A": [pd.Timestamp("2000")],
            "B": ["a"],
            "C": [1],
            "D": ["b"],
            "E": [pd.Timestamp("2000")],
            "F": [1],
        },
        index=np.array([0]),
        dtype=object,
    )
    tm.assert_frame_equal(result, expected)


class TestNamedAggregationSeries:
    def test_series_named_agg(self):
        df = Series([1, 2, 3, 4])
        gr = df.groupby([0, 0, 1, 1])
        result = gr.agg(a="sum", b="min")
        expected = DataFrame(
            {"a": [3, 7], "b": [1, 3]}, columns=["a", "b"], index=np.array([0, 1])
        )
        tm.assert_frame_equal(result, expected)

        result = gr.agg(b="min", a="sum")
        expected = expected[["b", "a"]]
        tm.assert_frame_equal(result, expected)

    def test_no_args_raises(self):
        gr = Series([1, 2]).groupby([0, 1])
        with pytest.raises(TypeError, match="Must provide"):
            gr.agg()

        # but we do allow this
        result = gr.agg([])
        expected = DataFrame(columns=[])
        tm.assert_frame_equal(result, expected)

    def test_series_named_agg_duplicates_no_raises(self):
        # GH28426
        gr = Series([1, 2, 3]).groupby([0, 0, 1])
        grouped = gr.agg(a="sum", b="sum")
        expected = DataFrame({"a": [3, 3], "b": [3, 3]}, index=np.array([0, 1]))
        tm.assert_frame_equal(expected, grouped)

    def test_mangled(self):
        gr = Series([1, 2, 3]).groupby([0, 0, 1])
        result = gr.agg(a=lambda x: 0, b=lambda x: 1)
        expected = DataFrame({"a": [0, 0], "b": [1, 1]}, index=np.array([0, 1]))
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "inp",
        [
            pd.NamedAgg(column="anything", aggfunc="min"),
            ("anything", "min"),
            ["anything", "min"],
        ],
    )
    def test_named_agg_nametuple(self, inp):
        # GH34422
        s = Series([1, 1, 2, 2, 3, 3, 4, 5])
        msg = f"func is expected but received {type(inp).__name__}"
        with pytest.raises(TypeError, match=msg):
            s.groupby(s.values).agg(a=inp)


class TestNamedAggregationDataFrame:
    def test_agg_relabel(self):
        df = DataFrame(
            {"group": ["a", "a", "b", "b"], "A": [0, 1, 2, 3], "B": [5, 6, 7, 8]}
        )
        result = df.groupby("group").agg(a_max=("A", "max"), b_max=("B", "max"))
        expected = DataFrame(
            {"a_max": [1, 3], "b_max": [6, 8]},
            index=Index(["a", "b"], name="group"),
            columns=["a_max", "b_max"],
        )
        tm.assert_frame_equal(result, expected)

        # order invariance
        p98 = functools.partial(np.percentile, q=98)
        result = df.groupby("group").agg(
            b_min=("B", "min"),
            a_min=("A", "min"),
            a_mean=("A", "mean"),
            a_max=("A", "max"),
            b_max=("B", "max"),
            a_98=("A", p98),
        )
        expected = DataFrame(
            {
                "b_min": [5, 7],
                "a_min": [0, 2],
                "a_mean": [0.5, 2.5],
                "a_max": [1, 3],
                "b_max": [6, 8],
                "a_98": [0.98, 2.98],
            },
            index=Index(["a", "b"], name="group"),
            columns=["b_min", "a_min", "a_mean", "a_max", "b_max", "a_98"],
        )
        tm.assert_frame_equal(result, expected)

    def test_agg_relabel_non_identifier(self):
        df = DataFrame(
            {"group": ["a", "a", "b", "b"], "A": [0, 1, 2, 3], "B": [5, 6, 7, 8]}
        )

        result = df.groupby("group").agg(**{"my col": ("A", "max")})
        expected = DataFrame({"my col": [1, 3]}, index=Index(["a", "b"], name="group"))
        tm.assert_frame_equal(result, expected)

    def test_duplicate_no_raises(self):
        # GH 28426, if use same input function on same column,
        # no error should raise
        df = DataFrame({"A": [0, 0, 1, 1], "B": [1, 2, 3, 4]})

        grouped = df.groupby("A").agg(a=("B", "min"), b=("B", "min"))
        expected = DataFrame({"a": [1, 3], "b": [1, 3]}, index=Index([0, 1], name="A"))
        tm.assert_frame_equal(grouped, expected)

        quant50 = functools.partial(np.percentile, q=50)
        quant70 = functools.partial(np.percentile, q=70)
        quant50.__name__ = "quant50"
        quant70.__name__ = "quant70"

        test = DataFrame({"col1": ["a", "a", "b", "b", "b"], "col2": [1, 2, 3, 4, 5]})

        grouped = test.groupby("col1").agg(
            quantile_50=("col2", quant50), quantile_70=("col2", quant70)
        )
        expected = DataFrame(
            {"quantile_50": [1.5, 4.0], "quantile_70": [1.7, 4.4]},
            index=Index(["a", "b"], name="col1"),
        )
        tm.assert_frame_equal(grouped, expected)

    def test_agg_relabel_with_level(self):
        df = DataFrame(
            {"A": [0, 0, 1, 1], "B": [1, 2, 3, 4]},
            index=MultiIndex.from_product([["A", "B"], ["a", "b"]]),
        )
        result = df.groupby(level=0).agg(
            aa=("A", "max"), bb=("A", "min"), cc=("B", "mean")
        )
        expected = DataFrame(
            {"aa": [0, 1], "bb": [0, 1], "cc": [1.5, 3.5]}, index=["A", "B"]
        )
        tm.assert_frame_equal(result, expected)

    def test_agg_relabel_other_raises(self):
        df = DataFrame({"A": [0, 0, 1], "B": [1, 2, 3]})
        grouped = df.groupby("A")
        match = "Must provide"
        with pytest.raises(TypeError, match=match):
            grouped.agg(foo=1)

        with pytest.raises(TypeError, match=match):
            grouped.agg()

        with pytest.raises(TypeError, match=match):
            grouped.agg(a=("B", "max"), b=(1, 2, 3))

    def test_missing_raises(self):
        df = DataFrame({"A": [0, 1], "B": [1, 2]})
        match = re.escape("Column(s) ['C'] do not exist")
        with pytest.raises(KeyError, match=match):
            df.groupby("A").agg(c=("C", "sum"))

    def test_agg_namedtuple(self):
        df = DataFrame({"A": [0, 1], "B": [1, 2]})
        result = df.groupby("A").agg(
            b=pd.NamedAgg("B", "sum"), c=pd.NamedAgg(column="B", aggfunc="count")
        )
        expected = df.groupby("A").agg(b=("B", "sum"), c=("B", "count"))
        tm.assert_frame_equal(result, expected)

    def test_mangled(self):
        df = DataFrame({"A": [0, 1], "B": [1, 2], "C": [3, 4]})
        result = df.groupby("A").agg(b=("B", lambda x: 0), c=("C", lambda x: 1))
        expected = DataFrame({"b": [0, 0], "c": [1, 1]}, index=Index([0, 1], name="A"))
        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "agg_col1, agg_col2, agg_col3, agg_result1, agg_result2, agg_result3",
    [
        (
            (("y", "A"), "max"),
            (("y", "A"), np.mean),
            (("y", "B"), "mean"),
            [1, 3],
            [0.5, 2.5],
            [5.5, 7.5],
        ),
        (
            (("y", "A"), lambda x: max(x)),
            (("y", "A"), lambda x: 1),
            (("y", "B"), np.mean),
            [1, 3],
            [1, 1],
            [5.5, 7.5],
        ),
        (
            pd.NamedAgg(("y", "A"), "max"),
            pd.NamedAgg(("y", "B"), np.mean),
            pd.NamedAgg(("y", "A"), lambda x: 1),
            [1, 3],
            [5.5, 7.5],
            [1, 1],
        ),
    ],
)
def test_agg_relabel_multiindex_column(
    agg_col1, agg_col2, agg_col3, agg_result1, agg_result2, agg_result3
):
    # GH 29422, add tests for multiindex column cases
    df = DataFrame(
        {"group": ["a", "a", "b", "b"], "A": [0, 1, 2, 3], "B": [5, 6, 7, 8]}
    )
    df.columns = MultiIndex.from_tuples([("x", "group"), ("y", "A"), ("y", "B")])
    idx = Index(["a", "b"], name=("x", "group"))

    result = df.groupby(("x", "group")).agg(a_max=(("y", "A"), "max"))
    expected = DataFrame({"a_max": [1, 3]}, index=idx)
    tm.assert_frame_equal(result, expected)

    msg = "is currently using SeriesGroupBy.mean"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = df.groupby(("x", "group")).agg(
            col_1=agg_col1, col_2=agg_col2, col_3=agg_col3
        )
    expected = DataFrame(
        {"col_1": agg_result1, "col_2": agg_result2, "col_3": agg_result3}, index=idx
    )
    tm.assert_frame_equal(result, expected)


def test_agg_relabel_multiindex_raises_not_exist():
    # GH 29422, add test for raises scenario when aggregate column does not exist
    df = DataFrame(
        {"group": ["a", "a", "b", "b"], "A": [0, 1, 2, 3], "B": [5, 6, 7, 8]}
    )
    df.columns = MultiIndex.from_tuples([("x", "group"), ("y", "A"), ("y", "B")])

    with pytest.raises(KeyError, match="do not exist"):
        df.groupby(("x", "group")).agg(a=(("Y", "a"), "max"))


def test_agg_relabel_multiindex_duplicates():
    # GH29422, add test for raises scenario when getting duplicates
    # GH28426, after this change, duplicates should also work if the relabelling is
    # different
    df = DataFrame(
        {"group": ["a", "a", "b", "b"], "A": [0, 1, 2, 3], "B": [5, 6, 7, 8]}
    )
    df.columns = MultiIndex.from_tuples([("x", "group"), ("y", "A"), ("y", "B")])

    result = df.groupby(("x", "group")).agg(
        a=(("y", "A"), "min"), b=(("y", "A"), "min")
    )
    idx = Index(["a", "b"], name=("x", "group"))
    expected = DataFrame({"a": [0, 2], "b": [0, 2]}, index=idx)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("kwargs", [{"c": ["min"]}, {"b": [], "c": ["min"]}])
def test_groupby_aggregate_empty_key(kwargs):
    # GH: 32580
    df = DataFrame({"a": [1, 1, 2], "b": [1, 2, 3], "c": [1, 2, 4]})
    result = df.groupby("a").agg(kwargs)
    expected = DataFrame(
        [1, 4],
        index=Index([1, 2], dtype="int64", name="a"),
        columns=MultiIndex.from_tuples([["c", "min"]]),
    )
    tm.assert_frame_equal(result, expected)


def test_groupby_aggregate_empty_key_empty_return():
    # GH: 32580 Check if everything works, when return is empty
    df = DataFrame({"a": [1, 1, 2], "b": [1, 2, 3], "c": [1, 2, 4]})
    result = df.groupby("a").agg({"b": []})
    expected = DataFrame(columns=MultiIndex(levels=[["b"], []], codes=[[], []]))
    tm.assert_frame_equal(result, expected)


def test_groupby_aggregate_empty_with_multiindex_frame():
    # GH 39178
    df = DataFrame(columns=["a", "b", "c"])
    result = df.groupby(["a", "b"], group_keys=False).agg(d=("c", list))
    expected = DataFrame(
        columns=["d"], index=MultiIndex([[], []], [[], []], names=["a", "b"])
    )
    tm.assert_frame_equal(result, expected)


def test_grouby_agg_loses_results_with_as_index_false_relabel():
    # GH 32240: When the aggregate function relabels column names and
    # as_index=False is specified, the results are dropped.

    df = DataFrame(
        {"key": ["x", "y", "z", "x", "y", "z"], "val": [1.0, 0.8, 2.0, 3.0, 3.6, 0.75]}
    )

    grouped = df.groupby("key", as_index=False)
    result = grouped.agg(min_val=pd.NamedAgg(column="val", aggfunc="min"))
    expected = DataFrame({"key": ["x", "y", "z"], "min_val": [1.0, 0.8, 0.75]})
    tm.assert_frame_equal(result, expected)


def test_grouby_agg_loses_results_with_as_index_false_relabel_multiindex():
    # GH 32240: When the aggregate function relabels column names and
    # as_index=False is specified, the results are dropped. Check if
    # multiindex is returned in the right order

    df = DataFrame(
        {
            "key": ["x", "y", "x", "y", "x", "x"],
            "key1": ["a", "b", "c", "b", "a", "c"],
            "val": [1.0, 0.8, 2.0, 3.0, 3.6, 0.75],
        }
    )

    grouped = df.groupby(["key", "key1"], as_index=False)
    result = grouped.agg(min_val=pd.NamedAgg(column="val", aggfunc="min"))
    expected = DataFrame(
        {"key": ["x", "x", "y"], "key1": ["a", "c", "b"], "min_val": [1.0, 0.75, 0.8]}
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "func", [lambda s: s.mean(), lambda s: np.mean(s), lambda s: np.nanmean(s)]
)
def test_multiindex_custom_func(func):
    # GH 31777
    data = [[1, 4, 2], [5, 7, 1]]
    df = DataFrame(
        data,
        columns=MultiIndex.from_arrays(
            [[1, 1, 2], [3, 4, 3]], names=["Sisko", "Janeway"]
        ),
    )
    result = df.groupby(np.array([0, 1])).agg(func)
    expected_dict = {
        (1, 3): {0: 1.0, 1: 5.0},
        (1, 4): {0: 4.0, 1: 7.0},
        (2, 3): {0: 2.0, 1: 1.0},
    }
    expected = DataFrame(expected_dict, index=np.array([0, 1]), columns=df.columns)
    tm.assert_frame_equal(result, expected)


def myfunc(s):
    return np.percentile(s, q=0.90)


@pytest.mark.parametrize("func", [lambda s: np.percentile(s, q=0.90), myfunc])
def test_lambda_named_agg(func):
    # see gh-28467
    animals = DataFrame(
        {
            "kind": ["cat", "dog", "cat", "dog"],
            "height": [9.1, 6.0, 9.5, 34.0],
            "weight": [7.9, 7.5, 9.9, 198.0],
        }
    )

    result = animals.groupby("kind").agg(
        mean_height=("height", "mean"), perc90=("height", func)
    )
    expected = DataFrame(
        [[9.3, 9.1036], [20.0, 6.252]],
        columns=["mean_height", "perc90"],
        index=Index(["cat", "dog"], name="kind"),
    )

    tm.assert_frame_equal(result, expected)


def test_aggregate_mixed_types():
    # GH 16916
    df = DataFrame(
        data=np.array([0] * 9).reshape(3, 3), columns=list("XYZ"), index=list("abc")
    )
    df["grouping"] = ["group 1", "group 1", 2]
    result = df.groupby("grouping").aggregate(lambda x: x.tolist())
    expected_data = [[[0], [0], [0]], [[0, 0], [0, 0], [0, 0]]]
    expected = DataFrame(
        expected_data,
        index=Index([2, "group 1"], dtype="object", name="grouping"),
        columns=Index(["X", "Y", "Z"]),
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.xfail(reason="Not implemented;see GH 31256")
def test_aggregate_udf_na_extension_type():
    # https://github.com/pandas-dev/pandas/pull/31359
    # This is currently failing to cast back to Int64Dtype.
    # The presence of the NA causes two problems
    # 1. NA is not an instance of Int64Dtype.type (numpy.int64)
    # 2. The presence of an NA forces object type, so the non-NA values is
    #    a Python int rather than a NumPy int64. Python ints aren't
    #    instances of numpy.int64.
    def aggfunc(x):
        if all(x > 2):
            return 1
        else:
            return pd.NA

    df = DataFrame({"A": pd.array([1, 2, 3])})
    result = df.groupby([1, 1, 2]).agg(aggfunc)
    expected = DataFrame({"A": pd.array([1, pd.NA], dtype="Int64")}, index=[1, 2])
    tm.assert_frame_equal(result, expected)


class TestLambdaMangling:
    def test_basic(self):
        df = DataFrame({"A": [0, 0, 1, 1], "B": [1, 2, 3, 4]})
        result = df.groupby("A").agg({"B": [lambda x: 0, lambda x: 1]})

        expected = DataFrame(
            {("B", "<lambda_0>"): [0, 0], ("B", "<lambda_1>"): [1, 1]},
            index=Index([0, 1], name="A"),
        )
        tm.assert_frame_equal(result, expected)

    def test_mangle_series_groupby(self):
        gr = Series([1, 2, 3, 4]).groupby([0, 0, 1, 1])
        result = gr.agg([lambda x: 0, lambda x: 1])
        exp_data = {"<lambda_0>": [0, 0], "<lambda_1>": [1, 1]}
        expected = DataFrame(exp_data, index=np.array([0, 1]))
        tm.assert_frame_equal(result, expected)

    @pytest.mark.xfail(reason="GH-26611. kwargs for multi-agg.")
    def test_with_kwargs(self):
        f1 = lambda x, y, b=1: x.sum() + y + b
        f2 = lambda x, y, b=2: x.sum() + y * b
        result = Series([1, 2]).groupby([0, 0]).agg([f1, f2], 0)
        expected = DataFrame({"<lambda_0>": [4], "<lambda_1>": [6]})
        tm.assert_frame_equal(result, expected)

        result = Series([1, 2]).groupby([0, 0]).agg([f1, f2], 0, b=10)
        expected = DataFrame({"<lambda_0>": [13], "<lambda_1>": [30]})
        tm.assert_frame_equal(result, expected)

    def test_agg_with_one_lambda(self):
        # GH 25719, write tests for DataFrameGroupby.agg with only one lambda
        df = DataFrame(
            {
                "kind": ["cat", "dog", "cat", "dog"],
                "height": [9.1, 6.0, 9.5, 34.0],
                "weight": [7.9, 7.5, 9.9, 198.0],
            }
        )

        columns = ["height_sqr_min", "height_max", "weight_max"]
        expected = DataFrame(
            {
                "height_sqr_min": [82.81, 36.00],
                "height_max": [9.5, 34.0],
                "weight_max": [9.9, 198.0],
            },
            index=Index(["cat", "dog"], name="kind"),
            columns=columns,
        )

        # check pd.NameAgg case
        result1 = df.groupby(by="kind").agg(
            height_sqr_min=pd.NamedAgg(
                column="height", aggfunc=lambda x: np.min(x**2)
            ),
            height_max=pd.NamedAgg(column="height", aggfunc="max"),
            weight_max=pd.NamedAgg(column="weight", aggfunc="max"),
        )
        tm.assert_frame_equal(result1, expected)

        # check agg(key=(col, aggfunc)) case
        result2 = df.groupby(by="kind").agg(
            height_sqr_min=("height", lambda x: np.min(x**2)),
            height_max=("height", "max"),
            weight_max=("weight", "max"),
        )
        tm.assert_frame_equal(result2, expected)

    def test_agg_multiple_lambda(self):
        # GH25719, test for DataFrameGroupby.agg with multiple lambdas
        # with mixed aggfunc
        df = DataFrame(
            {
                "kind": ["cat", "dog", "cat", "dog"],
                "height": [9.1, 6.0, 9.5, 34.0],
                "weight": [7.9, 7.5, 9.9, 198.0],
            }
        )
        columns = [
            "height_sqr_min",
            "height_max",
            "weight_max",
            "height_max_2",
            "weight_min",
        ]
        expected = DataFrame(
            {
                "height_sqr_min": [82.81, 36.00],
                "height_max": [9.5, 34.0],
                "weight_max": [9.9, 198.0],
                "height_max_2": [9.5, 34.0],
                "weight_min": [7.9, 7.5],
            },
            index=Index(["cat", "dog"], name="kind"),
            columns=columns,
        )

        # check agg(key=(col, aggfunc)) case
        result1 = df.groupby(by="kind").agg(
            height_sqr_min=("height", lambda x: np.min(x**2)),
            height_max=("height", "max"),
            weight_max=("weight", "max"),
            height_max_2=("height", lambda x: np.max(x)),
            weight_min=("weight", lambda x: np.min(x)),
        )
        tm.assert_frame_equal(result1, expected)

        # check pd.NamedAgg case
        result2 = df.groupby(by="kind").agg(
            height_sqr_min=pd.NamedAgg(
                column="height", aggfunc=lambda x: np.min(x**2)
            ),
            height_max=pd.NamedAgg(column="height", aggfunc="max"),
            weight_max=pd.NamedAgg(column="weight", aggfunc="max"),
            height_max_2=pd.NamedAgg(column="height", aggfunc=lambda x: np.max(x)),
            weight_min=pd.NamedAgg(column="weight", aggfunc=lambda x: np.min(x)),
        )
        tm.assert_frame_equal(result2, expected)


def test_groupby_get_by_index():
    # GH 33439
    df = DataFrame({"A": ["S", "W", "W"], "B": [1.0, 1.0, 2.0]})
    res = df.groupby("A").agg({"B": lambda x: x.get(x.index[-1])})
    expected = DataFrame({"A": ["S", "W"], "B": [1.0, 2.0]}).set_index("A")
    tm.assert_frame_equal(res, expected)


@pytest.mark.parametrize(
    "grp_col_dict, exp_data",
    [
        ({"nr": "min", "cat_ord": "min"}, {"nr": [1, 5], "cat_ord": ["a", "c"]}),
        ({"cat_ord": "min"}, {"cat_ord": ["a", "c"]}),
        ({"nr": "min"}, {"nr": [1, 5]}),
    ],
)
def test_groupby_single_agg_cat_cols(grp_col_dict, exp_data):
    # test single aggregations on ordered categorical cols GHGH27800

    # create the result dataframe
    input_df = DataFrame(
        {
            "nr": [1, 2, 3, 4, 5, 6, 7, 8],
            "cat_ord": list("aabbccdd"),
            "cat": list("aaaabbbb"),
        }
    )

    input_df = input_df.astype({"cat": "category", "cat_ord": "category"})
    input_df["cat_ord"] = input_df["cat_ord"].cat.as_ordered()
    result_df = input_df.groupby("cat", observed=False).agg(grp_col_dict)

    # create expected dataframe
    cat_index = pd.CategoricalIndex(
        ["a", "b"], categories=["a", "b"], ordered=False, name="cat", dtype="category"
    )

    expected_df = DataFrame(data=exp_data, index=cat_index)

    if "cat_ord" in expected_df:
        # ordered categorical columns should be preserved
        dtype = input_df["cat_ord"].dtype
        expected_df["cat_ord"] = expected_df["cat_ord"].astype(dtype)

    tm.assert_frame_equal(result_df, expected_df)


@pytest.mark.parametrize(
    "grp_col_dict, exp_data",
    [
        ({"nr": ["min", "max"], "cat_ord": "min"}, [(1, 4, "a"), (5, 8, "c")]),
        ({"nr": "min", "cat_ord": ["min", "max"]}, [(1, "a", "b"), (5, "c", "d")]),
        ({"cat_ord": ["min", "max"]}, [("a", "b"), ("c", "d")]),
    ],
)
def test_groupby_combined_aggs_cat_cols(grp_col_dict, exp_data):
    # test combined aggregations on ordered categorical cols GH27800

    # create the result dataframe
    input_df = DataFrame(
        {
            "nr": [1, 2, 3, 4, 5, 6, 7, 8],
            "cat_ord": list("aabbccdd"),
            "cat": list("aaaabbbb"),
        }
    )

    input_df = input_df.astype({"cat": "category", "cat_ord": "category"})
    input_df["cat_ord"] = input_df["cat_ord"].cat.as_ordered()
    result_df = input_df.groupby("cat", observed=False).agg(grp_col_dict)

    # create expected dataframe
    cat_index = pd.CategoricalIndex(
        ["a", "b"], categories=["a", "b"], ordered=False, name="cat", dtype="category"
    )

    # unpack the grp_col_dict to create the multi-index tuple
    # this tuple will be used to create the expected dataframe index
    multi_index_list = []
    for k, v in grp_col_dict.items():
        if isinstance(v, list):
            multi_index_list.extend([k, value] for value in v)
        else:
            multi_index_list.append([k, v])
    multi_index = MultiIndex.from_tuples(tuple(multi_index_list))

    expected_df = DataFrame(data=exp_data, columns=multi_index, index=cat_index)
    for col in expected_df.columns:
        if isinstance(col, tuple) and "cat_ord" in col:
            # ordered categorical should be preserved
            expected_df[col] = expected_df[col].astype(input_df["cat_ord"].dtype)

    tm.assert_frame_equal(result_df, expected_df)


def test_nonagg_agg():
    # GH 35490 - Single/Multiple agg of non-agg function give same results
    # TODO: agg should raise for functions that don't aggregate
    df = DataFrame({"a": [1, 1, 2, 2], "b": [1, 2, 2, 1]})
    g = df.groupby("a")

    result = g.agg(["cumsum"])
    result.columns = result.columns.droplevel(-1)
    expected = g.agg("cumsum")

    tm.assert_frame_equal(result, expected)


def test_aggregate_datetime_objects():
    # https://github.com/pandas-dev/pandas/issues/36003
    # ensure we don't raise an error but keep object dtype for out-of-bounds
    # datetimes
    df = DataFrame(
        {
            "A": ["X", "Y"],
            "B": [
                datetime.datetime(2005, 1, 1, 10, 30, 23, 540000),
                datetime.datetime(3005, 1, 1, 10, 30, 23, 540000),
            ],
        }
    )
    result = df.groupby("A").B.max()
    expected = df.set_index("A")["B"]
    tm.assert_series_equal(result, expected)


def test_groupby_index_object_dtype():
    # GH 40014
    df = DataFrame({"c0": ["x", "x", "x"], "c1": ["x", "x", "y"], "p": [0, 1, 2]})
    df.index = df.index.astype("O")
    grouped = df.groupby(["c0", "c1"])
    res = grouped.p.agg(lambda x: all(x > 0))
    # Check that providing a user-defined function in agg()
    # produces the correct index shape when using an object-typed index.
    expected_index = MultiIndex.from_tuples(
        [("x", "x"), ("x", "y")], names=("c0", "c1")
    )
    expected = Series([False, True], index=expected_index, name="p")
    tm.assert_series_equal(res, expected)


def test_timeseries_groupby_agg():
    # GH#43290

    def func(ser):
        if ser.isna().all():
            return None
        return np.sum(ser)

    df = DataFrame([1.0], index=[pd.Timestamp("2018-01-16 00:00:00+00:00")])
    res = df.groupby(lambda x: 1).agg(func)

    expected = DataFrame([[1.0]], index=[1])
    tm.assert_frame_equal(res, expected)


def test_groupby_agg_precision(any_real_numeric_dtype):
    if any_real_numeric_dtype in tm.ALL_INT_NUMPY_DTYPES:
        max_value = np.iinfo(any_real_numeric_dtype).max
    if any_real_numeric_dtype in tm.FLOAT_NUMPY_DTYPES:
        max_value = np.finfo(any_real_numeric_dtype).max
    if any_real_numeric_dtype in tm.FLOAT_EA_DTYPES:
        max_value = np.finfo(any_real_numeric_dtype.lower()).max
    if any_real_numeric_dtype in tm.ALL_INT_EA_DTYPES:
        max_value = np.iinfo(any_real_numeric_dtype.lower()).max

    df = DataFrame(
        {
            "key1": ["a"],
            "key2": ["b"],
            "key3": pd.array([max_value], dtype=any_real_numeric_dtype),
        }
    )
    arrays = [["a"], ["b"]]
    index = MultiIndex.from_arrays(arrays, names=("key1", "key2"))

    expected = DataFrame(
        {"key3": pd.array([max_value], dtype=any_real_numeric_dtype)}, index=index
    )
    result = df.groupby(["key1", "key2"]).agg(lambda x: x)
    tm.assert_frame_equal(result, expected)


def test_groupby_aggregate_directory(reduction_func):
    # GH#32793
    if reduction_func in ["corrwith", "nth"]:
        return None

    obj = DataFrame([[0, 1], [0, np.nan]])

    result_reduced_series = obj.groupby(0).agg(reduction_func)
    result_reduced_frame = obj.groupby(0).agg({1: reduction_func})

    if reduction_func in ["size", "ngroup"]:
        # names are different: None / 1
        tm.assert_series_equal(
            result_reduced_series, result_reduced_frame[1], check_names=False
        )
    else:
        tm.assert_frame_equal(result_reduced_series, result_reduced_frame)
        tm.assert_series_equal(
            result_reduced_series.dtypes, result_reduced_frame.dtypes
        )


def test_group_mean_timedelta_nat():
    # GH43132
    data = Series(["1 day", "3 days", "NaT"], dtype="timedelta64[ns]")
    expected = Series(["2 days"], dtype="timedelta64[ns]", index=np.array([0]))

    result = data.groupby([0, 0, 0]).mean()

    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "input_data, expected_output",
    [
        (  # no timezone
            ["2021-01-01T00:00", "NaT", "2021-01-01T02:00"],
            ["2021-01-01T01:00"],
        ),
        (  # timezone
            ["2021-01-01T00:00-0100", "NaT", "2021-01-01T02:00-0100"],
            ["2021-01-01T01:00-0100"],
        ),
    ],
)
def test_group_mean_datetime64_nat(input_data, expected_output):
    # GH43132
    data = to_datetime(Series(input_data))
    expected = to_datetime(Series(expected_output, index=np.array([0])))

    result = data.groupby([0, 0, 0]).mean()
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "func, output", [("mean", [8 + 18j, 10 + 22j]), ("sum", [40 + 90j, 50 + 110j])]
)
def test_groupby_complex(func, output):
    # GH#43701
    data = Series(np.arange(20).reshape(10, 2).dot([1, 2j]))
    result = data.groupby(data.index % 2).agg(func)
    expected = Series(output)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("func", ["min", "max", "var"])
def test_groupby_complex_raises(func):
    # GH#43701
    data = Series(np.arange(20).reshape(10, 2).dot([1, 2j]))
    msg = "No matching signature found"
    with pytest.raises(TypeError, match=msg):
        data.groupby(data.index % 2).agg(func)


@pytest.mark.parametrize(
    "func", [["min"], ["mean", "max"], {"b": "sum"}, {"b": "prod", "c": "median"}]
)
def test_multi_axis_1_raises(func):
    # GH#46995
    df = DataFrame({"a": [1, 1, 2], "b": [3, 4, 5], "c": [6, 7, 8]})
    msg = "DataFrame.groupby with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        gb = df.groupby("a", axis=1)
    with pytest.raises(NotImplementedError, match="axis other than 0 is not supported"):
        gb.agg(func)


@pytest.mark.parametrize(
    "test, constant",
    [
        ([[20, "A"], [20, "B"], [10, "C"]], {0: [10, 20], 1: ["C", ["A", "B"]]}),
        ([[20, "A"], [20, "B"], [30, "C"]], {0: [20, 30], 1: [["A", "B"], "C"]}),
        ([["a", 1], ["a", 1], ["b", 2], ["b", 3]], {0: ["a", "b"], 1: [1, [2, 3]]}),
        pytest.param(
            [["a", 1], ["a", 2], ["b", 3], ["b", 3]],
            {0: ["a", "b"], 1: [[1, 2], 3]},
            marks=pytest.mark.xfail,
        ),
    ],
)
def test_agg_of_mode_list(test, constant):
    # GH#25581
    df1 = DataFrame(test)
    result = df1.groupby(0).agg(Series.mode)
    # Mode usually only returns 1 value, but can return a list in the case of a tie.

    expected = DataFrame(constant)
    expected = expected.set_index(0)

    tm.assert_frame_equal(result, expected)


def test_dataframe_groupy_agg_list_like_func_with_args():
    # GH#50624
    df = DataFrame({"x": [1, 2, 3], "y": ["a", "b", "c"]})
    gb = df.groupby("y")

    def foo1(x, a=1, c=0):
        return x.sum() + a + c

    def foo2(x, b=2, c=0):
        return x.sum() + b + c

    msg = r"foo1\(\) got an unexpected keyword argument 'b'"
    with pytest.raises(TypeError, match=msg):
        gb.agg([foo1, foo2], 3, b=3, c=4)

    result = gb.agg([foo1, foo2], 3, c=4)
    expected = DataFrame(
        [[8, 8], [9, 9], [10, 10]],
        index=Index(["a", "b", "c"], name="y"),
        columns=MultiIndex.from_tuples([("x", "foo1"), ("x", "foo2")]),
    )
    tm.assert_frame_equal(result, expected)


def test_series_groupy_agg_list_like_func_with_args():
    # GH#50624
    s = Series([1, 2, 3])
    sgb = s.groupby(s)

    def foo1(x, a=1, c=0):
        return x.sum() + a + c

    def foo2(x, b=2, c=0):
        return x.sum() + b + c

    msg = r"foo1\(\) got an unexpected keyword argument 'b'"
    with pytest.raises(TypeError, match=msg):
        sgb.agg([foo1, foo2], 3, b=3, c=4)

    result = sgb.agg([foo1, foo2], 3, c=4)
    expected = DataFrame(
        [[8, 8], [9, 9], [10, 10]], index=Index([1, 2, 3]), columns=["foo1", "foo2"]
    )
    tm.assert_frame_equal(result, expected)


def test_agg_groupings_selection():
    # GH#51186 - a selected grouping should be in the output of agg
    df = DataFrame({"a": [1, 1, 2], "b": [3, 3, 4], "c": [5, 6, 7]})
    gb = df.groupby(["a", "b"])
    selected_gb = gb[["b", "c"]]
    result = selected_gb.agg(lambda x: x.sum())
    index = MultiIndex(
        levels=[[1, 2], [3, 4]], codes=[[0, 1], [0, 1]], names=["a", "b"]
    )
    expected = DataFrame({"b": [6, 4], "c": [11, 7]}, index=index)
    tm.assert_frame_equal(result, expected)


def test_agg_multiple_with_as_index_false_subset_to_a_single_column():
    # GH#50724
    df = DataFrame({"a": [1, 1, 2], "b": [3, 4, 5]})
    gb = df.groupby("a", as_index=False)["b"]
    result = gb.agg(["sum", "mean"])
    expected = DataFrame({"a": [1, 2], "sum": [7, 5], "mean": [3.5, 5.0]})
    tm.assert_frame_equal(result, expected)


def test_agg_with_as_index_false_with_list():
    # GH#52849
    df = DataFrame({"a1": [0, 0, 1], "a2": [2, 3, 3], "b": [4, 5, 6]})
    gb = df.groupby(by=["a1", "a2"], as_index=False)
    result = gb.agg(["sum"])

    expected = DataFrame(
        data=[[0, 2, 4], [0, 3, 5], [1, 3, 6]],
        columns=MultiIndex.from_tuples([("a1", ""), ("a2", ""), ("b", "sum")]),
    )
    tm.assert_frame_equal(result, expected)


def test_groupby_agg_extension_timedelta_cumsum_with_named_aggregation():
    # GH#41720
    expected = DataFrame(
        {
            "td": {
                0: pd.Timedelta("0 days 01:00:00"),
                1: pd.Timedelta("0 days 01:15:00"),
                2: pd.Timedelta("0 days 01:15:00"),
            }
        }
    )
    df = DataFrame(
        {
            "td": Series(
                ["0 days 01:00:00", "0 days 00:15:00", "0 days 01:15:00"],
                dtype="timedelta64[ns]",
            ),
            "grps": ["a", "a", "b"],
        }
    )
    gb = df.groupby("grps")
    result = gb.agg(td=("td", "cumsum"))
    tm.assert_frame_equal(result, expected)


def test_groupby_aggregation_empty_group():
    # https://github.com/pandas-dev/pandas/issues/18869
    def func(x):
        if len(x) == 0:
            raise ValueError("length must not be 0")
        return len(x)

    df = DataFrame(
        {"A": pd.Categorical(["a", "a"], categories=["a", "b", "c"]), "B": [1, 1]}
    )
    msg = "length must not be 0"
    with pytest.raises(ValueError, match=msg):
        df.groupby("A", observed=False).agg(func)
