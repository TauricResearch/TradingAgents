"""
test cython .agg behavior
"""

import numpy as np
import pytest

from pandas.core.dtypes.common import (
    is_float_dtype,
    is_integer_dtype,
)

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    NaT,
    Series,
    Timedelta,
    Timestamp,
    bdate_range,
)
import pandas._testing as tm
import pandas.core.common as com


@pytest.mark.parametrize(
    "op_name",
    [
        "count",
        "sum",
        "std",
        "var",
        "sem",
        "mean",
        pytest.param(
            "median",
            # ignore mean of empty slice
            # and all-NaN
            marks=[pytest.mark.filterwarnings("ignore::RuntimeWarning")],
        ),
        "prod",
        "min",
        "max",
    ],
)
def test_cythonized_aggers(op_name):
    data = {
        "A": [0, 0, 0, 0, 1, 1, 1, 1, 1, 1.0, np.nan, np.nan],
        "B": ["A", "B"] * 6,
        "C": np.random.default_rng(2).standard_normal(12),
    }
    df = DataFrame(data)
    df.loc[2:10:2, "C"] = np.nan

    op = lambda x: getattr(x, op_name)()

    # single column
    grouped = df.drop(["B"], axis=1).groupby("A")
    exp = {cat: op(group["C"]) for cat, group in grouped}
    exp = DataFrame({"C": exp})
    exp.index.name = "A"
    result = op(grouped)
    tm.assert_frame_equal(result, exp)

    # multiple columns
    grouped = df.groupby(["A", "B"])
    expd = {}
    for (cat1, cat2), group in grouped:
        expd.setdefault(cat1, {})[cat2] = op(group["C"])
    exp = DataFrame(expd).T.stack(future_stack=True)
    exp.index.names = ["A", "B"]
    exp.name = "C"

    result = op(grouped)["C"]
    if op_name in ["sum", "prod"]:
        tm.assert_series_equal(result, exp)


def test_cython_agg_boolean():
    frame = DataFrame(
        {
            "a": np.random.default_rng(2).integers(0, 5, 50),
            "b": np.random.default_rng(2).integers(0, 2, 50).astype("bool"),
        }
    )
    result = frame.groupby("a")["b"].mean()
    msg = "using SeriesGroupBy.mean"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        # GH#53425
        expected = frame.groupby("a")["b"].agg(np.mean)

    tm.assert_series_equal(result, expected)


def test_cython_agg_nothing_to_agg():
    frame = DataFrame(
        {"a": np.random.default_rng(2).integers(0, 5, 50), "b": ["foo", "bar"] * 25}
    )

    msg = "Cannot use numeric_only=True with SeriesGroupBy.mean and non-numeric dtypes"
    with pytest.raises(TypeError, match=msg):
        frame.groupby("a")["b"].mean(numeric_only=True)

    frame = DataFrame(
        {"a": np.random.default_rng(2).integers(0, 5, 50), "b": ["foo", "bar"] * 25}
    )

    result = frame[["b"]].groupby(frame["a"]).mean(numeric_only=True)
    expected = DataFrame(
        [],
        index=frame["a"].sort_values().drop_duplicates(),
        columns=Index([], dtype="str"),
    )
    tm.assert_frame_equal(result, expected)


def test_cython_agg_nothing_to_agg_with_dates():
    frame = DataFrame(
        {
            "a": np.random.default_rng(2).integers(0, 5, 50),
            "b": ["foo", "bar"] * 25,
            "dates": pd.date_range("now", periods=50, freq="min"),
        }
    )
    msg = "Cannot use numeric_only=True with SeriesGroupBy.mean and non-numeric dtypes"
    with pytest.raises(TypeError, match=msg):
        frame.groupby("b").dates.mean(numeric_only=True)


def test_cython_agg_frame_columns():
    # #2113
    df = DataFrame({"x": [1, 2, 3], "y": [3, 4, 5]})

    msg = "DataFrame.groupby with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.groupby(level=0, axis="columns").mean()
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.groupby(level=0, axis="columns").mean()
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.groupby(level=0, axis="columns").mean()
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.groupby(level=0, axis="columns").mean()


def test_cython_agg_return_dict():
    # GH 16741
    df = DataFrame(
        {
            "A": ["foo", "bar", "foo", "bar", "foo", "bar", "foo", "foo"],
            "B": ["one", "one", "two", "three", "two", "two", "one", "three"],
            "C": np.random.default_rng(2).standard_normal(8),
            "D": np.random.default_rng(2).standard_normal(8),
        }
    )

    ts = df.groupby("A")["B"].agg(lambda x: x.value_counts().to_dict())
    expected = Series(
        [{"two": 1, "one": 1, "three": 1}, {"two": 2, "one": 2, "three": 1}],
        index=Index(["bar", "foo"], name="A"),
        name="B",
    )
    tm.assert_series_equal(ts, expected)


def test_cython_fail_agg():
    dr = bdate_range("1/1/2000", periods=50)
    ts = Series(["A", "B", "C", "D", "E"] * 10, dtype=object, index=dr)

    grouped = ts.groupby(lambda x: x.month)
    summed = grouped.sum()
    msg = "using SeriesGroupBy.sum"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        # GH#53425
        expected = grouped.agg(np.sum).astype(object)
    tm.assert_series_equal(summed, expected)


@pytest.mark.parametrize(
    "op, targop",
    [
        ("mean", np.mean),
        ("median", np.median),
        ("var", np.var),
        ("sum", np.sum),
        ("prod", np.prod),
        ("min", np.min),
        ("max", np.max),
        ("first", lambda x: x.iloc[0]),
        ("last", lambda x: x.iloc[-1]),
    ],
)
def test__cython_agg_general(op, targop):
    df = DataFrame(np.random.default_rng(2).standard_normal(1000))
    labels = np.random.default_rng(2).integers(0, 50, size=1000).astype(float)

    result = df.groupby(labels)._cython_agg_general(op, alt=None, numeric_only=True)
    warn = FutureWarning if targop in com._cython_table else None
    msg = f"using DataFrameGroupBy.{op}"
    with tm.assert_produces_warning(warn, match=msg):
        # GH#53425
        expected = df.groupby(labels).agg(targop)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "op, targop",
    [
        ("mean", np.mean),
        ("median", lambda x: np.median(x) if len(x) > 0 else np.nan),
        ("var", lambda x: np.var(x, ddof=1)),
        ("min", np.min),
        ("max", np.max),
    ],
)
def test_cython_agg_empty_buckets(op, targop, observed):
    df = DataFrame([11, 12, 13])
    grps = range(0, 55, 5)

    # calling _cython_agg_general directly, instead of via the user API
    # which sets different values for min_count, so do that here.
    g = df.groupby(pd.cut(df[0], grps), observed=observed)
    result = g._cython_agg_general(op, alt=None, numeric_only=True)

    g = df.groupby(pd.cut(df[0], grps), observed=observed)
    expected = g.agg(lambda x: targop(x))
    tm.assert_frame_equal(result, expected)


def test_cython_agg_empty_buckets_nanops(observed):
    # GH-18869 can't call nanops on empty groups, so hardcode expected
    # for these
    df = DataFrame([11, 12, 13], columns=["a"])
    grps = np.arange(0, 25, 5, dtype=int)
    # add / sum
    result = df.groupby(pd.cut(df["a"], grps), observed=observed)._cython_agg_general(
        "sum", alt=None, numeric_only=True
    )
    intervals = pd.interval_range(0, 20, freq=5)
    expected = DataFrame(
        {"a": [0, 0, 36, 0]},
        index=pd.CategoricalIndex(intervals, name="a", ordered=True),
    )
    if observed:
        expected = expected[expected.a != 0]

    tm.assert_frame_equal(result, expected)

    # prod
    result = df.groupby(pd.cut(df["a"], grps), observed=observed)._cython_agg_general(
        "prod", alt=None, numeric_only=True
    )
    expected = DataFrame(
        {"a": [1, 1, 1716, 1]},
        index=pd.CategoricalIndex(intervals, name="a", ordered=True),
    )
    if observed:
        expected = expected[expected.a != 1]

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("op", ["first", "last", "max", "min"])
@pytest.mark.parametrize(
    "data", [Timestamp("2016-10-14 21:00:44.557"), Timedelta("17088 days 21:00:44.557")]
)
def test_cython_with_timestamp_and_nat(op, data):
    # https://github.com/pandas-dev/pandas/issues/19526
    df = DataFrame({"a": [0, 1], "b": [data, NaT]})
    index = Index([0, 1], name="a")

    # We will group by a and test the cython aggregations
    expected = DataFrame({"b": [data, NaT]}, index=index)

    result = df.groupby("a").aggregate(op)
    tm.assert_frame_equal(expected, result)


@pytest.mark.parametrize(
    "agg",
    [
        "min",
        "max",
        "count",
        "sum",
        "prod",
        "var",
        "mean",
        "median",
        "ohlc",
        "cumprod",
        "cumsum",
        "shift",
        "any",
        "all",
        "quantile",
        "first",
        "last",
        "rank",
        "cummin",
        "cummax",
    ],
)
def test_read_only_buffer_source_agg(agg):
    # https://github.com/pandas-dev/pandas/issues/36014
    df = DataFrame(
        {
            "sepal_length": [5.1, 4.9, 4.7, 4.6, 5.0],
            "species": ["setosa", "setosa", "setosa", "setosa", "setosa"],
        }
    )
    df._mgr.arrays[0].flags.writeable = False

    result = df.groupby(["species"]).agg({"sepal_length": agg})
    expected = df.copy().groupby(["species"]).agg({"sepal_length": agg})

    tm.assert_equal(result, expected)


@pytest.mark.parametrize(
    "op_name",
    [
        "count",
        "sum",
        "std",
        "var",
        "sem",
        "mean",
        "median",
        "prod",
        "min",
        "max",
    ],
)
def test_cython_agg_nullable_int(op_name):
    # ensure that the cython-based aggregations don't fail for nullable dtype
    # (eg https://github.com/pandas-dev/pandas/issues/37415)
    df = DataFrame(
        {
            "A": ["A", "B"] * 5,
            "B": pd.array([1, 2, 3, 4, 5, 6, 7, 8, 9, pd.NA], dtype="Int64"),
        }
    )
    result = getattr(df.groupby("A")["B"], op_name)()
    df2 = df.assign(B=df["B"].astype("float64"))
    expected = getattr(df2.groupby("A")["B"], op_name)()
    if op_name in ("mean", "median"):
        convert_integer = False
    else:
        convert_integer = True
    expected = expected.convert_dtypes(convert_integer=convert_integer)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("dtype", ["Int64", "Float64", "boolean"])
def test_count_masked_returns_masked_dtype(dtype):
    df = DataFrame(
        {
            "A": [1, 1],
            "B": pd.array([1, pd.NA], dtype=dtype),
            "C": pd.array([1, 1], dtype=dtype),
        }
    )
    result = df.groupby("A").count()
    expected = DataFrame(
        [[1, 2]], index=Index([1], name="A"), columns=["B", "C"], dtype="Int64"
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("with_na", [True, False])
@pytest.mark.parametrize(
    "op_name, action",
    [
        # ("count", "always_int"),
        ("sum", "large_int"),
        # ("std", "always_float"),
        ("var", "always_float"),
        # ("sem", "always_float"),
        ("mean", "always_float"),
        ("median", "always_float"),
        ("prod", "large_int"),
        ("min", "preserve"),
        ("max", "preserve"),
        ("first", "preserve"),
        ("last", "preserve"),
    ],
)
@pytest.mark.parametrize(
    "data",
    [
        pd.array([1, 2, 3, 4], dtype="Int64"),
        pd.array([1, 2, 3, 4], dtype="Int8"),
        pd.array([0.1, 0.2, 0.3, 0.4], dtype="Float32"),
        pd.array([0.1, 0.2, 0.3, 0.4], dtype="Float64"),
        pd.array([True, True, False, False], dtype="boolean"),
    ],
)
def test_cython_agg_EA_known_dtypes(data, op_name, action, with_na):
    if with_na:
        data[3] = pd.NA

    df = DataFrame({"key": ["a", "a", "b", "b"], "col": data})
    grouped = df.groupby("key")

    if action == "always_int":
        # always Int64
        expected_dtype = pd.Int64Dtype()
    elif action == "large_int":
        # for any int/bool use Int64, for float preserve dtype
        if is_float_dtype(data.dtype):
            expected_dtype = data.dtype
        elif is_integer_dtype(data.dtype):
            # match the numpy dtype we'd get with the non-nullable analogue
            expected_dtype = data.dtype
        else:
            expected_dtype = pd.Int64Dtype()
    elif action == "always_float":
        # for any int/bool use Float64, for float preserve dtype
        if is_float_dtype(data.dtype):
            expected_dtype = data.dtype
        else:
            expected_dtype = pd.Float64Dtype()
    elif action == "preserve":
        expected_dtype = data.dtype

    result = getattr(grouped, op_name)()
    assert result["col"].dtype == expected_dtype

    result = grouped.aggregate(op_name)
    assert result["col"].dtype == expected_dtype

    result = getattr(grouped["col"], op_name)()
    assert result.dtype == expected_dtype

    result = grouped["col"].aggregate(op_name)
    assert result.dtype == expected_dtype
