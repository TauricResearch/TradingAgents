import numpy as np
import pytest

from pandas._libs import lib

import pandas as pd
from pandas import (
    Index,
    MultiIndex,
)
import pandas._testing as tm


@pytest.mark.parametrize(
    "input_index, input_columns, input_values, "
    "expected_values, expected_columns, expected_index",
    [
        (
            ["lev4"],
            "lev3",
            "values",
            [
                [0.0, np.nan],
                [np.nan, 1.0],
                [2.0, np.nan],
                [np.nan, 3.0],
                [4.0, np.nan],
                [np.nan, 5.0],
                [6.0, np.nan],
                [np.nan, 7.0],
            ],
            Index([1, 2], name="lev3"),
            Index([1, 2, 3, 4, 5, 6, 7, 8], name="lev4"),
        ),
        (
            ["lev4"],
            "lev3",
            lib.no_default,
            [
                [1.0, np.nan, 1.0, np.nan, 0.0, np.nan],
                [np.nan, 1.0, np.nan, 1.0, np.nan, 1.0],
                [1.0, np.nan, 2.0, np.nan, 2.0, np.nan],
                [np.nan, 1.0, np.nan, 2.0, np.nan, 3.0],
                [2.0, np.nan, 1.0, np.nan, 4.0, np.nan],
                [np.nan, 2.0, np.nan, 1.0, np.nan, 5.0],
                [2.0, np.nan, 2.0, np.nan, 6.0, np.nan],
                [np.nan, 2.0, np.nan, 2.0, np.nan, 7.0],
            ],
            MultiIndex.from_tuples(
                [
                    ("lev1", 1),
                    ("lev1", 2),
                    ("lev2", 1),
                    ("lev2", 2),
                    ("values", 1),
                    ("values", 2),
                ],
                names=[None, "lev3"],
            ),
            Index([1, 2, 3, 4, 5, 6, 7, 8], name="lev4"),
        ),
        (
            ["lev1", "lev2"],
            "lev3",
            "values",
            [[0, 1], [2, 3], [4, 5], [6, 7]],
            Index([1, 2], name="lev3"),
            MultiIndex.from_tuples(
                [(1, 1), (1, 2), (2, 1), (2, 2)], names=["lev1", "lev2"]
            ),
        ),
        (
            ["lev1", "lev2"],
            "lev3",
            lib.no_default,
            [[1, 2, 0, 1], [3, 4, 2, 3], [5, 6, 4, 5], [7, 8, 6, 7]],
            MultiIndex.from_tuples(
                [("lev4", 1), ("lev4", 2), ("values", 1), ("values", 2)],
                names=[None, "lev3"],
            ),
            MultiIndex.from_tuples(
                [(1, 1), (1, 2), (2, 1), (2, 2)], names=["lev1", "lev2"]
            ),
        ),
    ],
)
def test_pivot_list_like_index(
    input_index,
    input_columns,
    input_values,
    expected_values,
    expected_columns,
    expected_index,
):
    # GH 21425, test when index is given a list
    df = pd.DataFrame(
        {
            "lev1": [1, 1, 1, 1, 2, 2, 2, 2],
            "lev2": [1, 1, 2, 2, 1, 1, 2, 2],
            "lev3": [1, 2, 1, 2, 1, 2, 1, 2],
            "lev4": [1, 2, 3, 4, 5, 6, 7, 8],
            "values": [0, 1, 2, 3, 4, 5, 6, 7],
        }
    )

    result = df.pivot(index=input_index, columns=input_columns, values=input_values)
    expected = pd.DataFrame(
        expected_values, columns=expected_columns, index=expected_index
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "input_index, input_columns, input_values, "
    "expected_values, expected_columns, expected_index",
    [
        (
            "lev4",
            ["lev3"],
            "values",
            [
                [0.0, np.nan],
                [np.nan, 1.0],
                [2.0, np.nan],
                [np.nan, 3.0],
                [4.0, np.nan],
                [np.nan, 5.0],
                [6.0, np.nan],
                [np.nan, 7.0],
            ],
            Index([1, 2], name="lev3"),
            Index([1, 2, 3, 4, 5, 6, 7, 8], name="lev4"),
        ),
        (
            ["lev1", "lev2"],
            ["lev3"],
            "values",
            [[0, 1], [2, 3], [4, 5], [6, 7]],
            Index([1, 2], name="lev3"),
            MultiIndex.from_tuples(
                [(1, 1), (1, 2), (2, 1), (2, 2)], names=["lev1", "lev2"]
            ),
        ),
        (
            ["lev1"],
            ["lev2", "lev3"],
            "values",
            [[0, 1, 2, 3], [4, 5, 6, 7]],
            MultiIndex.from_tuples(
                [(1, 1), (1, 2), (2, 1), (2, 2)], names=["lev2", "lev3"]
            ),
            Index([1, 2], name="lev1"),
        ),
        (
            ["lev1", "lev2"],
            ["lev3", "lev4"],
            "values",
            [
                [0.0, 1.0, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan],
                [np.nan, np.nan, 2.0, 3.0, np.nan, np.nan, np.nan, np.nan],
                [np.nan, np.nan, np.nan, np.nan, 4.0, 5.0, np.nan, np.nan],
                [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, 6.0, 7.0],
            ],
            MultiIndex.from_tuples(
                [(1, 1), (2, 2), (1, 3), (2, 4), (1, 5), (2, 6), (1, 7), (2, 8)],
                names=["lev3", "lev4"],
            ),
            MultiIndex.from_tuples(
                [(1, 1), (1, 2), (2, 1), (2, 2)], names=["lev1", "lev2"]
            ),
        ),
    ],
)
def test_pivot_list_like_columns(
    input_index,
    input_columns,
    input_values,
    expected_values,
    expected_columns,
    expected_index,
):
    # GH 21425, test when columns is given a list
    df = pd.DataFrame(
        {
            "lev1": [1, 1, 1, 1, 2, 2, 2, 2],
            "lev2": [1, 1, 2, 2, 1, 1, 2, 2],
            "lev3": [1, 2, 1, 2, 1, 2, 1, 2],
            "lev4": [1, 2, 3, 4, 5, 6, 7, 8],
            "values": [0, 1, 2, 3, 4, 5, 6, 7],
        }
    )

    result = df.pivot(index=input_index, columns=input_columns, values=input_values)
    expected = pd.DataFrame(
        expected_values, columns=expected_columns, index=expected_index
    )
    tm.assert_frame_equal(result, expected)


def test_pivot_multiindexed_rows_and_cols(using_array_manager):
    # GH 36360

    df = pd.DataFrame(
        data=np.arange(12).reshape(4, 3),
        columns=MultiIndex.from_tuples(
            [(0, 0), (0, 1), (0, 2)], names=["col_L0", "col_L1"]
        ),
        index=MultiIndex.from_tuples(
            [(0, 0, 0), (0, 0, 1), (1, 1, 1), (1, 0, 0)],
            names=["idx_L0", "idx_L1", "idx_L2"],
        ),
    )

    res = df.pivot_table(
        index=["idx_L0"],
        columns=["idx_L1"],
        values=[(0, 1)],
        aggfunc=lambda col: col.values.sum(),
    )

    expected = pd.DataFrame(
        data=[[5, np.nan], [10, 7.0]],
        columns=MultiIndex.from_tuples(
            [(0, 1, 0), (0, 1, 1)], names=["col_L0", "col_L1", "idx_L1"]
        ),
        index=Index([0, 1], dtype="int64", name="idx_L0"),
    )
    if not using_array_manager:
        # BlockManager does not preserve the dtypes
        expected = expected.astype("float64")

    tm.assert_frame_equal(res, expected)


def test_pivot_df_multiindex_index_none():
    # GH 23955
    df = pd.DataFrame(
        [
            ["A", "A1", "label1", 1],
            ["A", "A2", "label2", 2],
            ["B", "A1", "label1", 3],
            ["B", "A2", "label2", 4],
        ],
        columns=["index_1", "index_2", "label", "value"],
    )
    df = df.set_index(["index_1", "index_2"])

    result = df.pivot(columns="label", values="value")
    expected = pd.DataFrame(
        [[1.0, np.nan], [np.nan, 2.0], [3.0, np.nan], [np.nan, 4.0]],
        index=df.index,
        columns=Index(["label1", "label2"], name="label"),
    )
    tm.assert_frame_equal(result, expected)
