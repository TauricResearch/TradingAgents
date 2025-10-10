"""
test_indexing tests the following Index methods:
    __getitem__
    get_loc
    get_value
    __contains__
    take
    where
    get_indexer
    get_indexer_for
    slice_locs
    asof_locs

The corresponding tests.indexes.[index_type].test_indexing files
contain tests for the corresponding methods specific to those Index subclasses.
"""
import numpy as np
import pytest

from pandas.compat import PY314
from pandas.errors import InvalidIndexError

from pandas.core.dtypes.common import (
    is_float_dtype,
    is_scalar,
)

from pandas import (
    NA,
    DatetimeIndex,
    Index,
    IntervalIndex,
    MultiIndex,
    NaT,
    PeriodIndex,
    TimedeltaIndex,
)
import pandas._testing as tm


class TestTake:
    def test_take_invalid_kwargs(self, index):
        indices = [1, 2]

        msg = r"take\(\) got an unexpected keyword argument 'foo'"
        with pytest.raises(TypeError, match=msg):
            index.take(indices, foo=2)

        msg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=msg):
            index.take(indices, out=indices)

        msg = "the 'mode' parameter is not supported"
        with pytest.raises(ValueError, match=msg):
            index.take(indices, mode="clip")

    def test_take(self, index):
        indexer = [4, 3, 0, 2]
        if len(index) < 5:
            pytest.skip("Test doesn't make sense since not enough elements")

        result = index.take(indexer)
        expected = index[indexer]
        assert result.equals(expected)

        if not isinstance(index, (DatetimeIndex, PeriodIndex, TimedeltaIndex)):
            # GH 10791
            msg = r"'(.*Index)' object has no attribute 'freq'"
            with pytest.raises(AttributeError, match=msg):
                index.freq

    def test_take_indexer_type(self):
        # GH#42875
        integer_index = Index([0, 1, 2, 3])
        scalar_index = 1
        msg = "Expected indices to be array-like"
        with pytest.raises(TypeError, match=msg):
            integer_index.take(scalar_index)

    def test_take_minus1_without_fill(self, index):
        # -1 does not get treated as NA unless allow_fill=True is passed
        if len(index) == 0:
            # Test is not applicable
            pytest.skip("Test doesn't make sense for empty index")

        result = index.take([0, 0, -1])

        expected = index.take([0, 0, len(index) - 1])
        tm.assert_index_equal(result, expected)


class TestContains:
    @pytest.mark.parametrize(
        "index,val",
        [
            (Index([0, 1, 2]), 2),
            (Index([0, 1, "2"]), "2"),
            (Index([0, 1, 2, np.inf, 4]), 4),
            (Index([0, 1, 2, np.nan, 4]), 4),
            (Index([0, 1, 2, np.inf]), np.inf),
            (Index([0, 1, 2, np.nan]), np.nan),
        ],
    )
    def test_index_contains(self, index, val):
        assert val in index

    @pytest.mark.parametrize(
        "index,val",
        [
            (Index([0, 1, 2]), "2"),
            (Index([0, 1, "2"]), 2),
            (Index([0, 1, 2, np.inf]), 4),
            (Index([0, 1, 2, np.nan]), 4),
            (Index([0, 1, 2, np.inf]), np.nan),
            (Index([0, 1, 2, np.nan]), np.inf),
            # Checking if np.inf in int64 Index should not cause an OverflowError
            # Related to GH 16957
            (Index([0, 1, 2], dtype=np.int64), np.inf),
            (Index([0, 1, 2], dtype=np.int64), np.nan),
            (Index([0, 1, 2], dtype=np.uint64), np.inf),
            (Index([0, 1, 2], dtype=np.uint64), np.nan),
        ],
    )
    def test_index_not_contains(self, index, val):
        assert val not in index

    @pytest.mark.parametrize(
        "index,val", [(Index([0, 1, "2"]), 0), (Index([0, 1, "2"]), "2")]
    )
    def test_mixed_index_contains(self, index, val):
        # GH#19860
        assert val in index

    @pytest.mark.parametrize(
        "index,val", [(Index([0, 1, "2"]), "1"), (Index([0, 1, "2"]), 2)]
    )
    def test_mixed_index_not_contains(self, index, val):
        # GH#19860
        assert val not in index

    def test_contains_with_float_index(self, any_real_numpy_dtype):
        # GH#22085
        dtype = any_real_numpy_dtype
        data = [0, 1, 2, 3] if not is_float_dtype(dtype) else [0.1, 1.1, 2.2, 3.3]
        index = Index(data, dtype=dtype)

        if not is_float_dtype(index.dtype):
            assert 1.1 not in index
            assert 1.0 in index
            assert 1 in index
        else:
            assert 1.1 in index
            assert 1.0 not in index
            assert 1 not in index

    def test_contains_requires_hashable_raises(self, index):
        if isinstance(index, MultiIndex):
            return  # TODO: do we want this to raise?

        msg = "unhashable type: 'list'"
        with pytest.raises(TypeError, match=msg):
            [] in index

        if PY314:
            container_or_iterable = "a container or iterable"
        else:
            container_or_iterable = "iterable"

        msg = "|".join(
            [
                r"unhashable type: 'dict'",
                r"must be real number, not dict",
                r"an integer is required",
                r"\{\}",
                r"pandas\._libs\.interval\.IntervalTree' is not "
                f"{container_or_iterable}",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            {} in index._engine


class TestGetLoc:
    def test_get_loc_non_hashable(self, index):
        with pytest.raises(InvalidIndexError, match="[0, 1]"):
            index.get_loc([0, 1])

    def test_get_loc_non_scalar_hashable(self, index):
        # GH52877
        from enum import Enum

        class E(Enum):
            X1 = "x1"

        assert not is_scalar(E.X1)

        exc = KeyError
        msg = "<E.X1: 'x1'>"
        if isinstance(
            index,
            (
                DatetimeIndex,
                TimedeltaIndex,
                PeriodIndex,
                IntervalIndex,
            ),
        ):
            # TODO: make these more consistent?
            exc = InvalidIndexError
            msg = "E.X1"
        with pytest.raises(exc, match=msg):
            index.get_loc(E.X1)

    def test_get_loc_generator(self, index):
        exc = KeyError
        if isinstance(
            index,
            (
                DatetimeIndex,
                TimedeltaIndex,
                PeriodIndex,
                IntervalIndex,
                MultiIndex,
            ),
        ):
            # TODO: make these more consistent?
            exc = InvalidIndexError
        with pytest.raises(exc, match="generator object"):
            # MultiIndex specifically checks for generator; others for scalar
            index.get_loc(x for x in range(5))

    def test_get_loc_masked_duplicated_na(self):
        # GH#48411
        idx = Index([1, 2, NA, NA], dtype="Int64")
        result = idx.get_loc(NA)
        expected = np.array([False, False, True, True])
        tm.assert_numpy_array_equal(result, expected)


class TestGetIndexer:
    def test_get_indexer_base(self, index):
        if index._index_as_unique:
            expected = np.arange(index.size, dtype=np.intp)
            actual = index.get_indexer(index)
            tm.assert_numpy_array_equal(expected, actual)
        else:
            msg = "Reindexing only valid with uniquely valued Index objects"
            with pytest.raises(InvalidIndexError, match=msg):
                index.get_indexer(index)

        with pytest.raises(ValueError, match="Invalid fill method"):
            index.get_indexer(index, method="invalid")

    def test_get_indexer_consistency(self, index):
        # See GH#16819

        if index._index_as_unique:
            indexer = index.get_indexer(index[0:2])
            assert isinstance(indexer, np.ndarray)
            assert indexer.dtype == np.intp
        else:
            msg = "Reindexing only valid with uniquely valued Index objects"
            with pytest.raises(InvalidIndexError, match=msg):
                index.get_indexer(index[0:2])

        indexer, _ = index.get_indexer_non_unique(index[0:2])
        assert isinstance(indexer, np.ndarray)
        assert indexer.dtype == np.intp

    def test_get_indexer_masked_duplicated_na(self):
        # GH#48411
        idx = Index([1, 2, NA, NA], dtype="Int64")
        result = idx.get_indexer_for(Index([1, NA], dtype="Int64"))
        expected = np.array([0, 2, 3], dtype=result.dtype)
        tm.assert_numpy_array_equal(result, expected)


class TestConvertSliceIndexer:
    def test_convert_almost_null_slice(self, index):
        # slice with None at both ends, but not step

        key = slice(None, None, "foo")

        if isinstance(index, IntervalIndex):
            msg = "label-based slicing with step!=1 is not supported for IntervalIndex"
            with pytest.raises(ValueError, match=msg):
                index._convert_slice_indexer(key, "loc")
        else:
            msg = "'>=' not supported between instances of 'str' and 'int'"
            with pytest.raises(TypeError, match=msg):
                index._convert_slice_indexer(key, "loc")


class TestPutmask:
    def test_putmask_with_wrong_mask(self, index):
        # GH#18368
        if not len(index):
            pytest.skip("Test doesn't make sense for empty index")

        fill = index[0]

        msg = "putmask: mask and data must be the same size"
        with pytest.raises(ValueError, match=msg):
            index.putmask(np.ones(len(index) + 1, np.bool_), fill)

        with pytest.raises(ValueError, match=msg):
            index.putmask(np.ones(len(index) - 1, np.bool_), fill)

        with pytest.raises(ValueError, match=msg):
            index.putmask("foo", fill)


@pytest.mark.parametrize(
    "idx", [Index([1, 2, 3]), Index([0.1, 0.2, 0.3]), Index(["a", "b", "c"])]
)
def test_getitem_deprecated_float(idx):
    # https://github.com/pandas-dev/pandas/issues/34191

    msg = "Indexing with a float is no longer supported"
    with pytest.raises(IndexError, match=msg):
        idx[1.0]


@pytest.mark.parametrize(
    "idx,target,expected",
    [
        ([np.nan, "var1", np.nan], [np.nan], np.array([0, 2], dtype=np.intp)),
        (
            [np.nan, "var1", np.nan],
            [np.nan, "var1"],
            np.array([0, 2, 1], dtype=np.intp),
        ),
        (
            np.array([np.nan, "var1", np.nan], dtype=object),
            [np.nan],
            np.array([0, 2], dtype=np.intp),
        ),
        (
            DatetimeIndex(["2020-08-05", NaT, NaT]),
            [NaT],
            np.array([1, 2], dtype=np.intp),
        ),
        (["a", "b", "a", np.nan], [np.nan], np.array([3], dtype=np.intp)),
        (
            np.array(["b", np.nan, float("NaN"), "b"], dtype=object),
            Index([np.nan], dtype=object),
            np.array([1, 2], dtype=np.intp),
        ),
    ],
)
def test_get_indexer_non_unique_multiple_nans(idx, target, expected):
    # GH 35392
    axis = Index(idx)
    actual = axis.get_indexer_for(target)
    tm.assert_numpy_array_equal(actual, expected)


def test_get_indexer_non_unique_nans_in_object_dtype_target(nulls_fixture):
    idx = Index([1.0, 2.0])
    target = Index([1, nulls_fixture], dtype="object")

    result_idx, result_missing = idx.get_indexer_non_unique(target)
    tm.assert_numpy_array_equal(result_idx, np.array([0, -1], dtype=np.intp))
    tm.assert_numpy_array_equal(result_missing, np.array([1], dtype=np.intp))
