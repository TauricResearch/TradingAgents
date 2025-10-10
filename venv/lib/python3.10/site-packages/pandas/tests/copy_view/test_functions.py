import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    Series,
    concat,
    merge,
)
import pandas._testing as tm
from pandas.tests.copy_view.util import get_array


def test_concat_frames(using_copy_on_write):
    df = DataFrame({"b": ["a"] * 3}, dtype=object)
    df2 = DataFrame({"a": ["a"] * 3}, dtype=object)
    df_orig = df.copy()
    result = concat([df, df2], axis=1)

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "b"), get_array(df, "b"))
        assert np.shares_memory(get_array(result, "a"), get_array(df2, "a"))
    else:
        assert not np.shares_memory(get_array(result, "b"), get_array(df, "b"))
        assert not np.shares_memory(get_array(result, "a"), get_array(df2, "a"))

    result.iloc[0, 0] = "d"
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "b"), get_array(df, "b"))
        assert np.shares_memory(get_array(result, "a"), get_array(df2, "a"))

    result.iloc[0, 1] = "d"
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), get_array(df2, "a"))
    tm.assert_frame_equal(df, df_orig)


def test_concat_frames_updating_input(using_copy_on_write):
    df = DataFrame({"b": ["a"] * 3}, dtype=object)
    df2 = DataFrame({"a": ["a"] * 3}, dtype=object)
    result = concat([df, df2], axis=1)

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "b"), get_array(df, "b"))
        assert np.shares_memory(get_array(result, "a"), get_array(df2, "a"))
    else:
        assert not np.shares_memory(get_array(result, "b"), get_array(df, "b"))
        assert not np.shares_memory(get_array(result, "a"), get_array(df2, "a"))

    expected = result.copy()
    df.iloc[0, 0] = "d"
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "b"), get_array(df, "b"))
        assert np.shares_memory(get_array(result, "a"), get_array(df2, "a"))

    df2.iloc[0, 0] = "d"
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), get_array(df2, "a"))
    tm.assert_frame_equal(result, expected)


def test_concat_series(using_copy_on_write):
    ser = Series([1, 2], name="a")
    ser2 = Series([3, 4], name="b")
    ser_orig = ser.copy()
    ser2_orig = ser2.copy()
    result = concat([ser, ser2], axis=1)

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "a"), ser.values)
        assert np.shares_memory(get_array(result, "b"), ser2.values)
    else:
        assert not np.shares_memory(get_array(result, "a"), ser.values)
        assert not np.shares_memory(get_array(result, "b"), ser2.values)

    result.iloc[0, 0] = 100
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), ser.values)
        assert np.shares_memory(get_array(result, "b"), ser2.values)

    result.iloc[0, 1] = 1000
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "b"), ser2.values)
    tm.assert_series_equal(ser, ser_orig)
    tm.assert_series_equal(ser2, ser2_orig)


def test_concat_frames_chained(using_copy_on_write):
    df1 = DataFrame({"a": [1, 2, 3], "b": [0.1, 0.2, 0.3]})
    df2 = DataFrame({"c": [4, 5, 6]})
    df3 = DataFrame({"d": [4, 5, 6]})
    result = concat([concat([df1, df2], axis=1), df3], axis=1)
    expected = result.copy()

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert np.shares_memory(get_array(result, "c"), get_array(df2, "c"))
        assert np.shares_memory(get_array(result, "d"), get_array(df3, "d"))
    else:
        assert not np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert not np.shares_memory(get_array(result, "c"), get_array(df2, "c"))
        assert not np.shares_memory(get_array(result, "d"), get_array(df3, "d"))

    df1.iloc[0, 0] = 100
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), get_array(df1, "a"))

    tm.assert_frame_equal(result, expected)


def test_concat_series_chained(using_copy_on_write):
    ser1 = Series([1, 2, 3], name="a")
    ser2 = Series([4, 5, 6], name="c")
    ser3 = Series([4, 5, 6], name="d")
    result = concat([concat([ser1, ser2], axis=1), ser3], axis=1)
    expected = result.copy()

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "a"), get_array(ser1, "a"))
        assert np.shares_memory(get_array(result, "c"), get_array(ser2, "c"))
        assert np.shares_memory(get_array(result, "d"), get_array(ser3, "d"))
    else:
        assert not np.shares_memory(get_array(result, "a"), get_array(ser1, "a"))
        assert not np.shares_memory(get_array(result, "c"), get_array(ser2, "c"))
        assert not np.shares_memory(get_array(result, "d"), get_array(ser3, "d"))

    ser1.iloc[0] = 100
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), get_array(ser1, "a"))

    tm.assert_frame_equal(result, expected)


def test_concat_series_updating_input(using_copy_on_write):
    ser = Series([1, 2], name="a")
    ser2 = Series([3, 4], name="b")
    expected = DataFrame({"a": [1, 2], "b": [3, 4]})
    result = concat([ser, ser2], axis=1)

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "a"), get_array(ser, "a"))
        assert np.shares_memory(get_array(result, "b"), get_array(ser2, "b"))
    else:
        assert not np.shares_memory(get_array(result, "a"), get_array(ser, "a"))
        assert not np.shares_memory(get_array(result, "b"), get_array(ser2, "b"))

    ser.iloc[0] = 100
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), get_array(ser, "a"))
        assert np.shares_memory(get_array(result, "b"), get_array(ser2, "b"))
    tm.assert_frame_equal(result, expected)

    ser2.iloc[0] = 1000
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "b"), get_array(ser2, "b"))
    tm.assert_frame_equal(result, expected)


def test_concat_mixed_series_frame(using_copy_on_write):
    df = DataFrame({"a": [1, 2, 3], "c": 1})
    ser = Series([4, 5, 6], name="d")
    result = concat([df, ser], axis=1)
    expected = result.copy()

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "a"), get_array(df, "a"))
        assert np.shares_memory(get_array(result, "c"), get_array(df, "c"))
        assert np.shares_memory(get_array(result, "d"), get_array(ser, "d"))
    else:
        assert not np.shares_memory(get_array(result, "a"), get_array(df, "a"))
        assert not np.shares_memory(get_array(result, "c"), get_array(df, "c"))
        assert not np.shares_memory(get_array(result, "d"), get_array(ser, "d"))

    ser.iloc[0] = 100
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "d"), get_array(ser, "d"))

    df.iloc[0, 0] = 100
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), get_array(df, "a"))
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("copy", [True, None, False])
def test_concat_copy_keyword(using_copy_on_write, copy):
    df = DataFrame({"a": [1, 2]})
    df2 = DataFrame({"b": [1.5, 2.5]})

    result = concat([df, df2], axis=1, copy=copy)

    if using_copy_on_write or copy is False:
        assert np.shares_memory(get_array(df, "a"), get_array(result, "a"))
        assert np.shares_memory(get_array(df2, "b"), get_array(result, "b"))
    else:
        assert not np.shares_memory(get_array(df, "a"), get_array(result, "a"))
        assert not np.shares_memory(get_array(df2, "b"), get_array(result, "b"))


@pytest.mark.parametrize(
    "func",
    [
        lambda df1, df2, **kwargs: df1.merge(df2, **kwargs),
        lambda df1, df2, **kwargs: merge(df1, df2, **kwargs),
    ],
)
def test_merge_on_key(using_copy_on_write, func):
    df1 = DataFrame({"key": Series(["a", "b", "c"], dtype=object), "a": [1, 2, 3]})
    df2 = DataFrame({"key": Series(["a", "b", "c"], dtype=object), "b": [4, 5, 6]})
    df1_orig = df1.copy()
    df2_orig = df2.copy()

    result = func(df1, df2, on="key")

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert np.shares_memory(get_array(result, "b"), get_array(df2, "b"))
        assert np.shares_memory(get_array(result, "key"), get_array(df1, "key"))
        assert not np.shares_memory(get_array(result, "key"), get_array(df2, "key"))
    else:
        assert not np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert not np.shares_memory(get_array(result, "b"), get_array(df2, "b"))

    result.iloc[0, 1] = 0
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert np.shares_memory(get_array(result, "b"), get_array(df2, "b"))

    result.iloc[0, 2] = 0
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "b"), get_array(df2, "b"))
    tm.assert_frame_equal(df1, df1_orig)
    tm.assert_frame_equal(df2, df2_orig)


def test_merge_on_index(using_copy_on_write):
    df1 = DataFrame({"a": [1, 2, 3]})
    df2 = DataFrame({"b": [4, 5, 6]})
    df1_orig = df1.copy()
    df2_orig = df2.copy()

    result = merge(df1, df2, left_index=True, right_index=True)

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert np.shares_memory(get_array(result, "b"), get_array(df2, "b"))
    else:
        assert not np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert not np.shares_memory(get_array(result, "b"), get_array(df2, "b"))

    result.iloc[0, 0] = 0
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert np.shares_memory(get_array(result, "b"), get_array(df2, "b"))

    result.iloc[0, 1] = 0
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "b"), get_array(df2, "b"))
    tm.assert_frame_equal(df1, df1_orig)
    tm.assert_frame_equal(df2, df2_orig)


@pytest.mark.parametrize(
    "func, how",
    [
        (lambda df1, df2, **kwargs: merge(df2, df1, on="key", **kwargs), "right"),
        (lambda df1, df2, **kwargs: merge(df1, df2, on="key", **kwargs), "left"),
    ],
)
def test_merge_on_key_enlarging_one(using_copy_on_write, func, how):
    df1 = DataFrame({"key": Series(["a", "b", "c"], dtype=object), "a": [1, 2, 3]})
    df2 = DataFrame({"key": Series(["a", "b"], dtype=object), "b": [4, 5]})
    df1_orig = df1.copy()
    df2_orig = df2.copy()

    result = func(df1, df2, how=how)

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert not np.shares_memory(get_array(result, "b"), get_array(df2, "b"))
        assert df2._mgr._has_no_reference(1)
        assert df2._mgr._has_no_reference(0)
        assert np.shares_memory(get_array(result, "key"), get_array(df1, "key")) is (
            how == "left"
        )
        assert not np.shares_memory(get_array(result, "key"), get_array(df2, "key"))
    else:
        assert not np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert not np.shares_memory(get_array(result, "b"), get_array(df2, "b"))

    if how == "left":
        result.iloc[0, 1] = 0
    else:
        result.iloc[0, 2] = 0
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
    tm.assert_frame_equal(df1, df1_orig)
    tm.assert_frame_equal(df2, df2_orig)


@pytest.mark.parametrize("copy", [True, None, False])
def test_merge_copy_keyword(using_copy_on_write, copy):
    df = DataFrame({"a": [1, 2]})
    df2 = DataFrame({"b": [3, 4.5]})

    result = df.merge(df2, copy=copy, left_index=True, right_index=True)

    if using_copy_on_write or copy is False:
        assert np.shares_memory(get_array(df, "a"), get_array(result, "a"))
        assert np.shares_memory(get_array(df2, "b"), get_array(result, "b"))
    else:
        assert not np.shares_memory(get_array(df, "a"), get_array(result, "a"))
        assert not np.shares_memory(get_array(df2, "b"), get_array(result, "b"))


@pytest.mark.parametrize("dtype", [object, "str"])
def test_join_on_key(dtype, using_copy_on_write):
    df_index = Index(["a", "b", "c"], name="key", dtype=dtype)

    df1 = DataFrame({"a": [1, 2, 3]}, index=df_index.copy(deep=True))
    df2 = DataFrame({"b": [4, 5, 6]}, index=df_index.copy(deep=True))

    df1_orig = df1.copy()
    df2_orig = df2.copy()

    result = df1.join(df2, on="key")

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert np.shares_memory(get_array(result, "b"), get_array(df2, "b"))
        assert tm.shares_memory(get_array(result.index), get_array(df1.index))
        assert not np.shares_memory(get_array(result.index), get_array(df2.index))
    else:
        assert not np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert not np.shares_memory(get_array(result, "b"), get_array(df2, "b"))

    result.iloc[0, 0] = 0
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert np.shares_memory(get_array(result, "b"), get_array(df2, "b"))

    result.iloc[0, 1] = 0
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "b"), get_array(df2, "b"))

    tm.assert_frame_equal(df1, df1_orig)
    tm.assert_frame_equal(df2, df2_orig)


def test_join_multiple_dataframes_on_key(using_copy_on_write):
    df_index = Index(["a", "b", "c"], name="key", dtype=object)

    df1 = DataFrame({"a": [1, 2, 3]}, index=df_index.copy(deep=True))
    dfs_list = [
        DataFrame({"b": [4, 5, 6]}, index=df_index.copy(deep=True)),
        DataFrame({"c": [7, 8, 9]}, index=df_index.copy(deep=True)),
    ]

    df1_orig = df1.copy()
    dfs_list_orig = [df.copy() for df in dfs_list]

    result = df1.join(dfs_list)

    if using_copy_on_write:
        assert np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert np.shares_memory(get_array(result, "b"), get_array(dfs_list[0], "b"))
        assert np.shares_memory(get_array(result, "c"), get_array(dfs_list[1], "c"))
        assert np.shares_memory(get_array(result.index), get_array(df1.index))
        assert not np.shares_memory(
            get_array(result.index), get_array(dfs_list[0].index)
        )
        assert not np.shares_memory(
            get_array(result.index), get_array(dfs_list[1].index)
        )
    else:
        assert not np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert not np.shares_memory(get_array(result, "b"), get_array(dfs_list[0], "b"))
        assert not np.shares_memory(get_array(result, "c"), get_array(dfs_list[1], "c"))

    result.iloc[0, 0] = 0
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "a"), get_array(df1, "a"))
        assert np.shares_memory(get_array(result, "b"), get_array(dfs_list[0], "b"))
        assert np.shares_memory(get_array(result, "c"), get_array(dfs_list[1], "c"))

    result.iloc[0, 1] = 0
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "b"), get_array(dfs_list[0], "b"))
        assert np.shares_memory(get_array(result, "c"), get_array(dfs_list[1], "c"))

    result.iloc[0, 2] = 0
    if using_copy_on_write:
        assert not np.shares_memory(get_array(result, "c"), get_array(dfs_list[1], "c"))

    tm.assert_frame_equal(df1, df1_orig)
    for df, df_orig in zip(dfs_list, dfs_list_orig):
        tm.assert_frame_equal(df, df_orig)
