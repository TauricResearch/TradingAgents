import pytest

from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm
from pandas.core.reshape.merge import (
    MergeError,
    merge,
)


@pytest.mark.parametrize(
    ("input_col", "output_cols"), [("b", ["a", "b"]), ("a", ["a_x", "a_y"])]
)
def test_merge_cross(input_col, output_cols):
    # GH#5401
    left = DataFrame({"a": [1, 3]})
    right = DataFrame({input_col: [3, 4]})
    left_copy = left.copy()
    right_copy = right.copy()
    result = merge(left, right, how="cross")
    expected = DataFrame({output_cols[0]: [1, 1, 3, 3], output_cols[1]: [3, 4, 3, 4]})
    tm.assert_frame_equal(result, expected)
    tm.assert_frame_equal(left, left_copy)
    tm.assert_frame_equal(right, right_copy)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"left_index": True},
        {"right_index": True},
        {"on": "a"},
        {"left_on": "a"},
        {"right_on": "b"},
    ],
)
def test_merge_cross_error_reporting(kwargs):
    # GH#5401
    left = DataFrame({"a": [1, 3]})
    right = DataFrame({"b": [3, 4]})
    msg = (
        "Can not pass on, right_on, left_on or set right_index=True or "
        "left_index=True"
    )
    with pytest.raises(MergeError, match=msg):
        merge(left, right, how="cross", **kwargs)


def test_merge_cross_mixed_dtypes():
    # GH#5401
    left = DataFrame(["a", "b", "c"], columns=["A"])
    right = DataFrame(range(2), columns=["B"])
    result = merge(left, right, how="cross")
    expected = DataFrame({"A": ["a", "a", "b", "b", "c", "c"], "B": [0, 1, 0, 1, 0, 1]})
    tm.assert_frame_equal(result, expected)


def test_merge_cross_more_than_one_column():
    # GH#5401
    left = DataFrame({"A": list("ab"), "B": [2, 1]})
    right = DataFrame({"C": range(2), "D": range(4, 6)})
    result = merge(left, right, how="cross")
    expected = DataFrame(
        {
            "A": ["a", "a", "b", "b"],
            "B": [2, 2, 1, 1],
            "C": [0, 1, 0, 1],
            "D": [4, 5, 4, 5],
        }
    )
    tm.assert_frame_equal(result, expected)


def test_merge_cross_null_values(nulls_fixture):
    # GH#5401
    left = DataFrame({"a": [1, nulls_fixture]})
    right = DataFrame({"b": ["a", "b"], "c": [1.0, 2.0]})
    result = merge(left, right, how="cross")
    expected = DataFrame(
        {
            "a": [1, 1, nulls_fixture, nulls_fixture],
            "b": ["a", "b", "a", "b"],
            "c": [1.0, 2.0, 1.0, 2.0],
        }
    )
    tm.assert_frame_equal(result, expected)


def test_join_cross_error_reporting():
    # GH#5401
    left = DataFrame({"a": [1, 3]})
    right = DataFrame({"a": [3, 4]})
    msg = (
        "Can not pass on, right_on, left_on or set right_index=True or "
        "left_index=True"
    )
    with pytest.raises(MergeError, match=msg):
        left.join(right, how="cross", on="a")


def test_merge_cross_series():
    # GH#54055
    ls = Series([1, 2, 3, 4], index=[1, 2, 3, 4], name="left")
    rs = Series([3, 4, 5, 6], index=[3, 4, 5, 6], name="right")
    res = merge(ls, rs, how="cross")

    expected = merge(ls.to_frame(), rs.to_frame(), how="cross")
    tm.assert_frame_equal(res, expected)
