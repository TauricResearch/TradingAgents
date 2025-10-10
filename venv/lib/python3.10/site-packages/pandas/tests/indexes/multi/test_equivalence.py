import numpy as np
import pytest

from pandas.core.dtypes.common import is_any_real_numeric_dtype

import pandas as pd
from pandas import (
    Index,
    MultiIndex,
    Series,
)
import pandas._testing as tm


def test_equals(idx):
    assert idx.equals(idx)
    assert idx.equals(idx.copy())
    assert idx.equals(idx.astype(object))
    assert idx.equals(idx.to_flat_index())
    assert idx.equals(idx.to_flat_index().astype("category"))

    assert not idx.equals(list(idx))
    assert not idx.equals(np.array(idx))

    same_values = Index(idx, dtype=object)
    assert idx.equals(same_values)
    assert same_values.equals(idx)

    if idx.nlevels == 1:
        # do not test MultiIndex
        assert not idx.equals(Series(idx))


def test_equals_op(idx):
    # GH9947, GH10637
    index_a = idx

    n = len(index_a)
    index_b = index_a[0:-1]
    index_c = index_a[0:-1].append(index_a[-2:-1])
    index_d = index_a[0:1]
    with pytest.raises(ValueError, match="Lengths must match"):
        index_a == index_b
    expected1 = np.array([True] * n)
    expected2 = np.array([True] * (n - 1) + [False])
    tm.assert_numpy_array_equal(index_a == index_a, expected1)
    tm.assert_numpy_array_equal(index_a == index_c, expected2)

    # test comparisons with numpy arrays
    array_a = np.array(index_a)
    array_b = np.array(index_a[0:-1])
    array_c = np.array(index_a[0:-1].append(index_a[-2:-1]))
    array_d = np.array(index_a[0:1])
    with pytest.raises(ValueError, match="Lengths must match"):
        index_a == array_b
    tm.assert_numpy_array_equal(index_a == array_a, expected1)
    tm.assert_numpy_array_equal(index_a == array_c, expected2)

    # test comparisons with Series
    series_a = Series(array_a)
    series_b = Series(array_b)
    series_c = Series(array_c)
    series_d = Series(array_d)
    with pytest.raises(ValueError, match="Lengths must match"):
        index_a == series_b

    tm.assert_numpy_array_equal(index_a == series_a, expected1)
    tm.assert_numpy_array_equal(index_a == series_c, expected2)

    # cases where length is 1 for one of them
    with pytest.raises(ValueError, match="Lengths must match"):
        index_a == index_d
    with pytest.raises(ValueError, match="Lengths must match"):
        index_a == series_d
    with pytest.raises(ValueError, match="Lengths must match"):
        index_a == array_d
    msg = "Can only compare identically-labeled Series objects"
    with pytest.raises(ValueError, match=msg):
        series_a == series_d
    with pytest.raises(ValueError, match="Lengths must match"):
        series_a == array_d

    # comparing with a scalar should broadcast; note that we are excluding
    # MultiIndex because in this case each item in the index is a tuple of
    # length 2, and therefore is considered an array of length 2 in the
    # comparison instead of a scalar
    if not isinstance(index_a, MultiIndex):
        expected3 = np.array([False] * (len(index_a) - 2) + [True, False])
        # assuming the 2nd to last item is unique in the data
        item = index_a[-2]
        tm.assert_numpy_array_equal(index_a == item, expected3)
        tm.assert_series_equal(series_a == item, Series(expected3))


def test_compare_tuple():
    # GH#21517
    mi = MultiIndex.from_product([[1, 2]] * 2)

    all_false = np.array([False, False, False, False])

    result = mi == mi[0]
    expected = np.array([True, False, False, False])
    tm.assert_numpy_array_equal(result, expected)

    result = mi != mi[0]
    tm.assert_numpy_array_equal(result, ~expected)

    result = mi < mi[0]
    tm.assert_numpy_array_equal(result, all_false)

    result = mi <= mi[0]
    tm.assert_numpy_array_equal(result, expected)

    result = mi > mi[0]
    tm.assert_numpy_array_equal(result, ~expected)

    result = mi >= mi[0]
    tm.assert_numpy_array_equal(result, ~all_false)


def test_compare_tuple_strs():
    # GH#34180

    mi = MultiIndex.from_tuples([("a", "b"), ("b", "c"), ("c", "a")])

    result = mi == ("c", "a")
    expected = np.array([False, False, True])
    tm.assert_numpy_array_equal(result, expected)

    result = mi == ("c",)
    expected = np.array([False, False, False])
    tm.assert_numpy_array_equal(result, expected)


def test_equals_multi(idx):
    assert idx.equals(idx)
    assert not idx.equals(idx.values)
    assert idx.equals(Index(idx.values))

    assert idx.equal_levels(idx)
    assert not idx.equals(idx[:-1])
    assert not idx.equals(idx[-1])

    # different number of levels
    index = MultiIndex(
        levels=[Index(list(range(4))), Index(list(range(4))), Index(list(range(4)))],
        codes=[
            np.array([0, 0, 1, 2, 2, 2, 3, 3]),
            np.array([0, 1, 0, 0, 0, 1, 0, 1]),
            np.array([1, 0, 1, 1, 0, 0, 1, 0]),
        ],
    )

    index2 = MultiIndex(levels=index.levels[:-1], codes=index.codes[:-1])
    assert not index.equals(index2)
    assert not index.equal_levels(index2)

    # levels are different
    major_axis = Index(list(range(4)))
    minor_axis = Index(list(range(2)))

    major_codes = np.array([0, 0, 1, 2, 2, 3])
    minor_codes = np.array([0, 1, 0, 0, 1, 0])

    index = MultiIndex(
        levels=[major_axis, minor_axis], codes=[major_codes, minor_codes]
    )
    assert not idx.equals(index)
    assert not idx.equal_levels(index)

    # some of the labels are different
    major_axis = Index(["foo", "bar", "baz", "qux"])
    minor_axis = Index(["one", "two"])

    major_codes = np.array([0, 0, 2, 2, 3, 3])
    minor_codes = np.array([0, 1, 0, 1, 0, 1])

    index = MultiIndex(
        levels=[major_axis, minor_axis], codes=[major_codes, minor_codes]
    )
    assert not idx.equals(index)


def test_identical(idx):
    mi = idx.copy()
    mi2 = idx.copy()
    assert mi.identical(mi2)

    mi = mi.set_names(["new1", "new2"])
    assert mi.equals(mi2)
    assert not mi.identical(mi2)

    mi2 = mi2.set_names(["new1", "new2"])
    assert mi.identical(mi2)

    mi4 = Index(mi.tolist(), tupleize_cols=False)
    assert not mi.identical(mi4)
    assert mi.equals(mi4)


def test_equals_operator(idx):
    # GH9785
    assert (idx == idx).all()


def test_equals_missing_values():
    # make sure take is not using -1
    i = MultiIndex.from_tuples([(0, pd.NaT), (0, pd.Timestamp("20130101"))])
    result = i[0:1].equals(i[0])
    assert not result
    result = i[1:2].equals(i[1])
    assert not result


def test_equals_missing_values_differently_sorted():
    # GH#38439
    mi1 = MultiIndex.from_tuples([(81.0, np.nan), (np.nan, np.nan)])
    mi2 = MultiIndex.from_tuples([(np.nan, np.nan), (81.0, np.nan)])
    assert not mi1.equals(mi2)

    mi2 = MultiIndex.from_tuples([(81.0, np.nan), (np.nan, np.nan)])
    assert mi1.equals(mi2)


def test_is_():
    mi = MultiIndex.from_tuples(zip(range(10), range(10)))
    assert mi.is_(mi)
    assert mi.is_(mi.view())
    assert mi.is_(mi.view().view().view().view())
    mi2 = mi.view()
    # names are metadata, they don't change id
    mi2.names = ["A", "B"]
    assert mi2.is_(mi)
    assert mi.is_(mi2)

    assert not mi.is_(mi.set_names(["C", "D"]))
    # levels are inherent properties, they change identity
    mi3 = mi2.set_levels([list(range(10)), list(range(10))])
    assert not mi3.is_(mi2)
    # shouldn't change
    assert mi2.is_(mi)
    mi4 = mi3.view()

    # GH 17464 - Remove duplicate MultiIndex levels
    mi4 = mi4.set_levels([list(range(10)), list(range(10))])
    assert not mi4.is_(mi3)
    mi5 = mi.view()
    mi5 = mi5.set_levels(mi5.levels)
    assert not mi5.is_(mi)


def test_is_all_dates(idx):
    assert not idx._is_all_dates


def test_is_numeric(idx):
    # MultiIndex is never numeric
    assert not is_any_real_numeric_dtype(idx)


def test_multiindex_compare():
    # GH 21149
    # Ensure comparison operations for MultiIndex with nlevels == 1
    # behave consistently with those for MultiIndex with nlevels > 1

    midx = MultiIndex.from_product([[0, 1]])

    # Equality self-test: MultiIndex object vs self
    expected = Series([True, True])
    result = Series(midx == midx)
    tm.assert_series_equal(result, expected)

    # Greater than comparison: MultiIndex object vs self
    expected = Series([False, False])
    result = Series(midx > midx)
    tm.assert_series_equal(result, expected)


def test_equals_ea_int_regular_int():
    # GH#46026
    mi1 = MultiIndex.from_arrays([Index([1, 2], dtype="Int64"), [3, 4]])
    mi2 = MultiIndex.from_arrays([[1, 2], [3, 4]])
    assert not mi1.equals(mi2)
    assert not mi2.equals(mi1)
