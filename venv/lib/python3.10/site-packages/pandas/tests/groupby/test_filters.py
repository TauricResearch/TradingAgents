from string import ascii_lowercase

import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Series,
    Timestamp,
)
import pandas._testing as tm


def test_filter_series():
    s = Series([1, 3, 20, 5, 22, 24, 7])
    expected_odd = Series([1, 3, 5, 7], index=[0, 1, 3, 6])
    expected_even = Series([20, 22, 24], index=[2, 4, 5])
    grouper = s.apply(lambda x: x % 2)
    grouped = s.groupby(grouper)
    tm.assert_series_equal(grouped.filter(lambda x: x.mean() < 10), expected_odd)
    tm.assert_series_equal(grouped.filter(lambda x: x.mean() > 10), expected_even)
    # Test dropna=False.
    tm.assert_series_equal(
        grouped.filter(lambda x: x.mean() < 10, dropna=False),
        expected_odd.reindex(s.index),
    )
    tm.assert_series_equal(
        grouped.filter(lambda x: x.mean() > 10, dropna=False),
        expected_even.reindex(s.index),
    )


def test_filter_single_column_df():
    df = DataFrame([1, 3, 20, 5, 22, 24, 7])
    expected_odd = DataFrame([1, 3, 5, 7], index=[0, 1, 3, 6])
    expected_even = DataFrame([20, 22, 24], index=[2, 4, 5])
    grouper = df[0].apply(lambda x: x % 2)
    grouped = df.groupby(grouper)
    tm.assert_frame_equal(grouped.filter(lambda x: x.mean() < 10), expected_odd)
    tm.assert_frame_equal(grouped.filter(lambda x: x.mean() > 10), expected_even)
    # Test dropna=False.
    tm.assert_frame_equal(
        grouped.filter(lambda x: x.mean() < 10, dropna=False),
        expected_odd.reindex(df.index),
    )
    tm.assert_frame_equal(
        grouped.filter(lambda x: x.mean() > 10, dropna=False),
        expected_even.reindex(df.index),
    )


def test_filter_multi_column_df():
    df = DataFrame({"A": [1, 12, 12, 1], "B": [1, 1, 1, 1]})
    grouper = df["A"].apply(lambda x: x % 2)
    grouped = df.groupby(grouper)
    expected = DataFrame({"A": [12, 12], "B": [1, 1]}, index=[1, 2])
    tm.assert_frame_equal(
        grouped.filter(lambda x: x["A"].sum() - x["B"].sum() > 10), expected
    )


def test_filter_mixed_df():
    df = DataFrame({"A": [1, 12, 12, 1], "B": "a b c d".split()})
    grouper = df["A"].apply(lambda x: x % 2)
    grouped = df.groupby(grouper)
    expected = DataFrame({"A": [12, 12], "B": ["b", "c"]}, index=[1, 2])
    tm.assert_frame_equal(grouped.filter(lambda x: x["A"].sum() > 10), expected)


def test_filter_out_all_groups():
    s = Series([1, 3, 20, 5, 22, 24, 7])
    grouper = s.apply(lambda x: x % 2)
    grouped = s.groupby(grouper)
    tm.assert_series_equal(grouped.filter(lambda x: x.mean() > 1000), s[[]])
    df = DataFrame({"A": [1, 12, 12, 1], "B": "a b c d".split()})
    grouper = df["A"].apply(lambda x: x % 2)
    grouped = df.groupby(grouper)
    tm.assert_frame_equal(grouped.filter(lambda x: x["A"].sum() > 1000), df.loc[[]])


def test_filter_out_no_groups():
    s = Series([1, 3, 20, 5, 22, 24, 7])
    grouper = s.apply(lambda x: x % 2)
    grouped = s.groupby(grouper)
    filtered = grouped.filter(lambda x: x.mean() > 0)
    tm.assert_series_equal(filtered, s)
    df = DataFrame({"A": [1, 12, 12, 1], "B": "a b c d".split()})
    grouper = df["A"].apply(lambda x: x % 2)
    grouped = df.groupby(grouper)
    filtered = grouped.filter(lambda x: x["A"].mean() > 0)
    tm.assert_frame_equal(filtered, df)


def test_filter_out_all_groups_in_df():
    # GH12768
    df = DataFrame({"a": [1, 1, 2], "b": [1, 2, 0]})
    res = df.groupby("a")
    res = res.filter(lambda x: x["b"].sum() > 5, dropna=False)
    expected = DataFrame({"a": [np.nan] * 3, "b": [np.nan] * 3})
    tm.assert_frame_equal(expected, res)

    df = DataFrame({"a": [1, 1, 2], "b": [1, 2, 0]})
    res = df.groupby("a")
    res = res.filter(lambda x: x["b"].sum() > 5, dropna=True)
    expected = DataFrame({"a": [], "b": []}, dtype="int64")
    tm.assert_frame_equal(expected, res)


def test_filter_condition_raises():
    def raise_if_sum_is_zero(x):
        if x.sum() == 0:
            raise ValueError
        return x.sum() > 0

    s = Series([-1, 0, 1, 2])
    grouper = s.apply(lambda x: x % 2)
    grouped = s.groupby(grouper)
    msg = "the filter must return a boolean result"
    with pytest.raises(TypeError, match=msg):
        grouped.filter(raise_if_sum_is_zero)


def test_filter_with_axis_in_groupby():
    # issue 11041
    index = pd.MultiIndex.from_product([range(10), [0, 1]])
    data = DataFrame(np.arange(100).reshape(-1, 20), columns=index, dtype="int64")

    msg = "DataFrame.groupby with axis=1"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        gb = data.groupby(level=0, axis=1)
    result = gb.filter(lambda x: x.iloc[0, 0] > 10)
    expected = data.iloc[:, 12:20]
    tm.assert_frame_equal(result, expected)


def test_filter_bad_shapes():
    df = DataFrame({"A": np.arange(8), "B": list("aabbbbcc"), "C": np.arange(8)})
    s = df["B"]
    g_df = df.groupby("B")
    g_s = s.groupby(s)

    f = lambda x: x
    msg = "filter function returned a DataFrame, but expected a scalar bool"
    with pytest.raises(TypeError, match=msg):
        g_df.filter(f)
    msg = "the filter must return a boolean result"
    with pytest.raises(TypeError, match=msg):
        g_s.filter(f)

    f = lambda x: x == 1
    msg = "filter function returned a DataFrame, but expected a scalar bool"
    with pytest.raises(TypeError, match=msg):
        g_df.filter(f)
    msg = "the filter must return a boolean result"
    with pytest.raises(TypeError, match=msg):
        g_s.filter(f)

    f = lambda x: np.outer(x, x)
    msg = "can't multiply sequence by non-int of type 'str'"
    with pytest.raises(TypeError, match=msg):
        g_df.filter(f)
    msg = "the filter must return a boolean result"
    with pytest.raises(TypeError, match=msg):
        g_s.filter(f)


def test_filter_nan_is_false():
    df = DataFrame({"A": np.arange(8), "B": list("aabbbbcc"), "C": np.arange(8)})
    s = df["B"]
    g_df = df.groupby(df["B"])
    g_s = s.groupby(s)

    f = lambda x: np.nan
    tm.assert_frame_equal(g_df.filter(f), df.loc[[]])
    tm.assert_series_equal(g_s.filter(f), s[[]])


def test_filter_pdna_is_false():
    # in particular, dont raise in filter trying to call bool(pd.NA)
    df = DataFrame({"A": np.arange(8), "B": list("aabbbbcc"), "C": np.arange(8)})
    ser = df["B"]
    g_df = df.groupby(df["B"])
    g_s = ser.groupby(ser)

    func = lambda x: pd.NA
    res = g_df.filter(func)
    tm.assert_frame_equal(res, df.loc[[]])
    res = g_s.filter(func)
    tm.assert_series_equal(res, ser[[]])


def test_filter_against_workaround_ints():
    # Series of ints
    s = Series(np.random.default_rng(2).integers(0, 100, 100))
    grouper = s.apply(lambda x: np.round(x, -1))
    grouped = s.groupby(grouper)
    f = lambda x: x.mean() > 10

    old_way = s[grouped.transform(f).astype("bool")]
    new_way = grouped.filter(f)
    tm.assert_series_equal(new_way.sort_values(), old_way.sort_values())


def test_filter_against_workaround_floats():
    # Series of floats
    s = 100 * Series(np.random.default_rng(2).random(100))
    grouper = s.apply(lambda x: np.round(x, -1))
    grouped = s.groupby(grouper)
    f = lambda x: x.mean() > 10
    old_way = s[grouped.transform(f).astype("bool")]
    new_way = grouped.filter(f)
    tm.assert_series_equal(new_way.sort_values(), old_way.sort_values())


def test_filter_against_workaround_dataframe():
    # Set up DataFrame of ints, floats, strings.
    letters = np.array(list(ascii_lowercase))
    N = 100
    random_letters = letters.take(
        np.random.default_rng(2).integers(0, 26, N, dtype=int)
    )
    df = DataFrame(
        {
            "ints": Series(np.random.default_rng(2).integers(0, 100, N)),
            "floats": N / 10 * Series(np.random.default_rng(2).random(N)),
            "letters": Series(random_letters),
        }
    )

    # Group by ints; filter on floats.
    grouped = df.groupby("ints")
    old_way = df[grouped.floats.transform(lambda x: x.mean() > N / 20).astype("bool")]
    new_way = grouped.filter(lambda x: x["floats"].mean() > N / 20)
    tm.assert_frame_equal(new_way, old_way)

    # Group by floats (rounded); filter on strings.
    grouper = df.floats.apply(lambda x: np.round(x, -1))
    grouped = df.groupby(grouper)
    old_way = df[grouped.letters.transform(lambda x: len(x) < N / 10).astype("bool")]
    new_way = grouped.filter(lambda x: len(x.letters) < N / 10)
    tm.assert_frame_equal(new_way, old_way)

    # Group by strings; filter on ints.
    grouped = df.groupby("letters")
    old_way = df[grouped.ints.transform(lambda x: x.mean() > N / 20).astype("bool")]
    new_way = grouped.filter(lambda x: x["ints"].mean() > N / 20)
    tm.assert_frame_equal(new_way, old_way)


def test_filter_using_len():
    # BUG GH4447
    df = DataFrame({"A": np.arange(8), "B": list("aabbbbcc"), "C": np.arange(8)})
    grouped = df.groupby("B")
    actual = grouped.filter(lambda x: len(x) > 2)
    expected = DataFrame(
        {"A": np.arange(2, 6), "B": list("bbbb"), "C": np.arange(2, 6)},
        index=np.arange(2, 6, dtype=np.int64),
    )
    tm.assert_frame_equal(actual, expected)

    actual = grouped.filter(lambda x: len(x) > 4)
    expected = df.loc[[]]
    tm.assert_frame_equal(actual, expected)

    # Series have always worked properly, but we'll test anyway.
    s = df["B"]
    grouped = s.groupby(s)
    actual = grouped.filter(lambda x: len(x) > 2)
    expected = Series(4 * ["b"], index=np.arange(2, 6, dtype=np.int64), name="B")
    tm.assert_series_equal(actual, expected)

    actual = grouped.filter(lambda x: len(x) > 4)
    expected = s[[]]
    tm.assert_series_equal(actual, expected)


def test_filter_maintains_ordering():
    # Simple case: index is sequential. #4621
    df = DataFrame(
        {"pid": [1, 1, 1, 2, 2, 3, 3, 3], "tag": [23, 45, 62, 24, 45, 34, 25, 62]}
    )
    s = df["pid"]
    grouped = df.groupby("tag")
    actual = grouped.filter(lambda x: len(x) > 1)
    expected = df.iloc[[1, 2, 4, 7]]
    tm.assert_frame_equal(actual, expected)

    grouped = s.groupby(df["tag"])
    actual = grouped.filter(lambda x: len(x) > 1)
    expected = s.iloc[[1, 2, 4, 7]]
    tm.assert_series_equal(actual, expected)

    # Now index is sequentially decreasing.
    df.index = np.arange(len(df) - 1, -1, -1)
    s = df["pid"]
    grouped = df.groupby("tag")
    actual = grouped.filter(lambda x: len(x) > 1)
    expected = df.iloc[[1, 2, 4, 7]]
    tm.assert_frame_equal(actual, expected)

    grouped = s.groupby(df["tag"])
    actual = grouped.filter(lambda x: len(x) > 1)
    expected = s.iloc[[1, 2, 4, 7]]
    tm.assert_series_equal(actual, expected)

    # Index is shuffled.
    SHUFFLED = [4, 6, 7, 2, 1, 0, 5, 3]
    df.index = df.index[SHUFFLED]
    s = df["pid"]
    grouped = df.groupby("tag")
    actual = grouped.filter(lambda x: len(x) > 1)
    expected = df.iloc[[1, 2, 4, 7]]
    tm.assert_frame_equal(actual, expected)

    grouped = s.groupby(df["tag"])
    actual = grouped.filter(lambda x: len(x) > 1)
    expected = s.iloc[[1, 2, 4, 7]]
    tm.assert_series_equal(actual, expected)


def test_filter_multiple_timestamp():
    # GH 10114
    df = DataFrame(
        {
            "A": np.arange(5, dtype="int64"),
            "B": ["foo", "bar", "foo", "bar", "bar"],
            "C": Timestamp("20130101"),
        }
    )

    grouped = df.groupby(["B", "C"])

    result = grouped["A"].filter(lambda x: True)
    tm.assert_series_equal(df["A"], result)

    result = grouped["A"].transform(len)
    expected = Series([2, 3, 2, 3, 3], name="A")
    tm.assert_series_equal(result, expected)

    result = grouped.filter(lambda x: True)
    tm.assert_frame_equal(df, result)

    result = grouped.transform("sum")
    expected = DataFrame({"A": [2, 8, 2, 8, 8]})
    tm.assert_frame_equal(result, expected)

    result = grouped.transform(len)
    expected = DataFrame({"A": [2, 3, 2, 3, 3]})
    tm.assert_frame_equal(result, expected)


def test_filter_and_transform_with_non_unique_int_index():
    # GH4620
    index = [1, 1, 1, 2, 1, 1, 0, 1]
    df = DataFrame(
        {"pid": [1, 1, 1, 2, 2, 3, 3, 3], "tag": [23, 45, 62, 24, 45, 34, 25, 62]},
        index=index,
    )
    grouped_df = df.groupby("tag")
    ser = df["pid"]
    grouped_ser = ser.groupby(df["tag"])
    expected_indexes = [1, 2, 4, 7]

    # Filter DataFrame
    actual = grouped_df.filter(lambda x: len(x) > 1)
    expected = df.iloc[expected_indexes]
    tm.assert_frame_equal(actual, expected)

    actual = grouped_df.filter(lambda x: len(x) > 1, dropna=False)
    # Cast to avoid upcast when setting nan below
    expected = df.copy().astype("float64")
    expected.iloc[[0, 3, 5, 6]] = np.nan
    tm.assert_frame_equal(actual, expected)

    # Filter Series
    actual = grouped_ser.filter(lambda x: len(x) > 1)
    expected = ser.take(expected_indexes)
    tm.assert_series_equal(actual, expected)

    actual = grouped_ser.filter(lambda x: len(x) > 1, dropna=False)
    expected = Series([np.nan, 1, 1, np.nan, 2, np.nan, np.nan, 3], index, name="pid")
    # ^ made manually because this can get confusing!
    tm.assert_series_equal(actual, expected)

    # Transform Series
    actual = grouped_ser.transform(len)
    expected = Series([1, 2, 2, 1, 2, 1, 1, 2], index, name="pid")
    tm.assert_series_equal(actual, expected)

    # Transform (a column from) DataFrameGroupBy
    actual = grouped_df.pid.transform(len)
    tm.assert_series_equal(actual, expected)


def test_filter_and_transform_with_multiple_non_unique_int_index():
    # GH4620
    index = [1, 1, 1, 2, 0, 0, 0, 1]
    df = DataFrame(
        {"pid": [1, 1, 1, 2, 2, 3, 3, 3], "tag": [23, 45, 62, 24, 45, 34, 25, 62]},
        index=index,
    )
    grouped_df = df.groupby("tag")
    ser = df["pid"]
    grouped_ser = ser.groupby(df["tag"])
    expected_indexes = [1, 2, 4, 7]

    # Filter DataFrame
    actual = grouped_df.filter(lambda x: len(x) > 1)
    expected = df.iloc[expected_indexes]
    tm.assert_frame_equal(actual, expected)

    actual = grouped_df.filter(lambda x: len(x) > 1, dropna=False)
    # Cast to avoid upcast when setting nan below
    expected = df.copy().astype("float64")
    expected.iloc[[0, 3, 5, 6]] = np.nan
    tm.assert_frame_equal(actual, expected)

    # Filter Series
    actual = grouped_ser.filter(lambda x: len(x) > 1)
    expected = ser.take(expected_indexes)
    tm.assert_series_equal(actual, expected)

    actual = grouped_ser.filter(lambda x: len(x) > 1, dropna=False)
    expected = Series([np.nan, 1, 1, np.nan, 2, np.nan, np.nan, 3], index, name="pid")
    # ^ made manually because this can get confusing!
    tm.assert_series_equal(actual, expected)

    # Transform Series
    actual = grouped_ser.transform(len)
    expected = Series([1, 2, 2, 1, 2, 1, 1, 2], index, name="pid")
    tm.assert_series_equal(actual, expected)

    # Transform (a column from) DataFrameGroupBy
    actual = grouped_df.pid.transform(len)
    tm.assert_series_equal(actual, expected)


def test_filter_and_transform_with_non_unique_float_index():
    # GH4620
    index = np.array([1, 1, 1, 2, 1, 1, 0, 1], dtype=float)
    df = DataFrame(
        {"pid": [1, 1, 1, 2, 2, 3, 3, 3], "tag": [23, 45, 62, 24, 45, 34, 25, 62]},
        index=index,
    )
    grouped_df = df.groupby("tag")
    ser = df["pid"]
    grouped_ser = ser.groupby(df["tag"])
    expected_indexes = [1, 2, 4, 7]

    # Filter DataFrame
    actual = grouped_df.filter(lambda x: len(x) > 1)
    expected = df.iloc[expected_indexes]
    tm.assert_frame_equal(actual, expected)

    actual = grouped_df.filter(lambda x: len(x) > 1, dropna=False)
    # Cast to avoid upcast when setting nan below
    expected = df.copy().astype("float64")
    expected.iloc[[0, 3, 5, 6]] = np.nan
    tm.assert_frame_equal(actual, expected)

    # Filter Series
    actual = grouped_ser.filter(lambda x: len(x) > 1)
    expected = ser.take(expected_indexes)
    tm.assert_series_equal(actual, expected)

    actual = grouped_ser.filter(lambda x: len(x) > 1, dropna=False)
    expected = Series([np.nan, 1, 1, np.nan, 2, np.nan, np.nan, 3], index, name="pid")
    # ^ made manually because this can get confusing!
    tm.assert_series_equal(actual, expected)

    # Transform Series
    actual = grouped_ser.transform(len)
    expected = Series([1, 2, 2, 1, 2, 1, 1, 2], index, name="pid")
    tm.assert_series_equal(actual, expected)

    # Transform (a column from) DataFrameGroupBy
    actual = grouped_df.pid.transform(len)
    tm.assert_series_equal(actual, expected)


def test_filter_and_transform_with_non_unique_timestamp_index():
    # GH4620
    t0 = Timestamp("2013-09-30 00:05:00")
    t1 = Timestamp("2013-10-30 00:05:00")
    t2 = Timestamp("2013-11-30 00:05:00")
    index = [t1, t1, t1, t2, t1, t1, t0, t1]
    df = DataFrame(
        {"pid": [1, 1, 1, 2, 2, 3, 3, 3], "tag": [23, 45, 62, 24, 45, 34, 25, 62]},
        index=index,
    )
    grouped_df = df.groupby("tag")
    ser = df["pid"]
    grouped_ser = ser.groupby(df["tag"])
    expected_indexes = [1, 2, 4, 7]

    # Filter DataFrame
    actual = grouped_df.filter(lambda x: len(x) > 1)
    expected = df.iloc[expected_indexes]
    tm.assert_frame_equal(actual, expected)

    actual = grouped_df.filter(lambda x: len(x) > 1, dropna=False)
    # Cast to avoid upcast when setting nan below
    expected = df.copy().astype("float64")
    expected.iloc[[0, 3, 5, 6]] = np.nan
    tm.assert_frame_equal(actual, expected)

    # Filter Series
    actual = grouped_ser.filter(lambda x: len(x) > 1)
    expected = ser.take(expected_indexes)
    tm.assert_series_equal(actual, expected)

    actual = grouped_ser.filter(lambda x: len(x) > 1, dropna=False)
    expected = Series([np.nan, 1, 1, np.nan, 2, np.nan, np.nan, 3], index, name="pid")
    # ^ made manually because this can get confusing!
    tm.assert_series_equal(actual, expected)

    # Transform Series
    actual = grouped_ser.transform(len)
    expected = Series([1, 2, 2, 1, 2, 1, 1, 2], index, name="pid")
    tm.assert_series_equal(actual, expected)

    # Transform (a column from) DataFrameGroupBy
    actual = grouped_df.pid.transform(len)
    tm.assert_series_equal(actual, expected)


def test_filter_and_transform_with_non_unique_string_index():
    # GH4620
    index = list("bbbcbbab")
    df = DataFrame(
        {"pid": [1, 1, 1, 2, 2, 3, 3, 3], "tag": [23, 45, 62, 24, 45, 34, 25, 62]},
        index=index,
    )
    grouped_df = df.groupby("tag")
    ser = df["pid"]
    grouped_ser = ser.groupby(df["tag"])
    expected_indexes = [1, 2, 4, 7]

    # Filter DataFrame
    actual = grouped_df.filter(lambda x: len(x) > 1)
    expected = df.iloc[expected_indexes]
    tm.assert_frame_equal(actual, expected)

    actual = grouped_df.filter(lambda x: len(x) > 1, dropna=False)
    # Cast to avoid upcast when setting nan below
    expected = df.copy().astype("float64")
    expected.iloc[[0, 3, 5, 6]] = np.nan
    tm.assert_frame_equal(actual, expected)

    # Filter Series
    actual = grouped_ser.filter(lambda x: len(x) > 1)
    expected = ser.take(expected_indexes)
    tm.assert_series_equal(actual, expected)

    actual = grouped_ser.filter(lambda x: len(x) > 1, dropna=False)
    expected = Series([np.nan, 1, 1, np.nan, 2, np.nan, np.nan, 3], index, name="pid")
    # ^ made manually because this can get confusing!
    tm.assert_series_equal(actual, expected)

    # Transform Series
    actual = grouped_ser.transform(len)
    expected = Series([1, 2, 2, 1, 2, 1, 1, 2], index, name="pid")
    tm.assert_series_equal(actual, expected)

    # Transform (a column from) DataFrameGroupBy
    actual = grouped_df.pid.transform(len)
    tm.assert_series_equal(actual, expected)


def test_filter_has_access_to_grouped_cols():
    df = DataFrame([[1, 2], [1, 3], [5, 6]], columns=["A", "B"])
    g = df.groupby("A")
    # previously didn't have access to col A #????
    filt = g.filter(lambda x: x["A"].sum() == 2)
    tm.assert_frame_equal(filt, df.iloc[[0, 1]])


def test_filter_enforces_scalarness():
    df = DataFrame(
        [
            ["best", "a", "x"],
            ["worst", "b", "y"],
            ["best", "c", "x"],
            ["best", "d", "y"],
            ["worst", "d", "y"],
            ["worst", "d", "y"],
            ["best", "d", "z"],
        ],
        columns=["a", "b", "c"],
    )
    with pytest.raises(TypeError, match="filter function returned a.*"):
        df.groupby("c").filter(lambda g: g["a"] == "best")


def test_filter_non_bool_raises():
    df = DataFrame(
        [
            ["best", "a", 1],
            ["worst", "b", 1],
            ["best", "c", 1],
            ["best", "d", 1],
            ["worst", "d", 1],
            ["worst", "d", 1],
            ["best", "d", 1],
        ],
        columns=["a", "b", "c"],
    )
    with pytest.raises(TypeError, match="filter function returned a.*"):
        df.groupby("a").filter(lambda g: g.c.mean())


def test_filter_dropna_with_empty_groups():
    # GH 10780
    data = Series(np.random.default_rng(2).random(9), index=np.repeat([1, 2, 3], 3))
    grouped = data.groupby(level=0)
    result_false = grouped.filter(lambda x: x.mean() > 1, dropna=False)
    expected_false = Series([np.nan] * 9, index=np.repeat([1, 2, 3], 3))
    tm.assert_series_equal(result_false, expected_false)

    result_true = grouped.filter(lambda x: x.mean() > 1, dropna=True)
    expected_true = Series(index=pd.Index([], dtype=int), dtype=np.float64)
    tm.assert_series_equal(result_true, expected_true)


def test_filter_consistent_result_before_after_agg_func():
    # GH 17091
    df = DataFrame({"data": range(6), "key": list("ABCABC")})
    grouper = df.groupby("key")
    result = grouper.filter(lambda x: True)
    expected = DataFrame({"data": range(6), "key": list("ABCABC")})
    tm.assert_frame_equal(result, expected)

    grouper.sum()
    result = grouper.filter(lambda x: True)
    tm.assert_frame_equal(result, expected)
