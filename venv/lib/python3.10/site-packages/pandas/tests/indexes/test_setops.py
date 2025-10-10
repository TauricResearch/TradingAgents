"""
The tests in this package are to ensure the proper resultant dtypes of
set operations.
"""
from datetime import datetime
import operator

import numpy as np
import pytest

from pandas._libs import lib

from pandas.core.dtypes.cast import find_common_type

from pandas import (
    CategoricalDtype,
    CategoricalIndex,
    DatetimeTZDtype,
    Index,
    MultiIndex,
    PeriodDtype,
    RangeIndex,
    Series,
    Timestamp,
)
import pandas._testing as tm
from pandas.api.types import (
    is_signed_integer_dtype,
    pandas_dtype,
)


def equal_contents(arr1, arr2) -> bool:
    """
    Checks if the set of unique elements of arr1 and arr2 are equivalent.
    """
    return frozenset(arr1) == frozenset(arr2)


@pytest.fixture(
    params=tm.ALL_REAL_NUMPY_DTYPES
    + [
        "object",
        "category",
        "datetime64[ns]",
        "timedelta64[ns]",
    ]
)
def any_dtype_for_small_pos_integer_indexes(request):
    """
    Dtypes that can be given to an Index with small positive integers.

    This means that for any dtype `x` in the params list, `Index([1, 2, 3], dtype=x)` is
    valid and gives the correct Index (sub-)class.
    """
    return request.param


def test_union_same_types(index):
    # Union with a non-unique, non-monotonic index raises error
    # Only needed for bool index factory
    idx1 = index.sort_values()
    idx2 = index.sort_values()
    assert idx1.union(idx2).dtype == idx1.dtype


def test_union_different_types(index_flat, index_flat2, request, using_infer_string):
    # This test only considers combinations of indices
    # GH 23525
    idx1 = index_flat
    idx2 = index_flat2

    if (
        not idx1.is_unique
        and not idx2.is_unique
        and idx1.dtype.kind == "i"
        and idx2.dtype.kind == "b"
    ) or (
        not idx2.is_unique
        and not idx1.is_unique
        and idx2.dtype.kind == "i"
        and idx1.dtype.kind == "b"
    ):
        # Each condition had idx[1|2].is_monotonic_decreasing
        # but failed when e.g.
        # idx1 = Index(
        # [True, True, True, True, True, True, True, True, False, False], dtype='bool'
        # )
        # idx2 = Index([0, 0, 1, 1, 2, 2], dtype='int64')
        mark = pytest.mark.xfail(
            reason="GH#44000 True==1", raises=ValueError, strict=False
        )
        request.applymarker(mark)

    common_dtype = find_common_type([idx1.dtype, idx2.dtype])
    if using_infer_string:
        if len(idx1) == 0 and (idx1.dtype.kind == "O" or isinstance(idx1, RangeIndex)):
            common_dtype = idx2.dtype
        elif len(idx2) == 0 and (
            idx2.dtype.kind == "O" or isinstance(idx2, RangeIndex)
        ):
            common_dtype = idx1.dtype

    warn = None
    msg = "'<' not supported between"
    if not len(idx1) or not len(idx2):
        pass
    elif (idx1.dtype.kind == "c" and (not lib.is_np_dtype(idx2.dtype, "iufc"))) or (
        idx2.dtype.kind == "c" and (not lib.is_np_dtype(idx1.dtype, "iufc"))
    ):
        # complex objects non-sortable
        warn = RuntimeWarning
    elif (
        isinstance(idx1.dtype, PeriodDtype) and isinstance(idx2.dtype, CategoricalDtype)
    ) or (
        isinstance(idx2.dtype, PeriodDtype) and isinstance(idx1.dtype, CategoricalDtype)
    ):
        warn = FutureWarning
        msg = r"PeriodDtype\[B\] is deprecated"
        mark = pytest.mark.xfail(
            reason="Warning not produced on all builds",
            raises=AssertionError,
            strict=False,
        )
        request.applymarker(mark)

    any_uint64 = np.uint64 in (idx1.dtype, idx2.dtype)
    idx1_signed = is_signed_integer_dtype(idx1.dtype)
    idx2_signed = is_signed_integer_dtype(idx2.dtype)

    # Union with a non-unique, non-monotonic index raises error
    # This applies to the boolean index
    idx1 = idx1.sort_values()
    idx2 = idx2.sort_values()

    with tm.assert_produces_warning(warn, match=msg):
        res1 = idx1.union(idx2)
        res2 = idx2.union(idx1)

    if any_uint64 and (idx1_signed or idx2_signed):
        assert res1.dtype == np.dtype("O")
        assert res2.dtype == np.dtype("O")
    else:
        assert res1.dtype == common_dtype
        assert res2.dtype == common_dtype


@pytest.mark.parametrize(
    "idx1,idx2",
    [
        (Index(np.arange(5), dtype=np.int64), RangeIndex(5)),
        (Index(np.arange(5), dtype=np.float64), Index(np.arange(5), dtype=np.int64)),
        (Index(np.arange(5), dtype=np.float64), RangeIndex(5)),
        (Index(np.arange(5), dtype=np.float64), Index(np.arange(5), dtype=np.uint64)),
    ],
)
def test_compatible_inconsistent_pairs(idx1, idx2):
    # GH 23525
    res1 = idx1.union(idx2)
    res2 = idx2.union(idx1)

    assert res1.dtype in (idx1.dtype, idx2.dtype)
    assert res2.dtype in (idx1.dtype, idx2.dtype)


@pytest.mark.parametrize(
    "left, right, expected",
    [
        ("int64", "int64", "int64"),
        ("int64", "uint64", "object"),
        ("int64", "float64", "float64"),
        ("uint64", "float64", "float64"),
        ("uint64", "uint64", "uint64"),
        ("float64", "float64", "float64"),
        ("datetime64[ns]", "int64", "object"),
        ("datetime64[ns]", "uint64", "object"),
        ("datetime64[ns]", "float64", "object"),
        ("datetime64[ns, CET]", "int64", "object"),
        ("datetime64[ns, CET]", "uint64", "object"),
        ("datetime64[ns, CET]", "float64", "object"),
        ("Period[D]", "int64", "object"),
        ("Period[D]", "uint64", "object"),
        ("Period[D]", "float64", "object"),
    ],
)
@pytest.mark.parametrize("names", [("foo", "foo", "foo"), ("foo", "bar", None)])
def test_union_dtypes(left, right, expected, names):
    left = pandas_dtype(left)
    right = pandas_dtype(right)
    a = Index([], dtype=left, name=names[0])
    b = Index([], dtype=right, name=names[1])
    result = a.union(b)
    assert result.dtype == expected
    assert result.name == names[2]

    # Testing name retention
    # TODO: pin down desired dtype; do we want it to be commutative?
    result = a.intersection(b)
    assert result.name == names[2]


@pytest.mark.parametrize("values", [[1, 2, 2, 3], [3, 3]])
def test_intersection_duplicates(values):
    # GH#31326
    a = Index(values)
    b = Index([3, 3])
    result = a.intersection(b)
    expected = Index([3])
    tm.assert_index_equal(result, expected)


class TestSetOps:
    # Set operation tests shared by all indexes in the `index` fixture
    @pytest.mark.parametrize("case", [0.5, "xxx"])
    @pytest.mark.parametrize(
        "method", ["intersection", "union", "difference", "symmetric_difference"]
    )
    def test_set_ops_error_cases(self, case, method, index):
        # non-iterable input
        msg = "Input must be Index or array-like"
        with pytest.raises(TypeError, match=msg):
            getattr(index, method)(case)

    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_intersection_base(self, index):
        if isinstance(index, CategoricalIndex):
            pytest.skip(f"Not relevant for {type(index).__name__}")

        first = index[:5].unique()
        second = index[:3].unique()
        intersect = first.intersection(second)
        tm.assert_index_equal(intersect, second)

        if isinstance(index.dtype, DatetimeTZDtype):
            # The second.values below will drop tz, so the rest of this test
            #  is not applicable.
            return

        # GH#10149
        cases = [second.to_numpy(), second.to_series(), second.to_list()]
        for case in cases:
            result = first.intersection(case)
            assert equal_contents(result, second)

        if isinstance(index, MultiIndex):
            msg = "other must be a MultiIndex or a list of tuples"
            with pytest.raises(TypeError, match=msg):
                first.intersection([1, 2, 3])

    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_union_base(self, index):
        index = index.unique()
        first = index[3:]
        second = index[:5]
        everything = index

        union = first.union(second)
        tm.assert_index_equal(union.sort_values(), everything.sort_values())

        if isinstance(index.dtype, DatetimeTZDtype):
            # The second.values below will drop tz, so the rest of this test
            #  is not applicable.
            return

        # GH#10149
        cases = [second.to_numpy(), second.to_series(), second.to_list()]
        for case in cases:
            result = first.union(case)
            assert equal_contents(result, everything)

        if isinstance(index, MultiIndex):
            msg = "other must be a MultiIndex or a list of tuples"
            with pytest.raises(TypeError, match=msg):
                first.union([1, 2, 3])

    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_difference_base(self, sort, index):
        first = index[2:]
        second = index[:4]
        if index.inferred_type == "boolean":
            # i think (TODO: be sure) there assumptions baked in about
            #  the index fixture that don't hold here?
            answer = set(first).difference(set(second))
        elif isinstance(index, CategoricalIndex):
            answer = []
        else:
            answer = index[4:]
        result = first.difference(second, sort)
        assert equal_contents(result, answer)

        # GH#10149
        cases = [second.to_numpy(), second.to_series(), second.to_list()]
        for case in cases:
            result = first.difference(case, sort)
            assert equal_contents(result, answer)

        if isinstance(index, MultiIndex):
            msg = "other must be a MultiIndex or a list of tuples"
            with pytest.raises(TypeError, match=msg):
                first.difference([1, 2, 3], sort)

    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_symmetric_difference(self, index, using_infer_string, request):
        if (
            using_infer_string
            and index.dtype == "object"
            and index.inferred_type == "string"
        ):
            request.applymarker(pytest.mark.xfail(reason="TODO: infer_string"))
        if isinstance(index, CategoricalIndex):
            pytest.skip(f"Not relevant for {type(index).__name__}")
        if len(index) < 2:
            pytest.skip("Too few values for test")
        if index[0] in index[1:] or index[-1] in index[:-1]:
            # index fixture has e.g. an index of bools that does not satisfy this,
            #  another with [0, 0, 1, 1, 2, 2]
            pytest.skip("Index values no not satisfy test condition.")

        first = index[1:]
        second = index[:-1]
        answer = index[[0, -1]]
        result = first.symmetric_difference(second)
        tm.assert_index_equal(result.sort_values(), answer.sort_values())

        # GH#10149
        cases = [second.to_numpy(), second.to_series(), second.to_list()]
        for case in cases:
            result = first.symmetric_difference(case)
            assert equal_contents(result, answer)

        if isinstance(index, MultiIndex):
            msg = "other must be a MultiIndex or a list of tuples"
            with pytest.raises(TypeError, match=msg):
                first.symmetric_difference([1, 2, 3])

    @pytest.mark.parametrize(
        "fname, sname, expected_name",
        [
            ("A", "A", "A"),
            ("A", "B", None),
            ("A", None, None),
            (None, "B", None),
            (None, None, None),
        ],
    )
    def test_corner_union(self, index_flat, fname, sname, expected_name):
        # GH#9943, GH#9862
        # Test unions with various name combinations
        # Do not test MultiIndex or repeats
        if not index_flat.is_unique:
            index = index_flat.unique()
        else:
            index = index_flat

        # Test copy.union(copy)
        first = index.copy().set_names(fname)
        second = index.copy().set_names(sname)
        union = first.union(second)
        expected = index.copy().set_names(expected_name)
        tm.assert_index_equal(union, expected)

        # Test copy.union(empty)
        first = index.copy().set_names(fname)
        second = index.drop(index).set_names(sname)
        union = first.union(second)
        expected = index.copy().set_names(expected_name)
        tm.assert_index_equal(union, expected)

        # Test empty.union(copy)
        first = index.drop(index).set_names(fname)
        second = index.copy().set_names(sname)
        union = first.union(second)
        expected = index.copy().set_names(expected_name)
        tm.assert_index_equal(union, expected)

        # Test empty.union(empty)
        first = index.drop(index).set_names(fname)
        second = index.drop(index).set_names(sname)
        union = first.union(second)
        expected = index.drop(index).set_names(expected_name)
        tm.assert_index_equal(union, expected)

    @pytest.mark.parametrize(
        "fname, sname, expected_name",
        [
            ("A", "A", "A"),
            ("A", "B", None),
            ("A", None, None),
            (None, "B", None),
            (None, None, None),
        ],
    )
    def test_union_unequal(self, index_flat, fname, sname, expected_name):
        if not index_flat.is_unique:
            index = index_flat.unique()
        else:
            index = index_flat

        # test copy.union(subset) - need sort for unicode and string
        first = index.copy().set_names(fname)
        second = index[1:].set_names(sname)
        union = first.union(second).sort_values()
        expected = index.set_names(expected_name).sort_values()
        tm.assert_index_equal(union, expected)

    @pytest.mark.parametrize(
        "fname, sname, expected_name",
        [
            ("A", "A", "A"),
            ("A", "B", None),
            ("A", None, None),
            (None, "B", None),
            (None, None, None),
        ],
    )
    def test_corner_intersect(self, index_flat, fname, sname, expected_name):
        # GH#35847
        # Test intersections with various name combinations
        if not index_flat.is_unique:
            index = index_flat.unique()
        else:
            index = index_flat

        # Test copy.intersection(copy)
        first = index.copy().set_names(fname)
        second = index.copy().set_names(sname)
        intersect = first.intersection(second)
        expected = index.copy().set_names(expected_name)
        tm.assert_index_equal(intersect, expected)

        # Test copy.intersection(empty)
        first = index.copy().set_names(fname)
        second = index.drop(index).set_names(sname)
        intersect = first.intersection(second)
        expected = index.drop(index).set_names(expected_name)
        tm.assert_index_equal(intersect, expected)

        # Test empty.intersection(copy)
        first = index.drop(index).set_names(fname)
        second = index.copy().set_names(sname)
        intersect = first.intersection(second)
        expected = index.drop(index).set_names(expected_name)
        tm.assert_index_equal(intersect, expected)

        # Test empty.intersection(empty)
        first = index.drop(index).set_names(fname)
        second = index.drop(index).set_names(sname)
        intersect = first.intersection(second)
        expected = index.drop(index).set_names(expected_name)
        tm.assert_index_equal(intersect, expected)

    @pytest.mark.parametrize(
        "fname, sname, expected_name",
        [
            ("A", "A", "A"),
            ("A", "B", None),
            ("A", None, None),
            (None, "B", None),
            (None, None, None),
        ],
    )
    def test_intersect_unequal(self, index_flat, fname, sname, expected_name):
        if not index_flat.is_unique:
            index = index_flat.unique()
        else:
            index = index_flat

        # test copy.intersection(subset) - need sort for unicode and string
        first = index.copy().set_names(fname)
        second = index[1:].set_names(sname)
        intersect = first.intersection(second).sort_values()
        expected = index[1:].set_names(expected_name).sort_values()
        tm.assert_index_equal(intersect, expected)

    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_intersection_name_retention_with_nameless(self, index):
        if isinstance(index, MultiIndex):
            index = index.rename(list(range(index.nlevels)))
        else:
            index = index.rename("foo")

        other = np.asarray(index)

        result = index.intersection(other)
        assert result.name == index.name

        # empty other, same dtype
        result = index.intersection(other[:0])
        assert result.name == index.name

        # empty `self`
        result = index[:0].intersection(other)
        assert result.name == index.name

    def test_difference_preserves_type_empty(self, index, sort):
        # GH#20040
        # If taking difference of a set and itself, it
        # needs to preserve the type of the index
        if not index.is_unique:
            pytest.skip("Not relevant since index is not unique")
        result = index.difference(index, sort=sort)
        expected = index[:0]
        tm.assert_index_equal(result, expected, exact=True)

    def test_difference_name_retention_equals(self, index, names):
        if isinstance(index, MultiIndex):
            names = [[x] * index.nlevels for x in names]
        index = index.rename(names[0])
        other = index.rename(names[1])

        assert index.equals(other)

        result = index.difference(other)
        expected = index[:0].rename(names[2])
        tm.assert_index_equal(result, expected)

    def test_intersection_difference_match_empty(self, index, sort):
        # GH#20040
        # Test that the intersection of an index with an
        # empty index produces the same index as the difference
        # of an index with itself.  Test for all types
        if not index.is_unique:
            pytest.skip("Not relevant because index is not unique")
        inter = index.intersection(index[:0])
        diff = index.difference(index, sort=sort)
        tm.assert_index_equal(inter, diff, exact=True)


@pytest.mark.filterwarnings("ignore:invalid value encountered in cast:RuntimeWarning")
@pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
@pytest.mark.parametrize(
    "method", ["intersection", "union", "difference", "symmetric_difference"]
)
def test_setop_with_categorical(index_flat, sort, method, using_infer_string):
    # MultiIndex tested separately in tests.indexes.multi.test_setops
    index = index_flat

    other = index.astype("category")
    exact = "equiv" if isinstance(index, RangeIndex) else True

    result = getattr(index, method)(other, sort=sort)
    expected = getattr(index, method)(index, sort=sort)
    if (
        using_infer_string
        and index.empty
        and method in ("union", "symmetric_difference")
    ):
        expected = expected.astype("category")
    tm.assert_index_equal(result, expected, exact=exact)

    result = getattr(index, method)(other[:5], sort=sort)
    expected = getattr(index, method)(index[:5], sort=sort)
    if (
        using_infer_string
        and index.empty
        and method in ("union", "symmetric_difference")
    ):
        expected = expected.astype("category")
    tm.assert_index_equal(result, expected, exact=exact)


def test_intersection_duplicates_all_indexes(index):
    # GH#38743
    if index.empty:
        # No duplicates in empty indexes
        pytest.skip("Not relevant for empty Index")

    idx = index
    idx_non_unique = idx[[0, 0, 1, 2]]

    assert idx.intersection(idx_non_unique).equals(idx_non_unique.intersection(idx))
    assert idx.intersection(idx_non_unique).is_unique


def test_union_duplicate_index_subsets_of_each_other(
    any_dtype_for_small_pos_integer_indexes,
):
    # GH#31326
    dtype = any_dtype_for_small_pos_integer_indexes
    a = Index([1, 2, 2, 3], dtype=dtype)
    b = Index([3, 3, 4], dtype=dtype)

    expected = Index([1, 2, 2, 3, 3, 4], dtype=dtype)
    if isinstance(a, CategoricalIndex):
        expected = Index([1, 2, 2, 3, 3, 4])
    result = a.union(b)
    tm.assert_index_equal(result, expected)
    result = a.union(b, sort=False)
    tm.assert_index_equal(result, expected)


def test_union_with_duplicate_index_and_non_monotonic(
    any_dtype_for_small_pos_integer_indexes,
):
    # GH#36289
    dtype = any_dtype_for_small_pos_integer_indexes
    a = Index([1, 0, 0], dtype=dtype)
    b = Index([0, 1], dtype=dtype)
    expected = Index([0, 0, 1], dtype=dtype)

    result = a.union(b)
    tm.assert_index_equal(result, expected)

    result = b.union(a)
    tm.assert_index_equal(result, expected)


def test_union_duplicate_index_different_dtypes():
    # GH#36289
    a = Index([1, 2, 2, 3])
    b = Index(["1", "0", "0"])
    expected = Index([1, 2, 2, 3, "1", "0", "0"])
    result = a.union(b, sort=False)
    tm.assert_index_equal(result, expected)


def test_union_same_value_duplicated_in_both():
    # GH#36289
    a = Index([0, 0, 1])
    b = Index([0, 0, 1, 2])
    result = a.union(b)
    expected = Index([0, 0, 1, 2])
    tm.assert_index_equal(result, expected)


@pytest.mark.parametrize("dup", [1, np.nan])
def test_union_nan_in_both(dup):
    # GH#36289
    a = Index([np.nan, 1, 2, 2])
    b = Index([np.nan, dup, 1, 2])
    result = a.union(b, sort=False)
    expected = Index([np.nan, dup, 1.0, 2.0, 2.0])
    tm.assert_index_equal(result, expected)


def test_union_rangeindex_sort_true():
    # GH 53490
    idx1 = RangeIndex(1, 100, 6)
    idx2 = RangeIndex(1, 50, 3)
    result = idx1.union(idx2, sort=True)
    expected = Index(
        [
            1,
            4,
            7,
            10,
            13,
            16,
            19,
            22,
            25,
            28,
            31,
            34,
            37,
            40,
            43,
            46,
            49,
            55,
            61,
            67,
            73,
            79,
            85,
            91,
            97,
        ]
    )
    tm.assert_index_equal(result, expected)


def test_union_with_duplicate_index_not_subset_and_non_monotonic(
    any_dtype_for_small_pos_integer_indexes,
):
    # GH#36289
    dtype = any_dtype_for_small_pos_integer_indexes
    a = Index([1, 0, 2], dtype=dtype)
    b = Index([0, 0, 1], dtype=dtype)
    expected = Index([0, 0, 1, 2], dtype=dtype)
    if isinstance(a, CategoricalIndex):
        expected = Index([0, 0, 1, 2])

    result = a.union(b)
    tm.assert_index_equal(result, expected)

    result = b.union(a)
    tm.assert_index_equal(result, expected)


def test_union_int_categorical_with_nan():
    ci = CategoricalIndex([1, 2, np.nan])
    assert ci.categories.dtype.kind == "i"

    idx = Index([1, 2])

    result = idx.union(ci)
    expected = Index([1, 2, np.nan], dtype=np.float64)
    tm.assert_index_equal(result, expected)

    result = ci.union(idx)
    tm.assert_index_equal(result, expected)


class TestSetOpsUnsorted:
    # These may eventually belong in a dtype-specific test_setops, or
    #  parametrized over a more general fixture
    def test_intersect_str_dates(self):
        dt_dates = [datetime(2012, 2, 9), datetime(2012, 2, 22)]

        index1 = Index(dt_dates, dtype=object)
        index2 = Index(["aa"], dtype=object)
        result = index2.intersection(index1)

        expected = Index([], dtype=object)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("index", ["string"], indirect=True)
    def test_intersection(self, index, sort):
        first = index[:20]
        second = index[:10]
        intersect = first.intersection(second, sort=sort)
        if sort in (None, False):
            tm.assert_index_equal(intersect.sort_values(), second.sort_values())
        else:
            tm.assert_index_equal(intersect, second)

        # Corner cases
        inter = first.intersection(first, sort=sort)
        assert inter is first

    @pytest.mark.parametrize(
        "index2,keeps_name",
        [
            (Index([3, 4, 5, 6, 7], name="index"), True),  # preserve same name
            (Index([3, 4, 5, 6, 7], name="other"), False),  # drop diff names
            (Index([3, 4, 5, 6, 7]), False),
        ],
    )
    def test_intersection_name_preservation(self, index2, keeps_name, sort):
        index1 = Index([1, 2, 3, 4, 5], name="index")
        expected = Index([3, 4, 5])
        result = index1.intersection(index2, sort)

        if keeps_name:
            expected.name = "index"

        assert result.name == expected.name
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("index", ["string"], indirect=True)
    @pytest.mark.parametrize(
        "first_name,second_name,expected_name",
        [("A", "A", "A"), ("A", "B", None), (None, "B", None)],
    )
    def test_intersection_name_preservation2(
        self, index, first_name, second_name, expected_name, sort
    ):
        first = index[5:20]
        second = index[:10]
        first.name = first_name
        second.name = second_name
        intersect = first.intersection(second, sort=sort)
        assert intersect.name == expected_name

    def test_chained_union(self, sort):
        # Chained unions handles names correctly
        i1 = Index([1, 2], name="i1")
        i2 = Index([5, 6], name="i2")
        i3 = Index([3, 4], name="i3")
        union = i1.union(i2.union(i3, sort=sort), sort=sort)
        expected = i1.union(i2, sort=sort).union(i3, sort=sort)
        tm.assert_index_equal(union, expected)

        j1 = Index([1, 2], name="j1")
        j2 = Index([], name="j2")
        j3 = Index([], name="j3")
        union = j1.union(j2.union(j3, sort=sort), sort=sort)
        expected = j1.union(j2, sort=sort).union(j3, sort=sort)
        tm.assert_index_equal(union, expected)

    @pytest.mark.parametrize("index", ["string"], indirect=True)
    def test_union(self, index, sort):
        first = index[5:20]
        second = index[:10]
        everything = index[:20]

        union = first.union(second, sort=sort)
        if sort in (None, False):
            tm.assert_index_equal(union.sort_values(), everything.sort_values())
        else:
            tm.assert_index_equal(union, everything)

    @pytest.mark.parametrize("klass", [np.array, Series, list])
    @pytest.mark.parametrize("index", ["string"], indirect=True)
    def test_union_from_iterables(self, index, klass, sort):
        # GH#10149
        first = index[5:20]
        second = index[:10]
        everything = index[:20]

        case = klass(second.values)
        result = first.union(case, sort=sort)
        if sort in (None, False):
            tm.assert_index_equal(result.sort_values(), everything.sort_values())
        else:
            tm.assert_index_equal(result, everything)

    @pytest.mark.parametrize("index", ["string"], indirect=True)
    def test_union_identity(self, index, sort):
        first = index[5:20]

        union = first.union(first, sort=sort)
        # i.e. identity is not preserved when sort is True
        assert (union is first) is (not sort)

        # This should no longer be the same object, since [] is not consistent,
        # both objects will be recast to dtype('O')
        union = first.union(Index([], dtype=first.dtype), sort=sort)
        assert (union is first) is (not sort)

        union = Index([], dtype=first.dtype).union(first, sort=sort)
        assert (union is first) is (not sort)

    @pytest.mark.parametrize("index", ["string"], indirect=True)
    @pytest.mark.parametrize("second_name,expected", [(None, None), ("name", "name")])
    def test_difference_name_preservation(self, index, second_name, expected, sort):
        first = index[5:20]
        second = index[:10]
        answer = index[10:20]

        first.name = "name"
        second.name = second_name
        result = first.difference(second, sort=sort)

        if sort is True:
            tm.assert_index_equal(result, answer)
        else:
            answer.name = second_name
            tm.assert_index_equal(result.sort_values(), answer.sort_values())

        if expected is None:
            assert result.name is None
        else:
            assert result.name == expected

    def test_difference_empty_arg(self, index, sort):
        first = index.copy()
        first = first[5:20]
        first.name = "name"
        result = first.difference([], sort)
        expected = index[5:20].unique()
        expected.name = "name"
        tm.assert_index_equal(result, expected)

    def test_difference_should_not_compare(self):
        # GH 55113
        left = Index([1, 1])
        right = Index([True])
        result = left.difference(right)
        expected = Index([1])
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("index", ["string"], indirect=True)
    def test_difference_identity(self, index, sort):
        first = index[5:20]
        first.name = "name"
        result = first.difference(first, sort)

        assert len(result) == 0
        assert result.name == first.name

    @pytest.mark.parametrize("index", ["string"], indirect=True)
    def test_difference_sort(self, index, sort):
        first = index[5:20]
        second = index[:10]

        result = first.difference(second, sort)
        expected = index[10:20]

        if sort is None:
            expected = expected.sort_values()

        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("opname", ["difference", "symmetric_difference"])
    def test_difference_incomparable(self, opname):
        a = Index([3, Timestamp("2000"), 1])
        b = Index([2, Timestamp("1999"), 1])
        op = operator.methodcaller(opname, b)

        with tm.assert_produces_warning(RuntimeWarning):
            # sort=None, the default
            result = op(a)
        expected = Index([3, Timestamp("2000"), 2, Timestamp("1999")])
        if opname == "difference":
            expected = expected[:2]
        tm.assert_index_equal(result, expected)

        # sort=False
        op = operator.methodcaller(opname, b, sort=False)
        result = op(a)
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("opname", ["difference", "symmetric_difference"])
    def test_difference_incomparable_true(self, opname):
        a = Index([3, Timestamp("2000"), 1])
        b = Index([2, Timestamp("1999"), 1])
        op = operator.methodcaller(opname, b, sort=True)

        msg = "'<' not supported between instances of 'Timestamp' and 'int'"
        with pytest.raises(TypeError, match=msg):
            op(a)

    def test_symmetric_difference_mi(self, sort):
        index1 = MultiIndex.from_tuples(zip(["foo", "bar", "baz"], [1, 2, 3]))
        index2 = MultiIndex.from_tuples([("foo", 1), ("bar", 3)])
        result = index1.symmetric_difference(index2, sort=sort)
        expected = MultiIndex.from_tuples([("bar", 2), ("baz", 3), ("bar", 3)])
        if sort is None:
            expected = expected.sort_values()
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "index2,expected",
        [
            (Index([0, 1, np.nan]), Index([2.0, 3.0, 0.0])),
            (Index([0, 1]), Index([np.nan, 2.0, 3.0, 0.0])),
        ],
    )
    def test_symmetric_difference_missing(self, index2, expected, sort):
        # GH#13514 change: {nan} - {nan} == {}
        # (GH#6444, sorting of nans, is no longer an issue)
        index1 = Index([1, np.nan, 2, 3])

        result = index1.symmetric_difference(index2, sort=sort)
        if sort is None:
            expected = expected.sort_values()
        tm.assert_index_equal(result, expected)

    def test_symmetric_difference_non_index(self, sort):
        index1 = Index([1, 2, 3, 4], name="index1")
        index2 = np.array([2, 3, 4, 5])
        expected = Index([1, 5], name="index1")
        result = index1.symmetric_difference(index2, sort=sort)
        if sort in (None, True):
            tm.assert_index_equal(result, expected)
        else:
            tm.assert_index_equal(result.sort_values(), expected)
        assert result.name == "index1"

        result = index1.symmetric_difference(index2, result_name="new_name", sort=sort)
        expected.name = "new_name"
        if sort in (None, True):
            tm.assert_index_equal(result, expected)
        else:
            tm.assert_index_equal(result.sort_values(), expected)
        assert result.name == "new_name"

    def test_union_ea_dtypes(self, any_numeric_ea_and_arrow_dtype):
        # GH#51365
        idx = Index([1, 2, 3], dtype=any_numeric_ea_and_arrow_dtype)
        idx2 = Index([3, 4, 5], dtype=any_numeric_ea_and_arrow_dtype)
        result = idx.union(idx2)
        expected = Index([1, 2, 3, 4, 5], dtype=any_numeric_ea_and_arrow_dtype)
        tm.assert_index_equal(result, expected)

    def test_union_string_array(self, any_string_dtype):
        idx1 = Index(["a"], dtype=any_string_dtype)
        idx2 = Index(["b"], dtype=any_string_dtype)
        result = idx1.union(idx2)
        expected = Index(["a", "b"], dtype=any_string_dtype)
        tm.assert_index_equal(result, expected)
