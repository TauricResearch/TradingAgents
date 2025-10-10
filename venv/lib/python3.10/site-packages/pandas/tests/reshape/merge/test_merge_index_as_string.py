import numpy as np
import pytest

from pandas import DataFrame
import pandas._testing as tm


@pytest.fixture
def df1():
    return DataFrame(
        {
            "outer": [1, 1, 1, 2, 2, 2, 2, 3, 3, 4, 4],
            "inner": [1, 2, 3, 1, 2, 3, 4, 1, 2, 1, 2],
            "v1": np.linspace(0, 1, 11),
        }
    )


@pytest.fixture
def df2():
    return DataFrame(
        {
            "outer": [1, 1, 1, 1, 1, 1, 2, 2, 3, 3, 3, 3],
            "inner": [1, 2, 2, 3, 3, 4, 2, 3, 1, 1, 2, 3],
            "v2": np.linspace(10, 11, 12),
        }
    )


@pytest.fixture(params=[[], ["outer"], ["outer", "inner"]])
def left_df(request, df1):
    """Construct left test DataFrame with specified levels
    (any of 'outer', 'inner', and 'v1')
    """
    levels = request.param
    if levels:
        df1 = df1.set_index(levels)

    return df1


@pytest.fixture(params=[[], ["outer"], ["outer", "inner"]])
def right_df(request, df2):
    """Construct right test DataFrame with specified levels
    (any of 'outer', 'inner', and 'v2')
    """
    levels = request.param

    if levels:
        df2 = df2.set_index(levels)

    return df2


def compute_expected(df_left, df_right, on=None, left_on=None, right_on=None, how=None):
    """
    Compute the expected merge result for the test case.

    This method computes the expected result of merging two DataFrames on
    a combination of their columns and index levels. It does so by
    explicitly dropping/resetting their named index levels, performing a
    merge on their columns, and then finally restoring the appropriate
    index in the result.

    Parameters
    ----------
    df_left : DataFrame
        The left DataFrame (may have zero or more named index levels)
    df_right : DataFrame
        The right DataFrame (may have zero or more named index levels)
    on : list of str
        The on parameter to the merge operation
    left_on : list of str
        The left_on parameter to the merge operation
    right_on : list of str
        The right_on parameter to the merge operation
    how : str
        The how parameter to the merge operation

    Returns
    -------
    DataFrame
        The expected merge result
    """
    # Handle on param if specified
    if on is not None:
        left_on, right_on = on, on

    # Compute input named index levels
    left_levels = [n for n in df_left.index.names if n is not None]
    right_levels = [n for n in df_right.index.names if n is not None]

    # Compute output named index levels
    output_levels = [i for i in left_on if i in right_levels and i in left_levels]

    # Drop index levels that aren't involved in the merge
    drop_left = [n for n in left_levels if n not in left_on]
    if drop_left:
        df_left = df_left.reset_index(drop_left, drop=True)

    drop_right = [n for n in right_levels if n not in right_on]
    if drop_right:
        df_right = df_right.reset_index(drop_right, drop=True)

    # Convert remaining index levels to columns
    reset_left = [n for n in left_levels if n in left_on]
    if reset_left:
        df_left = df_left.reset_index(level=reset_left)

    reset_right = [n for n in right_levels if n in right_on]
    if reset_right:
        df_right = df_right.reset_index(level=reset_right)

    # Perform merge
    expected = df_left.merge(df_right, left_on=left_on, right_on=right_on, how=how)

    # Restore index levels
    if output_levels:
        expected = expected.set_index(output_levels)

    return expected


@pytest.mark.parametrize(
    "on,how",
    [
        (["outer"], "inner"),
        (["inner"], "left"),
        (["outer", "inner"], "right"),
        (["inner", "outer"], "outer"),
    ],
)
def test_merge_indexes_and_columns_on(left_df, right_df, on, how):
    # Construct expected result
    expected = compute_expected(left_df, right_df, on=on, how=how)

    # Perform merge
    result = left_df.merge(right_df, on=on, how=how)
    tm.assert_frame_equal(result, expected, check_like=True)


@pytest.mark.parametrize(
    "left_on,right_on,how",
    [
        (["outer"], ["outer"], "inner"),
        (["inner"], ["inner"], "right"),
        (["outer", "inner"], ["outer", "inner"], "left"),
        (["inner", "outer"], ["inner", "outer"], "outer"),
    ],
)
def test_merge_indexes_and_columns_lefton_righton(
    left_df, right_df, left_on, right_on, how
):
    # Construct expected result
    expected = compute_expected(
        left_df, right_df, left_on=left_on, right_on=right_on, how=how
    )

    # Perform merge
    result = left_df.merge(right_df, left_on=left_on, right_on=right_on, how=how)
    tm.assert_frame_equal(result, expected, check_like=True)


@pytest.mark.parametrize("left_index", ["inner", ["inner", "outer"]])
def test_join_indexes_and_columns_on(df1, df2, left_index, join_type):
    # Construct left_df
    left_df = df1.set_index(left_index)

    # Construct right_df
    right_df = df2.set_index(["outer", "inner"])

    # Result
    expected = (
        left_df.reset_index()
        .join(
            right_df, on=["outer", "inner"], how=join_type, lsuffix="_x", rsuffix="_y"
        )
        .set_index(left_index)
    )

    # Perform join
    result = left_df.join(
        right_df, on=["outer", "inner"], how=join_type, lsuffix="_x", rsuffix="_y"
    )

    tm.assert_frame_equal(result, expected, check_like=True)
