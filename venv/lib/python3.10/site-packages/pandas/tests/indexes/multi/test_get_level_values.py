import numpy as np

import pandas as pd
from pandas import (
    CategoricalIndex,
    Index,
    MultiIndex,
    Timestamp,
    date_range,
)
import pandas._testing as tm


class TestGetLevelValues:
    def test_get_level_values_box_datetime64(self):
        dates = date_range("1/1/2000", periods=4)
        levels = [dates, [0, 1]]
        codes = [[0, 0, 1, 1, 2, 2, 3, 3], [0, 1, 0, 1, 0, 1, 0, 1]]

        index = MultiIndex(levels=levels, codes=codes)

        assert isinstance(index.get_level_values(0)[0], Timestamp)


def test_get_level_values(idx):
    result = idx.get_level_values(0)
    expected = Index(["foo", "foo", "bar", "baz", "qux", "qux"], name="first")
    tm.assert_index_equal(result, expected)
    assert result.name == "first"

    result = idx.get_level_values("first")
    expected = idx.get_level_values(0)
    tm.assert_index_equal(result, expected)

    # GH 10460
    index = MultiIndex(
        levels=[CategoricalIndex(["A", "B"]), CategoricalIndex([1, 2, 3])],
        codes=[np.array([0, 0, 0, 1, 1, 1]), np.array([0, 1, 2, 0, 1, 2])],
    )

    exp = CategoricalIndex(["A", "A", "A", "B", "B", "B"])
    tm.assert_index_equal(index.get_level_values(0), exp)
    exp = CategoricalIndex([1, 2, 3, 1, 2, 3])
    tm.assert_index_equal(index.get_level_values(1), exp)


def test_get_level_values_all_na():
    # GH#17924 when level entirely consists of nan
    arrays = [[np.nan, np.nan, np.nan], ["a", np.nan, 1]]
    index = MultiIndex.from_arrays(arrays)
    result = index.get_level_values(0)
    expected = Index([np.nan, np.nan, np.nan], dtype=np.float64)
    tm.assert_index_equal(result, expected)

    result = index.get_level_values(1)
    expected = Index(["a", np.nan, 1], dtype=object)
    tm.assert_index_equal(result, expected)


def test_get_level_values_int_with_na():
    # GH#17924
    arrays = [["a", "b", "b"], [1, np.nan, 2]]
    index = MultiIndex.from_arrays(arrays)
    result = index.get_level_values(1)
    expected = Index([1, np.nan, 2])
    tm.assert_index_equal(result, expected)

    arrays = [["a", "b", "b"], [np.nan, np.nan, 2]]
    index = MultiIndex.from_arrays(arrays)
    result = index.get_level_values(1)
    expected = Index([np.nan, np.nan, 2])
    tm.assert_index_equal(result, expected)


def test_get_level_values_na():
    arrays = [[np.nan, np.nan, np.nan], ["a", np.nan, 1]]
    index = MultiIndex.from_arrays(arrays)
    result = index.get_level_values(0)
    expected = Index([np.nan, np.nan, np.nan])
    tm.assert_index_equal(result, expected)

    result = index.get_level_values(1)
    expected = Index(["a", np.nan, 1])
    tm.assert_index_equal(result, expected)

    arrays = [["a", "b", "b"], pd.DatetimeIndex([0, 1, pd.NaT])]
    index = MultiIndex.from_arrays(arrays)
    result = index.get_level_values(1)
    expected = pd.DatetimeIndex([0, 1, pd.NaT])
    tm.assert_index_equal(result, expected)

    arrays = [[], []]
    index = MultiIndex.from_arrays(arrays)
    result = index.get_level_values(0)
    expected = Index([], dtype=object)
    tm.assert_index_equal(result, expected)


def test_get_level_values_when_periods():
    # GH33131. See also discussion in GH32669.
    # This test can probably be removed when PeriodIndex._engine is removed.
    from pandas import (
        Period,
        PeriodIndex,
    )

    idx = MultiIndex.from_arrays(
        [PeriodIndex([Period("2019Q1"), Period("2019Q2")], name="b")]
    )
    idx2 = MultiIndex.from_arrays(
        [idx._get_level_values(level) for level in range(idx.nlevels)]
    )
    assert all(x.is_monotonic_increasing for x in idx2.levels)


def test_values_loses_freq_of_underlying_index():
    # GH#49054
    idx = pd.DatetimeIndex(date_range("20200101", periods=3, freq="BME"))
    expected = idx.copy(deep=True)
    idx2 = Index([1, 2, 3])
    midx = MultiIndex(levels=[idx, idx2], codes=[[0, 1, 2], [0, 1, 2]])
    midx.values
    assert idx.freq is not None
    tm.assert_index_equal(idx, expected)
