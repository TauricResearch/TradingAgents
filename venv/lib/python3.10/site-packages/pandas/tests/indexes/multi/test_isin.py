import numpy as np
import pytest

from pandas import MultiIndex
import pandas._testing as tm


def test_isin_nan():
    idx = MultiIndex.from_arrays([["foo", "bar"], [1.0, np.nan]])
    tm.assert_numpy_array_equal(idx.isin([("bar", np.nan)]), np.array([False, True]))
    tm.assert_numpy_array_equal(
        idx.isin([("bar", float("nan"))]), np.array([False, True])
    )


def test_isin_missing(nulls_fixture):
    # GH48905
    mi1 = MultiIndex.from_tuples([(1, nulls_fixture)])
    mi2 = MultiIndex.from_tuples([(1, 1), (1, 2)])
    result = mi2.isin(mi1)
    expected = np.array([False, False])
    tm.assert_numpy_array_equal(result, expected)


def test_isin():
    values = [("foo", 2), ("bar", 3), ("quux", 4)]

    idx = MultiIndex.from_arrays([["qux", "baz", "foo", "bar"], np.arange(4)])
    result = idx.isin(values)
    expected = np.array([False, False, True, True])
    tm.assert_numpy_array_equal(result, expected)

    # empty, return dtype bool
    idx = MultiIndex.from_arrays([[], []])
    result = idx.isin(values)
    assert len(result) == 0
    assert result.dtype == np.bool_


def test_isin_level_kwarg():
    idx = MultiIndex.from_arrays([["qux", "baz", "foo", "bar"], np.arange(4)])

    vals_0 = ["foo", "bar", "quux"]
    vals_1 = [2, 3, 10]

    expected = np.array([False, False, True, True])
    tm.assert_numpy_array_equal(expected, idx.isin(vals_0, level=0))
    tm.assert_numpy_array_equal(expected, idx.isin(vals_0, level=-2))

    tm.assert_numpy_array_equal(expected, idx.isin(vals_1, level=1))
    tm.assert_numpy_array_equal(expected, idx.isin(vals_1, level=-1))

    msg = "Too many levels: Index has only 2 levels, not 6"
    with pytest.raises(IndexError, match=msg):
        idx.isin(vals_0, level=5)
    msg = "Too many levels: Index has only 2 levels, -5 is not a valid level number"
    with pytest.raises(IndexError, match=msg):
        idx.isin(vals_0, level=-5)

    with pytest.raises(KeyError, match=r"'Level 1\.0 not found'"):
        idx.isin(vals_0, level=1.0)
    with pytest.raises(KeyError, match=r"'Level -1\.0 not found'"):
        idx.isin(vals_1, level=-1.0)
    with pytest.raises(KeyError, match="'Level A not found'"):
        idx.isin(vals_1, level="A")

    idx.names = ["A", "B"]
    tm.assert_numpy_array_equal(expected, idx.isin(vals_0, level="A"))
    tm.assert_numpy_array_equal(expected, idx.isin(vals_1, level="B"))

    with pytest.raises(KeyError, match="'Level C not found'"):
        idx.isin(vals_1, level="C")


@pytest.mark.parametrize(
    "labels,expected,level",
    [
        ([("b", np.nan)], np.array([False, False, True]), None),
        ([np.nan, "a"], np.array([True, True, False]), 0),
        (["d", np.nan], np.array([False, True, True]), 1),
    ],
)
def test_isin_multi_index_with_missing_value(labels, expected, level):
    # GH 19132
    midx = MultiIndex.from_arrays([[np.nan, "a", "b"], ["c", "d", np.nan]])
    result = midx.isin(labels, level=level)
    tm.assert_numpy_array_equal(result, expected)


def test_isin_empty():
    # GH#51599
    midx = MultiIndex.from_arrays([[1, 2], [3, 4]])
    result = midx.isin([])
    expected = np.array([False, False])
    tm.assert_numpy_array_equal(result, expected)


def test_isin_generator():
    # GH#52568
    midx = MultiIndex.from_tuples([(1, 2)])
    result = midx.isin(x for x in [(1, 2)])
    expected = np.array([True])
    tm.assert_numpy_array_equal(result, expected)
