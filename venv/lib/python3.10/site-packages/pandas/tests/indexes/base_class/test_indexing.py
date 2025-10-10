import numpy as np
import pytest

from pandas._libs import index as libindex

import pandas as pd
from pandas import (
    Index,
    NaT,
)
import pandas._testing as tm


class TestGetSliceBounds:
    @pytest.mark.parametrize("side, expected", [("left", 4), ("right", 5)])
    def test_get_slice_bounds_within(self, side, expected):
        index = Index(list("abcdef"))
        result = index.get_slice_bound("e", side=side)
        assert result == expected

    @pytest.mark.parametrize("side", ["left", "right"])
    @pytest.mark.parametrize(
        "data, bound, expected", [(list("abcdef"), "x", 6), (list("bcdefg"), "a", 0)]
    )
    def test_get_slice_bounds_outside(self, side, expected, data, bound):
        index = Index(data)
        result = index.get_slice_bound(bound, side=side)
        assert result == expected

    def test_get_slice_bounds_invalid_side(self):
        with pytest.raises(ValueError, match="Invalid value for side kwarg"):
            Index([]).get_slice_bound("a", side="middle")


class TestGetIndexerNonUnique:
    def test_get_indexer_non_unique_dtype_mismatch(self):
        # GH#25459
        indexes, missing = Index(["A", "B"]).get_indexer_non_unique(Index([0]))
        tm.assert_numpy_array_equal(np.array([-1], dtype=np.intp), indexes)
        tm.assert_numpy_array_equal(np.array([0], dtype=np.intp), missing)

    @pytest.mark.parametrize(
        "idx_values,idx_non_unique",
        [
            ([np.nan, 100, 200, 100], [np.nan, 100]),
            ([np.nan, 100.0, 200.0, 100.0], [np.nan, 100.0]),
        ],
    )
    def test_get_indexer_non_unique_int_index(self, idx_values, idx_non_unique):
        indexes, missing = Index(idx_values).get_indexer_non_unique(Index([np.nan]))
        tm.assert_numpy_array_equal(np.array([0], dtype=np.intp), indexes)
        tm.assert_numpy_array_equal(np.array([], dtype=np.intp), missing)

        indexes, missing = Index(idx_values).get_indexer_non_unique(
            Index(idx_non_unique)
        )
        tm.assert_numpy_array_equal(np.array([0, 1, 3], dtype=np.intp), indexes)
        tm.assert_numpy_array_equal(np.array([], dtype=np.intp), missing)


class TestGetLoc:
    @pytest.mark.slow  # to_flat_index takes a while
    def test_get_loc_tuple_monotonic_above_size_cutoff(self, monkeypatch):
        # Go through the libindex path for which using
        # _bin_search vs ndarray.searchsorted makes a difference

        with monkeypatch.context():
            monkeypatch.setattr(libindex, "_SIZE_CUTOFF", 100)
            lev = list("ABCD")
            dti = pd.date_range("2016-01-01", periods=10)

            mi = pd.MultiIndex.from_product([lev, range(5), dti])
            oidx = mi.to_flat_index()

            loc = len(oidx) // 2
            tup = oidx[loc]

            res = oidx.get_loc(tup)
        assert res == loc

    def test_get_loc_nan_object_dtype_nonmonotonic_nonunique(self):
        # case that goes through _maybe_get_bool_indexer
        idx = Index(["foo", np.nan, None, "foo", 1.0, None], dtype=object)

        # we dont raise KeyError on nan
        res = idx.get_loc(np.nan)
        assert res == 1

        # we only match on None, not on np.nan
        res = idx.get_loc(None)
        expected = np.array([False, False, True, False, False, True])
        tm.assert_numpy_array_equal(res, expected)

        # we don't match at all on mismatched NA
        with pytest.raises(KeyError, match="NaT"):
            idx.get_loc(NaT)


def test_getitem_boolean_ea_indexer():
    # GH#45806
    ser = pd.Series([True, False, pd.NA], dtype="boolean")
    result = ser.index[ser]
    expected = Index([0])
    tm.assert_index_equal(result, expected)
