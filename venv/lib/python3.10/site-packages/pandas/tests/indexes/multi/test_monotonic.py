import numpy as np
import pytest

from pandas import (
    Index,
    MultiIndex,
)


def test_is_monotonic_increasing_lexsorted(lexsorted_two_level_string_multiindex):
    # string ordering
    mi = lexsorted_two_level_string_multiindex
    assert mi.is_monotonic_increasing is False
    assert Index(mi.values).is_monotonic_increasing is False
    assert mi._is_strictly_monotonic_increasing is False
    assert Index(mi.values)._is_strictly_monotonic_increasing is False


def test_is_monotonic_increasing():
    i = MultiIndex.from_product([np.arange(10), np.arange(10)], names=["one", "two"])
    assert i.is_monotonic_increasing is True
    assert i._is_strictly_monotonic_increasing is True
    assert Index(i.values).is_monotonic_increasing is True
    assert i._is_strictly_monotonic_increasing is True

    i = MultiIndex.from_product(
        [np.arange(10, 0, -1), np.arange(10)], names=["one", "two"]
    )
    assert i.is_monotonic_increasing is False
    assert i._is_strictly_monotonic_increasing is False
    assert Index(i.values).is_monotonic_increasing is False
    assert Index(i.values)._is_strictly_monotonic_increasing is False

    i = MultiIndex.from_product(
        [np.arange(10), np.arange(10, 0, -1)], names=["one", "two"]
    )
    assert i.is_monotonic_increasing is False
    assert i._is_strictly_monotonic_increasing is False
    assert Index(i.values).is_monotonic_increasing is False
    assert Index(i.values)._is_strictly_monotonic_increasing is False

    i = MultiIndex.from_product([[1.0, np.nan, 2.0], ["a", "b", "c"]])
    assert i.is_monotonic_increasing is False
    assert i._is_strictly_monotonic_increasing is False
    assert Index(i.values).is_monotonic_increasing is False
    assert Index(i.values)._is_strictly_monotonic_increasing is False

    i = MultiIndex(
        levels=[["bar", "baz", "foo", "qux"], ["mom", "next", "zenith"]],
        codes=[[0, 0, 0, 1, 1, 2, 2, 3, 3, 3], [0, 1, 2, 0, 1, 1, 2, 0, 1, 2]],
        names=["first", "second"],
    )
    assert i.is_monotonic_increasing is True
    assert Index(i.values).is_monotonic_increasing is True
    assert i._is_strictly_monotonic_increasing is True
    assert Index(i.values)._is_strictly_monotonic_increasing is True

    # mixed levels, hits the TypeError
    i = MultiIndex(
        levels=[
            [1, 2, 3, 4],
            [
                "gb00b03mlx29",
                "lu0197800237",
                "nl0000289783",
                "nl0000289965",
                "nl0000301109",
            ],
        ],
        codes=[[0, 1, 1, 2, 2, 2, 3], [4, 2, 0, 0, 1, 3, -1]],
        names=["household_id", "asset_id"],
    )

    assert i.is_monotonic_increasing is False
    assert i._is_strictly_monotonic_increasing is False

    # empty
    i = MultiIndex.from_arrays([[], []])
    assert i.is_monotonic_increasing is True
    assert Index(i.values).is_monotonic_increasing is True
    assert i._is_strictly_monotonic_increasing is True
    assert Index(i.values)._is_strictly_monotonic_increasing is True


def test_is_monotonic_decreasing():
    i = MultiIndex.from_product(
        [np.arange(9, -1, -1), np.arange(9, -1, -1)], names=["one", "two"]
    )
    assert i.is_monotonic_decreasing is True
    assert i._is_strictly_monotonic_decreasing is True
    assert Index(i.values).is_monotonic_decreasing is True
    assert i._is_strictly_monotonic_decreasing is True

    i = MultiIndex.from_product(
        [np.arange(10), np.arange(10, 0, -1)], names=["one", "two"]
    )
    assert i.is_monotonic_decreasing is False
    assert i._is_strictly_monotonic_decreasing is False
    assert Index(i.values).is_monotonic_decreasing is False
    assert Index(i.values)._is_strictly_monotonic_decreasing is False

    i = MultiIndex.from_product(
        [np.arange(10, 0, -1), np.arange(10)], names=["one", "two"]
    )
    assert i.is_monotonic_decreasing is False
    assert i._is_strictly_monotonic_decreasing is False
    assert Index(i.values).is_monotonic_decreasing is False
    assert Index(i.values)._is_strictly_monotonic_decreasing is False

    i = MultiIndex.from_product([[2.0, np.nan, 1.0], ["c", "b", "a"]])
    assert i.is_monotonic_decreasing is False
    assert i._is_strictly_monotonic_decreasing is False
    assert Index(i.values).is_monotonic_decreasing is False
    assert Index(i.values)._is_strictly_monotonic_decreasing is False

    # string ordering
    i = MultiIndex(
        levels=[["qux", "foo", "baz", "bar"], ["three", "two", "one"]],
        codes=[[0, 0, 0, 1, 1, 2, 2, 3, 3, 3], [0, 1, 2, 0, 1, 1, 2, 0, 1, 2]],
        names=["first", "second"],
    )
    assert i.is_monotonic_decreasing is False
    assert Index(i.values).is_monotonic_decreasing is False
    assert i._is_strictly_monotonic_decreasing is False
    assert Index(i.values)._is_strictly_monotonic_decreasing is False

    i = MultiIndex(
        levels=[["qux", "foo", "baz", "bar"], ["zenith", "next", "mom"]],
        codes=[[0, 0, 0, 1, 1, 2, 2, 3, 3, 3], [0, 1, 2, 0, 1, 1, 2, 0, 1, 2]],
        names=["first", "second"],
    )
    assert i.is_monotonic_decreasing is True
    assert Index(i.values).is_monotonic_decreasing is True
    assert i._is_strictly_monotonic_decreasing is True
    assert Index(i.values)._is_strictly_monotonic_decreasing is True

    # mixed levels, hits the TypeError
    i = MultiIndex(
        levels=[
            [4, 3, 2, 1],
            [
                "nl0000301109",
                "nl0000289965",
                "nl0000289783",
                "lu0197800237",
                "gb00b03mlx29",
            ],
        ],
        codes=[[0, 1, 1, 2, 2, 2, 3], [4, 2, 0, 0, 1, 3, -1]],
        names=["household_id", "asset_id"],
    )

    assert i.is_monotonic_decreasing is False
    assert i._is_strictly_monotonic_decreasing is False

    # empty
    i = MultiIndex.from_arrays([[], []])
    assert i.is_monotonic_decreasing is True
    assert Index(i.values).is_monotonic_decreasing is True
    assert i._is_strictly_monotonic_decreasing is True
    assert Index(i.values)._is_strictly_monotonic_decreasing is True


def test_is_strictly_monotonic_increasing():
    idx = MultiIndex(
        levels=[["bar", "baz"], ["mom", "next"]], codes=[[0, 0, 1, 1], [0, 0, 0, 1]]
    )
    assert idx.is_monotonic_increasing is True
    assert idx._is_strictly_monotonic_increasing is False


def test_is_strictly_monotonic_decreasing():
    idx = MultiIndex(
        levels=[["baz", "bar"], ["next", "mom"]], codes=[[0, 0, 1, 1], [0, 0, 0, 1]]
    )
    assert idx.is_monotonic_decreasing is True
    assert idx._is_strictly_monotonic_decreasing is False


@pytest.mark.parametrize("attr", ["is_monotonic_increasing", "is_monotonic_decreasing"])
@pytest.mark.parametrize(
    "values",
    [[(np.nan,), (1,), (2,)], [(1,), (np.nan,), (2,)], [(1,), (2,), (np.nan,)]],
)
def test_is_monotonic_with_nans(values, attr):
    # GH: 37220
    idx = MultiIndex.from_tuples(values, names=["test"])
    assert getattr(idx, attr) is False
