import numpy as np

from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    RangeIndex,
    Series,
)
import pandas._testing as tm
from pandas.tests.copy_view.util import get_array

# -----------------------------------------------------------------------------
# Copy/view behaviour for the values that are set in a DataFrame


def test_set_column_with_array():
    # Case: setting an array as a new column (df[col] = arr) copies that data
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    arr = np.array([1, 2, 3], dtype="int64")

    df["c"] = arr

    # the array data is copied
    assert not np.shares_memory(get_array(df, "c"), arr)
    # and thus modifying the array does not modify the DataFrame
    arr[0] = 0
    tm.assert_series_equal(df["c"], Series([1, 2, 3], name="c"))


def test_set_column_with_series(using_copy_on_write):
    # Case: setting a series as a new column (df[col] = s) copies that data
    # (with delayed copy with CoW)
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    ser = Series([1, 2, 3])

    df["c"] = ser

    if using_copy_on_write:
        assert np.shares_memory(get_array(df, "c"), get_array(ser))
    else:
        # the series data is copied
        assert not np.shares_memory(get_array(df, "c"), get_array(ser))

    # and modifying the series does not modify the DataFrame
    ser.iloc[0] = 0
    assert ser.iloc[0] == 0
    tm.assert_series_equal(df["c"], Series([1, 2, 3], name="c"))


def test_set_column_with_index(using_copy_on_write):
    # Case: setting an index as a new column (df[col] = idx) copies that data
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    idx = Index([1, 2, 3])

    df["c"] = idx

    # the index data is copied
    assert not np.shares_memory(get_array(df, "c"), idx.values)

    idx = RangeIndex(1, 4)
    arr = idx.values

    df["d"] = idx

    assert not np.shares_memory(get_array(df, "d"), arr)


def test_set_columns_with_dataframe(using_copy_on_write):
    # Case: setting a DataFrame as new columns copies that data
    # (with delayed copy with CoW)
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    df2 = DataFrame({"c": [7, 8, 9], "d": [10, 11, 12]})

    df[["c", "d"]] = df2

    if using_copy_on_write:
        assert np.shares_memory(get_array(df, "c"), get_array(df2, "c"))
    else:
        # the data is copied
        assert not np.shares_memory(get_array(df, "c"), get_array(df2, "c"))

    # and modifying the set DataFrame does not modify the original DataFrame
    df2.iloc[0, 0] = 0
    tm.assert_series_equal(df["c"], Series([7, 8, 9], name="c"))


def test_setitem_series_no_copy(using_copy_on_write):
    # Case: setting a Series as column into a DataFrame can delay copying that data
    df = DataFrame({"a": [1, 2, 3]})
    rhs = Series([4, 5, 6])
    rhs_orig = rhs.copy()

    # adding a new column
    df["b"] = rhs
    if using_copy_on_write:
        assert np.shares_memory(get_array(rhs), get_array(df, "b"))

    df.iloc[0, 1] = 100
    tm.assert_series_equal(rhs, rhs_orig)


def test_setitem_series_no_copy_single_block(using_copy_on_write):
    # Overwriting an existing column that is a single block
    df = DataFrame({"a": [1, 2, 3], "b": [0.1, 0.2, 0.3]})
    rhs = Series([4, 5, 6])
    rhs_orig = rhs.copy()

    df["a"] = rhs
    if using_copy_on_write:
        assert np.shares_memory(get_array(rhs), get_array(df, "a"))

    df.iloc[0, 0] = 100
    tm.assert_series_equal(rhs, rhs_orig)


def test_setitem_series_no_copy_split_block(using_copy_on_write):
    # Overwriting an existing column that is part of a larger block
    df = DataFrame({"a": [1, 2, 3], "b": 1})
    rhs = Series([4, 5, 6])
    rhs_orig = rhs.copy()

    df["b"] = rhs
    if using_copy_on_write:
        assert np.shares_memory(get_array(rhs), get_array(df, "b"))

    df.iloc[0, 1] = 100
    tm.assert_series_equal(rhs, rhs_orig)


def test_setitem_series_column_midx_broadcasting(using_copy_on_write):
    # Setting a Series to multiple columns will repeat the data
    # (currently copying the data eagerly)
    df = DataFrame(
        [[1, 2, 3], [3, 4, 5]],
        columns=MultiIndex.from_arrays([["a", "a", "b"], [1, 2, 3]]),
    )
    rhs = Series([10, 11])
    df["a"] = rhs
    assert not np.shares_memory(get_array(rhs), df._get_column_array(0))
    if using_copy_on_write:
        assert df._mgr._has_no_reference(0)


def test_set_column_with_inplace_operator(using_copy_on_write, warn_copy_on_write):
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

    # this should not raise any warning
    with tm.assert_produces_warning(None):
        df["a"] += 1

    # when it is not in a chain, then it should produce a warning
    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    ser = df["a"]
    with tm.assert_cow_warning(warn_copy_on_write):
        ser += 1
