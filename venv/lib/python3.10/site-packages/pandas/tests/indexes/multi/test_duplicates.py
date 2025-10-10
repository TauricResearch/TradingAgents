from itertools import product

import numpy as np
import pytest

from pandas._libs import (
    hashtable,
    index as libindex,
)

from pandas import (
    NA,
    DatetimeIndex,
    Index,
    MultiIndex,
    Series,
)
import pandas._testing as tm


@pytest.fixture
def idx_dup():
    # compare tests/indexes/multi/conftest.py
    major_axis = Index(["foo", "bar", "baz", "qux"])
    minor_axis = Index(["one", "two"])

    major_codes = np.array([0, 0, 1, 0, 1, 1])
    minor_codes = np.array([0, 1, 0, 1, 0, 1])
    index_names = ["first", "second"]
    mi = MultiIndex(
        levels=[major_axis, minor_axis],
        codes=[major_codes, minor_codes],
        names=index_names,
        verify_integrity=False,
    )
    return mi


@pytest.mark.parametrize("names", [None, ["first", "second"]])
def test_unique(names):
    mi = MultiIndex.from_arrays([[1, 2, 1, 2], [1, 1, 1, 2]], names=names)

    res = mi.unique()
    exp = MultiIndex.from_arrays([[1, 2, 2], [1, 1, 2]], names=mi.names)
    tm.assert_index_equal(res, exp)

    mi = MultiIndex.from_arrays([list("aaaa"), list("abab")], names=names)
    res = mi.unique()
    exp = MultiIndex.from_arrays([list("aa"), list("ab")], names=mi.names)
    tm.assert_index_equal(res, exp)

    mi = MultiIndex.from_arrays([list("aaaa"), list("aaaa")], names=names)
    res = mi.unique()
    exp = MultiIndex.from_arrays([["a"], ["a"]], names=mi.names)
    tm.assert_index_equal(res, exp)

    # GH #20568 - empty MI
    mi = MultiIndex.from_arrays([[], []], names=names)
    res = mi.unique()
    tm.assert_index_equal(mi, res)


def test_unique_datetimelike():
    idx1 = DatetimeIndex(
        ["2015-01-01", "2015-01-01", "2015-01-01", "2015-01-01", "NaT", "NaT"]
    )
    idx2 = DatetimeIndex(
        ["2015-01-01", "2015-01-01", "2015-01-02", "2015-01-02", "NaT", "2015-01-01"],
        tz="Asia/Tokyo",
    )
    result = MultiIndex.from_arrays([idx1, idx2]).unique()

    eidx1 = DatetimeIndex(["2015-01-01", "2015-01-01", "NaT", "NaT"])
    eidx2 = DatetimeIndex(
        ["2015-01-01", "2015-01-02", "NaT", "2015-01-01"], tz="Asia/Tokyo"
    )
    exp = MultiIndex.from_arrays([eidx1, eidx2])
    tm.assert_index_equal(result, exp)


@pytest.mark.parametrize("level", [0, "first", 1, "second"])
def test_unique_level(idx, level):
    # GH #17896 - with level= argument
    result = idx.unique(level=level)
    expected = idx.get_level_values(level).unique()
    tm.assert_index_equal(result, expected)

    # With already unique level
    mi = MultiIndex.from_arrays([[1, 3, 2, 4], [1, 3, 2, 5]], names=["first", "second"])
    result = mi.unique(level=level)
    expected = mi.get_level_values(level)
    tm.assert_index_equal(result, expected)

    # With empty MI
    mi = MultiIndex.from_arrays([[], []], names=["first", "second"])
    result = mi.unique(level=level)
    expected = mi.get_level_values(level)
    tm.assert_index_equal(result, expected)


def test_duplicate_multiindex_codes():
    # GH 17464
    # Make sure that a MultiIndex with duplicate levels throws a ValueError
    msg = r"Level values must be unique: \[[A', ]+\] on level 0"
    with pytest.raises(ValueError, match=msg):
        mi = MultiIndex([["A"] * 10, range(10)], [[0] * 10, range(10)])

    # And that using set_levels with duplicate levels fails
    mi = MultiIndex.from_arrays([["A", "A", "B", "B", "B"], [1, 2, 1, 2, 3]])
    msg = r"Level values must be unique: \[[AB', ]+\] on level 0"
    with pytest.raises(ValueError, match=msg):
        mi.set_levels([["A", "B", "A", "A", "B"], [2, 1, 3, -2, 5]])


@pytest.mark.parametrize("names", [["a", "b", "a"], [1, 1, 2], [1, "a", 1]])
def test_duplicate_level_names(names):
    # GH18872, GH19029
    mi = MultiIndex.from_product([[0, 1]] * 3, names=names)
    assert mi.names == names

    # With .rename()
    mi = MultiIndex.from_product([[0, 1]] * 3)
    mi = mi.rename(names)
    assert mi.names == names

    # With .rename(., level=)
    mi.rename(names[1], level=1, inplace=True)
    mi = mi.rename([names[0], names[2]], level=[0, 2])
    assert mi.names == names


def test_duplicate_meta_data():
    # GH 10115
    mi = MultiIndex(
        levels=[[0, 1], [0, 1, 2]], codes=[[0, 0, 0, 0, 1, 1, 1], [0, 1, 2, 0, 0, 1, 2]]
    )

    for idx in [
        mi,
        mi.set_names([None, None]),
        mi.set_names([None, "Num"]),
        mi.set_names(["Upper", "Num"]),
    ]:
        assert idx.has_duplicates
        assert idx.drop_duplicates().names == idx.names


def test_has_duplicates(idx, idx_dup):
    # see fixtures
    assert idx.is_unique is True
    assert idx.has_duplicates is False
    assert idx_dup.is_unique is False
    assert idx_dup.has_duplicates is True

    mi = MultiIndex(
        levels=[[0, 1], [0, 1, 2]], codes=[[0, 0, 0, 0, 1, 1, 1], [0, 1, 2, 0, 0, 1, 2]]
    )
    assert mi.is_unique is False
    assert mi.has_duplicates is True

    # single instance of NaN
    mi_nan = MultiIndex(
        levels=[["a", "b"], [0, 1]], codes=[[-1, 0, 0, 1, 1], [-1, 0, 1, 0, 1]]
    )
    assert mi_nan.is_unique is True
    assert mi_nan.has_duplicates is False

    # multiple instances of NaN
    mi_nan_dup = MultiIndex(
        levels=[["a", "b"], [0, 1]], codes=[[-1, -1, 0, 0, 1, 1], [-1, -1, 0, 1, 0, 1]]
    )
    assert mi_nan_dup.is_unique is False
    assert mi_nan_dup.has_duplicates is True


def test_has_duplicates_from_tuples():
    # GH 9075
    t = [
        ("x", "out", "z", 5, "y", "in", "z", 169),
        ("x", "out", "z", 7, "y", "in", "z", 119),
        ("x", "out", "z", 9, "y", "in", "z", 135),
        ("x", "out", "z", 13, "y", "in", "z", 145),
        ("x", "out", "z", 14, "y", "in", "z", 158),
        ("x", "out", "z", 16, "y", "in", "z", 122),
        ("x", "out", "z", 17, "y", "in", "z", 160),
        ("x", "out", "z", 18, "y", "in", "z", 180),
        ("x", "out", "z", 20, "y", "in", "z", 143),
        ("x", "out", "z", 21, "y", "in", "z", 128),
        ("x", "out", "z", 22, "y", "in", "z", 129),
        ("x", "out", "z", 25, "y", "in", "z", 111),
        ("x", "out", "z", 28, "y", "in", "z", 114),
        ("x", "out", "z", 29, "y", "in", "z", 121),
        ("x", "out", "z", 31, "y", "in", "z", 126),
        ("x", "out", "z", 32, "y", "in", "z", 155),
        ("x", "out", "z", 33, "y", "in", "z", 123),
        ("x", "out", "z", 12, "y", "in", "z", 144),
    ]

    mi = MultiIndex.from_tuples(t)
    assert not mi.has_duplicates


@pytest.mark.parametrize("nlevels", [4, 8])
@pytest.mark.parametrize("with_nulls", [True, False])
def test_has_duplicates_overflow(nlevels, with_nulls):
    # handle int64 overflow if possible
    # no overflow with 4
    # overflow possible with 8
    codes = np.tile(np.arange(500), 2)
    level = np.arange(500)

    if with_nulls:  # inject some null values
        codes[500] = -1  # common nan value
        codes = [codes.copy() for i in range(nlevels)]
        for i in range(nlevels):
            codes[i][500 + i - nlevels // 2] = -1

        codes += [np.array([-1, 1]).repeat(500)]
    else:
        codes = [codes] * nlevels + [np.arange(2).repeat(500)]

    levels = [level] * nlevels + [[0, 1]]

    # no dups
    mi = MultiIndex(levels=levels, codes=codes)
    assert not mi.has_duplicates

    # with a dup
    if with_nulls:

        def f(a):
            return np.insert(a, 1000, a[0])

        codes = list(map(f, codes))
        mi = MultiIndex(levels=levels, codes=codes)
    else:
        values = mi.values.tolist()
        mi = MultiIndex.from_tuples(values + [values[0]])

    assert mi.has_duplicates


@pytest.mark.parametrize(
    "keep, expected",
    [
        ("first", np.array([False, False, False, True, True, False])),
        ("last", np.array([False, True, True, False, False, False])),
        (False, np.array([False, True, True, True, True, False])),
    ],
)
def test_duplicated(idx_dup, keep, expected):
    result = idx_dup.duplicated(keep=keep)
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.arm_slow
def test_duplicated_hashtable_impl(keep, monkeypatch):
    # GH 9125
    n, k = 6, 10
    levels = [np.arange(n), [str(i) for i in range(n)], 1000 + np.arange(n)]
    codes = [np.random.default_rng(2).choice(n, k * n) for _ in levels]
    with monkeypatch.context() as m:
        m.setattr(libindex, "_SIZE_CUTOFF", 50)
        mi = MultiIndex(levels=levels, codes=codes)

        result = mi.duplicated(keep=keep)
        expected = hashtable.duplicated(mi.values, keep=keep)
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("val", [101, 102])
def test_duplicated_with_nan(val):
    # GH5873
    mi = MultiIndex.from_arrays([[101, val], [3.5, np.nan]])
    assert not mi.has_duplicates

    tm.assert_numpy_array_equal(mi.duplicated(), np.zeros(2, dtype="bool"))


@pytest.mark.parametrize("n", range(1, 6))
@pytest.mark.parametrize("m", range(1, 5))
def test_duplicated_with_nan_multi_shape(n, m):
    # GH5873
    # all possible unique combinations, including nan
    codes = product(range(-1, n), range(-1, m))
    mi = MultiIndex(
        levels=[list("abcde")[:n], list("WXYZ")[:m]],
        codes=np.random.default_rng(2).permutation(list(codes)).T,
    )
    assert len(mi) == (n + 1) * (m + 1)
    assert not mi.has_duplicates

    tm.assert_numpy_array_equal(mi.duplicated(), np.zeros(len(mi), dtype="bool"))


def test_duplicated_drop_duplicates():
    # GH#4060
    idx = MultiIndex.from_arrays(([1, 2, 3, 1, 2, 3], [1, 1, 1, 1, 2, 2]))

    expected = np.array([False, False, False, True, False, False], dtype=bool)
    duplicated = idx.duplicated()
    tm.assert_numpy_array_equal(duplicated, expected)
    assert duplicated.dtype == bool
    expected = MultiIndex.from_arrays(([1, 2, 3, 2, 3], [1, 1, 1, 2, 2]))
    tm.assert_index_equal(idx.drop_duplicates(), expected)

    expected = np.array([True, False, False, False, False, False])
    duplicated = idx.duplicated(keep="last")
    tm.assert_numpy_array_equal(duplicated, expected)
    assert duplicated.dtype == bool
    expected = MultiIndex.from_arrays(([2, 3, 1, 2, 3], [1, 1, 1, 2, 2]))
    tm.assert_index_equal(idx.drop_duplicates(keep="last"), expected)

    expected = np.array([True, False, False, True, False, False])
    duplicated = idx.duplicated(keep=False)
    tm.assert_numpy_array_equal(duplicated, expected)
    assert duplicated.dtype == bool
    expected = MultiIndex.from_arrays(([2, 3, 2, 3], [1, 1, 2, 2]))
    tm.assert_index_equal(idx.drop_duplicates(keep=False), expected)


@pytest.mark.parametrize(
    "dtype",
    [
        np.complex64,
        np.complex128,
    ],
)
def test_duplicated_series_complex_numbers(dtype):
    # GH 17927
    expected = Series(
        [False, False, False, True, False, False, False, True, False, True],
        dtype=bool,
    )
    result = Series(
        [
            np.nan + np.nan * 1j,
            0,
            1j,
            1j,
            1,
            1 + 1j,
            1 + 2j,
            1 + 1j,
            np.nan,
            np.nan + np.nan * 1j,
        ],
        dtype=dtype,
    ).duplicated()
    tm.assert_series_equal(result, expected)


def test_midx_unique_ea_dtype():
    # GH#48335
    vals_a = Series([1, 2, NA, NA], dtype="Int64")
    vals_b = np.array([1, 2, 3, 3])
    midx = MultiIndex.from_arrays([vals_a, vals_b], names=["a", "b"])
    result = midx.unique()

    exp_vals_a = Series([1, 2, NA], dtype="Int64")
    exp_vals_b = np.array([1, 2, 3])
    expected = MultiIndex.from_arrays([exp_vals_a, exp_vals_b], names=["a", "b"])
    tm.assert_index_equal(result, expected)
