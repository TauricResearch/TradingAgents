"""
Collection of tests asserting things that should be true for
any index subclass except for MultiIndex. Makes use of the `index_flat`
fixture defined in pandas/conftest.py.
"""
from copy import (
    copy,
    deepcopy,
)
import re

import numpy as np
import pytest

from pandas.compat import IS64
from pandas.compat.numpy import np_version_gte1p25

from pandas.core.dtypes.common import (
    is_integer_dtype,
    is_numeric_dtype,
)

import pandas as pd
from pandas import (
    CategoricalIndex,
    MultiIndex,
    PeriodIndex,
    RangeIndex,
)
import pandas._testing as tm


class TestCommon:
    @pytest.mark.parametrize("name", [None, "new_name"])
    def test_to_frame(self, name, index_flat, using_copy_on_write):
        # see GH#15230, GH#22580
        idx = index_flat

        if name:
            idx_name = name
        else:
            idx_name = idx.name or 0

        df = idx.to_frame(name=idx_name)

        assert df.index is idx
        assert len(df.columns) == 1
        assert df.columns[0] == idx_name
        if not using_copy_on_write:
            assert df[idx_name].values is not idx.values

        df = idx.to_frame(index=False, name=idx_name)
        assert df.index is not idx

    def test_droplevel(self, index_flat):
        # GH 21115
        # MultiIndex is tested separately in test_multi.py
        index = index_flat

        assert index.droplevel([]).equals(index)

        for level in [index.name, [index.name]]:
            if isinstance(index.name, tuple) and level is index.name:
                # GH 21121 : droplevel with tuple name
                continue
            msg = (
                "Cannot remove 1 levels from an index with 1 levels: at least one "
                "level must be left."
            )
            with pytest.raises(ValueError, match=msg):
                index.droplevel(level)

        for level in "wrong", ["wrong"]:
            with pytest.raises(
                KeyError,
                match=r"'Requested level \(wrong\) does not match index name \(None\)'",
            ):
                index.droplevel(level)

    def test_constructor_non_hashable_name(self, index_flat):
        # GH 20527
        index = index_flat

        message = "Index.name must be a hashable type"
        renamed = [["1"]]

        # With .rename()
        with pytest.raises(TypeError, match=message):
            index.rename(name=renamed)

        # With .set_names()
        with pytest.raises(TypeError, match=message):
            index.set_names(names=renamed)

    def test_constructor_unwraps_index(self, index_flat):
        a = index_flat
        # Passing dtype is necessary for Index([True, False], dtype=object)
        #  case.
        b = type(a)(a, dtype=a.dtype)
        tm.assert_equal(a._data, b._data)

    def test_to_flat_index(self, index_flat):
        # 22866
        index = index_flat

        result = index.to_flat_index()
        tm.assert_index_equal(result, index)

    def test_set_name_methods(self, index_flat):
        # MultiIndex tested separately
        index = index_flat
        new_name = "This is the new name for this index"

        original_name = index.name
        new_ind = index.set_names([new_name])
        assert new_ind.name == new_name
        assert index.name == original_name
        res = index.rename(new_name, inplace=True)

        # should return None
        assert res is None
        assert index.name == new_name
        assert index.names == [new_name]
        with pytest.raises(ValueError, match="Level must be None"):
            index.set_names("a", level=0)

        # rename in place just leaves tuples and other containers alone
        name = ("A", "B")
        index.rename(name, inplace=True)
        assert index.name == name
        assert index.names == [name]

    @pytest.mark.xfail
    def test_set_names_single_label_no_level(self, index_flat):
        with pytest.raises(TypeError, match="list-like"):
            # should still fail even if it would be the right length
            index_flat.set_names("a")

    def test_copy_and_deepcopy(self, index_flat):
        index = index_flat

        for func in (copy, deepcopy):
            idx_copy = func(index)
            assert idx_copy is not index
            assert idx_copy.equals(index)

        new_copy = index.copy(deep=True, name="banana")
        assert new_copy.name == "banana"

    @pytest.mark.filterwarnings(r"ignore:Dtype inference:FutureWarning")
    def test_copy_name(self, index_flat):
        # GH#12309: Check that the "name" argument
        # passed at initialization is honored.
        index = index_flat

        first = type(index)(index, copy=True, name="mario")
        second = type(first)(first, copy=False)

        # Even though "copy=False", we want a new object.
        assert first is not second
        tm.assert_index_equal(first, second)

        # Not using tm.assert_index_equal() since names differ.
        assert index.equals(first)

        assert first.name == "mario"
        assert second.name == "mario"

        # TODO: belongs in series arithmetic tests?
        s1 = pd.Series(2, index=first)
        s2 = pd.Series(3, index=second[:-1])
        # See GH#13365
        s3 = s1 * s2
        assert s3.index.name == "mario"

    def test_copy_name2(self, index_flat):
        # GH#35592
        index = index_flat

        assert index.copy(name="mario").name == "mario"

        with pytest.raises(ValueError, match="Length of new names must be 1, got 2"):
            index.copy(name=["mario", "luigi"])

        msg = f"{type(index).__name__}.name must be a hashable type"
        with pytest.raises(TypeError, match=msg):
            index.copy(name=[["mario"]])

    def test_unique_level(self, index_flat):
        # don't test a MultiIndex here (as its tested separated)
        index = index_flat

        # GH 17896
        expected = index.drop_duplicates()
        for level in [0, index.name, None]:
            result = index.unique(level=level)
            tm.assert_index_equal(result, expected)

        msg = "Too many levels: Index has only 1 level, not 4"
        with pytest.raises(IndexError, match=msg):
            index.unique(level=3)

        msg = (
            rf"Requested level \(wrong\) does not match index name "
            rf"\({re.escape(index.name.__repr__())}\)"
        )
        with pytest.raises(KeyError, match=msg):
            index.unique(level="wrong")

    def test_unique(self, index_flat):
        # MultiIndex tested separately
        index = index_flat
        if not len(index):
            pytest.skip("Skip check for empty Index and MultiIndex")

        idx = index[[0] * 5]
        idx_unique = index[[0]]

        # We test against `idx_unique`, so first we make sure it's unique
        # and doesn't contain nans.
        assert idx_unique.is_unique is True
        try:
            assert idx_unique.hasnans is False
        except NotImplementedError:
            pass

        result = idx.unique()
        tm.assert_index_equal(result, idx_unique)

        # nans:
        if not index._can_hold_na:
            pytest.skip("Skip na-check if index cannot hold na")

        vals = index._values[[0] * 5]
        vals[0] = np.nan

        vals_unique = vals[:2]
        idx_nan = index._shallow_copy(vals)
        idx_unique_nan = index._shallow_copy(vals_unique)
        assert idx_unique_nan.is_unique is True

        assert idx_nan.dtype == index.dtype
        assert idx_unique_nan.dtype == index.dtype

        expected = idx_unique_nan
        for pos, i in enumerate([idx_nan, idx_unique_nan]):
            result = i.unique()
            tm.assert_index_equal(result, expected)

    @pytest.mark.filterwarnings("ignore:Period with BDay freq:FutureWarning")
    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_searchsorted_monotonic(self, index_flat, request):
        # GH17271
        index = index_flat
        # not implemented for tuple searches in MultiIndex
        # or Intervals searches in IntervalIndex
        if isinstance(index, pd.IntervalIndex):
            mark = pytest.mark.xfail(
                reason="IntervalIndex.searchsorted does not support Interval arg",
                raises=NotImplementedError,
            )
            request.applymarker(mark)

        # nothing to test if the index is empty
        if index.empty:
            pytest.skip("Skip check for empty Index")
        value = index[0]

        # determine the expected results (handle dupes for 'right')
        expected_left, expected_right = 0, (index == value).argmin()
        if expected_right == 0:
            # all values are the same, expected_right should be length
            expected_right = len(index)

        # test _searchsorted_monotonic in all cases
        # test searchsorted only for increasing
        if index.is_monotonic_increasing:
            ssm_left = index._searchsorted_monotonic(value, side="left")
            assert expected_left == ssm_left

            ssm_right = index._searchsorted_monotonic(value, side="right")
            assert expected_right == ssm_right

            ss_left = index.searchsorted(value, side="left")
            assert expected_left == ss_left

            ss_right = index.searchsorted(value, side="right")
            assert expected_right == ss_right

        elif index.is_monotonic_decreasing:
            ssm_left = index._searchsorted_monotonic(value, side="left")
            assert expected_left == ssm_left

            ssm_right = index._searchsorted_monotonic(value, side="right")
            assert expected_right == ssm_right
        else:
            # non-monotonic should raise.
            msg = "index must be monotonic increasing or decreasing"
            with pytest.raises(ValueError, match=msg):
                index._searchsorted_monotonic(value, side="left")

    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_drop_duplicates(self, index_flat, keep):
        # MultiIndex is tested separately
        index = index_flat
        if isinstance(index, RangeIndex):
            pytest.skip(
                "RangeIndex is tested in test_drop_duplicates_no_duplicates "
                "as it cannot hold duplicates"
            )
        if len(index) == 0:
            pytest.skip(
                "empty index is tested in test_drop_duplicates_no_duplicates "
                "as it cannot hold duplicates"
            )

        # make unique index
        holder = type(index)
        unique_values = list(set(index))
        dtype = index.dtype if is_numeric_dtype(index) else None
        unique_idx = holder(unique_values, dtype=dtype)

        # make duplicated index
        n = len(unique_idx)
        duplicated_selection = np.random.default_rng(2).choice(n, int(n * 1.5))
        idx = holder(unique_idx.values[duplicated_selection])

        # Series.duplicated is tested separately
        expected_duplicated = (
            pd.Series(duplicated_selection).duplicated(keep=keep).values
        )
        tm.assert_numpy_array_equal(idx.duplicated(keep=keep), expected_duplicated)

        # Series.drop_duplicates is tested separately
        expected_dropped = holder(pd.Series(idx).drop_duplicates(keep=keep))
        tm.assert_index_equal(idx.drop_duplicates(keep=keep), expected_dropped)

    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_drop_duplicates_no_duplicates(self, index_flat):
        # MultiIndex is tested separately
        index = index_flat

        # make unique index
        if isinstance(index, RangeIndex):
            # RangeIndex cannot have duplicates
            unique_idx = index
        else:
            holder = type(index)
            unique_values = list(set(index))
            dtype = index.dtype if is_numeric_dtype(index) else None
            unique_idx = holder(unique_values, dtype=dtype)

        # check on unique index
        expected_duplicated = np.array([False] * len(unique_idx), dtype="bool")
        tm.assert_numpy_array_equal(unique_idx.duplicated(), expected_duplicated)
        result_dropped = unique_idx.drop_duplicates()
        tm.assert_index_equal(result_dropped, unique_idx)
        # validate shallow copy
        assert result_dropped is not unique_idx

    def test_drop_duplicates_inplace(self, index):
        msg = r"drop_duplicates\(\) got an unexpected keyword argument"
        with pytest.raises(TypeError, match=msg):
            index.drop_duplicates(inplace=True)

    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_has_duplicates(self, index_flat):
        # MultiIndex tested separately in:
        #   tests/indexes/multi/test_unique_and_duplicates.
        index = index_flat
        holder = type(index)
        if not len(index) or isinstance(index, RangeIndex):
            # MultiIndex tested separately in:
            #   tests/indexes/multi/test_unique_and_duplicates.
            # RangeIndex is unique by definition.
            pytest.skip("Skip check for empty Index, MultiIndex, and RangeIndex")

        idx = holder([index[0]] * 5)
        assert idx.is_unique is False
        assert idx.has_duplicates is True

    @pytest.mark.parametrize(
        "dtype",
        ["int64", "uint64", "float64", "category", "datetime64[ns]", "timedelta64[ns]"],
    )
    def test_astype_preserves_name(self, index, dtype):
        # https://github.com/pandas-dev/pandas/issues/32013
        if isinstance(index, MultiIndex):
            index.names = ["idx" + str(i) for i in range(index.nlevels)]
        else:
            index.name = "idx"

        warn = None
        if index.dtype.kind == "c" and dtype in ["float64", "int64", "uint64"]:
            # imaginary components discarded
            if np_version_gte1p25:
                warn = np.exceptions.ComplexWarning
            else:
                warn = np.ComplexWarning

        is_pyarrow_str = str(index.dtype) == "string[pyarrow]" and dtype == "category"
        try:
            # Some of these conversions cannot succeed so we use a try / except
            with tm.assert_produces_warning(
                warn,
                raise_on_extra_warnings=is_pyarrow_str,
                check_stacklevel=False,
            ):
                result = index.astype(dtype)
        except (ValueError, TypeError, NotImplementedError, SystemError):
            return

        if isinstance(index, MultiIndex):
            assert result.names == index.names
        else:
            assert result.name == index.name

    def test_hasnans_isnans(self, index_flat):
        # GH#11343, added tests for hasnans / isnans
        index = index_flat

        # cases in indices doesn't include NaN
        idx = index.copy(deep=True)
        expected = np.array([False] * len(idx), dtype=bool)
        tm.assert_numpy_array_equal(idx._isnan, expected)
        assert idx.hasnans is False

        idx = index.copy(deep=True)
        values = idx._values

        if len(index) == 0:
            return
        elif is_integer_dtype(index.dtype):
            return
        elif index.dtype == bool:
            # values[1] = np.nan below casts to True!
            return

        values[1] = np.nan

        idx = type(index)(values)

        expected = np.array([False] * len(idx), dtype=bool)
        expected[1] = True
        tm.assert_numpy_array_equal(idx._isnan, expected)
        assert idx.hasnans is True


@pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
@pytest.mark.parametrize("na_position", [None, "middle"])
def test_sort_values_invalid_na_position(index_with_missing, na_position):
    with pytest.raises(ValueError, match=f"invalid na_position: {na_position}"):
        index_with_missing.sort_values(na_position=na_position)


@pytest.mark.fails_arm_wheels
@pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
@pytest.mark.parametrize("na_position", ["first", "last"])
def test_sort_values_with_missing(index_with_missing, na_position, request):
    # GH 35584. Test that sort_values works with missing values,
    # sort non-missing and place missing according to na_position

    if isinstance(index_with_missing, CategoricalIndex):
        request.applymarker(
            pytest.mark.xfail(
                reason="missing value sorting order not well-defined", strict=False
            )
        )

    missing_count = np.sum(index_with_missing.isna())
    not_na_vals = index_with_missing[index_with_missing.notna()].values
    sorted_values = np.sort(not_na_vals)
    if na_position == "first":
        sorted_values = np.concatenate([[None] * missing_count, sorted_values])
    else:
        sorted_values = np.concatenate([sorted_values, [None] * missing_count])

    # Explicitly pass dtype needed for Index backed by EA e.g. IntegerArray
    expected = type(index_with_missing)(sorted_values, dtype=index_with_missing.dtype)

    result = index_with_missing.sort_values(na_position=na_position)
    tm.assert_index_equal(result, expected)


def test_ndarray_compat_properties(index):
    if isinstance(index, PeriodIndex) and not IS64:
        pytest.skip("Overflow")
    idx = index
    assert idx.T.equals(idx)
    assert idx.transpose().equals(idx)

    values = idx.values

    assert idx.shape == values.shape
    assert idx.ndim == values.ndim
    assert idx.size == values.size

    if not isinstance(index, (RangeIndex, MultiIndex)):
        # These two are not backed by an ndarray
        assert idx.nbytes == values.nbytes

    # test for validity
    idx.nbytes
    idx.values.nbytes


def test_compare_read_only_array():
    # GH#57130
    arr = np.array([], dtype=object)
    arr.flags.writeable = False
    idx = pd.Index(arr)
    result = idx > 69
    assert result.dtype == bool
