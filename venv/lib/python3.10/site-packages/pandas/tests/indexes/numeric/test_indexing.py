import numpy as np
import pytest

from pandas.errors import InvalidIndexError

from pandas import (
    NA,
    Index,
    RangeIndex,
    Series,
    Timestamp,
)
import pandas._testing as tm
from pandas.core.arrays import (
    ArrowExtensionArray,
    FloatingArray,
)


@pytest.fixture
def index_large():
    # large values used in Index[uint64] tests where no compat needed with Int64/Float64
    large = [2**63, 2**63 + 10, 2**63 + 15, 2**63 + 20, 2**63 + 25]
    return Index(large, dtype=np.uint64)


class TestGetLoc:
    def test_get_loc(self):
        index = Index([0, 1, 2])
        assert index.get_loc(1) == 1

    def test_get_loc_raises_bad_label(self):
        index = Index([0, 1, 2])
        with pytest.raises(InvalidIndexError, match=r"\[1, 2\]"):
            index.get_loc([1, 2])

    def test_get_loc_float64(self):
        idx = Index([0.0, 1.0, 2.0], dtype=np.float64)

        with pytest.raises(KeyError, match="^'foo'$"):
            idx.get_loc("foo")
        with pytest.raises(KeyError, match=r"^1\.5$"):
            idx.get_loc(1.5)
        with pytest.raises(KeyError, match="^True$"):
            idx.get_loc(True)
        with pytest.raises(KeyError, match="^False$"):
            idx.get_loc(False)

    def test_get_loc_na(self):
        idx = Index([np.nan, 1, 2], dtype=np.float64)
        assert idx.get_loc(1) == 1
        assert idx.get_loc(np.nan) == 0

        idx = Index([np.nan, 1, np.nan], dtype=np.float64)
        assert idx.get_loc(1) == 1

        # representable by slice [0:2:2]
        msg = "'Cannot get left slice bound for non-unique label: nan'"
        with pytest.raises(KeyError, match=msg):
            idx.slice_locs(np.nan)
        # not representable by slice
        idx = Index([np.nan, 1, np.nan, np.nan], dtype=np.float64)
        assert idx.get_loc(1) == 1
        msg = "'Cannot get left slice bound for non-unique label: nan"
        with pytest.raises(KeyError, match=msg):
            idx.slice_locs(np.nan)

    def test_get_loc_missing_nan(self):
        # GH#8569
        idx = Index([1, 2], dtype=np.float64)
        assert idx.get_loc(1) == 0
        with pytest.raises(KeyError, match=r"^3$"):
            idx.get_loc(3)
        with pytest.raises(KeyError, match="^nan$"):
            idx.get_loc(np.nan)
        with pytest.raises(InvalidIndexError, match=r"\[nan\]"):
            # listlike/non-hashable raises TypeError
            idx.get_loc([np.nan])

    @pytest.mark.parametrize("vals", [[1], [1.0], [Timestamp("2019-12-31")], ["test"]])
    def test_get_loc_float_index_nan_with_method(self, vals):
        # GH#39382
        idx = Index(vals)
        with pytest.raises(KeyError, match="nan"):
            idx.get_loc(np.nan)

    @pytest.mark.parametrize("dtype", ["f8", "i8", "u8"])
    def test_get_loc_numericindex_none_raises(self, dtype):
        # case that goes through searchsorted and key is non-comparable to values
        arr = np.arange(10**7, dtype=dtype)
        idx = Index(arr)
        with pytest.raises(KeyError, match="None"):
            idx.get_loc(None)

    def test_get_loc_overflows(self):
        # unique but non-monotonic goes through IndexEngine.mapping.get_item
        idx = Index([0, 2, 1])

        val = np.iinfo(np.int64).max + 1

        with pytest.raises(KeyError, match=str(val)):
            idx.get_loc(val)
        with pytest.raises(KeyError, match=str(val)):
            idx._engine.get_loc(val)


class TestGetIndexer:
    def test_get_indexer(self):
        index1 = Index([1, 2, 3, 4, 5])
        index2 = Index([2, 4, 6])

        r1 = index1.get_indexer(index2)
        e1 = np.array([1, 3, -1], dtype=np.intp)
        tm.assert_almost_equal(r1, e1)

    @pytest.mark.parametrize("reverse", [True, False])
    @pytest.mark.parametrize(
        "expected,method",
        [
            (np.array([-1, 0, 0, 1, 1], dtype=np.intp), "pad"),
            (np.array([-1, 0, 0, 1, 1], dtype=np.intp), "ffill"),
            (np.array([0, 0, 1, 1, 2], dtype=np.intp), "backfill"),
            (np.array([0, 0, 1, 1, 2], dtype=np.intp), "bfill"),
        ],
    )
    def test_get_indexer_methods(self, reverse, expected, method):
        index1 = Index([1, 2, 3, 4, 5])
        index2 = Index([2, 4, 6])

        if reverse:
            index1 = index1[::-1]
            expected = expected[::-1]

        result = index2.get_indexer(index1, method=method)
        tm.assert_almost_equal(result, expected)

    def test_get_indexer_invalid(self):
        # GH10411
        index = Index(np.arange(10))

        with pytest.raises(ValueError, match="tolerance argument"):
            index.get_indexer([1, 0], tolerance=1)

        with pytest.raises(ValueError, match="limit argument"):
            index.get_indexer([1, 0], limit=1)

    @pytest.mark.parametrize(
        "method, tolerance, indexer, expected",
        [
            ("pad", None, [0, 5, 9], [0, 5, 9]),
            ("backfill", None, [0, 5, 9], [0, 5, 9]),
            ("nearest", None, [0, 5, 9], [0, 5, 9]),
            ("pad", 0, [0, 5, 9], [0, 5, 9]),
            ("backfill", 0, [0, 5, 9], [0, 5, 9]),
            ("nearest", 0, [0, 5, 9], [0, 5, 9]),
            ("pad", None, [0.2, 1.8, 8.5], [0, 1, 8]),
            ("backfill", None, [0.2, 1.8, 8.5], [1, 2, 9]),
            ("nearest", None, [0.2, 1.8, 8.5], [0, 2, 9]),
            ("pad", 1, [0.2, 1.8, 8.5], [0, 1, 8]),
            ("backfill", 1, [0.2, 1.8, 8.5], [1, 2, 9]),
            ("nearest", 1, [0.2, 1.8, 8.5], [0, 2, 9]),
            ("pad", 0.2, [0.2, 1.8, 8.5], [0, -1, -1]),
            ("backfill", 0.2, [0.2, 1.8, 8.5], [-1, 2, -1]),
            ("nearest", 0.2, [0.2, 1.8, 8.5], [0, 2, -1]),
        ],
    )
    def test_get_indexer_nearest(self, method, tolerance, indexer, expected):
        index = Index(np.arange(10))

        actual = index.get_indexer(indexer, method=method, tolerance=tolerance)
        tm.assert_numpy_array_equal(actual, np.array(expected, dtype=np.intp))

    @pytest.mark.parametrize("listtype", [list, tuple, Series, np.array])
    @pytest.mark.parametrize(
        "tolerance, expected",
        list(
            zip(
                [[0.3, 0.3, 0.1], [0.2, 0.1, 0.1], [0.1, 0.5, 0.5]],
                [[0, 2, -1], [0, -1, -1], [-1, 2, 9]],
            )
        ),
    )
    def test_get_indexer_nearest_listlike_tolerance(
        self, tolerance, expected, listtype
    ):
        index = Index(np.arange(10))

        actual = index.get_indexer(
            [0.2, 1.8, 8.5], method="nearest", tolerance=listtype(tolerance)
        )
        tm.assert_numpy_array_equal(actual, np.array(expected, dtype=np.intp))

    def test_get_indexer_nearest_error(self):
        index = Index(np.arange(10))
        with pytest.raises(ValueError, match="limit argument"):
            index.get_indexer([1, 0], method="nearest", limit=1)

        with pytest.raises(ValueError, match="tolerance size must match"):
            index.get_indexer([1, 0], method="nearest", tolerance=[1, 2, 3])

    @pytest.mark.parametrize(
        "method,expected",
        [("pad", [8, 7, 0]), ("backfill", [9, 8, 1]), ("nearest", [9, 7, 0])],
    )
    def test_get_indexer_nearest_decreasing(self, method, expected):
        index = Index(np.arange(10))[::-1]

        actual = index.get_indexer([0, 5, 9], method=method)
        tm.assert_numpy_array_equal(actual, np.array([9, 4, 0], dtype=np.intp))

        actual = index.get_indexer([0.2, 1.8, 8.5], method=method)
        tm.assert_numpy_array_equal(actual, np.array(expected, dtype=np.intp))

    @pytest.mark.parametrize("idx_dtype", ["int64", "float64", "uint64", "range"])
    @pytest.mark.parametrize("method", ["get_indexer", "get_indexer_non_unique"])
    def test_get_indexer_numeric_index_boolean_target(self, method, idx_dtype):
        # GH 16877

        if idx_dtype == "range":
            numeric_index = RangeIndex(4)
        else:
            numeric_index = Index(np.arange(4, dtype=idx_dtype))

        other = Index([True, False, True])

        result = getattr(numeric_index, method)(other)
        expected = np.array([-1, -1, -1], dtype=np.intp)
        if method == "get_indexer":
            tm.assert_numpy_array_equal(result, expected)
        else:
            missing = np.arange(3, dtype=np.intp)
            tm.assert_numpy_array_equal(result[0], expected)
            tm.assert_numpy_array_equal(result[1], missing)

    @pytest.mark.parametrize("method", ["pad", "backfill", "nearest"])
    def test_get_indexer_with_method_numeric_vs_bool(self, method):
        left = Index([1, 2, 3])
        right = Index([True, False])

        with pytest.raises(TypeError, match="Cannot compare"):
            left.get_indexer(right, method=method)

        with pytest.raises(TypeError, match="Cannot compare"):
            right.get_indexer(left, method=method)

    def test_get_indexer_numeric_vs_bool(self):
        left = Index([1, 2, 3])
        right = Index([True, False])

        res = left.get_indexer(right)
        expected = -1 * np.ones(len(right), dtype=np.intp)
        tm.assert_numpy_array_equal(res, expected)

        res = right.get_indexer(left)
        expected = -1 * np.ones(len(left), dtype=np.intp)
        tm.assert_numpy_array_equal(res, expected)

        res = left.get_indexer_non_unique(right)[0]
        expected = -1 * np.ones(len(right), dtype=np.intp)
        tm.assert_numpy_array_equal(res, expected)

        res = right.get_indexer_non_unique(left)[0]
        expected = -1 * np.ones(len(left), dtype=np.intp)
        tm.assert_numpy_array_equal(res, expected)

    def test_get_indexer_float64(self):
        idx = Index([0.0, 1.0, 2.0], dtype=np.float64)
        tm.assert_numpy_array_equal(
            idx.get_indexer(idx), np.array([0, 1, 2], dtype=np.intp)
        )

        target = [-0.1, 0.5, 1.1]
        tm.assert_numpy_array_equal(
            idx.get_indexer(target, "pad"), np.array([-1, 0, 1], dtype=np.intp)
        )
        tm.assert_numpy_array_equal(
            idx.get_indexer(target, "backfill"), np.array([0, 1, 2], dtype=np.intp)
        )
        tm.assert_numpy_array_equal(
            idx.get_indexer(target, "nearest"), np.array([0, 1, 1], dtype=np.intp)
        )

    def test_get_indexer_nan(self):
        # GH#7820
        result = Index([1, 2, np.nan], dtype=np.float64).get_indexer([np.nan])
        expected = np.array([2], dtype=np.intp)
        tm.assert_numpy_array_equal(result, expected)

    def test_get_indexer_int64(self):
        index = Index(range(0, 20, 2), dtype=np.int64)
        target = Index(np.arange(10), dtype=np.int64)
        indexer = index.get_indexer(target)
        expected = np.array([0, -1, 1, -1, 2, -1, 3, -1, 4, -1], dtype=np.intp)
        tm.assert_numpy_array_equal(indexer, expected)

        target = Index(np.arange(10), dtype=np.int64)
        indexer = index.get_indexer(target, method="pad")
        expected = np.array([0, 0, 1, 1, 2, 2, 3, 3, 4, 4], dtype=np.intp)
        tm.assert_numpy_array_equal(indexer, expected)

        target = Index(np.arange(10), dtype=np.int64)
        indexer = index.get_indexer(target, method="backfill")
        expected = np.array([0, 1, 1, 2, 2, 3, 3, 4, 4, 5], dtype=np.intp)
        tm.assert_numpy_array_equal(indexer, expected)

    def test_get_indexer_uint64(self, index_large):
        target = Index(np.arange(10).astype("uint64") * 5 + 2**63)
        indexer = index_large.get_indexer(target)
        expected = np.array([0, -1, 1, 2, 3, 4, -1, -1, -1, -1], dtype=np.intp)
        tm.assert_numpy_array_equal(indexer, expected)

        target = Index(np.arange(10).astype("uint64") * 5 + 2**63)
        indexer = index_large.get_indexer(target, method="pad")
        expected = np.array([0, 0, 1, 2, 3, 4, 4, 4, 4, 4], dtype=np.intp)
        tm.assert_numpy_array_equal(indexer, expected)

        target = Index(np.arange(10).astype("uint64") * 5 + 2**63)
        indexer = index_large.get_indexer(target, method="backfill")
        expected = np.array([0, 1, 1, 2, 3, 4, -1, -1, -1, -1], dtype=np.intp)
        tm.assert_numpy_array_equal(indexer, expected)

    @pytest.mark.parametrize("val, val2", [(4, 5), (4, 4), (4, NA), (NA, NA)])
    def test_get_loc_masked(self, val, val2, any_numeric_ea_and_arrow_dtype):
        # GH#39133
        idx = Index([1, 2, 3, val, val2], dtype=any_numeric_ea_and_arrow_dtype)
        result = idx.get_loc(2)
        assert result == 1

        with pytest.raises(KeyError, match="9"):
            idx.get_loc(9)

    def test_get_loc_masked_na(self, any_numeric_ea_and_arrow_dtype):
        # GH#39133
        idx = Index([1, 2, NA], dtype=any_numeric_ea_and_arrow_dtype)
        result = idx.get_loc(NA)
        assert result == 2

        idx = Index([1, 2, NA, NA], dtype=any_numeric_ea_and_arrow_dtype)
        result = idx.get_loc(NA)
        tm.assert_numpy_array_equal(result, np.array([False, False, True, True]))

        idx = Index([1, 2, 3], dtype=any_numeric_ea_and_arrow_dtype)
        with pytest.raises(KeyError, match="NA"):
            idx.get_loc(NA)

    def test_get_loc_masked_na_and_nan(self):
        # GH#39133
        idx = Index(
            FloatingArray(
                np.array([1, 2, 1, np.nan]), mask=np.array([False, False, True, False])
            )
        )
        result = idx.get_loc(NA)
        assert result == 2
        result = idx.get_loc(np.nan)
        assert result == 3

        idx = Index(
            FloatingArray(np.array([1, 2, 1.0]), mask=np.array([False, False, True]))
        )
        result = idx.get_loc(NA)
        assert result == 2
        with pytest.raises(KeyError, match="nan"):
            idx.get_loc(np.nan)

        idx = Index(
            FloatingArray(
                np.array([1, 2, np.nan]), mask=np.array([False, False, False])
            )
        )
        result = idx.get_loc(np.nan)
        assert result == 2
        with pytest.raises(KeyError, match="NA"):
            idx.get_loc(NA)

    @pytest.mark.parametrize("val", [4, 2])
    def test_get_indexer_masked_na(self, any_numeric_ea_and_arrow_dtype, val):
        # GH#39133
        idx = Index([1, 2, NA, 3, val], dtype=any_numeric_ea_and_arrow_dtype)
        result = idx.get_indexer_for([1, NA, 5])
        expected = np.array([0, 2, -1])
        tm.assert_numpy_array_equal(result, expected, check_dtype=False)

    @pytest.mark.parametrize("dtype", ["boolean", "bool[pyarrow]"])
    def test_get_indexer_masked_na_boolean(self, dtype):
        # GH#39133
        if dtype == "bool[pyarrow]":
            pytest.importorskip("pyarrow")
        idx = Index([True, False, NA], dtype=dtype)
        result = idx.get_loc(False)
        assert result == 1
        result = idx.get_loc(NA)
        assert result == 2

    def test_get_indexer_arrow_dictionary_target(self):
        pa = pytest.importorskip("pyarrow")
        target = Index(
            ArrowExtensionArray(
                pa.array([1, 2], type=pa.dictionary(pa.int8(), pa.int8()))
            )
        )
        idx = Index([1])

        result = idx.get_indexer(target)
        expected = np.array([0, -1], dtype=np.int64)
        tm.assert_numpy_array_equal(result, expected)

        result_1, result_2 = idx.get_indexer_non_unique(target)
        expected_1, expected_2 = np.array([0, -1], dtype=np.int64), np.array(
            [1], dtype=np.int64
        )
        tm.assert_numpy_array_equal(result_1, expected_1)
        tm.assert_numpy_array_equal(result_2, expected_2)


class TestWhere:
    @pytest.mark.parametrize(
        "index",
        [
            Index(np.arange(5, dtype="float64")),
            Index(range(0, 20, 2), dtype=np.int64),
            Index(np.arange(5, dtype="uint64")),
        ],
    )
    def test_where(self, listlike_box, index):
        cond = [True] * len(index)
        expected = index
        result = index.where(listlike_box(cond))

        cond = [False] + [True] * (len(index) - 1)
        expected = Index([index._na_value] + index[1:].tolist(), dtype=np.float64)
        result = index.where(listlike_box(cond))
        tm.assert_index_equal(result, expected)

    def test_where_uint64(self):
        idx = Index([0, 6, 2], dtype=np.uint64)
        mask = np.array([False, True, False])
        other = np.array([1], dtype=np.int64)

        expected = Index([1, 6, 1], dtype=np.uint64)

        result = idx.where(mask, other)
        tm.assert_index_equal(result, expected)

        result = idx.putmask(~mask, other)
        tm.assert_index_equal(result, expected)

    def test_where_infers_type_instead_of_trying_to_convert_string_to_float(self):
        # GH 32413
        index = Index([1, np.nan])
        cond = index.notna()
        other = Index(["a", "b"], dtype="string")

        expected = Index([1.0, "b"])
        result = index.where(cond, other)

        tm.assert_index_equal(result, expected)


class TestTake:
    @pytest.mark.parametrize("idx_dtype", [np.float64, np.int64, np.uint64])
    def test_take_preserve_name(self, idx_dtype):
        index = Index([1, 2, 3, 4], dtype=idx_dtype, name="foo")
        taken = index.take([3, 0, 1])
        assert index.name == taken.name

    def test_take_fill_value_float64(self):
        # GH 12631
        idx = Index([1.0, 2.0, 3.0], name="xxx", dtype=np.float64)
        result = idx.take(np.array([1, 0, -1]))
        expected = Index([2.0, 1.0, 3.0], dtype=np.float64, name="xxx")
        tm.assert_index_equal(result, expected)

        # fill_value
        result = idx.take(np.array([1, 0, -1]), fill_value=True)
        expected = Index([2.0, 1.0, np.nan], dtype=np.float64, name="xxx")
        tm.assert_index_equal(result, expected)

        # allow_fill=False
        result = idx.take(np.array([1, 0, -1]), allow_fill=False, fill_value=True)
        expected = Index([2.0, 1.0, 3.0], dtype=np.float64, name="xxx")
        tm.assert_index_equal(result, expected)

        msg = (
            "When allow_fill=True and fill_value is not None, "
            "all indices must be >= -1"
        )
        with pytest.raises(ValueError, match=msg):
            idx.take(np.array([1, 0, -2]), fill_value=True)
        with pytest.raises(ValueError, match=msg):
            idx.take(np.array([1, 0, -5]), fill_value=True)

        msg = "index -5 is out of bounds for (axis 0 with )?size 3"
        with pytest.raises(IndexError, match=msg):
            idx.take(np.array([1, -5]))

    @pytest.mark.parametrize("dtype", [np.int64, np.uint64])
    def test_take_fill_value_ints(self, dtype):
        # see gh-12631
        idx = Index([1, 2, 3], dtype=dtype, name="xxx")
        result = idx.take(np.array([1, 0, -1]))
        expected = Index([2, 1, 3], dtype=dtype, name="xxx")
        tm.assert_index_equal(result, expected)

        name = type(idx).__name__
        msg = f"Unable to fill values because {name} cannot contain NA"

        # fill_value=True
        with pytest.raises(ValueError, match=msg):
            idx.take(np.array([1, 0, -1]), fill_value=True)

        # allow_fill=False
        result = idx.take(np.array([1, 0, -1]), allow_fill=False, fill_value=True)
        expected = Index([2, 1, 3], dtype=dtype, name="xxx")
        tm.assert_index_equal(result, expected)

        with pytest.raises(ValueError, match=msg):
            idx.take(np.array([1, 0, -2]), fill_value=True)
        with pytest.raises(ValueError, match=msg):
            idx.take(np.array([1, 0, -5]), fill_value=True)

        msg = "index -5 is out of bounds for (axis 0 with )?size 3"
        with pytest.raises(IndexError, match=msg):
            idx.take(np.array([1, -5]))


class TestContains:
    @pytest.mark.parametrize("dtype", [np.float64, np.int64, np.uint64])
    def test_contains_none(self, dtype):
        # GH#35788 should return False, not raise TypeError
        index = Index([0, 1, 2, 3, 4], dtype=dtype)
        assert None not in index

    def test_contains_float64_nans(self):
        index = Index([1.0, 2.0, np.nan], dtype=np.float64)
        assert np.nan in index

    def test_contains_float64_not_nans(self):
        index = Index([1.0, 2.0, np.nan], dtype=np.float64)
        assert 1.0 in index


class TestSliceLocs:
    @pytest.mark.parametrize("dtype", [int, float])
    def test_slice_locs(self, dtype):
        index = Index(np.array([0, 1, 2, 5, 6, 7, 9, 10], dtype=dtype))
        n = len(index)

        assert index.slice_locs(start=2) == (2, n)
        assert index.slice_locs(start=3) == (3, n)
        assert index.slice_locs(3, 8) == (3, 6)
        assert index.slice_locs(5, 10) == (3, n)
        assert index.slice_locs(end=8) == (0, 6)
        assert index.slice_locs(end=9) == (0, 7)

        # reversed
        index2 = index[::-1]
        assert index2.slice_locs(8, 2) == (2, 6)
        assert index2.slice_locs(7, 3) == (2, 5)

    @pytest.mark.parametrize("dtype", [int, float])
    def test_slice_locs_float_locs(self, dtype):
        index = Index(np.array([0, 1, 2, 5, 6, 7, 9, 10], dtype=dtype))
        n = len(index)
        assert index.slice_locs(5.0, 10.0) == (3, n)
        assert index.slice_locs(4.5, 10.5) == (3, 8)

        index2 = index[::-1]
        assert index2.slice_locs(8.5, 1.5) == (2, 6)
        assert index2.slice_locs(10.5, -1) == (0, n)

    @pytest.mark.parametrize("dtype", [int, float])
    def test_slice_locs_dup_numeric(self, dtype):
        index = Index(np.array([10, 12, 12, 14], dtype=dtype))
        assert index.slice_locs(12, 12) == (1, 3)
        assert index.slice_locs(11, 13) == (1, 3)

        index2 = index[::-1]
        assert index2.slice_locs(12, 12) == (1, 3)
        assert index2.slice_locs(13, 11) == (1, 3)

    def test_slice_locs_na(self):
        index = Index([np.nan, 1, 2])
        assert index.slice_locs(1) == (1, 3)
        assert index.slice_locs(np.nan) == (0, 3)

        index = Index([0, np.nan, np.nan, 1, 2])
        assert index.slice_locs(np.nan) == (1, 5)

    def test_slice_locs_na_raises(self):
        index = Index([np.nan, 1, 2])
        with pytest.raises(KeyError, match=""):
            index.slice_locs(start=1.5)

        with pytest.raises(KeyError, match=""):
            index.slice_locs(end=1.5)


class TestGetSliceBounds:
    @pytest.mark.parametrize("side, expected", [("left", 4), ("right", 5)])
    def test_get_slice_bounds_within(self, side, expected):
        index = Index(range(6))
        result = index.get_slice_bound(4, side=side)
        assert result == expected

    @pytest.mark.parametrize("side", ["left", "right"])
    @pytest.mark.parametrize("bound, expected", [(-1, 0), (10, 6)])
    def test_get_slice_bounds_outside(self, side, expected, bound):
        index = Index(range(6))
        result = index.get_slice_bound(bound, side=side)
        assert result == expected
