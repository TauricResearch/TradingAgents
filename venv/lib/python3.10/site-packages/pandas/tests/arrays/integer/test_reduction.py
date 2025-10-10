import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Series,
    array,
)
import pandas._testing as tm


@pytest.mark.parametrize(
    "op, expected",
    [
        ["sum", np.int64(3)],
        ["prod", np.int64(2)],
        ["min", np.int64(1)],
        ["max", np.int64(2)],
        ["mean", np.float64(1.5)],
        ["median", np.float64(1.5)],
        ["var", np.float64(0.5)],
        ["std", np.float64(0.5**0.5)],
        ["skew", pd.NA],
        ["kurt", pd.NA],
        ["any", True],
        ["all", True],
    ],
)
def test_series_reductions(op, expected):
    ser = Series([1, 2], dtype="Int64")
    result = getattr(ser, op)()
    tm.assert_equal(result, expected)


@pytest.mark.parametrize(
    "op, expected",
    [
        ["sum", Series([3], index=["a"], dtype="Int64")],
        ["prod", Series([2], index=["a"], dtype="Int64")],
        ["min", Series([1], index=["a"], dtype="Int64")],
        ["max", Series([2], index=["a"], dtype="Int64")],
        ["mean", Series([1.5], index=["a"], dtype="Float64")],
        ["median", Series([1.5], index=["a"], dtype="Float64")],
        ["var", Series([0.5], index=["a"], dtype="Float64")],
        ["std", Series([0.5**0.5], index=["a"], dtype="Float64")],
        ["skew", Series([pd.NA], index=["a"], dtype="Float64")],
        ["kurt", Series([pd.NA], index=["a"], dtype="Float64")],
        ["any", Series([True], index=["a"], dtype="boolean")],
        ["all", Series([True], index=["a"], dtype="boolean")],
    ],
)
def test_dataframe_reductions(op, expected):
    df = DataFrame({"a": array([1, 2], dtype="Int64")})
    result = getattr(df, op)()
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "op, expected",
    [
        ["sum", array([1, 3], dtype="Int64")],
        ["prod", array([1, 3], dtype="Int64")],
        ["min", array([1, 3], dtype="Int64")],
        ["max", array([1, 3], dtype="Int64")],
        ["mean", array([1, 3], dtype="Float64")],
        ["median", array([1, 3], dtype="Float64")],
        ["var", array([pd.NA], dtype="Float64")],
        ["std", array([pd.NA], dtype="Float64")],
        ["skew", array([pd.NA], dtype="Float64")],
        ["any", array([True, True], dtype="boolean")],
        ["all", array([True, True], dtype="boolean")],
    ],
)
def test_groupby_reductions(op, expected):
    df = DataFrame(
        {
            "A": ["a", "b", "b"],
            "B": array([1, None, 3], dtype="Int64"),
        }
    )
    result = getattr(df.groupby("A"), op)()
    expected = DataFrame(expected, index=pd.Index(["a", "b"], name="A"), columns=["B"])

    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "op, expected",
    [
        ["sum", Series([4, 4], index=["B", "C"], dtype="Float64")],
        ["prod", Series([3, 3], index=["B", "C"], dtype="Float64")],
        ["min", Series([1, 1], index=["B", "C"], dtype="Float64")],
        ["max", Series([3, 3], index=["B", "C"], dtype="Float64")],
        ["mean", Series([2, 2], index=["B", "C"], dtype="Float64")],
        ["median", Series([2, 2], index=["B", "C"], dtype="Float64")],
        ["var", Series([2, 2], index=["B", "C"], dtype="Float64")],
        ["std", Series([2**0.5, 2**0.5], index=["B", "C"], dtype="Float64")],
        ["skew", Series([pd.NA, pd.NA], index=["B", "C"], dtype="Float64")],
        ["kurt", Series([pd.NA, pd.NA], index=["B", "C"], dtype="Float64")],
        ["any", Series([True, True, True], index=["A", "B", "C"], dtype="boolean")],
        ["all", Series([True, True, True], index=["A", "B", "C"], dtype="boolean")],
    ],
)
def test_mixed_reductions(op, expected):
    df = DataFrame(
        {
            "A": ["a", "b", "b"],
            "B": [1, None, 3],
            "C": array([1, None, 3], dtype="Int64"),
        }
    )

    # series
    result = getattr(df.C, op)()
    tm.assert_equal(result, expected["C"])

    # frame
    if op in ["any", "all"]:
        result = getattr(df, op)()
    else:
        result = getattr(df, op)(numeric_only=True)
    tm.assert_series_equal(result, expected)
