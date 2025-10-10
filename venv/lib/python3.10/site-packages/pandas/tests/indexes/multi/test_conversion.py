import numpy as np
import pytest

from pandas.compat.numpy import np_version_gt2

import pandas as pd
from pandas import (
    DataFrame,
    MultiIndex,
)
import pandas._testing as tm


def test_to_numpy(idx):
    result = idx.to_numpy()
    exp = idx.values
    tm.assert_numpy_array_equal(result, exp)


def test_array_interface(idx):
    # https://github.com/pandas-dev/pandas/pull/60046
    result = np.asarray(idx)
    expected = np.empty((6,), dtype=object)
    expected[:] = [
        ("foo", "one"),
        ("foo", "two"),
        ("bar", "one"),
        ("baz", "two"),
        ("qux", "one"),
        ("qux", "two"),
    ]
    tm.assert_numpy_array_equal(result, expected)

    # it always gives a copy by default, but the values are cached, so results
    # are still sharing memory
    result_copy1 = np.asarray(idx)
    result_copy2 = np.asarray(idx)
    assert np.may_share_memory(result_copy1, result_copy2)

    # with explicit copy=True, then it is an actual copy
    result_copy1 = np.array(idx, copy=True)
    result_copy2 = np.array(idx, copy=True)
    assert not np.may_share_memory(result_copy1, result_copy2)

    if not np_version_gt2:
        # copy=False semantics are only supported in NumPy>=2.
        return

    # for MultiIndex, copy=False is never allowed
    msg = "Starting with NumPy 2.0, the behavior of the 'copy' keyword has changed"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        np.array(idx, copy=False)


def test_to_frame():
    tuples = [(1, "one"), (1, "two"), (2, "one"), (2, "two")]

    index = MultiIndex.from_tuples(tuples)
    result = index.to_frame(index=False)
    expected = DataFrame(tuples)
    tm.assert_frame_equal(result, expected)

    result = index.to_frame()
    expected.index = index
    tm.assert_frame_equal(result, expected)

    tuples = [(1, "one"), (1, "two"), (2, "one"), (2, "two")]
    index = MultiIndex.from_tuples(tuples, names=["first", "second"])
    result = index.to_frame(index=False)
    expected = DataFrame(tuples)
    expected.columns = ["first", "second"]
    tm.assert_frame_equal(result, expected)

    result = index.to_frame()
    expected.index = index
    tm.assert_frame_equal(result, expected)

    # See GH-22580
    index = MultiIndex.from_tuples(tuples)
    result = index.to_frame(index=False, name=["first", "second"])
    expected = DataFrame(tuples)
    expected.columns = ["first", "second"]
    tm.assert_frame_equal(result, expected)

    result = index.to_frame(name=["first", "second"])
    expected.index = index
    expected.columns = ["first", "second"]
    tm.assert_frame_equal(result, expected)

    msg = "'name' must be a list / sequence of column names."
    with pytest.raises(TypeError, match=msg):
        index.to_frame(name="first")

    msg = "'name' should have same length as number of levels on index."
    with pytest.raises(ValueError, match=msg):
        index.to_frame(name=["first"])

    # Tests for datetime index
    index = MultiIndex.from_product([range(5), pd.date_range("20130101", periods=3)])
    result = index.to_frame(index=False)
    expected = DataFrame(
        {
            0: np.repeat(np.arange(5, dtype="int64"), 3),
            1: np.tile(pd.date_range("20130101", periods=3), 5),
        }
    )
    tm.assert_frame_equal(result, expected)

    result = index.to_frame()
    expected.index = index
    tm.assert_frame_equal(result, expected)

    # See GH-22580
    result = index.to_frame(index=False, name=["first", "second"])
    expected = DataFrame(
        {
            "first": np.repeat(np.arange(5, dtype="int64"), 3),
            "second": np.tile(pd.date_range("20130101", periods=3), 5),
        }
    )
    tm.assert_frame_equal(result, expected)

    result = index.to_frame(name=["first", "second"])
    expected.index = index
    tm.assert_frame_equal(result, expected)


def test_to_frame_dtype_fidelity():
    # GH 22420
    mi = MultiIndex.from_arrays(
        [
            pd.date_range("19910905", periods=6, tz="US/Eastern"),
            [1, 1, 1, 2, 2, 2],
            pd.Categorical(["a", "a", "b", "b", "c", "c"], ordered=True),
            ["x", "x", "y", "z", "x", "y"],
        ],
        names=["dates", "a", "b", "c"],
    )
    original_dtypes = {name: mi.levels[i].dtype for i, name in enumerate(mi.names)}

    expected_df = DataFrame(
        {
            "dates": pd.date_range("19910905", periods=6, tz="US/Eastern"),
            "a": [1, 1, 1, 2, 2, 2],
            "b": pd.Categorical(["a", "a", "b", "b", "c", "c"], ordered=True),
            "c": ["x", "x", "y", "z", "x", "y"],
        }
    )
    df = mi.to_frame(index=False)
    df_dtypes = df.dtypes.to_dict()

    tm.assert_frame_equal(df, expected_df)
    assert original_dtypes == df_dtypes


def test_to_frame_resulting_column_order():
    # GH 22420
    expected = ["z", 0, "a"]
    mi = MultiIndex.from_arrays(
        [["a", "b", "c"], ["x", "y", "z"], ["q", "w", "e"]], names=expected
    )
    result = mi.to_frame().columns.tolist()
    assert result == expected


def test_to_frame_duplicate_labels():
    # GH 45245
    data = [(1, 2), (3, 4)]
    names = ["a", "a"]
    index = MultiIndex.from_tuples(data, names=names)
    with pytest.raises(ValueError, match="Cannot create duplicate column labels"):
        index.to_frame()

    result = index.to_frame(allow_duplicates=True)
    expected = DataFrame(data, index=index, columns=names)
    tm.assert_frame_equal(result, expected)

    names = [None, 0]
    index = MultiIndex.from_tuples(data, names=names)
    with pytest.raises(ValueError, match="Cannot create duplicate column labels"):
        index.to_frame()

    result = index.to_frame(allow_duplicates=True)
    expected = DataFrame(data, index=index, columns=[0, 0])
    tm.assert_frame_equal(result, expected)


def test_to_flat_index(idx):
    expected = pd.Index(
        (
            ("foo", "one"),
            ("foo", "two"),
            ("bar", "one"),
            ("baz", "two"),
            ("qux", "one"),
            ("qux", "two"),
        ),
        tupleize_cols=False,
    )
    result = idx.to_flat_index()
    tm.assert_index_equal(result, expected)
