import numpy as np
import pytest

import pandas as pd
from pandas import Index
import pandas._testing as tm


def _isnan(val):
    try:
        return val is not pd.NA and np.isnan(val)
    except TypeError:
        return False


def _equivalent_na(dtype, null):
    if dtype.na_value is pd.NA and null is pd.NA:
        return True
    elif _isnan(dtype.na_value) and _isnan(null):
        return True
    else:
        return False


class TestGetLoc:
    def test_get_loc(self, any_string_dtype):
        index = Index(["a", "b", "c"], dtype=any_string_dtype)
        assert index.get_loc("b") == 1

    def test_get_loc_raises(self, any_string_dtype):
        index = Index(["a", "b", "c"], dtype=any_string_dtype)
        with pytest.raises(KeyError, match="d"):
            index.get_loc("d")

    def test_get_loc_invalid_value(self, any_string_dtype):
        index = Index(["a", "b", "c"], dtype=any_string_dtype)
        with pytest.raises(KeyError, match="1"):
            index.get_loc(1)

    def test_get_loc_non_unique(self, any_string_dtype):
        index = Index(["a", "b", "a"], dtype=any_string_dtype)
        result = index.get_loc("a")
        expected = np.array([True, False, True])
        tm.assert_numpy_array_equal(result, expected)

    def test_get_loc_non_missing(self, any_string_dtype, nulls_fixture):
        index = Index(["a", "b", "c"], dtype=any_string_dtype)
        with pytest.raises(KeyError):
            index.get_loc(nulls_fixture)

    def test_get_loc_missing(self, any_string_dtype, nulls_fixture):
        index = Index(["a", "b", nulls_fixture], dtype=any_string_dtype)
        assert index.get_loc(nulls_fixture) == 2


class TestGetIndexer:
    @pytest.mark.parametrize(
        "method,expected",
        [
            ("pad", [-1, 0, 1, 1]),
            ("backfill", [0, 0, 1, -1]),
        ],
    )
    def test_get_indexer_strings(self, any_string_dtype, method, expected):
        expected = np.array(expected, dtype=np.intp)
        index = Index(["b", "c"], dtype=any_string_dtype)
        actual = index.get_indexer(["a", "b", "c", "d"], method=method)

        tm.assert_numpy_array_equal(actual, expected)

    def test_get_indexer_strings_raises(self, any_string_dtype):
        index = Index(["b", "c"], dtype=any_string_dtype)

        msg = "|".join(
            [
                "operation 'sub' not supported for dtype 'str",
                r"unsupported operand type\(s\) for -: 'str' and 'str'",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            index.get_indexer(["a", "b", "c", "d"], method="nearest")

        with pytest.raises(TypeError, match=msg):
            index.get_indexer(["a", "b", "c", "d"], method="pad", tolerance=2)

        with pytest.raises(TypeError, match=msg):
            index.get_indexer(
                ["a", "b", "c", "d"], method="pad", tolerance=[2, 2, 2, 2]
            )

    @pytest.mark.parametrize("null", [None, np.nan, float("nan"), pd.NA])
    def test_get_indexer_missing(self, any_string_dtype, null, using_infer_string):
        # NaT and Decimal("NaN") from null_fixture are not supported for string dtype
        index = Index(["a", "b", null], dtype=any_string_dtype)
        result = index.get_indexer(["a", null, "c"])
        if using_infer_string:
            expected = np.array([0, 2, -1], dtype=np.intp)
        elif any_string_dtype == "string" and not _equivalent_na(
            any_string_dtype, null
        ):
            expected = np.array([0, -1, -1], dtype=np.intp)
        else:
            expected = np.array([0, 2, -1], dtype=np.intp)

        tm.assert_numpy_array_equal(result, expected)


class TestGetIndexerNonUnique:
    @pytest.mark.parametrize("null", [None, np.nan, float("nan"), pd.NA])
    def test_get_indexer_non_unique_nas(
        self, any_string_dtype, null, using_infer_string
    ):
        index = Index(["a", "b", null], dtype=any_string_dtype)
        indexer, missing = index.get_indexer_non_unique(["a", null])

        if using_infer_string:
            expected_indexer = np.array([0, 2], dtype=np.intp)
            expected_missing = np.array([], dtype=np.intp)
        elif any_string_dtype == "string" and not _equivalent_na(
            any_string_dtype, null
        ):
            expected_indexer = np.array([0, -1], dtype=np.intp)
            expected_missing = np.array([1], dtype=np.intp)
        else:
            expected_indexer = np.array([0, 2], dtype=np.intp)
            expected_missing = np.array([], dtype=np.intp)
        tm.assert_numpy_array_equal(indexer, expected_indexer)
        tm.assert_numpy_array_equal(missing, expected_missing)

        # actually non-unique
        index = Index(["a", null, "b", null], dtype=any_string_dtype)
        indexer, missing = index.get_indexer_non_unique(["a", null])

        if using_infer_string:
            expected_indexer = np.array([0, 1, 3], dtype=np.intp)
        elif any_string_dtype == "string" and not _equivalent_na(
            any_string_dtype, null
        ):
            pass
        else:
            expected_indexer = np.array([0, 1, 3], dtype=np.intp)
        tm.assert_numpy_array_equal(indexer, expected_indexer)
        tm.assert_numpy_array_equal(missing, expected_missing)


class TestSliceLocs:
    @pytest.mark.parametrize(
        "in_slice,expected",
        [
            # error: Slice index must be an integer or None
            (pd.IndexSlice[::-1], "yxdcb"),
            (pd.IndexSlice["b":"y":-1], ""),  # type: ignore[misc]
            (pd.IndexSlice["b"::-1], "b"),  # type: ignore[misc]
            (pd.IndexSlice[:"b":-1], "yxdcb"),  # type: ignore[misc]
            (pd.IndexSlice[:"y":-1], "y"),  # type: ignore[misc]
            (pd.IndexSlice["y"::-1], "yxdcb"),  # type: ignore[misc]
            (pd.IndexSlice["y"::-4], "yb"),  # type: ignore[misc]
            # absent labels
            (pd.IndexSlice[:"a":-1], "yxdcb"),  # type: ignore[misc]
            (pd.IndexSlice[:"a":-2], "ydb"),  # type: ignore[misc]
            (pd.IndexSlice["z"::-1], "yxdcb"),  # type: ignore[misc]
            (pd.IndexSlice["z"::-3], "yc"),  # type: ignore[misc]
            (pd.IndexSlice["m"::-1], "dcb"),  # type: ignore[misc]
            (pd.IndexSlice[:"m":-1], "yx"),  # type: ignore[misc]
            (pd.IndexSlice["a":"a":-1], ""),  # type: ignore[misc]
            (pd.IndexSlice["z":"z":-1], ""),  # type: ignore[misc]
            (pd.IndexSlice["m":"m":-1], ""),  # type: ignore[misc]
        ],
    )
    def test_slice_locs_negative_step(self, in_slice, expected, any_string_dtype):
        index = Index(list("bcdxy"), dtype=any_string_dtype)

        s_start, s_stop = index.slice_locs(in_slice.start, in_slice.stop, in_slice.step)
        result = index[s_start : s_stop : in_slice.step]
        expected = Index(list(expected), dtype=any_string_dtype)
        tm.assert_index_equal(result, expected)

    def test_slice_locs_negative_step_oob(self, any_string_dtype):
        index = Index(list("bcdxy"), dtype=any_string_dtype)

        result = index[-10:5:1]
        tm.assert_index_equal(result, index)

        result = index[4:-10:-1]
        expected = Index(list("yxdcb"), dtype=any_string_dtype)
        tm.assert_index_equal(result, expected)

    def test_slice_locs_dup(self, any_string_dtype):
        index = Index(["a", "a", "b", "c", "d", "d"], dtype=any_string_dtype)
        assert index.slice_locs("a", "d") == (0, 6)
        assert index.slice_locs(end="d") == (0, 6)
        assert index.slice_locs("a", "c") == (0, 4)
        assert index.slice_locs("b", "d") == (2, 6)

        index2 = index[::-1]
        assert index2.slice_locs("d", "a") == (0, 6)
        assert index2.slice_locs(end="a") == (0, 6)
        assert index2.slice_locs("d", "b") == (0, 4)
        assert index2.slice_locs("c", "a") == (2, 6)
