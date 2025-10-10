import numpy as np
import pytest

from pandas import (
    DataFrame,
    Series,
    array as pd_array,
    date_range,
)
import pandas._testing as tm


@pytest.fixture
def df():
    """
    base dataframe for testing
    """
    return DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})


def test_case_when_caselist_is_not_a_list(df):
    """
    Raise ValueError if caselist is not a list.
    """
    msg = "The caselist argument should be a list; "
    msg += "instead got.+"
    with pytest.raises(TypeError, match=msg):  # GH39154
        df["a"].case_when(caselist=())


def test_case_when_no_caselist(df):
    """
    Raise ValueError if no caselist is provided.
    """
    msg = "provide at least one boolean condition, "
    msg += "with a corresponding replacement."
    with pytest.raises(ValueError, match=msg):  # GH39154
        df["a"].case_when([])


def test_case_when_odd_caselist(df):
    """
    Raise ValueError if no of caselist is odd.
    """
    msg = "Argument 0 must have length 2; "
    msg += "a condition and replacement; instead got length 3."

    with pytest.raises(ValueError, match=msg):
        df["a"].case_when([(df["a"].eq(1), 1, df.a.gt(1))])


def test_case_when_raise_error_from_mask(df):
    """
    Raise Error from within Series.mask
    """
    msg = "Failed to apply condition0 and replacement0."
    with pytest.raises(ValueError, match=msg):
        df["a"].case_when([(df["a"].eq(1), [1, 2])])


def test_case_when_single_condition(df):
    """
    Test output on a single condition.
    """
    result = Series([np.nan, np.nan, np.nan]).case_when([(df.a.eq(1), 1)])
    expected = Series([1, np.nan, np.nan])
    tm.assert_series_equal(result, expected)


def test_case_when_multiple_conditions(df):
    """
    Test output when booleans are derived from a computation
    """
    result = Series([np.nan, np.nan, np.nan]).case_when(
        [(df.a.eq(1), 1), (Series([False, True, False]), 2)]
    )
    expected = Series([1, 2, np.nan])
    tm.assert_series_equal(result, expected)


def test_case_when_multiple_conditions_replacement_list(df):
    """
    Test output when replacement is a list
    """
    result = Series([np.nan, np.nan, np.nan]).case_when(
        [([True, False, False], 1), (df["a"].gt(1) & df["b"].eq(5), [1, 2, 3])]
    )
    expected = Series([1, 2, np.nan])
    tm.assert_series_equal(result, expected)


def test_case_when_multiple_conditions_replacement_extension_dtype(df):
    """
    Test output when replacement has an extension dtype
    """
    result = Series([np.nan, np.nan, np.nan]).case_when(
        [
            ([True, False, False], 1),
            (df["a"].gt(1) & df["b"].eq(5), pd_array([1, 2, 3], dtype="Int64")),
        ],
    )
    expected = Series([1, 2, np.nan], dtype="Float64")
    tm.assert_series_equal(result, expected)


def test_case_when_multiple_conditions_replacement_series(df):
    """
    Test output when replacement is a Series
    """
    result = Series([np.nan, np.nan, np.nan]).case_when(
        [
            (np.array([True, False, False]), 1),
            (df["a"].gt(1) & df["b"].eq(5), Series([1, 2, 3])),
        ],
    )
    expected = Series([1, 2, np.nan])
    tm.assert_series_equal(result, expected)


def test_case_when_non_range_index():
    """
    Test output if index is not RangeIndex
    """
    rng = np.random.default_rng(seed=123)
    dates = date_range("1/1/2000", periods=8)
    df = DataFrame(
        rng.standard_normal(size=(8, 4)), index=dates, columns=["A", "B", "C", "D"]
    )
    result = Series(5, index=df.index, name="A").case_when([(df.A.gt(0), df.B)])
    expected = df.A.mask(df.A.gt(0), df.B).where(df.A.gt(0), 5)
    tm.assert_series_equal(result, expected)


def test_case_when_callable():
    """
    Test output on a callable
    """
    # https://numpy.org/doc/stable/reference/generated/numpy.piecewise.html
    x = np.linspace(-2.5, 2.5, 6)
    ser = Series(x)
    result = ser.case_when(
        caselist=[
            (lambda df: df < 0, lambda df: -df),
            (lambda df: df >= 0, lambda df: df),
        ]
    )
    expected = np.piecewise(x, [x < 0, x >= 0], [lambda x: -x, lambda x: x])
    tm.assert_series_equal(result, Series(expected))
