""" test with the .transform """
import numpy as np
import pytest

from pandas._libs import lib

from pandas.core.dtypes.common import ensure_platform_int

import pandas as pd
from pandas import (
    Categorical,
    DataFrame,
    Index,
    MultiIndex,
    Series,
    Timestamp,
    concat,
    date_range,
)
import pandas._testing as tm
from pandas.tests.groupby import get_groupby_method_args


def assert_fp_equal(a, b):
    assert (np.abs(a - b) < 1e-12).all()


def test_transform():
    data = Series(np.arange(9) // 3, index=np.arange(9))

    index = np.arange(9)
    np.random.default_rng(2).shuffle(index)
    data = data.reindex(index)

    grouped = data.groupby(lambda x: x // 3)

    transformed = grouped.transform(lambda x: x * x.sum())
    assert transformed[7] == 12

    # GH 8046
    # make sure that we preserve the input order

    df = DataFrame(
        np.arange(6, dtype="int64").reshape(3, 2), columns=["a", "b"], index=[0, 2, 1]
    )
    key = [0, 0, 1]
    expected = (
        df.sort_index()
        .groupby(key)
        .transform(lambda x: x - x.mean())
        .groupby(key)
        .mean()
    )
    result = df.groupby(key).transform(lambda x: x - x.mean()).groupby(key).mean()
    tm.assert_frame_equal(result, expected)

    def demean(arr):
        return arr - arr.mean(axis=0)

    people = DataFrame(
        np.random.default_rng(2).standard_normal((5, 5)),
        columns=["a", "b", "c", "d", "e"],
        index=["Joe", "Steve", "Wes", "Jim", "Travis"],
    )
    key = ["one", "two", "one", "two", "one"]
    result = people.groupby(key).transform(demean).groupby(key).mean()
    expected = people.groupby(key, group_keys=False).apply(demean).groupby(key).mean()
    tm.assert_frame_equal(result, expected)

    # GH 8430
    df = DataFrame(
        np.random.default_rng(2).standard_normal((50, 4)),
        columns=Index(list("ABCD"), dtype=object),
        index=date_range("2000-01-01", periods=50, freq="B"),
    )
    g = df.groupby(pd.Grouper(freq="ME"))
    g.transform(lambda x: x - 1)

    # GH 9700
    df = DataFrame({"a": range(5, 10), "b": range(5)})
    msg = "using DataFrameGroupBy.max"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = df.groupby("a").transform(max)
    expected = DataFrame({"b": range(5)})
    tm.assert_frame_equal(result, expected)


def test_transform_fast():
    df = DataFrame(
        {
            "id": np.arange(100000) / 3,
            "val": np.random.default_rng(2).standard_normal(100000),
        }
    )

    grp = df.groupby("id")["val"]

    values = np.repeat(grp.mean().values, ensure_platform_int(grp.count().values))
    expected = Series(values, index=df.index, name="val")

    msg = "using SeriesGroupBy.mean"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = grp.transform(np.mean)
    tm.assert_series_equal(result, expected)

    result = grp.transform("mean")
    tm.assert_series_equal(result, expected)


def test_transform_fast2():
    # GH 12737
    df = DataFrame(
        {
            "grouping": [0, 1, 1, 3],
            "f": [1.1, 2.1, 3.1, 4.5],
            "d": date_range("2014-1-1", "2014-1-4"),
            "i": [1, 2, 3, 4],
        },
        columns=["grouping", "f", "i", "d"],
    )
    result = df.groupby("grouping").transform("first")

    dates = Index(
        [
            Timestamp("2014-1-1"),
            Timestamp("2014-1-2"),
            Timestamp("2014-1-2"),
            Timestamp("2014-1-4"),
        ],
        dtype="M8[ns]",
    )
    expected = DataFrame(
        {"f": [1.1, 2.1, 2.1, 4.5], "d": dates, "i": [1, 2, 2, 4]},
        columns=["f", "i", "d"],
    )
    tm.assert_frame_equal(result, expected)

    # selection
    result = df.groupby("grouping")[["f", "i"]].transform("first")
    expected = expected[["f", "i"]]
    tm.assert_frame_equal(result, expected)


def test_transform_fast3():
    # dup columns
    df = DataFrame([[1, 2, 3], [4, 5, 6]], columns=["g", "a", "a"])
    result = df.groupby("g").transform("first")
    expected = df.drop("g", axis=1)
    tm.assert_frame_equal(result, expected)


def test_transform_broadcast(tsframe, ts):
    grouped = ts.groupby(lambda x: x.month)
    msg = "using SeriesGroupBy.mean"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = grouped.transform(np.mean)

    tm.assert_index_equal(result.index, ts.index)
    for _, gp in grouped:
        assert_fp_equal(result.reindex(gp.index), gp.mean())

    grouped = tsframe.groupby(lambda x: x.month)
    msg = "using DataFrameGroupBy.mean"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = grouped.transform(np.mean)
    tm.assert_index_equal(result.index, tsframe.index)
    for _, gp in grouped:
        agged = gp.mean(axis=0)
        res = result.reindex(gp.index)
        for col in tsframe:
            assert_fp_equal(res[col], agged[col])

    # group columns
    msg = "DataFrame.groupby with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        grouped = tsframe.groupby({"A": 0, "B": 0, "C": 1, "D": 1}, axis=1)
    msg = "using DataFrameGroupBy.mean"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = grouped.transform(np.mean)
    tm.assert_index_equal(result.index, tsframe.index)
    tm.assert_index_equal(result.columns, tsframe.columns)
    for _, gp in grouped:
        agged = gp.mean(1)
        res = result.reindex(columns=gp.columns)
        for idx in gp.index:
            assert_fp_equal(res.xs(idx), agged[idx])


def test_transform_axis_1(request, transformation_func):
    # GH 36308

    df = DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]}, index=["x", "y"])
    args = get_groupby_method_args(transformation_func, df)
    msg = "DataFrame.groupby with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        gb = df.groupby([0, 0, 1], axis=1)
    warn = FutureWarning if transformation_func == "fillna" else None
    msg = "DataFrameGroupBy.fillna is deprecated"
    with tm.assert_produces_warning(warn, match=msg):
        result = gb.transform(transformation_func, *args)
    msg = "DataFrameGroupBy.fillna is deprecated"
    with tm.assert_produces_warning(warn, match=msg):
        expected = df.T.groupby([0, 0, 1]).transform(transformation_func, *args).T

    if transformation_func in ["diff", "shift"]:
        # Result contains nans, so transpose coerces to float
        expected["b"] = expected["b"].astype("int64")

    # cumcount returns Series; the rest are DataFrame
    tm.assert_equal(result, expected)


def test_transform_axis_1_reducer(request, reduction_func):
    # GH#45715
    if reduction_func in (
        "corrwith",
        "ngroup",
        "nth",
    ):
        marker = pytest.mark.xfail(reason="transform incorrectly fails - GH#45986")
        request.applymarker(marker)

    df = DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]}, index=["x", "y"])
    msg = "DataFrame.groupby with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        gb = df.groupby([0, 0, 1], axis=1)

    result = gb.transform(reduction_func)
    expected = df.T.groupby([0, 0, 1]).transform(reduction_func).T
    tm.assert_equal(result, expected)


def test_transform_axis_ts(tsframe):
    # make sure that we are setting the axes
    # correctly when on axis=0 or 1
    # in the presence of a non-monotonic indexer
    # GH12713

    base = tsframe.iloc[0:5]
    r = len(base.index)
    c = len(base.columns)
    tso = DataFrame(
        np.random.default_rng(2).standard_normal((r, c)),
        index=base.index,
        columns=base.columns,
        dtype="float64",
    )
    # monotonic
    ts = tso
    grouped = ts.groupby(lambda x: x.weekday(), group_keys=False)
    result = ts - grouped.transform("mean")
    expected = grouped.apply(lambda x: x - x.mean(axis=0))
    tm.assert_frame_equal(result, expected)

    ts = ts.T
    msg = "DataFrame.groupby with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        grouped = ts.groupby(lambda x: x.weekday(), axis=1, group_keys=False)
    result = ts - grouped.transform("mean")
    expected = grouped.apply(lambda x: (x.T - x.mean(1)).T)
    tm.assert_frame_equal(result, expected)

    # non-monotonic
    ts = tso.iloc[[1, 0] + list(range(2, len(base)))]
    grouped = ts.groupby(lambda x: x.weekday(), group_keys=False)
    result = ts - grouped.transform("mean")
    expected = grouped.apply(lambda x: x - x.mean(axis=0))
    tm.assert_frame_equal(result, expected)

    ts = ts.T
    msg = "DataFrame.groupby with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        grouped = ts.groupby(lambda x: x.weekday(), axis=1, group_keys=False)
    result = ts - grouped.transform("mean")
    expected = grouped.apply(lambda x: (x.T - x.mean(1)).T)
    tm.assert_frame_equal(result, expected)


def test_transform_dtype():
    # GH 9807
    # Check transform dtype output is preserved
    df = DataFrame([[1, 3], [2, 3]])
    result = df.groupby(1).transform("mean")
    expected = DataFrame([[1.5], [1.5]])
    tm.assert_frame_equal(result, expected)


def test_transform_bug():
    # GH 5712
    # transforming on a datetime column
    df = DataFrame({"A": Timestamp("20130101"), "B": np.arange(5)})
    result = df.groupby("A")["B"].transform(lambda x: x.rank(ascending=False))
    expected = Series(np.arange(5, 0, step=-1), name="B", dtype="float64")
    tm.assert_series_equal(result, expected)


def test_transform_numeric_to_boolean():
    # GH 16875
    # inconsistency in transforming boolean values
    expected = Series([True, True], name="A")

    df = DataFrame({"A": [1.1, 2.2], "B": [1, 2]})
    result = df.groupby("B").A.transform(lambda x: True)
    tm.assert_series_equal(result, expected)

    df = DataFrame({"A": [1, 2], "B": [1, 2]})
    result = df.groupby("B").A.transform(lambda x: True)
    tm.assert_series_equal(result, expected)


def test_transform_datetime_to_timedelta():
    # GH 15429
    # transforming a datetime to timedelta
    df = DataFrame({"A": Timestamp("20130101"), "B": np.arange(5)})
    expected = Series(
        Timestamp("20130101") - Timestamp("20130101"), index=range(5), name="A"
    )

    # this does date math without changing result type in transform
    base_time = df["A"][0]
    result = (
        df.groupby("A")["A"].transform(lambda x: x.max() - x.min() + base_time)
        - base_time
    )
    tm.assert_series_equal(result, expected)

    # this does date math and causes the transform to return timedelta
    result = df.groupby("A")["A"].transform(lambda x: x.max() - x.min())
    tm.assert_series_equal(result, expected)


def test_transform_datetime_to_numeric():
    # GH 10972
    # convert dt to float
    df = DataFrame({"a": 1, "b": date_range("2015-01-01", periods=2, freq="D")})
    result = df.groupby("a").b.transform(
        lambda x: x.dt.dayofweek - x.dt.dayofweek.mean()
    )

    expected = Series([-0.5, 0.5], name="b")
    tm.assert_series_equal(result, expected)

    # convert dt to int
    df = DataFrame({"a": 1, "b": date_range("2015-01-01", periods=2, freq="D")})
    result = df.groupby("a").b.transform(
        lambda x: x.dt.dayofweek - x.dt.dayofweek.min()
    )

    expected = Series([0, 1], dtype=np.int32, name="b")
    tm.assert_series_equal(result, expected)


def test_transform_casting():
    # 13046
    times = [
        "13:43:27",
        "14:26:19",
        "14:29:01",
        "18:39:34",
        "18:40:18",
        "18:44:30",
        "18:46:00",
        "18:52:15",
        "18:59:59",
        "19:17:48",
        "19:21:38",
    ]
    df = DataFrame(
        {
            "A": [f"B-{i}" for i in range(11)],
            "ID3": np.take(
                ["a", "b", "c", "d", "e"], [0, 1, 2, 1, 3, 1, 1, 1, 4, 1, 1]
            ),
            "DATETIME": pd.to_datetime([f"2014-10-08 {time}" for time in times]),
        },
        index=pd.RangeIndex(11, name="idx"),
    )

    result = df.groupby("ID3")["DATETIME"].transform(lambda x: x.diff())
    assert lib.is_np_dtype(result.dtype, "m")

    result = df[["ID3", "DATETIME"]].groupby("ID3").transform(lambda x: x.diff())
    assert lib.is_np_dtype(result.DATETIME.dtype, "m")


def test_transform_multiple(ts):
    grouped = ts.groupby([lambda x: x.year, lambda x: x.month])

    grouped.transform(lambda x: x * 2)

    msg = "using SeriesGroupBy.mean"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        grouped.transform(np.mean)


def test_dispatch_transform(tsframe):
    df = tsframe[::5].reindex(tsframe.index)

    grouped = df.groupby(lambda x: x.month)

    msg = "DataFrameGroupBy.fillna is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        filled = grouped.fillna(method="pad")
    msg = "Series.fillna with 'method' is deprecated"
    fillit = lambda x: x.fillna(method="pad")
    with tm.assert_produces_warning(FutureWarning, match=msg):
        expected = df.groupby(lambda x: x.month).transform(fillit)
    tm.assert_frame_equal(filled, expected)


def test_transform_fillna_null():
    df = DataFrame(
        {
            "price": [10, 10, 20, 20, 30, 30],
            "color": [10, 10, 20, 20, 30, 30],
            "cost": (100, 200, 300, 400, 500, 600),
        }
    )
    msg = "DataFrameGroupBy.fillna is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        with pytest.raises(ValueError, match="Must specify a fill 'value' or 'method'"):
            df.groupby(["price"]).transform("fillna")
    with tm.assert_produces_warning(FutureWarning, match=msg):
        with pytest.raises(ValueError, match="Must specify a fill 'value' or 'method'"):
            df.groupby(["price"]).fillna()


def test_transform_transformation_func(transformation_func):
    # GH 30918
    df = DataFrame(
        {
            "A": ["foo", "foo", "foo", "foo", "bar", "bar", "baz"],
            "B": [1, 2, np.nan, 3, 3, np.nan, 4],
        },
        index=date_range("2020-01-01", "2020-01-07"),
    )
    if transformation_func == "cumcount":
        test_op = lambda x: x.transform("cumcount")
        mock_op = lambda x: Series(range(len(x)), x.index)
    elif transformation_func == "fillna":
        test_op = lambda x: x.transform("fillna", value=0)
        mock_op = lambda x: x.fillna(value=0)
    elif transformation_func == "ngroup":
        test_op = lambda x: x.transform("ngroup")
        counter = -1

        def mock_op(x):
            nonlocal counter
            counter += 1
            return Series(counter, index=x.index)

    else:
        test_op = lambda x: x.transform(transformation_func)
        mock_op = lambda x: getattr(x, transformation_func)()

    if transformation_func == "pct_change":
        msg = "The default fill_method='pad' in DataFrame.pct_change is deprecated"
        groupby_msg = (
            "The default fill_method='ffill' in DataFrameGroupBy.pct_change "
            "is deprecated"
        )
        warn = FutureWarning
        groupby_warn = FutureWarning
    elif transformation_func == "fillna":
        msg = ""
        groupby_msg = "DataFrameGroupBy.fillna is deprecated"
        warn = None
        groupby_warn = FutureWarning
    else:
        msg = groupby_msg = ""
        warn = groupby_warn = None

    with tm.assert_produces_warning(groupby_warn, match=groupby_msg):
        result = test_op(df.groupby("A"))

    # pass the group in same order as iterating `for ... in df.groupby(...)`
    # but reorder to match df's index since this is a transform
    groups = [df[["B"]].iloc[4:6], df[["B"]].iloc[6:], df[["B"]].iloc[:4]]
    with tm.assert_produces_warning(warn, match=msg):
        expected = concat([mock_op(g) for g in groups]).sort_index()
    # sort_index does not preserve the freq
    expected = expected.set_axis(df.index)

    if transformation_func in ("cumcount", "ngroup"):
        tm.assert_series_equal(result, expected)
    else:
        tm.assert_frame_equal(result, expected)


def test_transform_select_columns(df):
    f = lambda x: x.mean()
    result = df.groupby("A")[["C", "D"]].transform(f)

    selection = df[["C", "D"]]
    expected = selection.groupby(df["A"]).transform(f)

    tm.assert_frame_equal(result, expected)


def test_transform_nuisance_raises(df, using_infer_string):
    # case that goes through _transform_item_by_item

    df.columns = ["A", "B", "B", "D"]

    # this also tests orderings in transform between
    # series/frame to make sure it's consistent
    grouped = df.groupby("A")

    gbc = grouped["B"]
    msg = "Could not convert"
    if using_infer_string:
        msg = "Cannot perform reduction 'mean' with string dtype"
    with pytest.raises(TypeError, match=msg):
        gbc.transform(lambda x: np.mean(x))

    with pytest.raises(TypeError, match=msg):
        df.groupby("A").transform(lambda x: np.mean(x))


def test_transform_function_aliases(df):
    result = df.groupby("A").transform("mean", numeric_only=True)
    msg = "using DataFrameGroupBy.mean"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        expected = df.groupby("A")[["C", "D"]].transform(np.mean)
    tm.assert_frame_equal(result, expected)

    result = df.groupby("A")["C"].transform("mean")
    msg = "using SeriesGroupBy.mean"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        expected = df.groupby("A")["C"].transform(np.mean)
    tm.assert_series_equal(result, expected)


def test_series_fast_transform_date():
    # GH 13191
    df = DataFrame(
        {"grouping": [np.nan, 1, 1, 3], "d": date_range("2014-1-1", "2014-1-4")}
    )
    result = df.groupby("grouping")["d"].transform("first")
    dates = [
        pd.NaT,
        Timestamp("2014-1-2"),
        Timestamp("2014-1-2"),
        Timestamp("2014-1-4"),
    ]
    expected = Series(dates, name="d", dtype="M8[ns]")
    tm.assert_series_equal(result, expected)


def test_transform_length():
    # GH 9697
    df = DataFrame({"col1": [1, 1, 2, 2], "col2": [1, 2, 3, np.nan]})
    expected = Series([3.0] * 4)

    def nsum(x):
        return np.nansum(x)

    msg = "using DataFrameGroupBy.sum"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        results = [
            df.groupby("col1").transform(sum)["col2"],
            df.groupby("col1")["col2"].transform(sum),
            df.groupby("col1").transform(nsum)["col2"],
            df.groupby("col1")["col2"].transform(nsum),
        ]
    for result in results:
        tm.assert_series_equal(result, expected, check_names=False)


def test_transform_coercion():
    # 14457
    # when we are transforming be sure to not coerce
    # via assignment
    df = DataFrame({"A": ["a", "a", "b", "b"], "B": [0, 1, 3, 4]})
    g = df.groupby("A")

    msg = "using DataFrameGroupBy.mean"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        expected = g.transform(np.mean)

    result = g.transform(lambda x: np.mean(x, axis=0))
    tm.assert_frame_equal(result, expected)


def test_groupby_transform_with_int(using_infer_string):
    # GH 3740, make sure that we might upcast on item-by-item transform

    # floats
    df = DataFrame(
        {
            "A": [1, 1, 1, 2, 2, 2],
            "B": Series(1, dtype="float64"),
            "C": Series([1, 2, 3, 1, 2, 3], dtype="float64"),
            "D": "foo",
        }
    )
    with np.errstate(all="ignore"):
        result = df.groupby("A")[["B", "C"]].transform(
            lambda x: (x - x.mean()) / x.std()
        )
    expected = DataFrame(
        {"B": np.nan, "C": Series([-1, 0, 1, -1, 0, 1], dtype="float64")}
    )
    tm.assert_frame_equal(result, expected)

    # int case
    df = DataFrame(
        {
            "A": [1, 1, 1, 2, 2, 2],
            "B": 1,
            "C": [1, 2, 3, 1, 2, 3],
            "D": "foo",
        }
    )
    msg = "Could not convert"
    if using_infer_string:
        msg = "Cannot perform reduction 'mean' with string dtype"
    with np.errstate(all="ignore"):
        with pytest.raises(TypeError, match=msg):
            df.groupby("A").transform(lambda x: (x - x.mean()) / x.std())
        result = df.groupby("A")[["B", "C"]].transform(
            lambda x: (x - x.mean()) / x.std()
        )
    expected = DataFrame({"B": np.nan, "C": [-1.0, 0.0, 1.0, -1.0, 0.0, 1.0]})
    tm.assert_frame_equal(result, expected)

    # int that needs float conversion
    s = Series([2, 3, 4, 10, 5, -1])
    df = DataFrame({"A": [1, 1, 1, 2, 2, 2], "B": 1, "C": s, "D": "foo"})
    with np.errstate(all="ignore"):
        with pytest.raises(TypeError, match=msg):
            df.groupby("A").transform(lambda x: (x - x.mean()) / x.std())
        result = df.groupby("A")[["B", "C"]].transform(
            lambda x: (x - x.mean()) / x.std()
        )

    s1 = s.iloc[0:3]
    s1 = (s1 - s1.mean()) / s1.std()
    s2 = s.iloc[3:6]
    s2 = (s2 - s2.mean()) / s2.std()
    expected = DataFrame({"B": np.nan, "C": concat([s1, s2])})
    tm.assert_frame_equal(result, expected)

    # int doesn't get downcasted
    result = df.groupby("A")[["B", "C"]].transform(lambda x: x * 2 / 2)
    expected = DataFrame({"B": 1.0, "C": [2.0, 3.0, 4.0, 10.0, 5.0, -1.0]})
    tm.assert_frame_equal(result, expected)


def test_groupby_transform_with_nan_group():
    # GH 9941
    df = DataFrame({"a": range(10), "b": [1, 1, 2, 3, np.nan, 4, 4, 5, 5, 5]})
    msg = "using SeriesGroupBy.max"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = df.groupby(df.b)["a"].transform(max)
    expected = Series([1.0, 1.0, 2.0, 3.0, np.nan, 6.0, 6.0, 9.0, 9.0, 9.0], name="a")
    tm.assert_series_equal(result, expected)


def test_transform_mixed_type():
    index = MultiIndex.from_arrays([[0, 0, 0, 1, 1, 1], [1, 2, 3, 1, 2, 3]])
    df = DataFrame(
        {
            "d": [1.0, 1.0, 1.0, 2.0, 2.0, 2.0],
            "c": np.tile(["a", "b", "c"], 2),
            "v": np.arange(1.0, 7.0),
        },
        index=index,
    )

    def f(group):
        group["g"] = group["d"] * 2
        return group[:1]

    grouped = df.groupby("c")
    msg = "DataFrameGroupBy.apply operated on the grouping columns"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = grouped.apply(f)

    assert result["d"].dtype == np.float64

    # this is by definition a mutating operation!
    with pd.option_context("mode.chained_assignment", None):
        for key, group in grouped:
            res = f(group)
            tm.assert_frame_equal(res, result.loc[key])


@pytest.mark.parametrize(
    "op, args, targop",
    [
        ("cumprod", (), lambda x: x.cumprod()),
        ("cumsum", (), lambda x: x.cumsum()),
        ("shift", (-1,), lambda x: x.shift(-1)),
        ("shift", (1,), lambda x: x.shift()),
    ],
)
def test_cython_transform_series(op, args, targop):
    # GH 4095
    s = Series(np.random.default_rng(2).standard_normal(1000))
    s_missing = s.copy()
    s_missing.iloc[2:10] = np.nan
    labels = np.random.default_rng(2).integers(0, 50, size=1000).astype(float)

    # series
    for data in [s, s_missing]:
        # print(data.head())
        expected = data.groupby(labels).transform(targop)

        tm.assert_series_equal(expected, data.groupby(labels).transform(op, *args))
        tm.assert_series_equal(expected, getattr(data.groupby(labels), op)(*args))


@pytest.mark.parametrize("op", ["cumprod", "cumsum"])
@pytest.mark.parametrize("skipna", [False, True])
@pytest.mark.parametrize(
    "input, exp",
    [
        # When everything is NaN
        ({"key": ["b"] * 10, "value": np.nan}, Series([np.nan] * 10, name="value")),
        # When there is a single NaN
        (
            {"key": ["b"] * 10 + ["a"] * 2, "value": [3] * 3 + [np.nan] + [3] * 8},
            {
                ("cumprod", False): [3.0, 9.0, 27.0] + [np.nan] * 7 + [3.0, 9.0],
                ("cumprod", True): [
                    3.0,
                    9.0,
                    27.0,
                    np.nan,
                    81.0,
                    243.0,
                    729.0,
                    2187.0,
                    6561.0,
                    19683.0,
                    3.0,
                    9.0,
                ],
                ("cumsum", False): [3.0, 6.0, 9.0] + [np.nan] * 7 + [3.0, 6.0],
                ("cumsum", True): [
                    3.0,
                    6.0,
                    9.0,
                    np.nan,
                    12.0,
                    15.0,
                    18.0,
                    21.0,
                    24.0,
                    27.0,
                    3.0,
                    6.0,
                ],
            },
        ),
    ],
)
def test_groupby_cum_skipna(op, skipna, input, exp):
    df = DataFrame(input)
    result = df.groupby("key")["value"].transform(op, skipna=skipna)
    if isinstance(exp, dict):
        expected = exp[(op, skipna)]
    else:
        expected = exp
    expected = Series(expected, name="value")
    tm.assert_series_equal(expected, result)


@pytest.fixture
def frame():
    floating = Series(np.random.default_rng(2).standard_normal(10))
    floating_missing = floating.copy()
    floating_missing.iloc[2:7] = np.nan
    strings = list("abcde") * 2
    strings_missing = strings[:]
    strings_missing[5] = np.nan

    df = DataFrame(
        {
            "float": floating,
            "float_missing": floating_missing,
            "int": [1, 1, 1, 1, 2] * 2,
            "datetime": date_range("1990-1-1", periods=10),
            "timedelta": pd.timedelta_range(1, freq="s", periods=10),
            "string": strings,
            "string_missing": strings_missing,
            "cat": Categorical(strings),
        },
    )
    return df


@pytest.fixture
def frame_mi(frame):
    frame.index = MultiIndex.from_product([range(5), range(2)])
    return frame


@pytest.mark.slow
@pytest.mark.parametrize(
    "op, args, targop",
    [
        ("cumprod", (), lambda x: x.cumprod()),
        ("cumsum", (), lambda x: x.cumsum()),
        ("shift", (-1,), lambda x: x.shift(-1)),
        ("shift", (1,), lambda x: x.shift()),
    ],
)
@pytest.mark.parametrize("df_fix", ["frame", "frame_mi"])
@pytest.mark.parametrize(
    "gb_target",
    [
        {"by": np.random.default_rng(2).integers(0, 50, size=10).astype(float)},
        {"level": 0},
        {"by": "string"},
        pytest.param({"by": "string_missing"}, marks=pytest.mark.xfail),
        {"by": ["int", "string"]},
    ],
)
def test_cython_transform_frame(request, op, args, targop, df_fix, gb_target):
    df = request.getfixturevalue(df_fix)
    gb = df.groupby(group_keys=False, **gb_target)

    if op != "shift" and "int" not in gb_target:
        # numeric apply fastpath promotes dtype so have
        # to apply separately and concat
        i = gb[["int"]].apply(targop)
        f = gb[["float", "float_missing"]].apply(targop)
        expected = concat([f, i], axis=1)
    else:
        if op != "shift" or not isinstance(gb_target.get("by"), (str, list)):
            warn = None
        else:
            warn = FutureWarning
        msg = "DataFrameGroupBy.apply operated on the grouping columns"
        with tm.assert_produces_warning(warn, match=msg):
            expected = gb.apply(targop)

    expected = expected.sort_index(axis=1)
    if op == "shift":
        depr_msg = "The 'downcast' keyword in fillna is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            expected["string_missing"] = expected["string_missing"].fillna(
                np.nan, downcast=False
            )
            expected["string"] = expected["string"].fillna(np.nan, downcast=False)

    result = gb[expected.columns].transform(op, *args).sort_index(axis=1)
    tm.assert_frame_equal(result, expected)
    result = getattr(gb[expected.columns], op)(*args).sort_index(axis=1)
    tm.assert_frame_equal(result, expected)


@pytest.mark.slow
@pytest.mark.parametrize(
    "op, args, targop",
    [
        ("cumprod", (), lambda x: x.cumprod()),
        ("cumsum", (), lambda x: x.cumsum()),
        ("shift", (-1,), lambda x: x.shift(-1)),
        ("shift", (1,), lambda x: x.shift()),
    ],
)
@pytest.mark.parametrize("df_fix", ["frame", "frame_mi"])
@pytest.mark.parametrize(
    "gb_target",
    [
        {"by": np.random.default_rng(2).integers(0, 50, size=10).astype(float)},
        {"level": 0},
        {"by": "string"},
        # TODO: create xfail condition given other params
        # {"by": 'string_missing'},
        {"by": ["int", "string"]},
    ],
)
@pytest.mark.parametrize(
    "column",
    [
        "float",
        "float_missing",
        "int",
        "datetime",
        "timedelta",
        "string",
        "string_missing",
    ],
)
def test_cython_transform_frame_column(
    request, op, args, targop, df_fix, gb_target, column
):
    df = request.getfixturevalue(df_fix)
    gb = df.groupby(group_keys=False, **gb_target)
    c = column
    if (
        c not in ["float", "int", "float_missing"]
        and op != "shift"
        and not (c == "timedelta" and op == "cumsum")
    ):
        msg = "|".join(
            [
                "does not support .* operations",
                ".* is not supported for object dtype",
                "is not implemented for this dtype",
                ".* is not supported for str dtype",
                "dtype 'str' does not support operation '.*'",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            gb[c].transform(op)
        with pytest.raises(TypeError, match=msg):
            getattr(gb[c], op)()
    else:
        expected = gb[c].apply(targop)
        expected.name = c
        if c in ["string_missing", "string"]:
            depr_msg = "The 'downcast' keyword in fillna is deprecated"
            with tm.assert_produces_warning(FutureWarning, match=depr_msg):
                expected = expected.fillna(np.nan, downcast=False)

        res = gb[c].transform(op, *args)
        tm.assert_series_equal(expected, res)
        res2 = getattr(gb[c], op)(*args)
        tm.assert_series_equal(expected, res2)


def test_transform_with_non_scalar_group():
    # GH 10165
    cols = MultiIndex.from_tuples(
        [
            ("syn", "A"),
            ("foo", "A"),
            ("non", "A"),
            ("syn", "C"),
            ("foo", "C"),
            ("non", "C"),
            ("syn", "T"),
            ("foo", "T"),
            ("non", "T"),
            ("syn", "G"),
            ("foo", "G"),
            ("non", "G"),
        ]
    )
    df = DataFrame(
        np.random.default_rng(2).integers(1, 10, (4, 12)),
        columns=cols,
        index=["A", "C", "G", "T"],
    )

    msg = "DataFrame.groupby with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        gb = df.groupby(axis=1, level=1)
    msg = "transform must return a scalar value for each group.*"
    with pytest.raises(ValueError, match=msg):
        gb.transform(lambda z: z.div(z.sum(axis=1), axis=0))


@pytest.mark.parametrize(
    "cols,expected",
    [
        ("a", Series([1, 1, 1], name="a")),
        (
            ["a", "c"],
            DataFrame({"a": [1, 1, 1], "c": [1, 1, 1]}),
        ),
    ],
)
@pytest.mark.parametrize("agg_func", ["count", "rank", "size"])
def test_transform_numeric_ret(cols, expected, agg_func):
    # GH#19200 and GH#27469
    df = DataFrame(
        {"a": date_range("2018-01-01", periods=3), "b": range(3), "c": range(7, 10)}
    )
    result = df.groupby("b")[cols].transform(agg_func)

    if agg_func == "rank":
        expected = expected.astype("float")
    elif agg_func == "size" and cols == ["a", "c"]:
        # transform("size") returns a Series
        expected = expected["a"].rename(None)
    tm.assert_equal(result, expected)


def test_transform_ffill():
    # GH 24211
    data = [["a", 0.0], ["a", float("nan")], ["b", 1.0], ["b", float("nan")]]
    df = DataFrame(data, columns=["key", "values"])
    result = df.groupby("key").transform("ffill")
    expected = DataFrame({"values": [0.0, 0.0, 1.0, 1.0]})
    tm.assert_frame_equal(result, expected)
    result = df.groupby("key")["values"].transform("ffill")
    expected = Series([0.0, 0.0, 1.0, 1.0], name="values")
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("mix_groupings", [True, False])
@pytest.mark.parametrize("as_series", [True, False])
@pytest.mark.parametrize("val1,val2", [("foo", "bar"), (1, 2), (1.0, 2.0)])
@pytest.mark.parametrize(
    "fill_method,limit,exp_vals",
    [
        (
            "ffill",
            None,
            [np.nan, np.nan, "val1", "val1", "val1", "val2", "val2", "val2"],
        ),
        ("ffill", 1, [np.nan, np.nan, "val1", "val1", np.nan, "val2", "val2", np.nan]),
        (
            "bfill",
            None,
            ["val1", "val1", "val1", "val2", "val2", "val2", np.nan, np.nan],
        ),
        ("bfill", 1, [np.nan, "val1", "val1", np.nan, "val2", "val2", np.nan, np.nan]),
    ],
)
def test_group_fill_methods(
    mix_groupings, as_series, val1, val2, fill_method, limit, exp_vals
):
    vals = [np.nan, np.nan, val1, np.nan, np.nan, val2, np.nan, np.nan]
    _exp_vals = list(exp_vals)
    # Overwrite placeholder values
    for index, exp_val in enumerate(_exp_vals):
        if exp_val == "val1":
            _exp_vals[index] = val1
        elif exp_val == "val2":
            _exp_vals[index] = val2

    # Need to modify values and expectations depending on the
    # Series / DataFrame that we ultimately want to generate
    if mix_groupings:  # ['a', 'b', 'a, 'b', ...]
        keys = ["a", "b"] * len(vals)

        def interweave(list_obj):
            temp = []
            for x in list_obj:
                temp.extend([x, x])

            return temp

        _exp_vals = interweave(_exp_vals)
        vals = interweave(vals)
    else:  # ['a', 'a', 'a', ... 'b', 'b', 'b']
        keys = ["a"] * len(vals) + ["b"] * len(vals)
        _exp_vals = _exp_vals * 2
        vals = vals * 2

    df = DataFrame({"key": keys, "val": vals})
    if as_series:
        result = getattr(df.groupby("key")["val"], fill_method)(limit=limit)
        exp = Series(_exp_vals, name="val")
        tm.assert_series_equal(result, exp)
    else:
        result = getattr(df.groupby("key"), fill_method)(limit=limit)
        exp = DataFrame({"val": _exp_vals})
        tm.assert_frame_equal(result, exp)


@pytest.mark.parametrize("fill_method", ["ffill", "bfill"])
def test_pad_stable_sorting(fill_method):
    # GH 21207
    x = [0] * 20
    y = [np.nan] * 10 + [1] * 10

    if fill_method == "bfill":
        y = y[::-1]

    df = DataFrame({"x": x, "y": y})
    expected = df.drop("x", axis=1)

    result = getattr(df.groupby("x"), fill_method)()

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "freq",
    [
        None,
        pytest.param(
            "D",
            marks=pytest.mark.xfail(
                reason="GH#23918 before method uses freq in vectorized approach"
            ),
        ),
    ],
)
@pytest.mark.parametrize("periods", [1, -1])
@pytest.mark.parametrize("fill_method", ["ffill", "bfill", None])
@pytest.mark.parametrize("limit", [None, 1])
def test_pct_change(frame_or_series, freq, periods, fill_method, limit):
    # GH 21200, 21621, 30463
    vals = [3, np.nan, np.nan, np.nan, 1, 2, 4, 10, np.nan, 4]
    keys = ["a", "b"]
    key_v = np.repeat(keys, len(vals))
    df = DataFrame({"key": key_v, "vals": vals * 2})

    df_g = df
    if fill_method is not None:
        df_g = getattr(df.groupby("key"), fill_method)(limit=limit)
    grp = df_g.groupby(df.key)

    expected = grp["vals"].obj / grp["vals"].shift(periods) - 1

    gb = df.groupby("key")

    if frame_or_series is Series:
        gb = gb["vals"]
    else:
        expected = expected.to_frame("vals")

    msg = (
        "The 'fill_method' keyword being not None and the 'limit' keyword in "
        f"{type(gb).__name__}.pct_change are deprecated"
    )
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = gb.pct_change(
            periods=periods, fill_method=fill_method, limit=limit, freq=freq
        )
    tm.assert_equal(result, expected)


@pytest.mark.parametrize(
    "func, expected_status",
    [
        ("ffill", ["shrt", "shrt", "lng", np.nan, "shrt", "ntrl", "ntrl"]),
        ("bfill", ["shrt", "lng", "lng", "shrt", "shrt", "ntrl", np.nan]),
    ],
)
def test_ffill_bfill_non_unique_multilevel(func, expected_status):
    # GH 19437
    date = pd.to_datetime(
        [
            "2018-01-01",
            "2018-01-01",
            "2018-01-01",
            "2018-01-01",
            "2018-01-02",
            "2018-01-01",
            "2018-01-02",
        ]
    )
    symbol = ["MSFT", "MSFT", "MSFT", "AAPL", "AAPL", "TSLA", "TSLA"]
    status = ["shrt", np.nan, "lng", np.nan, "shrt", "ntrl", np.nan]

    df = DataFrame({"date": date, "symbol": symbol, "status": status})
    df = df.set_index(["date", "symbol"])
    result = getattr(df.groupby("symbol")["status"], func)()

    index = MultiIndex.from_tuples(
        tuples=list(zip(*[date, symbol])), names=["date", "symbol"]
    )
    expected = Series(expected_status, index=index, name="status")

    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("func", [np.any, np.all])
def test_any_all_np_func(func):
    # GH 20653
    df = DataFrame(
        [["foo", True], [np.nan, True], ["foo", True]], columns=["key", "val"]
    )

    exp = Series([True, np.nan, True], name="val")

    msg = "using SeriesGroupBy.[any|all]"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        res = df.groupby("key")["val"].transform(func)
    tm.assert_series_equal(res, exp)


def test_groupby_transform_rename():
    # https://github.com/pandas-dev/pandas/issues/23461
    def demean_rename(x):
        result = x - x.mean()

        if isinstance(x, Series):
            return result

        result = result.rename(columns={c: f"{c}_demeaned" for c in result.columns})

        return result

    df = DataFrame({"group": list("ababa"), "value": [1, 1, 1, 2, 2]})
    expected = DataFrame({"value": [-1.0 / 3, -0.5, -1.0 / 3, 0.5, 2.0 / 3]})

    result = df.groupby("group").transform(demean_rename)
    tm.assert_frame_equal(result, expected)
    result_single = df.groupby("group").value.transform(demean_rename)
    tm.assert_series_equal(result_single, expected["value"])


@pytest.mark.parametrize("func", [min, max, np.min, np.max, "first", "last"])
def test_groupby_transform_timezone_column(func):
    # GH 24198
    ts = pd.to_datetime("now", utc=True).tz_convert("Asia/Singapore")
    result = DataFrame({"end_time": [ts], "id": [1]})
    warn = FutureWarning if not isinstance(func, str) else None
    msg = "using SeriesGroupBy.[min|max]"
    with tm.assert_produces_warning(warn, match=msg):
        result["max_end_time"] = result.groupby("id").end_time.transform(func)
    expected = DataFrame([[ts, 1, ts]], columns=["end_time", "id", "max_end_time"])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "func, values",
    [
        ("idxmin", ["1/1/2011"] * 2 + ["1/3/2011"] * 7 + ["1/10/2011"]),
        ("idxmax", ["1/2/2011"] * 2 + ["1/9/2011"] * 7 + ["1/10/2011"]),
    ],
)
def test_groupby_transform_with_datetimes(func, values):
    # GH 15306
    dates = date_range("1/1/2011", periods=10, freq="D")

    stocks = DataFrame({"price": np.arange(10.0)}, index=dates)
    stocks["week_id"] = dates.isocalendar().week

    result = stocks.groupby(stocks["week_id"])["price"].transform(func)

    expected = Series(
        data=pd.to_datetime(values).as_unit("ns"), index=dates, name="price"
    )

    tm.assert_series_equal(result, expected)


def test_groupby_transform_dtype():
    # GH 22243
    df = DataFrame({"a": [1], "val": [1.35]})

    result = df["val"].transform(lambda x: x.map(lambda y: f"+{y}"))
    expected1 = Series(["+1.35"], name="val")
    tm.assert_series_equal(result, expected1)

    result = df.groupby("a")["val"].transform(lambda x: x.map(lambda y: f"+{y}"))
    tm.assert_series_equal(result, expected1)

    result = df.groupby("a")["val"].transform(lambda x: x.map(lambda y: f"+({y})"))
    expected2 = Series(["+(1.35)"], name="val")
    tm.assert_series_equal(result, expected2)

    df["val"] = df["val"].astype(object)
    result = df.groupby("a")["val"].transform(lambda x: x.map(lambda y: f"+{y}"))
    tm.assert_series_equal(result, expected1)


@pytest.mark.parametrize("func", ["cumsum", "cumprod", "cummin", "cummax"])
def test_transform_absent_categories(func):
    # GH 16771
    # cython transforms with more groups than rows
    x_vals = [1]
    x_cats = range(2)
    y = [1]
    df = DataFrame({"x": Categorical(x_vals, x_cats), "y": y})
    result = getattr(df.y.groupby(df.x, observed=False), func)()
    expected = df.y
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("func", ["ffill", "bfill", "shift"])
@pytest.mark.parametrize("key, val", [("level", 0), ("by", Series([0]))])
def test_ffill_not_in_axis(func, key, val):
    # GH 21521
    df = DataFrame([[np.nan]])
    result = getattr(df.groupby(**{key: val}), func)()
    expected = df

    tm.assert_frame_equal(result, expected)


def test_transform_invalid_name_raises():
    # GH#27486
    df = DataFrame({"a": [0, 1, 1, 2]})
    g = df.groupby(["a", "b", "b", "c"])
    with pytest.raises(ValueError, match="not a valid function name"):
        g.transform("some_arbitrary_name")

    # method exists on the object, but is not a valid transformation/agg
    assert hasattr(g, "aggregate")  # make sure the method exists
    with pytest.raises(ValueError, match="not a valid function name"):
        g.transform("aggregate")

    # Test SeriesGroupBy
    g = df["a"].groupby(["a", "b", "b", "c"])
    with pytest.raises(ValueError, match="not a valid function name"):
        g.transform("some_arbitrary_name")


def test_transform_agg_by_name(request, reduction_func, frame_or_series):
    func = reduction_func

    obj = DataFrame(
        {"a": [0, 0, 0, 1, 1, 1], "b": range(6)},
        index=["A", "B", "C", "D", "E", "F"],
    )
    if frame_or_series is Series:
        obj = obj["a"]

    g = obj.groupby(np.repeat([0, 1], 3))

    if func == "corrwith" and isinstance(obj, Series):  # GH#32293
        # TODO: implement SeriesGroupBy.corrwith
        assert not hasattr(g, func)
        return

    args = get_groupby_method_args(reduction_func, obj)
    result = g.transform(func, *args)

    # this is the *definition* of a transformation
    tm.assert_index_equal(result.index, obj.index)

    if func not in ("ngroup", "size") and obj.ndim == 2:
        # size/ngroup return a Series, unlike other transforms
        tm.assert_index_equal(result.columns, obj.columns)

    # verify that values were broadcasted across each group
    assert len(set(DataFrame(result).iloc[-3:, -1])) == 1


def test_transform_lambda_with_datetimetz():
    # GH 27496
    df = DataFrame(
        {
            "time": [
                Timestamp("2010-07-15 03:14:45"),
                Timestamp("2010-11-19 18:47:06"),
            ],
            "timezone": ["Etc/GMT+4", "US/Eastern"],
        }
    )
    result = df.groupby(["timezone"])["time"].transform(
        lambda x: x.dt.tz_localize(x.name)
    )
    expected = Series(
        [
            Timestamp("2010-07-15 03:14:45", tz="Etc/GMT+4"),
            Timestamp("2010-11-19 18:47:06", tz="US/Eastern"),
        ],
        name="time",
    )
    tm.assert_series_equal(result, expected)


def test_transform_fastpath_raises():
    # GH#29631 case where fastpath defined in groupby.generic _choose_path
    #  raises, but slow_path does not

    df = DataFrame({"A": [1, 1, 2, 2], "B": [1, -1, 1, 2]})
    gb = df.groupby("A")

    def func(grp):
        # we want a function such that func(frame) fails but func.apply(frame)
        #  works
        if grp.ndim == 2:
            # Ensure that fast_path fails
            raise NotImplementedError("Don't cross the streams")
        return grp * 2

    # Check that the fastpath raises, see _transform_general
    obj = gb._obj_with_exclusions
    gen = gb._grouper.get_iterator(obj, axis=gb.axis)
    fast_path, slow_path = gb._define_paths(func)
    _, group = next(gen)

    with pytest.raises(NotImplementedError, match="Don't cross the streams"):
        fast_path(group)

    result = gb.transform(func)

    expected = DataFrame([2, -2, 2, 4], columns=["B"])
    tm.assert_frame_equal(result, expected)


def test_transform_lambda_indexing():
    # GH 7883
    df = DataFrame(
        {
            "A": ["foo", "bar", "foo", "bar", "foo", "flux", "foo", "flux"],
            "B": ["one", "one", "two", "three", "two", "six", "five", "three"],
            "C": range(8),
            "D": range(8),
            "E": range(8),
        }
    )
    df = df.set_index(["A", "B"])
    df = df.sort_index()
    result = df.groupby(level="A").transform(lambda x: x.iloc[-1])
    expected = DataFrame(
        {
            "C": [3, 3, 7, 7, 4, 4, 4, 4],
            "D": [3, 3, 7, 7, 4, 4, 4, 4],
            "E": [3, 3, 7, 7, 4, 4, 4, 4],
        },
        index=MultiIndex.from_tuples(
            [
                ("bar", "one"),
                ("bar", "three"),
                ("flux", "six"),
                ("flux", "three"),
                ("foo", "five"),
                ("foo", "one"),
                ("foo", "two"),
                ("foo", "two"),
            ],
            names=["A", "B"],
        ),
    )
    tm.assert_frame_equal(result, expected)


def test_categorical_and_not_categorical_key(observed):
    # Checks that groupby-transform, when grouping by both a categorical
    # and a non-categorical key, doesn't try to expand the output to include
    # non-observed categories but instead matches the input shape.
    # GH 32494
    df_with_categorical = DataFrame(
        {
            "A": Categorical(["a", "b", "a"], categories=["a", "b", "c"]),
            "B": [1, 2, 3],
            "C": ["a", "b", "a"],
        }
    )
    df_without_categorical = DataFrame(
        {"A": ["a", "b", "a"], "B": [1, 2, 3], "C": ["a", "b", "a"]}
    )

    # DataFrame case
    result = df_with_categorical.groupby(["A", "C"], observed=observed).transform("sum")
    expected = df_without_categorical.groupby(["A", "C"]).transform("sum")
    tm.assert_frame_equal(result, expected)
    expected_explicit = DataFrame({"B": [4, 2, 4]})
    tm.assert_frame_equal(result, expected_explicit)

    # Series case
    result = df_with_categorical.groupby(["A", "C"], observed=observed)["B"].transform(
        "sum"
    )
    expected = df_without_categorical.groupby(["A", "C"])["B"].transform("sum")
    tm.assert_series_equal(result, expected)
    expected_explicit = Series([4, 2, 4], name="B")
    tm.assert_series_equal(result, expected_explicit)


def test_string_rank_grouping():
    # GH 19354
    df = DataFrame({"A": [1, 1, 2], "B": [1, 2, 3]})
    result = df.groupby("A").transform("rank")
    expected = DataFrame({"B": [1.0, 2.0, 1.0]})
    tm.assert_frame_equal(result, expected)


def test_transform_cumcount():
    # GH 27472
    df = DataFrame({"a": [0, 0, 0, 1, 1, 1], "b": range(6)})
    grp = df.groupby(np.repeat([0, 1], 3))

    result = grp.cumcount()
    expected = Series([0, 1, 2, 0, 1, 2])
    tm.assert_series_equal(result, expected)

    result = grp.transform("cumcount")
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("keys", [["A1"], ["A1", "A2"]])
def test_null_group_lambda_self(sort, dropna, keys):
    # GH 17093
    size = 50
    nulls1 = np.random.default_rng(2).choice([False, True], size)
    nulls2 = np.random.default_rng(2).choice([False, True], size)
    # Whether a group contains a null value or not
    nulls_grouper = nulls1 if len(keys) == 1 else nulls1 | nulls2

    a1 = np.random.default_rng(2).integers(0, 5, size=size).astype(float)
    a1[nulls1] = np.nan
    a2 = np.random.default_rng(2).integers(0, 5, size=size).astype(float)
    a2[nulls2] = np.nan
    values = np.random.default_rng(2).integers(0, 5, size=a1.shape)
    df = DataFrame({"A1": a1, "A2": a2, "B": values})

    expected_values = values
    if dropna and nulls_grouper.any():
        expected_values = expected_values.astype(float)
        expected_values[nulls_grouper] = np.nan
    expected = DataFrame(expected_values, columns=["B"])

    gb = df.groupby(keys, dropna=dropna, sort=sort)
    result = gb[["B"]].transform(lambda x: x)
    tm.assert_frame_equal(result, expected)


def test_null_group_str_reducer(request, dropna, reduction_func):
    # GH 17093
    if reduction_func == "corrwith":
        msg = "incorrectly raises"
        request.applymarker(pytest.mark.xfail(reason=msg))

    index = [1, 2, 3, 4]  # test transform preserves non-standard index
    df = DataFrame({"A": [1, 1, np.nan, np.nan], "B": [1, 2, 2, 3]}, index=index)
    gb = df.groupby("A", dropna=dropna)

    args = get_groupby_method_args(reduction_func, df)

    # Manually handle reducers that don't fit the generic pattern
    # Set expected with dropna=False, then replace if necessary
    if reduction_func == "first":
        expected = DataFrame({"B": [1, 1, 2, 2]}, index=index)
    elif reduction_func == "last":
        expected = DataFrame({"B": [2, 2, 3, 3]}, index=index)
    elif reduction_func == "nth":
        expected = DataFrame({"B": [1, 1, 2, 2]}, index=index)
    elif reduction_func == "size":
        expected = Series([2, 2, 2, 2], index=index)
    elif reduction_func == "corrwith":
        expected = DataFrame({"B": [1.0, 1.0, 1.0, 1.0]}, index=index)
    else:
        expected_gb = df.groupby("A", dropna=False)
        buffer = []
        for idx, group in expected_gb:
            res = getattr(group["B"], reduction_func)()
            buffer.append(Series(res, index=group.index))
        expected = concat(buffer).to_frame("B")
    if dropna:
        dtype = object if reduction_func in ("any", "all") else float
        expected = expected.astype(dtype)
        if expected.ndim == 2:
            expected.iloc[[2, 3], 0] = np.nan
        else:
            expected.iloc[[2, 3]] = np.nan

    result = gb.transform(reduction_func, *args)
    tm.assert_equal(result, expected)


def test_null_group_str_transformer(request, dropna, transformation_func):
    # GH 17093
    df = DataFrame({"A": [1, 1, np.nan], "B": [1, 2, 2]}, index=[1, 2, 3])
    args = get_groupby_method_args(transformation_func, df)
    gb = df.groupby("A", dropna=dropna)

    buffer = []
    for k, (idx, group) in enumerate(gb):
        if transformation_func == "cumcount":
            # DataFrame has no cumcount method
            res = DataFrame({"B": range(len(group))}, index=group.index)
        elif transformation_func == "ngroup":
            res = DataFrame(len(group) * [k], index=group.index, columns=["B"])
        else:
            res = getattr(group[["B"]], transformation_func)(*args)
        buffer.append(res)
    if dropna:
        dtype = object if transformation_func in ("any", "all") else None
        buffer.append(DataFrame([[np.nan]], index=[3], dtype=dtype, columns=["B"]))
    expected = concat(buffer)

    if transformation_func in ("cumcount", "ngroup"):
        # ngroup/cumcount always returns a Series as it counts the groups, not values
        expected = expected["B"].rename(None)

    if transformation_func == "pct_change" and not dropna:
        warn = FutureWarning
        msg = (
            "The default fill_method='ffill' in DataFrameGroupBy.pct_change "
            "is deprecated"
        )
    elif transformation_func == "fillna":
        warn = FutureWarning
        msg = "DataFrameGroupBy.fillna is deprecated"
    else:
        warn = None
        msg = ""
    with tm.assert_produces_warning(warn, match=msg):
        result = gb.transform(transformation_func, *args)

    tm.assert_equal(result, expected)


def test_null_group_str_reducer_series(request, dropna, reduction_func):
    # GH 17093
    index = [1, 2, 3, 4]  # test transform preserves non-standard index
    ser = Series([1, 2, 2, 3], index=index)
    gb = ser.groupby([1, 1, np.nan, np.nan], dropna=dropna)

    if reduction_func == "corrwith":
        # corrwith not implemented for SeriesGroupBy
        assert not hasattr(gb, reduction_func)
        return

    args = get_groupby_method_args(reduction_func, ser)

    # Manually handle reducers that don't fit the generic pattern
    # Set expected with dropna=False, then replace if necessary
    if reduction_func == "first":
        expected = Series([1, 1, 2, 2], index=index)
    elif reduction_func == "last":
        expected = Series([2, 2, 3, 3], index=index)
    elif reduction_func == "nth":
        expected = Series([1, 1, 2, 2], index=index)
    elif reduction_func == "size":
        expected = Series([2, 2, 2, 2], index=index)
    elif reduction_func == "corrwith":
        expected = Series([1, 1, 2, 2], index=index)
    else:
        expected_gb = ser.groupby([1, 1, np.nan, np.nan], dropna=False)
        buffer = []
        for idx, group in expected_gb:
            res = getattr(group, reduction_func)()
            buffer.append(Series(res, index=group.index))
        expected = concat(buffer)
    if dropna:
        dtype = object if reduction_func in ("any", "all") else float
        expected = expected.astype(dtype)
        expected.iloc[[2, 3]] = np.nan

    result = gb.transform(reduction_func, *args)
    tm.assert_series_equal(result, expected)


def test_null_group_str_transformer_series(dropna, transformation_func):
    # GH 17093
    ser = Series([1, 2, 2], index=[1, 2, 3])
    args = get_groupby_method_args(transformation_func, ser)
    gb = ser.groupby([1, 1, np.nan], dropna=dropna)

    buffer = []
    for k, (idx, group) in enumerate(gb):
        if transformation_func == "cumcount":
            # Series has no cumcount method
            res = Series(range(len(group)), index=group.index)
        elif transformation_func == "ngroup":
            res = Series(k, index=group.index)
        else:
            res = getattr(group, transformation_func)(*args)
        buffer.append(res)
    if dropna:
        dtype = object if transformation_func in ("any", "all") else None
        buffer.append(Series([np.nan], index=[3], dtype=dtype))
    expected = concat(buffer)

    warn = FutureWarning if transformation_func == "fillna" else None
    msg = "SeriesGroupBy.fillna is deprecated"
    with tm.assert_produces_warning(warn, match=msg):
        result = gb.transform(transformation_func, *args)

    tm.assert_equal(result, expected)


@pytest.mark.parametrize(
    "func, expected_values",
    [
        (Series.sort_values, [5, 4, 3, 2, 1]),
        (lambda x: x.head(1), [5.0, np.nan, 3, 2, np.nan]),
    ],
)
@pytest.mark.parametrize("keys", [["a1"], ["a1", "a2"]])
@pytest.mark.parametrize("keys_in_index", [True, False])
def test_transform_aligns(func, frame_or_series, expected_values, keys, keys_in_index):
    # GH#45648 - transform should align with the input's index
    df = DataFrame({"a1": [1, 1, 3, 2, 2], "b": [5, 4, 3, 2, 1]})
    if "a2" in keys:
        df["a2"] = df["a1"]
    if keys_in_index:
        df = df.set_index(keys, append=True)

    gb = df.groupby(keys)
    if frame_or_series is Series:
        gb = gb["b"]

    result = gb.transform(func)
    expected = DataFrame({"b": expected_values}, index=df.index)
    if frame_or_series is Series:
        expected = expected["b"]
    tm.assert_equal(result, expected)


@pytest.mark.parametrize("keys", ["A", ["A", "B"]])
def test_as_index_no_change(keys, df, groupby_func):
    # GH#49834 - as_index should have no impact on DataFrameGroupBy.transform
    if keys == "A":
        # Column B is string dtype; will fail on some ops
        df = df.drop(columns="B")
    args = get_groupby_method_args(groupby_func, df)
    gb_as_index_true = df.groupby(keys, as_index=True)
    gb_as_index_false = df.groupby(keys, as_index=False)
    warn = FutureWarning if groupby_func == "fillna" else None
    msg = "DataFrameGroupBy.fillna is deprecated"
    with tm.assert_produces_warning(warn, match=msg):
        result = gb_as_index_true.transform(groupby_func, *args)
    with tm.assert_produces_warning(warn, match=msg):
        expected = gb_as_index_false.transform(groupby_func, *args)
    tm.assert_equal(result, expected)


@pytest.mark.parametrize("how", ["idxmax", "idxmin"])
@pytest.mark.parametrize("numeric_only", [True, False])
def test_idxmin_idxmax_transform_args(how, skipna, numeric_only):
    # GH#55268 - ensure *args are passed through when calling transform
    df = DataFrame({"a": [1, 1, 1, 2], "b": [3.0, 4.0, np.nan, 6.0], "c": list("abcd")})
    gb = df.groupby("a")
    msg = f"'axis' keyword in DataFrameGroupBy.{how} is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = gb.transform(how, 0, skipna, numeric_only)
    warn = None if skipna else FutureWarning
    msg = f"The behavior of DataFrameGroupBy.{how} with .* any-NA and skipna=False"
    with tm.assert_produces_warning(warn, match=msg):
        expected = gb.transform(how, skipna=skipna, numeric_only=numeric_only)
    tm.assert_frame_equal(result, expected)
