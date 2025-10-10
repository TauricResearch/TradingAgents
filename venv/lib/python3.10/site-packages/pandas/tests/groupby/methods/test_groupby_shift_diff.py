import numpy as np
import pytest

from pandas import (
    DataFrame,
    NaT,
    Series,
    Timedelta,
    Timestamp,
    date_range,
)
import pandas._testing as tm


def test_group_shift_with_null_key():
    # This test is designed to replicate the segfault in issue #13813.
    n_rows = 1200

    # Generate a moderately large dataframe with occasional missing
    # values in column `B`, and then group by [`A`, `B`]. This should
    # force `-1` in `labels` array of `g._grouper.group_info` exactly
    # at those places, where the group-by key is partially missing.
    df = DataFrame(
        [(i % 12, i % 3 if i % 3 else np.nan, i) for i in range(n_rows)],
        dtype=float,
        columns=["A", "B", "Z"],
        index=None,
    )
    g = df.groupby(["A", "B"])

    expected = DataFrame(
        [(i + 12 if i % 3 and i < n_rows - 12 else np.nan) for i in range(n_rows)],
        dtype=float,
        columns=["Z"],
        index=None,
    )
    result = g.shift(-1)

    tm.assert_frame_equal(result, expected)


def test_group_shift_with_fill_value():
    # GH #24128
    n_rows = 24
    df = DataFrame(
        [(i % 12, i % 3, i) for i in range(n_rows)],
        dtype=float,
        columns=["A", "B", "Z"],
        index=None,
    )
    g = df.groupby(["A", "B"])

    expected = DataFrame(
        [(i + 12 if i < n_rows - 12 else 0) for i in range(n_rows)],
        dtype=float,
        columns=["Z"],
        index=None,
    )
    result = g.shift(-1, fill_value=0)

    tm.assert_frame_equal(result, expected)


def test_group_shift_lose_timezone():
    # GH 30134
    now_dt = Timestamp.utcnow().as_unit("ns")
    df = DataFrame({"a": [1, 1], "date": now_dt})
    result = df.groupby("a").shift(0).iloc[0]
    expected = Series({"date": now_dt}, name=result.name)
    tm.assert_series_equal(result, expected)


def test_group_diff_real_series(any_real_numpy_dtype):
    df = DataFrame(
        {"a": [1, 2, 3, 3, 2], "b": [1, 2, 3, 4, 5]},
        dtype=any_real_numpy_dtype,
    )
    result = df.groupby("a")["b"].diff()
    exp_dtype = "float"
    if any_real_numpy_dtype in ["int8", "int16", "float32"]:
        exp_dtype = "float32"
    expected = Series([np.nan, np.nan, np.nan, 1.0, 3.0], dtype=exp_dtype, name="b")
    tm.assert_series_equal(result, expected)


def test_group_diff_real_frame(any_real_numpy_dtype):
    df = DataFrame(
        {
            "a": [1, 2, 3, 3, 2],
            "b": [1, 2, 3, 4, 5],
            "c": [1, 2, 3, 4, 6],
        },
        dtype=any_real_numpy_dtype,
    )
    result = df.groupby("a").diff()
    exp_dtype = "float"
    if any_real_numpy_dtype in ["int8", "int16", "float32"]:
        exp_dtype = "float32"
    expected = DataFrame(
        {
            "b": [np.nan, np.nan, np.nan, 1.0, 3.0],
            "c": [np.nan, np.nan, np.nan, 1.0, 4.0],
        },
        dtype=exp_dtype,
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "data",
    [
        [
            Timestamp("2013-01-01"),
            Timestamp("2013-01-02"),
            Timestamp("2013-01-03"),
        ],
        [Timedelta("5 days"), Timedelta("6 days"), Timedelta("7 days")],
    ],
)
def test_group_diff_datetimelike(data, unit):
    df = DataFrame({"a": [1, 2, 2], "b": data})
    df["b"] = df["b"].dt.as_unit(unit)
    result = df.groupby("a")["b"].diff()
    expected = Series([NaT, NaT, Timedelta("1 days")], name="b").dt.as_unit(unit)
    tm.assert_series_equal(result, expected)


def test_group_diff_bool():
    df = DataFrame({"a": [1, 2, 3, 3, 2], "b": [True, True, False, False, True]})
    result = df.groupby("a")["b"].diff()
    expected = Series([np.nan, np.nan, np.nan, False, False], name="b")
    tm.assert_series_equal(result, expected)


def test_group_diff_object_raises(object_dtype):
    df = DataFrame(
        {"a": ["foo", "bar", "bar"], "b": ["baz", "foo", "foo"]}, dtype=object_dtype
    )
    with pytest.raises(TypeError, match=r"unsupported operand type\(s\) for -"):
        df.groupby("a")["b"].diff()


def test_empty_shift_with_fill():
    # GH 41264, single-index check
    df = DataFrame(columns=["a", "b", "c"])
    shifted = df.groupby(["a"]).shift(1)
    shifted_with_fill = df.groupby(["a"]).shift(1, fill_value=0)
    tm.assert_frame_equal(shifted, shifted_with_fill)
    tm.assert_index_equal(shifted.index, shifted_with_fill.index)


def test_multindex_empty_shift_with_fill():
    # GH 41264, multi-index check
    df = DataFrame(columns=["a", "b", "c"])
    shifted = df.groupby(["a", "b"]).shift(1)
    shifted_with_fill = df.groupby(["a", "b"]).shift(1, fill_value=0)
    tm.assert_frame_equal(shifted, shifted_with_fill)
    tm.assert_index_equal(shifted.index, shifted_with_fill.index)


def test_shift_periods_freq():
    # GH 54093
    data = {"a": [1, 2, 3, 4, 5, 6], "b": [0, 0, 0, 1, 1, 1]}
    df = DataFrame(data, index=date_range(start="20100101", periods=6))
    result = df.groupby(df.index).shift(periods=-2, freq="D")
    expected = DataFrame(data, index=date_range(start="2009-12-30", periods=6))
    tm.assert_frame_equal(result, expected)


def test_shift_deprecate_freq_and_fill_value():
    # GH 53832
    data = {"a": [1, 2, 3, 4, 5, 6], "b": [0, 0, 0, 1, 1, 1]}
    df = DataFrame(data, index=date_range(start="20100101", periods=6))
    msg = (
        "Passing a 'freq' together with a 'fill_value' silently ignores the fill_value"
    )
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.groupby(df.index).shift(periods=-2, freq="D", fill_value="1")


def test_shift_disallow_suffix_if_periods_is_int():
    # GH#44424
    data = {"a": [1, 2, 3, 4, 5, 6], "b": [0, 0, 0, 1, 1, 1]}
    df = DataFrame(data)
    msg = "Cannot specify `suffix` if `periods` is an int."
    with pytest.raises(ValueError, match=msg):
        df.groupby("b").shift(1, suffix="fails")


def test_group_shift_with_multiple_periods():
    # GH#44424
    df = DataFrame({"a": [1, 2, 3, 3, 2], "b": [True, True, False, False, True]})

    shifted_df = df.groupby("b")[["a"]].shift([0, 1])
    expected_df = DataFrame(
        {"a_0": [1, 2, 3, 3, 2], "a_1": [np.nan, 1.0, np.nan, 3.0, 2.0]}
    )
    tm.assert_frame_equal(shifted_df, expected_df)

    # series
    shifted_series = df.groupby("b")["a"].shift([0, 1])
    tm.assert_frame_equal(shifted_series, expected_df)


def test_group_shift_with_multiple_periods_and_freq():
    # GH#44424
    df = DataFrame(
        {"a": [1, 2, 3, 4, 5], "b": [True, True, False, False, True]},
        index=date_range("1/1/2000", periods=5, freq="h"),
    )
    shifted_df = df.groupby("b")[["a"]].shift(
        [0, 1],
        freq="h",
    )
    expected_df = DataFrame(
        {
            "a_0": [1.0, 2.0, 3.0, 4.0, 5.0, np.nan],
            "a_1": [
                np.nan,
                1.0,
                2.0,
                3.0,
                4.0,
                5.0,
            ],
        },
        index=date_range("1/1/2000", periods=6, freq="h"),
    )
    tm.assert_frame_equal(shifted_df, expected_df)


def test_group_shift_with_multiple_periods_and_fill_value():
    # GH#44424
    df = DataFrame(
        {"a": [1, 2, 3, 4, 5], "b": [True, True, False, False, True]},
    )
    shifted_df = df.groupby("b")[["a"]].shift([0, 1], fill_value=-1)
    expected_df = DataFrame(
        {"a_0": [1, 2, 3, 4, 5], "a_1": [-1, 1, -1, 3, 2]},
    )
    tm.assert_frame_equal(shifted_df, expected_df)


def test_group_shift_with_multiple_periods_and_both_fill_and_freq_deprecated():
    # GH#44424
    df = DataFrame(
        {"a": [1, 2, 3, 4, 5], "b": [True, True, False, False, True]},
        index=date_range("1/1/2000", periods=5, freq="h"),
    )
    msg = (
        "Passing a 'freq' together with a 'fill_value' silently ignores the "
        "fill_value"
    )
    with tm.assert_produces_warning(FutureWarning, match=msg):
        df.groupby("b")[["a"]].shift([1, 2], fill_value=1, freq="h")
