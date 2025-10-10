import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Series,
    Timestamp,
    date_range,
)
import pandas._testing as tm


def test_apply_describe_bug(multiindex_dataframe_random_data):
    grouped = multiindex_dataframe_random_data.groupby(level="first")
    grouped.describe()  # it works!


def test_series_describe_multikey():
    ts = Series(
        np.arange(10, dtype=np.float64), index=date_range("2020-01-01", periods=10)
    )
    grouped = ts.groupby([lambda x: x.year, lambda x: x.month])
    result = grouped.describe()
    tm.assert_series_equal(result["mean"], grouped.mean(), check_names=False)
    tm.assert_series_equal(result["std"], grouped.std(), check_names=False)
    tm.assert_series_equal(result["min"], grouped.min(), check_names=False)


def test_series_describe_single():
    ts = Series(
        np.arange(10, dtype=np.float64), index=date_range("2020-01-01", periods=10)
    )
    grouped = ts.groupby(lambda x: x.month)
    result = grouped.apply(lambda x: x.describe())
    expected = grouped.describe().stack(future_stack=True)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("keys", ["key1", ["key1", "key2"]])
def test_series_describe_as_index(as_index, keys):
    # GH#49256
    df = DataFrame(
        {
            "key1": ["one", "two", "two", "three", "two"],
            "key2": ["one", "two", "two", "three", "two"],
            "foo2": [1, 2, 4, 4, 6],
        }
    )
    gb = df.groupby(keys, as_index=as_index)["foo2"]
    result = gb.describe()
    expected = DataFrame(
        {
            "key1": ["one", "three", "two"],
            "count": [1.0, 1.0, 3.0],
            "mean": [1.0, 4.0, 4.0],
            "std": [np.nan, np.nan, 2.0],
            "min": [1.0, 4.0, 2.0],
            "25%": [1.0, 4.0, 3.0],
            "50%": [1.0, 4.0, 4.0],
            "75%": [1.0, 4.0, 5.0],
            "max": [1.0, 4.0, 6.0],
        }
    )
    if len(keys) == 2:
        expected.insert(1, "key2", expected["key1"])
    if as_index:
        expected = expected.set_index(keys)
    tm.assert_frame_equal(result, expected)


def test_frame_describe_multikey(tsframe, using_infer_string):
    grouped = tsframe.groupby([lambda x: x.year, lambda x: x.month])
    result = grouped.describe()
    desc_groups = []
    for col in tsframe:
        group = grouped[col].describe()
        # GH 17464 - Remove duplicate MultiIndex levels
        group_col = MultiIndex(
            levels=[Index([col], dtype=tsframe.columns.dtype), group.columns],
            codes=[[0] * len(group.columns), range(len(group.columns))],
        )
        group = DataFrame(group.values, columns=group_col, index=group.index)
        desc_groups.append(group)
    expected = pd.concat(desc_groups, axis=1)
    tm.assert_frame_equal(result, expected)

    # remainder of the tests fails with string dtype but is testing deprecated behaviour
    if using_infer_string:
        return

    msg = "DataFrame.groupby with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        groupedT = tsframe.groupby({"A": 0, "B": 0, "C": 1, "D": 1}, axis=1)
    result = groupedT.describe()
    expected = tsframe.describe().T
    # reverting the change from https://github.com/pandas-dev/pandas/pull/35441/
    expected.index = MultiIndex(
        levels=[[0, 1], expected.index],
        codes=[[0, 0, 1, 1], range(len(expected.index))],
    )
    tm.assert_frame_equal(result, expected)


def test_frame_describe_tupleindex():
    # GH 14848 - regression from 0.19.0 to 0.19.1
    df1 = DataFrame(
        {
            "x": [1, 2, 3, 4, 5] * 3,
            "y": [10, 20, 30, 40, 50] * 3,
            "z": [100, 200, 300, 400, 500] * 3,
        }
    )
    df1["k"] = [(0, 0, 1), (0, 1, 0), (1, 0, 0)] * 5
    df2 = df1.rename(columns={"k": "key"})
    msg = "Names should be list-like for a MultiIndex"
    with pytest.raises(ValueError, match=msg):
        df1.groupby("k").describe()
    with pytest.raises(ValueError, match=msg):
        df2.groupby("key").describe()


def test_frame_describe_unstacked_format():
    # GH 4792
    prices = {
        Timestamp("2011-01-06 10:59:05", tz=None): 24990,
        Timestamp("2011-01-06 12:43:33", tz=None): 25499,
        Timestamp("2011-01-06 12:54:09", tz=None): 25499,
    }
    volumes = {
        Timestamp("2011-01-06 10:59:05", tz=None): 1500000000,
        Timestamp("2011-01-06 12:43:33", tz=None): 5000000000,
        Timestamp("2011-01-06 12:54:09", tz=None): 100000000,
    }
    df = DataFrame({"PRICE": prices, "VOLUME": volumes})
    result = df.groupby("PRICE").VOLUME.describe()
    data = [
        df[df.PRICE == 24990].VOLUME.describe().values.tolist(),
        df[df.PRICE == 25499].VOLUME.describe().values.tolist(),
    ]
    expected = DataFrame(
        data,
        index=Index([24990, 25499], name="PRICE"),
        columns=["count", "mean", "std", "min", "25%", "50%", "75%", "max"],
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.filterwarnings(
    "ignore:"
    "indexing past lexsort depth may impact performance:"
    "pandas.errors.PerformanceWarning"
)
@pytest.mark.parametrize("as_index", [True, False])
@pytest.mark.parametrize("keys", [["a1"], ["a1", "a2"]])
def test_describe_with_duplicate_output_column_names(as_index, keys):
    # GH 35314
    df = DataFrame(
        {
            "a1": [99, 99, 99, 88, 88, 88],
            "a2": [99, 99, 99, 88, 88, 88],
            "b": [1, 2, 3, 4, 5, 6],
            "c": [10, 20, 30, 40, 50, 60],
        },
        columns=["a1", "a2", "b", "b"],
        copy=False,
    )
    if keys == ["a1"]:
        df = df.drop(columns="a2")

    expected = (
        DataFrame.from_records(
            [
                ("b", "count", 3.0, 3.0),
                ("b", "mean", 5.0, 2.0),
                ("b", "std", 1.0, 1.0),
                ("b", "min", 4.0, 1.0),
                ("b", "25%", 4.5, 1.5),
                ("b", "50%", 5.0, 2.0),
                ("b", "75%", 5.5, 2.5),
                ("b", "max", 6.0, 3.0),
                ("b", "count", 3.0, 3.0),
                ("b", "mean", 5.0, 2.0),
                ("b", "std", 1.0, 1.0),
                ("b", "min", 4.0, 1.0),
                ("b", "25%", 4.5, 1.5),
                ("b", "50%", 5.0, 2.0),
                ("b", "75%", 5.5, 2.5),
                ("b", "max", 6.0, 3.0),
            ],
        )
        .set_index([0, 1])
        .T
    )
    expected.columns.names = [None, None]
    if len(keys) == 2:
        expected.index = MultiIndex(
            levels=[[88, 99], [88, 99]], codes=[[0, 1], [0, 1]], names=["a1", "a2"]
        )
    else:
        expected.index = Index([88, 99], name="a1")

    if not as_index:
        expected = expected.reset_index()

    result = df.groupby(keys, as_index=as_index).describe()

    tm.assert_frame_equal(result, expected)


def test_describe_duplicate_columns():
    # GH#50806
    df = DataFrame([[0, 1, 2, 3]])
    df.columns = [0, 1, 2, 0]
    gb = df.groupby(df[1])
    result = gb.describe(percentiles=[])

    columns = ["count", "mean", "std", "min", "50%", "max"]
    frames = [
        DataFrame([[1.0, val, np.nan, val, val, val]], index=[1], columns=columns)
        for val in (0.0, 2.0, 3.0)
    ]
    expected = pd.concat(frames, axis=1)
    expected.columns = MultiIndex(
        levels=[[0, 2], columns],
        codes=[6 * [0] + 6 * [1] + 6 * [0], 3 * list(range(6))],
    )
    expected.index.names = [1]
    tm.assert_frame_equal(result, expected)


class TestGroupByNonCythonPaths:
    # GH#5610 non-cython calls should not include the grouper
    # Tests for code not expected to go through cython paths.

    @pytest.fixture
    def df(self):
        df = DataFrame(
            [[1, 2, "foo"], [1, np.nan, "bar"], [3, np.nan, "baz"]],
            columns=["A", "B", "C"],
        )
        return df

    @pytest.fixture
    def gb(self, df):
        gb = df.groupby("A")
        return gb

    @pytest.fixture
    def gni(self, df):
        gni = df.groupby("A", as_index=False)
        return gni

    def test_describe(self, df, gb, gni):
        # describe
        expected_index = Index([1, 3], name="A")
        expected_col = MultiIndex(
            levels=[["B"], ["count", "mean", "std", "min", "25%", "50%", "75%", "max"]],
            codes=[[0] * 8, list(range(8))],
        )
        expected = DataFrame(
            [
                [1.0, 2.0, np.nan, 2.0, 2.0, 2.0, 2.0, 2.0],
                [0.0, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan],
            ],
            index=expected_index,
            columns=expected_col,
        )
        result = gb.describe()
        tm.assert_frame_equal(result, expected)

        expected = expected.reset_index()
        result = gni.describe()
        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("dtype", [int, float, object])
@pytest.mark.parametrize(
    "kwargs",
    [
        {"percentiles": [0.10, 0.20, 0.30], "include": "all", "exclude": None},
        {"percentiles": [0.10, 0.20, 0.30], "include": None, "exclude": ["int"]},
        {"percentiles": [0.10, 0.20, 0.30], "include": ["int"], "exclude": None},
    ],
)
def test_groupby_empty_dataset(dtype, kwargs):
    # GH#41575
    df = DataFrame([[1, 2, 3]], columns=["A", "B", "C"], dtype=dtype)
    df["B"] = df["B"].astype(int)
    df["C"] = df["C"].astype(float)

    result = df.iloc[:0].groupby("A").describe(**kwargs)
    expected = df.groupby("A").describe(**kwargs).reset_index(drop=True).iloc[:0]
    tm.assert_frame_equal(result, expected)

    result = df.iloc[:0].groupby("A").B.describe(**kwargs)
    expected = df.groupby("A").B.describe(**kwargs).reset_index(drop=True).iloc[:0]
    expected.index = Index([], dtype=df.columns.dtype)
    tm.assert_frame_equal(result, expected)
