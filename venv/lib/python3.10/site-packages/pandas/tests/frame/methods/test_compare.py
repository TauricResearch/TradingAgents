import numpy as np
import pytest

from pandas.compat.numpy import np_version_gte1p25

import pandas as pd
import pandas._testing as tm


@pytest.mark.parametrize("align_axis", [0, 1, "index", "columns"])
def test_compare_axis(align_axis):
    # GH#30429
    df = pd.DataFrame(
        {"col1": ["a", "b", "c"], "col2": [1.0, 2.0, np.nan], "col3": [1.0, 2.0, 3.0]},
        columns=["col1", "col2", "col3"],
    )
    df2 = df.copy()
    df2.loc[0, "col1"] = "c"
    df2.loc[2, "col3"] = 4.0

    result = df.compare(df2, align_axis=align_axis)

    if align_axis in (1, "columns"):
        indices = pd.Index([0, 2])
        columns = pd.MultiIndex.from_product([["col1", "col3"], ["self", "other"]])
        expected = pd.DataFrame(
            [["a", "c", np.nan, np.nan], [np.nan, np.nan, 3.0, 4.0]],
            index=indices,
            columns=columns,
        )
    else:
        indices = pd.MultiIndex.from_product([[0, 2], ["self", "other"]])
        columns = pd.Index(["col1", "col3"])
        expected = pd.DataFrame(
            [["a", np.nan], ["c", np.nan], [np.nan, 3.0], [np.nan, 4.0]],
            index=indices,
            columns=columns,
        )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "keep_shape, keep_equal",
    [
        (True, False),
        (False, True),
        (True, True),
        # False, False case is already covered in test_compare_axis
    ],
)
def test_compare_various_formats(keep_shape, keep_equal):
    df = pd.DataFrame(
        {"col1": ["a", "b", "c"], "col2": [1.0, 2.0, np.nan], "col3": [1.0, 2.0, 3.0]},
        columns=["col1", "col2", "col3"],
    )
    df2 = df.copy()
    df2.loc[0, "col1"] = "c"
    df2.loc[2, "col3"] = 4.0

    result = df.compare(df2, keep_shape=keep_shape, keep_equal=keep_equal)

    if keep_shape:
        indices = pd.Index([0, 1, 2])
        columns = pd.MultiIndex.from_product(
            [["col1", "col2", "col3"], ["self", "other"]]
        )
        if keep_equal:
            expected = pd.DataFrame(
                [
                    ["a", "c", 1.0, 1.0, 1.0, 1.0],
                    ["b", "b", 2.0, 2.0, 2.0, 2.0],
                    ["c", "c", np.nan, np.nan, 3.0, 4.0],
                ],
                index=indices,
                columns=columns,
            )
        else:
            expected = pd.DataFrame(
                [
                    ["a", "c", np.nan, np.nan, np.nan, np.nan],
                    [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan],
                    [np.nan, np.nan, np.nan, np.nan, 3.0, 4.0],
                ],
                index=indices,
                columns=columns,
            )
    else:
        indices = pd.Index([0, 2])
        columns = pd.MultiIndex.from_product([["col1", "col3"], ["self", "other"]])
        expected = pd.DataFrame(
            [["a", "c", 1.0, 1.0], ["c", "c", 3.0, 4.0]], index=indices, columns=columns
        )
    tm.assert_frame_equal(result, expected)


def test_compare_with_equal_nulls():
    # We want to make sure two NaNs are considered the same
    # and dropped where applicable
    df = pd.DataFrame(
        {"col1": ["a", "b", "c"], "col2": [1.0, 2.0, np.nan], "col3": [1.0, 2.0, 3.0]},
        columns=["col1", "col2", "col3"],
    )
    df2 = df.copy()
    df2.loc[0, "col1"] = "c"

    result = df.compare(df2)
    indices = pd.Index([0])
    columns = pd.MultiIndex.from_product([["col1"], ["self", "other"]])
    expected = pd.DataFrame([["a", "c"]], index=indices, columns=columns)
    tm.assert_frame_equal(result, expected)


def test_compare_with_non_equal_nulls():
    # We want to make sure the relevant NaNs do not get dropped
    # even if the entire row or column are NaNs
    df = pd.DataFrame(
        {"col1": ["a", "b", "c"], "col2": [1.0, 2.0, np.nan], "col3": [1.0, 2.0, 3.0]},
        columns=["col1", "col2", "col3"],
    )
    df2 = df.copy()
    df2.loc[0, "col1"] = "c"
    df2.loc[2, "col3"] = np.nan

    result = df.compare(df2)

    indices = pd.Index([0, 2])
    columns = pd.MultiIndex.from_product([["col1", "col3"], ["self", "other"]])
    expected = pd.DataFrame(
        [["a", "c", np.nan, np.nan], [np.nan, np.nan, 3.0, np.nan]],
        index=indices,
        columns=columns,
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("align_axis", [0, 1])
def test_compare_multi_index(align_axis):
    df = pd.DataFrame(
        {"col1": ["a", "b", "c"], "col2": [1.0, 2.0, np.nan], "col3": [1.0, 2.0, 3.0]}
    )
    df.columns = pd.MultiIndex.from_arrays([["a", "a", "b"], ["col1", "col2", "col3"]])
    df.index = pd.MultiIndex.from_arrays([["x", "x", "y"], [0, 1, 2]])

    df2 = df.copy()
    df2.iloc[0, 0] = "c"
    df2.iloc[2, 2] = 4.0

    result = df.compare(df2, align_axis=align_axis)

    if align_axis == 0:
        indices = pd.MultiIndex.from_arrays(
            [["x", "x", "y", "y"], [0, 0, 2, 2], ["self", "other", "self", "other"]]
        )
        columns = pd.MultiIndex.from_arrays([["a", "b"], ["col1", "col3"]])
        data = [["a", np.nan], ["c", np.nan], [np.nan, 3.0], [np.nan, 4.0]]
    else:
        indices = pd.MultiIndex.from_arrays([["x", "y"], [0, 2]])
        columns = pd.MultiIndex.from_arrays(
            [
                ["a", "a", "b", "b"],
                ["col1", "col1", "col3", "col3"],
                ["self", "other", "self", "other"],
            ]
        )
        data = [["a", "c", np.nan, np.nan], [np.nan, np.nan, 3.0, 4.0]]

    expected = pd.DataFrame(data=data, index=indices, columns=columns)
    tm.assert_frame_equal(result, expected)


def test_compare_unaligned_objects():
    # test DataFrames with different indices
    msg = (
        r"Can only compare identically-labeled \(both index and columns\) DataFrame "
        "objects"
    )
    with pytest.raises(ValueError, match=msg):
        df1 = pd.DataFrame([1, 2, 3], index=["a", "b", "c"])
        df2 = pd.DataFrame([1, 2, 3], index=["a", "b", "d"])
        df1.compare(df2)

    # test DataFrames with different shapes
    msg = (
        r"Can only compare identically-labeled \(both index and columns\) DataFrame "
        "objects"
    )
    with pytest.raises(ValueError, match=msg):
        df1 = pd.DataFrame(np.ones((3, 3)))
        df2 = pd.DataFrame(np.zeros((2, 1)))
        df1.compare(df2)


def test_compare_result_names():
    # GH 44354
    df1 = pd.DataFrame(
        {"col1": ["a", "b", "c"], "col2": [1.0, 2.0, np.nan], "col3": [1.0, 2.0, 3.0]},
    )
    df2 = pd.DataFrame(
        {
            "col1": ["c", "b", "c"],
            "col2": [1.0, 2.0, np.nan],
            "col3": [1.0, 2.0, np.nan],
        },
    )
    result = df1.compare(df2, result_names=("left", "right"))
    expected = pd.DataFrame(
        {
            ("col1", "left"): {0: "a", 2: np.nan},
            ("col1", "right"): {0: "c", 2: np.nan},
            ("col3", "left"): {0: np.nan, 2: 3.0},
            ("col3", "right"): {0: np.nan, 2: np.nan},
        }
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "result_names",
    [
        [1, 2],
        "HK",
        {"2": 2, "3": 3},
        3,
        3.0,
    ],
)
def test_invalid_input_result_names(result_names):
    # GH 44354
    df1 = pd.DataFrame(
        {"col1": ["a", "b", "c"], "col2": [1.0, 2.0, np.nan], "col3": [1.0, 2.0, 3.0]},
    )
    df2 = pd.DataFrame(
        {
            "col1": ["c", "b", "c"],
            "col2": [1.0, 2.0, np.nan],
            "col3": [1.0, 2.0, np.nan],
        },
    )
    with pytest.raises(
        TypeError,
        match=(
            f"Passing 'result_names' as a {type(result_names)} is not "
            "supported. Provide 'result_names' as a tuple instead."
        ),
    ):
        df1.compare(df2, result_names=result_names)


@pytest.mark.parametrize(
    "val1,val2",
    [(4, pd.NA), (pd.NA, pd.NA), (pd.NA, 4)],
)
def test_compare_ea_and_np_dtype(val1, val2):
    # GH 48966
    arr = [4.0, val1]
    ser = pd.Series([1, val2], dtype="Int64")

    df1 = pd.DataFrame({"a": arr, "b": [1.0, 2]})
    df2 = pd.DataFrame({"a": ser, "b": [1.0, 2]})
    expected = pd.DataFrame(
        {
            ("a", "self"): arr,
            ("a", "other"): ser,
            ("b", "self"): np.nan,
            ("b", "other"): np.nan,
        }
    )
    if val1 is pd.NA and val2 is pd.NA:
        # GH#18463 TODO: is this really the desired behavior?
        expected.loc[1, ("a", "self")] = np.nan

    if val1 is pd.NA and np_version_gte1p25:
        # can't compare with numpy array if it contains pd.NA
        with pytest.raises(TypeError, match="boolean value of NA is ambiguous"):
            result = df1.compare(df2, keep_shape=True)
    else:
        result = df1.compare(df2, keep_shape=True)
        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "df1_val,df2_val,diff_self,diff_other",
    [
        (4, 3, 4, 3),
        (4, 4, pd.NA, pd.NA),
        (4, pd.NA, 4, pd.NA),
        (pd.NA, pd.NA, pd.NA, pd.NA),
    ],
)
def test_compare_nullable_int64_dtype(df1_val, df2_val, diff_self, diff_other):
    # GH 48966
    df1 = pd.DataFrame({"a": pd.Series([df1_val, pd.NA], dtype="Int64"), "b": [1.0, 2]})
    df2 = df1.copy()
    df2.loc[0, "a"] = df2_val

    expected = pd.DataFrame(
        {
            ("a", "self"): pd.Series([diff_self, pd.NA], dtype="Int64"),
            ("a", "other"): pd.Series([diff_other, pd.NA], dtype="Int64"),
            ("b", "self"): np.nan,
            ("b", "other"): np.nan,
        }
    )
    result = df1.compare(df2, keep_shape=True)
    tm.assert_frame_equal(result, expected)
