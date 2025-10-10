import re

import numpy as np
import pytest

from pandas._libs import index as libindex

from pandas.core.dtypes.cast import construct_1d_object_array_from_listlike

import pandas as pd
from pandas import (
    Index,
    IntervalIndex,
    MultiIndex,
    RangeIndex,
)
import pandas._testing as tm


def test_labels_dtypes():
    # GH 8456
    i = MultiIndex.from_tuples([("A", 1), ("A", 2)])
    assert i.codes[0].dtype == "int8"
    assert i.codes[1].dtype == "int8"

    i = MultiIndex.from_product([["a"], range(40)])
    assert i.codes[1].dtype == "int8"
    i = MultiIndex.from_product([["a"], range(400)])
    assert i.codes[1].dtype == "int16"
    i = MultiIndex.from_product([["a"], range(40000)])
    assert i.codes[1].dtype == "int32"

    i = MultiIndex.from_product([["a"], range(1000)])
    assert (i.codes[0] >= 0).all()
    assert (i.codes[1] >= 0).all()


def test_values_boxed():
    tuples = [
        (1, pd.Timestamp("2000-01-01")),
        (2, pd.NaT),
        (3, pd.Timestamp("2000-01-03")),
        (1, pd.Timestamp("2000-01-04")),
        (2, pd.Timestamp("2000-01-02")),
        (3, pd.Timestamp("2000-01-03")),
    ]
    result = MultiIndex.from_tuples(tuples)
    expected = construct_1d_object_array_from_listlike(tuples)
    tm.assert_numpy_array_equal(result.values, expected)
    # Check that code branches for boxed values produce identical results
    tm.assert_numpy_array_equal(result.values[:4], result[:4].values)


def test_values_multiindex_datetimeindex():
    # Test to ensure we hit the boxing / nobox part of MI.values
    ints = np.arange(10**18, 10**18 + 5)
    naive = pd.DatetimeIndex(ints)

    aware = pd.DatetimeIndex(ints, tz="US/Central")

    idx = MultiIndex.from_arrays([naive, aware])
    result = idx.values

    outer = pd.DatetimeIndex([x[0] for x in result])
    tm.assert_index_equal(outer, naive)

    inner = pd.DatetimeIndex([x[1] for x in result])
    tm.assert_index_equal(inner, aware)

    # n_lev > n_lab
    result = idx[:2].values

    outer = pd.DatetimeIndex([x[0] for x in result])
    tm.assert_index_equal(outer, naive[:2])

    inner = pd.DatetimeIndex([x[1] for x in result])
    tm.assert_index_equal(inner, aware[:2])


def test_values_multiindex_periodindex():
    # Test to ensure we hit the boxing / nobox part of MI.values
    ints = np.arange(2007, 2012)
    pidx = pd.PeriodIndex(ints, freq="D")

    idx = MultiIndex.from_arrays([ints, pidx])
    result = idx.values

    outer = Index([x[0] for x in result])
    tm.assert_index_equal(outer, Index(ints, dtype=np.int64))

    inner = pd.PeriodIndex([x[1] for x in result])
    tm.assert_index_equal(inner, pidx)

    # n_lev > n_lab
    result = idx[:2].values

    outer = Index([x[0] for x in result])
    tm.assert_index_equal(outer, Index(ints[:2], dtype=np.int64))

    inner = pd.PeriodIndex([x[1] for x in result])
    tm.assert_index_equal(inner, pidx[:2])


def test_consistency():
    # need to construct an overflow
    major_axis = list(range(70000))
    minor_axis = list(range(10))

    major_codes = np.arange(70000)
    minor_codes = np.repeat(range(10), 7000)

    # the fact that is works means it's consistent
    index = MultiIndex(
        levels=[major_axis, minor_axis], codes=[major_codes, minor_codes]
    )

    # inconsistent
    major_codes = np.array([0, 0, 1, 1, 1, 2, 2, 3, 3])
    minor_codes = np.array([0, 1, 0, 1, 1, 0, 1, 0, 1])
    index = MultiIndex(
        levels=[major_axis, minor_axis], codes=[major_codes, minor_codes]
    )

    assert index.is_unique is False


@pytest.mark.slow
def test_hash_collisions(monkeypatch):
    # non-smoke test that we don't get hash collisions
    size_cutoff = 50
    with monkeypatch.context() as m:
        m.setattr(libindex, "_SIZE_CUTOFF", size_cutoff)
        index = MultiIndex.from_product(
            [np.arange(8), np.arange(8)], names=["one", "two"]
        )
        result = index.get_indexer(index.values)
        tm.assert_numpy_array_equal(result, np.arange(len(index), dtype="intp"))

        for i in [0, 1, len(index) - 2, len(index) - 1]:
            result = index.get_loc(index[i])
            assert result == i


def test_dims():
    pass


def test_take_invalid_kwargs():
    vals = [["A", "B"], [pd.Timestamp("2011-01-01"), pd.Timestamp("2011-01-02")]]
    idx = MultiIndex.from_product(vals, names=["str", "dt"])
    indices = [1, 2]

    msg = r"take\(\) got an unexpected keyword argument 'foo'"
    with pytest.raises(TypeError, match=msg):
        idx.take(indices, foo=2)

    msg = "the 'out' parameter is not supported"
    with pytest.raises(ValueError, match=msg):
        idx.take(indices, out=indices)

    msg = "the 'mode' parameter is not supported"
    with pytest.raises(ValueError, match=msg):
        idx.take(indices, mode="clip")


def test_isna_behavior(idx):
    # should not segfault GH5123
    # NOTE: if MI representation changes, may make sense to allow
    # isna(MI)
    msg = "isna is not defined for MultiIndex"
    with pytest.raises(NotImplementedError, match=msg):
        pd.isna(idx)


def test_large_multiindex_error(monkeypatch):
    # GH12527
    size_cutoff = 50
    with monkeypatch.context() as m:
        m.setattr(libindex, "_SIZE_CUTOFF", size_cutoff)
        df_below_cutoff = pd.DataFrame(
            1,
            index=MultiIndex.from_product([[1, 2], range(size_cutoff - 1)]),
            columns=["dest"],
        )
        with pytest.raises(KeyError, match=r"^\(-1, 0\)$"):
            df_below_cutoff.loc[(-1, 0), "dest"]
        with pytest.raises(KeyError, match=r"^\(3, 0\)$"):
            df_below_cutoff.loc[(3, 0), "dest"]
        df_above_cutoff = pd.DataFrame(
            1,
            index=MultiIndex.from_product([[1, 2], range(size_cutoff + 1)]),
            columns=["dest"],
        )
        with pytest.raises(KeyError, match=r"^\(-1, 0\)$"):
            df_above_cutoff.loc[(-1, 0), "dest"]
        with pytest.raises(KeyError, match=r"^\(3, 0\)$"):
            df_above_cutoff.loc[(3, 0), "dest"]


def test_mi_hashtable_populated_attribute_error(monkeypatch):
    # GH 18165
    monkeypatch.setattr(libindex, "_SIZE_CUTOFF", 50)
    r = range(50)
    df = pd.DataFrame({"a": r, "b": r}, index=MultiIndex.from_arrays([r, r]))

    msg = "'Series' object has no attribute 'foo'"
    with pytest.raises(AttributeError, match=msg):
        df["a"].foo()


def test_can_hold_identifiers(idx):
    key = idx[0]
    assert idx._can_hold_identifiers_and_holds_name(key) is True


def test_metadata_immutable(idx):
    levels, codes = idx.levels, idx.codes
    # shouldn't be able to set at either the top level or base level
    mutable_regex = re.compile("does not support mutable operations")
    with pytest.raises(TypeError, match=mutable_regex):
        levels[0] = levels[0]
    with pytest.raises(TypeError, match=mutable_regex):
        levels[0][0] = levels[0][0]
    # ditto for labels
    with pytest.raises(TypeError, match=mutable_regex):
        codes[0] = codes[0]
    with pytest.raises(ValueError, match="assignment destination is read-only"):
        codes[0][0] = codes[0][0]
    # and for names
    names = idx.names
    with pytest.raises(TypeError, match=mutable_regex):
        names[0] = names[0]


def test_level_setting_resets_attributes():
    ind = MultiIndex.from_arrays([["A", "A", "B", "B", "B"], [1, 2, 1, 2, 3]])
    assert ind.is_monotonic_increasing
    ind = ind.set_levels([["A", "B"], [1, 3, 2]])
    # if this fails, probably didn't reset the cache correctly.
    assert not ind.is_monotonic_increasing


def test_rangeindex_fallback_coercion_bug():
    # GH 12893
    df1 = pd.DataFrame(np.arange(100).reshape((10, 10)))
    df2 = pd.DataFrame(np.arange(100).reshape((10, 10)))
    df = pd.concat(
        {"df1": df1.stack(future_stack=True), "df2": df2.stack(future_stack=True)},
        axis=1,
    )
    df.index.names = ["fizz", "buzz"]

    expected = pd.DataFrame(
        {"df2": np.arange(100), "df1": np.arange(100)},
        index=MultiIndex.from_product([range(10), range(10)], names=["fizz", "buzz"]),
    )
    tm.assert_frame_equal(df, expected, check_like=True)

    result = df.index.get_level_values("fizz")
    expected = Index(np.arange(10, dtype=np.int64), name="fizz").repeat(10)
    tm.assert_index_equal(result, expected)

    result = df.index.get_level_values("buzz")
    expected = Index(np.tile(np.arange(10, dtype=np.int64), 10), name="buzz")
    tm.assert_index_equal(result, expected)


def test_memory_usage(idx):
    result = idx.memory_usage()
    if len(idx):
        idx.get_loc(idx[0])
        result2 = idx.memory_usage()
        result3 = idx.memory_usage(deep=True)

        # RangeIndex, IntervalIndex
        # don't have engines
        if not isinstance(idx, (RangeIndex, IntervalIndex)):
            assert result2 > result

        if idx.inferred_type == "object":
            assert result3 > result2

    else:
        # we report 0 for no-length
        assert result == 0


def test_nlevels(idx):
    assert idx.nlevels == 2
