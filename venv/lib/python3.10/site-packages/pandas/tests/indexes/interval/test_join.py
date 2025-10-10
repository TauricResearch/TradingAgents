import pytest

from pandas import (
    IntervalIndex,
    MultiIndex,
    RangeIndex,
)
import pandas._testing as tm


@pytest.fixture
def range_index():
    return RangeIndex(3, name="range_index")


@pytest.fixture
def interval_index():
    return IntervalIndex.from_tuples(
        [(0.0, 1.0), (1.0, 2.0), (1.5, 2.5)], name="interval_index"
    )


def test_join_overlapping_in_mi_to_same_intervalindex(range_index, interval_index):
    #  GH-45661
    multi_index = MultiIndex.from_product([interval_index, range_index])
    result = multi_index.join(interval_index)

    tm.assert_index_equal(result, multi_index)


def test_join_overlapping_to_multiindex_with_same_interval(range_index, interval_index):
    #  GH-45661
    multi_index = MultiIndex.from_product([interval_index, range_index])
    result = interval_index.join(multi_index)

    tm.assert_index_equal(result, multi_index)


def test_join_overlapping_interval_to_another_intervalindex(interval_index):
    #  GH-45661
    flipped_interval_index = interval_index[::-1]
    result = interval_index.join(flipped_interval_index)

    tm.assert_index_equal(result, interval_index)
