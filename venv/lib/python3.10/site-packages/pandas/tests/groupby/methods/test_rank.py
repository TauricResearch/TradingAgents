from datetime import datetime

import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    NaT,
    Series,
    concat,
)
import pandas._testing as tm


def test_rank_unordered_categorical_typeerror():
    # GH#51034 should be TypeError, not NotImplementedError
    cat = pd.Categorical([], ordered=False)
    ser = Series(cat)
    df = ser.to_frame()

    msg = "Cannot perform rank with non-ordered Categorical"

    gb = ser.groupby(cat, observed=False)
    with pytest.raises(TypeError, match=msg):
        gb.rank()

    gb2 = df.groupby(cat, observed=False)
    with pytest.raises(TypeError, match=msg):
        gb2.rank()


def test_rank_apply():
    lev1 = np.array(["a" * 10] * 100, dtype=object)
    lev2 = np.array(["b" * 10] * 130, dtype=object)
    lab1 = np.random.default_rng(2).integers(0, 100, size=500, dtype=int)
    lab2 = np.random.default_rng(2).integers(0, 130, size=500, dtype=int)

    df = DataFrame(
        {
            "value": np.random.default_rng(2).standard_normal(500),
            "key1": lev1.take(lab1),
            "key2": lev2.take(lab2),
        }
    )

    result = df.groupby(["key1", "key2"]).value.rank()

    expected = [piece.value.rank() for key, piece in df.groupby(["key1", "key2"])]
    expected = concat(expected, axis=0)
    expected = expected.reindex(result.index)
    tm.assert_series_equal(result, expected)

    result = df.groupby(["key1", "key2"]).value.rank(pct=True)

    expected = [
        piece.value.rank(pct=True) for key, piece in df.groupby(["key1", "key2"])
    ]
    expected = concat(expected, axis=0)
    expected = expected.reindex(result.index)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("grps", [["qux"], ["qux", "quux"]])
@pytest.mark.parametrize(
    "vals",
    [
        np.array([2, 2, 8, 2, 6], dtype=dtype)
        for dtype in ["i8", "i4", "i2", "i1", "u8", "u4", "u2", "u1", "f8", "f4", "f2"]
    ]
    + [
        [
            pd.Timestamp("2018-01-02"),
            pd.Timestamp("2018-01-02"),
            pd.Timestamp("2018-01-08"),
            pd.Timestamp("2018-01-02"),
            pd.Timestamp("2018-01-06"),
        ],
        [
            pd.Timestamp("2018-01-02", tz="US/Pacific"),
            pd.Timestamp("2018-01-02", tz="US/Pacific"),
            pd.Timestamp("2018-01-08", tz="US/Pacific"),
            pd.Timestamp("2018-01-02", tz="US/Pacific"),
            pd.Timestamp("2018-01-06", tz="US/Pacific"),
        ],
        [
            pd.Timestamp("2018-01-02") - pd.Timestamp(0),
            pd.Timestamp("2018-01-02") - pd.Timestamp(0),
            pd.Timestamp("2018-01-08") - pd.Timestamp(0),
            pd.Timestamp("2018-01-02") - pd.Timestamp(0),
            pd.Timestamp("2018-01-06") - pd.Timestamp(0),
        ],
        [
            pd.Timestamp("2018-01-02").to_period("D"),
            pd.Timestamp("2018-01-02").to_period("D"),
            pd.Timestamp("2018-01-08").to_period("D"),
            pd.Timestamp("2018-01-02").to_period("D"),
            pd.Timestamp("2018-01-06").to_period("D"),
        ],
    ],
    ids=lambda x: type(x[0]),
)
@pytest.mark.parametrize(
    "ties_method,ascending,pct,exp",
    [
        ("average", True, False, [2.0, 2.0, 5.0, 2.0, 4.0]),
        ("average", True, True, [0.4, 0.4, 1.0, 0.4, 0.8]),
        ("average", False, False, [4.0, 4.0, 1.0, 4.0, 2.0]),
        ("average", False, True, [0.8, 0.8, 0.2, 0.8, 0.4]),
        ("min", True, False, [1.0, 1.0, 5.0, 1.0, 4.0]),
        ("min", True, True, [0.2, 0.2, 1.0, 0.2, 0.8]),
        ("min", False, False, [3.0, 3.0, 1.0, 3.0, 2.0]),
        ("min", False, True, [0.6, 0.6, 0.2, 0.6, 0.4]),
        ("max", True, False, [3.0, 3.0, 5.0, 3.0, 4.0]),
        ("max", True, True, [0.6, 0.6, 1.0, 0.6, 0.8]),
        ("max", False, False, [5.0, 5.0, 1.0, 5.0, 2.0]),
        ("max", False, True, [1.0, 1.0, 0.2, 1.0, 0.4]),
        ("first", True, False, [1.0, 2.0, 5.0, 3.0, 4.0]),
        ("first", True, True, [0.2, 0.4, 1.0, 0.6, 0.8]),
        ("first", False, False, [3.0, 4.0, 1.0, 5.0, 2.0]),
        ("first", False, True, [0.6, 0.8, 0.2, 1.0, 0.4]),
        ("dense", True, False, [1.0, 1.0, 3.0, 1.0, 2.0]),
        ("dense", True, True, [1.0 / 3.0, 1.0 / 3.0, 3.0 / 3.0, 1.0 / 3.0, 2.0 / 3.0]),
        ("dense", False, False, [3.0, 3.0, 1.0, 3.0, 2.0]),
        ("dense", False, True, [3.0 / 3.0, 3.0 / 3.0, 1.0 / 3.0, 3.0 / 3.0, 2.0 / 3.0]),
    ],
)
def test_rank_args(grps, vals, ties_method, ascending, pct, exp):
    key = np.repeat(grps, len(vals))

    orig_vals = vals
    vals = list(vals) * len(grps)
    if isinstance(orig_vals, np.ndarray):
        vals = np.array(vals, dtype=orig_vals.dtype)

    df = DataFrame({"key": key, "val": vals})
    result = df.groupby("key").rank(method=ties_method, ascending=ascending, pct=pct)

    exp_df = DataFrame(exp * len(grps), columns=["val"])
    tm.assert_frame_equal(result, exp_df)


@pytest.mark.parametrize("grps", [["qux"], ["qux", "quux"]])
@pytest.mark.parametrize(
    "vals", [[-np.inf, -np.inf, np.nan, 1.0, np.nan, np.inf, np.inf]]
)
@pytest.mark.parametrize(
    "ties_method,ascending,na_option,exp",
    [
        ("average", True, "keep", [1.5, 1.5, np.nan, 3, np.nan, 4.5, 4.5]),
        ("average", True, "top", [3.5, 3.5, 1.5, 5.0, 1.5, 6.5, 6.5]),
        ("average", True, "bottom", [1.5, 1.5, 6.5, 3.0, 6.5, 4.5, 4.5]),
        ("average", False, "keep", [4.5, 4.5, np.nan, 3, np.nan, 1.5, 1.5]),
        ("average", False, "top", [6.5, 6.5, 1.5, 5.0, 1.5, 3.5, 3.5]),
        ("average", False, "bottom", [4.5, 4.5, 6.5, 3.0, 6.5, 1.5, 1.5]),
        ("min", True, "keep", [1.0, 1.0, np.nan, 3.0, np.nan, 4.0, 4.0]),
        ("min", True, "top", [3.0, 3.0, 1.0, 5.0, 1.0, 6.0, 6.0]),
        ("min", True, "bottom", [1.0, 1.0, 6.0, 3.0, 6.0, 4.0, 4.0]),
        ("min", False, "keep", [4.0, 4.0, np.nan, 3.0, np.nan, 1.0, 1.0]),
        ("min", False, "top", [6.0, 6.0, 1.0, 5.0, 1.0, 3.0, 3.0]),
        ("min", False, "bottom", [4.0, 4.0, 6.0, 3.0, 6.0, 1.0, 1.0]),
        ("max", True, "keep", [2.0, 2.0, np.nan, 3.0, np.nan, 5.0, 5.0]),
        ("max", True, "top", [4.0, 4.0, 2.0, 5.0, 2.0, 7.0, 7.0]),
        ("max", True, "bottom", [2.0, 2.0, 7.0, 3.0, 7.0, 5.0, 5.0]),
        ("max", False, "keep", [5.0, 5.0, np.nan, 3.0, np.nan, 2.0, 2.0]),
        ("max", False, "top", [7.0, 7.0, 2.0, 5.0, 2.0, 4.0, 4.0]),
        ("max", False, "bottom", [5.0, 5.0, 7.0, 3.0, 7.0, 2.0, 2.0]),
        ("first", True, "keep", [1.0, 2.0, np.nan, 3.0, np.nan, 4.0, 5.0]),
        ("first", True, "top", [3.0, 4.0, 1.0, 5.0, 2.0, 6.0, 7.0]),
        ("first", True, "bottom", [1.0, 2.0, 6.0, 3.0, 7.0, 4.0, 5.0]),
        ("first", False, "keep", [4.0, 5.0, np.nan, 3.0, np.nan, 1.0, 2.0]),
        ("first", False, "top", [6.0, 7.0, 1.0, 5.0, 2.0, 3.0, 4.0]),
        ("first", False, "bottom", [4.0, 5.0, 6.0, 3.0, 7.0, 1.0, 2.0]),
        ("dense", True, "keep", [1.0, 1.0, np.nan, 2.0, np.nan, 3.0, 3.0]),
        ("dense", True, "top", [2.0, 2.0, 1.0, 3.0, 1.0, 4.0, 4.0]),
        ("dense", True, "bottom", [1.0, 1.0, 4.0, 2.0, 4.0, 3.0, 3.0]),
        ("dense", False, "keep", [3.0, 3.0, np.nan, 2.0, np.nan, 1.0, 1.0]),
        ("dense", False, "top", [4.0, 4.0, 1.0, 3.0, 1.0, 2.0, 2.0]),
        ("dense", False, "bottom", [3.0, 3.0, 4.0, 2.0, 4.0, 1.0, 1.0]),
    ],
)
def test_infs_n_nans(grps, vals, ties_method, ascending, na_option, exp):
    # GH 20561
    key = np.repeat(grps, len(vals))
    vals = vals * len(grps)
    df = DataFrame({"key": key, "val": vals})
    result = df.groupby("key").rank(
        method=ties_method, ascending=ascending, na_option=na_option
    )
    exp_df = DataFrame(exp * len(grps), columns=["val"])
    tm.assert_frame_equal(result, exp_df)


@pytest.mark.parametrize("grps", [["qux"], ["qux", "quux"]])
@pytest.mark.parametrize(
    "vals",
    [
        np.array([2, 2, np.nan, 8, 2, 6, np.nan, np.nan], dtype=dtype)
        for dtype in ["f8", "f4", "f2"]
    ]
    + [
        [
            pd.Timestamp("2018-01-02"),
            pd.Timestamp("2018-01-02"),
            np.nan,
            pd.Timestamp("2018-01-08"),
            pd.Timestamp("2018-01-02"),
            pd.Timestamp("2018-01-06"),
            np.nan,
            np.nan,
        ],
        [
            pd.Timestamp("2018-01-02", tz="US/Pacific"),
            pd.Timestamp("2018-01-02", tz="US/Pacific"),
            np.nan,
            pd.Timestamp("2018-01-08", tz="US/Pacific"),
            pd.Timestamp("2018-01-02", tz="US/Pacific"),
            pd.Timestamp("2018-01-06", tz="US/Pacific"),
            np.nan,
            np.nan,
        ],
        [
            pd.Timestamp("2018-01-02") - pd.Timestamp(0),
            pd.Timestamp("2018-01-02") - pd.Timestamp(0),
            np.nan,
            pd.Timestamp("2018-01-08") - pd.Timestamp(0),
            pd.Timestamp("2018-01-02") - pd.Timestamp(0),
            pd.Timestamp("2018-01-06") - pd.Timestamp(0),
            np.nan,
            np.nan,
        ],
        [
            pd.Timestamp("2018-01-02").to_period("D"),
            pd.Timestamp("2018-01-02").to_period("D"),
            np.nan,
            pd.Timestamp("2018-01-08").to_period("D"),
            pd.Timestamp("2018-01-02").to_period("D"),
            pd.Timestamp("2018-01-06").to_period("D"),
            np.nan,
            np.nan,
        ],
    ],
    ids=lambda x: type(x[0]),
)
@pytest.mark.parametrize(
    "ties_method,ascending,na_option,pct,exp",
    [
        (
            "average",
            True,
            "keep",
            False,
            [2.0, 2.0, np.nan, 5.0, 2.0, 4.0, np.nan, np.nan],
        ),
        (
            "average",
            True,
            "keep",
            True,
            [0.4, 0.4, np.nan, 1.0, 0.4, 0.8, np.nan, np.nan],
        ),
        (
            "average",
            False,
            "keep",
            False,
            [4.0, 4.0, np.nan, 1.0, 4.0, 2.0, np.nan, np.nan],
        ),
        (
            "average",
            False,
            "keep",
            True,
            [0.8, 0.8, np.nan, 0.2, 0.8, 0.4, np.nan, np.nan],
        ),
        ("min", True, "keep", False, [1.0, 1.0, np.nan, 5.0, 1.0, 4.0, np.nan, np.nan]),
        ("min", True, "keep", True, [0.2, 0.2, np.nan, 1.0, 0.2, 0.8, np.nan, np.nan]),
        (
            "min",
            False,
            "keep",
            False,
            [3.0, 3.0, np.nan, 1.0, 3.0, 2.0, np.nan, np.nan],
        ),
        ("min", False, "keep", True, [0.6, 0.6, np.nan, 0.2, 0.6, 0.4, np.nan, np.nan]),
        ("max", True, "keep", False, [3.0, 3.0, np.nan, 5.0, 3.0, 4.0, np.nan, np.nan]),
        ("max", True, "keep", True, [0.6, 0.6, np.nan, 1.0, 0.6, 0.8, np.nan, np.nan]),
        (
            "max",
            False,
            "keep",
            False,
            [5.0, 5.0, np.nan, 1.0, 5.0, 2.0, np.nan, np.nan],
        ),
        ("max", False, "keep", True, [1.0, 1.0, np.nan, 0.2, 1.0, 0.4, np.nan, np.nan]),
        (
            "first",
            True,
            "keep",
            False,
            [1.0, 2.0, np.nan, 5.0, 3.0, 4.0, np.nan, np.nan],
        ),
        (
            "first",
            True,
            "keep",
            True,
            [0.2, 0.4, np.nan, 1.0, 0.6, 0.8, np.nan, np.nan],
        ),
        (
            "first",
            False,
            "keep",
            False,
            [3.0, 4.0, np.nan, 1.0, 5.0, 2.0, np.nan, np.nan],
        ),
        (
            "first",
            False,
            "keep",
            True,
            [0.6, 0.8, np.nan, 0.2, 1.0, 0.4, np.nan, np.nan],
        ),
        (
            "dense",
            True,
            "keep",
            False,
            [1.0, 1.0, np.nan, 3.0, 1.0, 2.0, np.nan, np.nan],
        ),
        (
            "dense",
            True,
            "keep",
            True,
            [
                1.0 / 3.0,
                1.0 / 3.0,
                np.nan,
                3.0 / 3.0,
                1.0 / 3.0,
                2.0 / 3.0,
                np.nan,
                np.nan,
            ],
        ),
        (
            "dense",
            False,
            "keep",
            False,
            [3.0, 3.0, np.nan, 1.0, 3.0, 2.0, np.nan, np.nan],
        ),
        (
            "dense",
            False,
            "keep",
            True,
            [
                3.0 / 3.0,
                3.0 / 3.0,
                np.nan,
                1.0 / 3.0,
                3.0 / 3.0,
                2.0 / 3.0,
                np.nan,
                np.nan,
            ],
        ),
        ("average", True, "bottom", False, [2.0, 2.0, 7.0, 5.0, 2.0, 4.0, 7.0, 7.0]),
        (
            "average",
            True,
            "bottom",
            True,
            [0.25, 0.25, 0.875, 0.625, 0.25, 0.5, 0.875, 0.875],
        ),
        ("average", False, "bottom", False, [4.0, 4.0, 7.0, 1.0, 4.0, 2.0, 7.0, 7.0]),
        (
            "average",
            False,
            "bottom",
            True,
            [0.5, 0.5, 0.875, 0.125, 0.5, 0.25, 0.875, 0.875],
        ),
        ("min", True, "bottom", False, [1.0, 1.0, 6.0, 5.0, 1.0, 4.0, 6.0, 6.0]),
        (
            "min",
            True,
            "bottom",
            True,
            [0.125, 0.125, 0.75, 0.625, 0.125, 0.5, 0.75, 0.75],
        ),
        ("min", False, "bottom", False, [3.0, 3.0, 6.0, 1.0, 3.0, 2.0, 6.0, 6.0]),
        (
            "min",
            False,
            "bottom",
            True,
            [0.375, 0.375, 0.75, 0.125, 0.375, 0.25, 0.75, 0.75],
        ),
        ("max", True, "bottom", False, [3.0, 3.0, 8.0, 5.0, 3.0, 4.0, 8.0, 8.0]),
        ("max", True, "bottom", True, [0.375, 0.375, 1.0, 0.625, 0.375, 0.5, 1.0, 1.0]),
        ("max", False, "bottom", False, [5.0, 5.0, 8.0, 1.0, 5.0, 2.0, 8.0, 8.0]),
        (
            "max",
            False,
            "bottom",
            True,
            [0.625, 0.625, 1.0, 0.125, 0.625, 0.25, 1.0, 1.0],
        ),
        ("first", True, "bottom", False, [1.0, 2.0, 6.0, 5.0, 3.0, 4.0, 7.0, 8.0]),
        (
            "first",
            True,
            "bottom",
            True,
            [0.125, 0.25, 0.75, 0.625, 0.375, 0.5, 0.875, 1.0],
        ),
        ("first", False, "bottom", False, [3.0, 4.0, 6.0, 1.0, 5.0, 2.0, 7.0, 8.0]),
        (
            "first",
            False,
            "bottom",
            True,
            [0.375, 0.5, 0.75, 0.125, 0.625, 0.25, 0.875, 1.0],
        ),
        ("dense", True, "bottom", False, [1.0, 1.0, 4.0, 3.0, 1.0, 2.0, 4.0, 4.0]),
        ("dense", True, "bottom", True, [0.25, 0.25, 1.0, 0.75, 0.25, 0.5, 1.0, 1.0]),
        ("dense", False, "bottom", False, [3.0, 3.0, 4.0, 1.0, 3.0, 2.0, 4.0, 4.0]),
        ("dense", False, "bottom", True, [0.75, 0.75, 1.0, 0.25, 0.75, 0.5, 1.0, 1.0]),
    ],
)
def test_rank_args_missing(grps, vals, ties_method, ascending, na_option, pct, exp):
    key = np.repeat(grps, len(vals))

    orig_vals = vals
    vals = list(vals) * len(grps)
    if isinstance(orig_vals, np.ndarray):
        vals = np.array(vals, dtype=orig_vals.dtype)

    df = DataFrame({"key": key, "val": vals})
    result = df.groupby("key").rank(
        method=ties_method, ascending=ascending, na_option=na_option, pct=pct
    )

    exp_df = DataFrame(exp * len(grps), columns=["val"])
    tm.assert_frame_equal(result, exp_df)


@pytest.mark.parametrize(
    "pct,exp", [(False, [3.0, 3.0, 3.0, 3.0, 3.0]), (True, [0.6, 0.6, 0.6, 0.6, 0.6])]
)
def test_rank_resets_each_group(pct, exp):
    df = DataFrame(
        {"key": ["a", "a", "a", "a", "a", "b", "b", "b", "b", "b"], "val": [1] * 10}
    )
    result = df.groupby("key").rank(pct=pct)
    exp_df = DataFrame(exp * 2, columns=["val"])
    tm.assert_frame_equal(result, exp_df)


@pytest.mark.parametrize(
    "dtype", ["int64", "int32", "uint64", "uint32", "float64", "float32"]
)
@pytest.mark.parametrize("upper", [True, False])
def test_rank_avg_even_vals(dtype, upper):
    if upper:
        # use IntegerDtype/FloatingDtype
        dtype = dtype[0].upper() + dtype[1:]
        dtype = dtype.replace("Ui", "UI")
    df = DataFrame({"key": ["a"] * 4, "val": [1] * 4})
    df["val"] = df["val"].astype(dtype)
    assert df["val"].dtype == dtype

    result = df.groupby("key").rank()
    exp_df = DataFrame([2.5, 2.5, 2.5, 2.5], columns=["val"])
    if upper:
        exp_df = exp_df.astype("Float64")
    tm.assert_frame_equal(result, exp_df)


@pytest.mark.parametrize("ties_method", ["average", "min", "max", "first", "dense"])
@pytest.mark.parametrize("ascending", [True, False])
@pytest.mark.parametrize("na_option", ["keep", "top", "bottom"])
@pytest.mark.parametrize("pct", [True, False])
@pytest.mark.parametrize(
    "vals", [["bar", "bar", "foo", "bar", "baz"], ["bar", np.nan, "foo", np.nan, "baz"]]
)
def test_rank_object_dtype(ties_method, ascending, na_option, pct, vals):
    df = DataFrame({"key": ["foo"] * 5, "val": vals})
    mask = df["val"].isna()

    gb = df.groupby("key")
    res = gb.rank(method=ties_method, ascending=ascending, na_option=na_option, pct=pct)

    # construct our expected by using numeric values with the same ordering
    if mask.any():
        df2 = DataFrame({"key": ["foo"] * 5, "val": [0, np.nan, 2, np.nan, 1]})
    else:
        df2 = DataFrame({"key": ["foo"] * 5, "val": [0, 0, 2, 0, 1]})

    gb2 = df2.groupby("key")
    alt = gb2.rank(
        method=ties_method, ascending=ascending, na_option=na_option, pct=pct
    )

    tm.assert_frame_equal(res, alt)


@pytest.mark.parametrize("na_option", [True, "bad", 1])
@pytest.mark.parametrize("ties_method", ["average", "min", "max", "first", "dense"])
@pytest.mark.parametrize("ascending", [True, False])
@pytest.mark.parametrize("pct", [True, False])
@pytest.mark.parametrize(
    "vals",
    [
        ["bar", "bar", "foo", "bar", "baz"],
        ["bar", np.nan, "foo", np.nan, "baz"],
        [1, np.nan, 2, np.nan, 3],
    ],
)
def test_rank_naoption_raises(ties_method, ascending, na_option, pct, vals):
    df = DataFrame({"key": ["foo"] * 5, "val": vals})
    msg = "na_option must be one of 'keep', 'top', or 'bottom'"

    with pytest.raises(ValueError, match=msg):
        df.groupby("key").rank(
            method=ties_method, ascending=ascending, na_option=na_option, pct=pct
        )


def test_rank_empty_group():
    # see gh-22519
    column = "A"
    df = DataFrame({"A": [0, 1, 0], "B": [1.0, np.nan, 2.0]})

    result = df.groupby(column).B.rank(pct=True)
    expected = Series([0.5, np.nan, 1.0], name="B")
    tm.assert_series_equal(result, expected)

    result = df.groupby(column).rank(pct=True)
    expected = DataFrame({"B": [0.5, np.nan, 1.0]})
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "input_key,input_value,output_value",
    [
        ([1, 2], [1, 1], [1.0, 1.0]),
        ([1, 1, 2, 2], [1, 2, 1, 2], [0.5, 1.0, 0.5, 1.0]),
        ([1, 1, 2, 2], [1, 2, 1, np.nan], [0.5, 1.0, 1.0, np.nan]),
        ([1, 1, 2], [1, 2, np.nan], [0.5, 1.0, np.nan]),
    ],
)
def test_rank_zero_div(input_key, input_value, output_value):
    # GH 23666
    df = DataFrame({"A": input_key, "B": input_value})

    result = df.groupby("A").rank(method="dense", pct=True)
    expected = DataFrame({"B": output_value})
    tm.assert_frame_equal(result, expected)


def test_rank_min_int():
    # GH-32859
    df = DataFrame(
        {
            "grp": [1, 1, 2],
            "int_col": [
                np.iinfo(np.int64).min,
                np.iinfo(np.int64).max,
                np.iinfo(np.int64).min,
            ],
            "datetimelike": [NaT, datetime(2001, 1, 1), NaT],
        }
    )

    result = df.groupby("grp").rank()
    expected = DataFrame(
        {"int_col": [1.0, 2.0, 1.0], "datetimelike": [np.nan, 1.0, np.nan]}
    )

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("use_nan", [True, False])
def test_rank_pct_equal_values_on_group_transition(use_nan):
    # GH#40518
    fill_value = np.nan if use_nan else 3
    df = DataFrame(
        [
            [-1, 1],
            [-1, 2],
            [1, fill_value],
            [-1, fill_value],
        ],
        columns=["group", "val"],
    )
    result = df.groupby(["group"])["val"].rank(
        method="dense",
        pct=True,
    )
    if use_nan:
        expected = Series([0.5, 1, np.nan, np.nan], name="val")
    else:
        expected = Series([1 / 3, 2 / 3, 1, 1], name="val")

    tm.assert_series_equal(result, expected)


def test_rank_multiindex():
    # GH27721
    df = concat(
        {
            "a": DataFrame({"col1": [3, 4], "col2": [1, 2]}),
            "b": DataFrame({"col3": [5, 6], "col4": [7, 8]}),
        },
        axis=1,
    )

    msg = "DataFrame.groupby with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        gb = df.groupby(level=0, axis=1)
    msg = "DataFrameGroupBy.rank with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = gb.rank(axis=1)

    expected = concat(
        [
            df["a"].rank(axis=1),
            df["b"].rank(axis=1),
        ],
        axis=1,
        keys=["a", "b"],
    )
    tm.assert_frame_equal(result, expected)


def test_groupby_axis0_rank_axis1():
    # GH#41320
    df = DataFrame(
        {0: [1, 3, 5, 7], 1: [2, 4, 6, 8], 2: [1.5, 3.5, 5.5, 7.5]},
        index=["a", "a", "b", "b"],
    )
    msg = "The 'axis' keyword in DataFrame.groupby is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        gb = df.groupby(level=0, axis=0)

    msg = "DataFrameGroupBy.rank with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        res = gb.rank(axis=1)

    # This should match what we get when "manually" operating group-by-group
    expected = concat([df.loc["a"].rank(axis=1), df.loc["b"].rank(axis=1)], axis=0)
    tm.assert_frame_equal(res, expected)

    # check that we haven't accidentally written a case that coincidentally
    # matches rank(axis=0)
    msg = "The 'axis' keyword in DataFrameGroupBy.rank"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        alt = gb.rank(axis=0)
    assert not alt.equals(expected)


def test_groupby_axis0_cummax_axis1():
    # case where groupby axis is 0 and axis keyword in transform is 1

    # df has mixed dtype -> multiple blocks
    df = DataFrame(
        {0: [1, 3, 5, 7], 1: [2, 4, 6, 8], 2: [1.5, 3.5, 5.5, 7.5]},
        index=["a", "a", "b", "b"],
    )
    msg = "The 'axis' keyword in DataFrame.groupby is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        gb = df.groupby(level=0, axis=0)

    msg = "DataFrameGroupBy.cummax with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        cmax = gb.cummax(axis=1)
    expected = df[[0, 1]].astype(np.float64)
    expected[2] = expected[1]
    tm.assert_frame_equal(cmax, expected)


def test_non_unique_index():
    # GH 16577
    df = DataFrame(
        {"A": [1.0, 2.0, 3.0, np.nan], "value": 1.0},
        index=[pd.Timestamp("20170101", tz="US/Eastern")] * 4,
    )
    result = df.groupby([df.index, "A"]).value.rank(ascending=True, pct=True)
    expected = Series(
        [1.0, 1.0, 1.0, np.nan],
        index=[pd.Timestamp("20170101", tz="US/Eastern")] * 4,
        name="value",
    )
    tm.assert_series_equal(result, expected)


def test_rank_categorical():
    cat = pd.Categorical(["a", "a", "b", np.nan, "c", "b"], ordered=True)
    cat2 = pd.Categorical([1, 2, 3, np.nan, 4, 5], ordered=True)

    df = DataFrame({"col1": [0, 1, 0, 1, 0, 1], "col2": cat, "col3": cat2})

    gb = df.groupby("col1")

    res = gb.rank()

    expected = df.astype(object).groupby("col1").rank()
    tm.assert_frame_equal(res, expected)


@pytest.mark.parametrize("na_option", ["top", "bottom"])
def test_groupby_op_with_nullables(na_option):
    # GH 54206
    df = DataFrame({"x": [None]}, dtype="Float64")
    result = df.groupby("x", dropna=False)["x"].rank(method="min", na_option=na_option)
    expected = Series([1.0], dtype="Float64", name=result.name)
    tm.assert_series_equal(result, expected)
