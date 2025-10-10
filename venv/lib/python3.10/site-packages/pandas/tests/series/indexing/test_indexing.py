""" test get/set & misc """
from datetime import timedelta
import re

import numpy as np
import pytest

from pandas.compat import WARNING_CHECK_DISABLED
from pandas.errors import IndexingError

from pandas import (
    NA,
    DataFrame,
    Index,
    IndexSlice,
    MultiIndex,
    NaT,
    Series,
    Timedelta,
    Timestamp,
    concat,
    date_range,
    isna,
    period_range,
    timedelta_range,
)
import pandas._testing as tm


def test_basic_indexing():
    s = Series(
        np.random.default_rng(2).standard_normal(5), index=["a", "b", "a", "a", "b"]
    )

    warn_msg = "Series.__[sg]etitem__ treating keys as positions is deprecated"
    msg = "index 5 is out of bounds for axis 0 with size 5"
    with pytest.raises(IndexError, match=msg):
        with tm.assert_produces_warning(FutureWarning, match=warn_msg):
            s[5]
    with pytest.raises(IndexError, match=msg):
        with tm.assert_produces_warning(FutureWarning, match=warn_msg):
            s[5] = 0

    with pytest.raises(KeyError, match=r"^'c'$"):
        s["c"]

    s = s.sort_index()

    with pytest.raises(IndexError, match=msg):
        with tm.assert_produces_warning(FutureWarning, match=warn_msg):
            s[5]
    msg = r"index 5 is out of bounds for axis (0|1) with size 5|^5$"
    with pytest.raises(IndexError, match=msg):
        with tm.assert_produces_warning(FutureWarning, match=warn_msg):
            s[5] = 0


def test_getitem_numeric_should_not_fallback_to_positional(any_numeric_dtype):
    # GH51053
    dtype = any_numeric_dtype
    idx = Index([1, 0, 1], dtype=dtype)
    ser = Series(range(3), index=idx)
    result = ser[1]
    expected = Series([0, 2], index=Index([1, 1], dtype=dtype))
    tm.assert_series_equal(result, expected, check_exact=True)


def test_setitem_numeric_should_not_fallback_to_positional(any_numeric_dtype):
    # GH51053
    dtype = any_numeric_dtype
    idx = Index([1, 0, 1], dtype=dtype)
    ser = Series(range(3), index=idx)
    ser[1] = 10
    expected = Series([10, 1, 10], index=idx)
    tm.assert_series_equal(ser, expected, check_exact=True)


def test_basic_getitem_with_labels(datetime_series):
    indices = datetime_series.index[[5, 10, 15]]

    result = datetime_series[indices]
    expected = datetime_series.reindex(indices)
    tm.assert_series_equal(result, expected)

    result = datetime_series[indices[0] : indices[2]]
    expected = datetime_series.loc[indices[0] : indices[2]]
    tm.assert_series_equal(result, expected)


def test_basic_getitem_dt64tz_values():
    # GH12089
    # with tz for values
    ser = Series(
        date_range("2011-01-01", periods=3, tz="US/Eastern"), index=["a", "b", "c"]
    )
    expected = Timestamp("2011-01-01", tz="US/Eastern")
    result = ser.loc["a"]
    assert result == expected
    result = ser.iloc[0]
    assert result == expected
    result = ser["a"]
    assert result == expected


def test_getitem_setitem_ellipsis(using_copy_on_write, warn_copy_on_write):
    s = Series(np.random.default_rng(2).standard_normal(10))

    result = s[...]
    tm.assert_series_equal(result, s)

    with tm.assert_cow_warning(warn_copy_on_write):
        s[...] = 5
    if not using_copy_on_write:
        assert (result == 5).all()


@pytest.mark.parametrize(
    "result_1, duplicate_item, expected_1",
    [
        [
            Series({1: 12, 2: [1, 2, 2, 3]}),
            Series({1: 313}),
            Series({1: 12}, dtype=object),
        ],
        [
            Series({1: [1, 2, 3], 2: [1, 2, 2, 3]}),
            Series({1: [1, 2, 3]}),
            Series({1: [1, 2, 3]}),
        ],
    ],
)
def test_getitem_with_duplicates_indices(result_1, duplicate_item, expected_1):
    # GH 17610
    result = result_1._append(duplicate_item)
    expected = expected_1._append(duplicate_item)
    tm.assert_series_equal(result[1], expected)
    assert result[2] == result_1[2]


def test_getitem_setitem_integers():
    # caused bug without test
    s = Series([1, 2, 3], ["a", "b", "c"])

    assert s.iloc[0] == s["a"]
    s.iloc[0] = 5
    tm.assert_almost_equal(s["a"], 5)


def test_series_box_timestamp():
    rng = date_range("20090415", "20090519", freq="B")
    ser = Series(rng)
    assert isinstance(ser[0], Timestamp)
    assert isinstance(ser.at[1], Timestamp)
    assert isinstance(ser.iat[2], Timestamp)
    assert isinstance(ser.loc[3], Timestamp)
    assert isinstance(ser.iloc[4], Timestamp)

    ser = Series(rng, index=rng)
    msg = "Series.__getitem__ treating keys as positions is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        assert isinstance(ser[0], Timestamp)
    assert isinstance(ser.at[rng[1]], Timestamp)
    assert isinstance(ser.iat[2], Timestamp)
    assert isinstance(ser.loc[rng[3]], Timestamp)
    assert isinstance(ser.iloc[4], Timestamp)


def test_series_box_timedelta():
    rng = timedelta_range("1 day 1 s", periods=5, freq="h")
    ser = Series(rng)
    assert isinstance(ser[0], Timedelta)
    assert isinstance(ser.at[1], Timedelta)
    assert isinstance(ser.iat[2], Timedelta)
    assert isinstance(ser.loc[3], Timedelta)
    assert isinstance(ser.iloc[4], Timedelta)


def test_getitem_ambiguous_keyerror(indexer_sl):
    ser = Series(range(10), index=list(range(0, 20, 2)))
    with pytest.raises(KeyError, match=r"^1$"):
        indexer_sl(ser)[1]


def test_getitem_dups_with_missing(indexer_sl):
    # breaks reindex, so need to use .loc internally
    # GH 4246
    ser = Series([1, 2, 3, 4], ["foo", "bar", "foo", "bah"])
    with pytest.raises(KeyError, match=re.escape("['bam'] not in index")):
        indexer_sl(ser)[["foo", "bar", "bah", "bam"]]


def test_setitem_ambiguous_keyerror(indexer_sl):
    s = Series(range(10), index=list(range(0, 20, 2)))

    # equivalent of an append
    s2 = s.copy()
    indexer_sl(s2)[1] = 5
    expected = concat([s, Series([5], index=[1])])
    tm.assert_series_equal(s2, expected)


def test_setitem(datetime_series):
    datetime_series[datetime_series.index[5]] = np.nan
    datetime_series.iloc[[1, 2, 17]] = np.nan
    datetime_series.iloc[6] = np.nan
    assert np.isnan(datetime_series.iloc[6])
    assert np.isnan(datetime_series.iloc[2])
    datetime_series[np.isnan(datetime_series)] = 5
    assert not np.isnan(datetime_series.iloc[2])


def test_setslice(datetime_series):
    sl = datetime_series[5:20]
    assert len(sl) == len(sl.index)
    assert sl.index.is_unique is True


def test_basic_getitem_setitem_corner(datetime_series):
    # invalid tuples, e.g. td.ts[:, None] vs. td.ts[:, 2]
    msg = "key of type tuple not found and not a MultiIndex"
    with pytest.raises(KeyError, match=msg):
        datetime_series[:, 2]
    with pytest.raises(KeyError, match=msg):
        datetime_series[:, 2] = 2

    # weird lists. [slice(0, 5)] raises but not two slices
    msg = "Indexing with a single-item list"
    with pytest.raises(ValueError, match=msg):
        # GH#31299
        datetime_series[[slice(None, 5)]]

    # but we're OK with a single-element tuple
    result = datetime_series[(slice(None, 5),)]
    expected = datetime_series[:5]
    tm.assert_series_equal(result, expected)

    # OK
    msg = r"unhashable type(: 'slice')?"
    with pytest.raises(TypeError, match=msg):
        datetime_series[[5, [None, None]]]
    with pytest.raises(TypeError, match=msg):
        datetime_series[[5, [None, None]]] = 2


def test_slice(string_series, object_series, using_copy_on_write, warn_copy_on_write):
    original = string_series.copy()
    numSlice = string_series[10:20]
    numSliceEnd = string_series[-10:]
    objSlice = object_series[10:20]

    assert string_series.index[9] not in numSlice.index
    assert object_series.index[9] not in objSlice.index

    assert len(numSlice) == len(numSlice.index)
    assert string_series[numSlice.index[0]] == numSlice[numSlice.index[0]]

    assert numSlice.index[1] == string_series.index[11]
    tm.assert_numpy_array_equal(np.array(numSliceEnd), np.array(string_series)[-10:])

    # Test return view.
    sl = string_series[10:20]
    with tm.assert_cow_warning(warn_copy_on_write):
        sl[:] = 0

    if using_copy_on_write:
        # Doesn't modify parent (CoW)
        tm.assert_series_equal(string_series, original)
    else:
        assert (string_series[10:20] == 0).all()


def test_timedelta_assignment():
    # GH 8209
    s = Series([], dtype=object)
    s.loc["B"] = timedelta(1)
    expected = Series(Timedelta("1 days"), dtype="timedelta64[ns]", index=["B"])
    tm.assert_series_equal(s, expected)

    s = s.reindex(s.index.insert(0, "A"))
    expected = Series(
        [np.nan, Timedelta("1 days")], dtype="timedelta64[ns]", index=["A", "B"]
    )
    tm.assert_series_equal(s, expected)

    s.loc["A"] = timedelta(1)
    expected = Series(Timedelta("1 days"), dtype="timedelta64[ns]", index=["A", "B"])
    tm.assert_series_equal(s, expected)


def test_underlying_data_conversion(using_copy_on_write):
    # GH 4080
    df = DataFrame({c: [1, 2, 3] for c in ["a", "b", "c"]})
    return_value = df.set_index(["a", "b", "c"], inplace=True)
    assert return_value is None
    s = Series([1], index=[(2, 2, 2)])
    df["val"] = 0
    df_original = df.copy()
    df

    if using_copy_on_write:
        with tm.raises_chained_assignment_error():
            df["val"].update(s)
        expected = df_original
    else:
        with tm.assert_produces_warning(
            FutureWarning if not WARNING_CHECK_DISABLED else None,
            match="inplace method",
        ):
            df["val"].update(s)
        expected = DataFrame(
            {"a": [1, 2, 3], "b": [1, 2, 3], "c": [1, 2, 3], "val": [0, 1, 0]}
        )
        return_value = expected.set_index(["a", "b", "c"], inplace=True)
        assert return_value is None
    tm.assert_frame_equal(df, expected)


def test_preserve_refs(datetime_series):
    seq = datetime_series.iloc[[5, 10, 15]]
    seq.iloc[1] = np.nan
    assert not np.isnan(datetime_series.iloc[10])


def test_multilevel_preserve_name(lexsorted_two_level_string_multiindex, indexer_sl):
    index = lexsorted_two_level_string_multiindex
    ser = Series(
        np.random.default_rng(2).standard_normal(len(index)), index=index, name="sth"
    )

    result = indexer_sl(ser)["foo"]
    assert result.name == ser.name


# miscellaneous methods


@pytest.mark.parametrize(
    "index",
    [
        date_range("2014-01-01", periods=20, freq="MS"),
        period_range("2014-01", periods=20, freq="M"),
        timedelta_range("0", periods=20, freq="h"),
    ],
)
def test_slice_with_negative_step(index):
    keystr1 = str(index[9])
    keystr2 = str(index[13])

    ser = Series(np.arange(20), index)
    SLC = IndexSlice

    for key in [keystr1, index[9]]:
        tm.assert_indexing_slices_equivalent(ser, SLC[key::-1], SLC[9::-1])
        tm.assert_indexing_slices_equivalent(ser, SLC[:key:-1], SLC[:8:-1])

        for key2 in [keystr2, index[13]]:
            tm.assert_indexing_slices_equivalent(ser, SLC[key2:key:-1], SLC[13:8:-1])
            tm.assert_indexing_slices_equivalent(ser, SLC[key:key2:-1], SLC[0:0:-1])


def test_tuple_index():
    # GH 35534 - Selecting values when a Series has an Index of tuples
    s = Series([1, 2], index=[("a",), ("b",)])
    assert s[("a",)] == 1
    assert s[("b",)] == 2
    s[("b",)] = 3
    assert s[("b",)] == 3


def test_frozenset_index():
    # GH35747 - Selecting values when a Series has an Index of frozenset
    idx0, idx1 = frozenset("a"), frozenset("b")
    s = Series([1, 2], index=[idx0, idx1])
    assert s[idx0] == 1
    assert s[idx1] == 2
    s[idx1] = 3
    assert s[idx1] == 3


def test_loc_setitem_all_false_indexer():
    # GH#45778
    ser = Series([1, 2], index=["a", "b"])
    expected = ser.copy()
    rhs = Series([6, 7], index=["a", "b"])
    ser.loc[ser > 100] = rhs
    tm.assert_series_equal(ser, expected)


def test_loc_boolean_indexer_non_matching_index():
    # GH#46551
    ser = Series([1])
    result = ser.loc[Series([NA, False], dtype="boolean")]
    expected = Series([], dtype="int64")
    tm.assert_series_equal(result, expected)


def test_loc_boolean_indexer_miss_matching_index():
    # GH#46551
    ser = Series([1])
    indexer = Series([NA, False], dtype="boolean", index=[1, 2])
    with pytest.raises(IndexingError, match="Unalignable"):
        ser.loc[indexer]


def test_loc_setitem_nested_data_enlargement():
    # GH#48614
    df = DataFrame({"a": [1]})
    ser = Series({"label": df})
    ser.loc["new_label"] = df
    expected = Series({"label": df, "new_label": df})
    tm.assert_series_equal(ser, expected)


def test_loc_ea_numeric_index_oob_slice_end():
    # GH#50161
    ser = Series(1, index=Index([0, 1, 2], dtype="Int64"))
    result = ser.loc[2:3]
    expected = Series(1, index=Index([2], dtype="Int64"))
    tm.assert_series_equal(result, expected)


def test_getitem_bool_int_key():
    # GH#48653
    ser = Series({True: 1, False: 0})
    with pytest.raises(KeyError, match="0"):
        ser.loc[0]


@pytest.mark.parametrize("val", [{}, {"b": "x"}])
@pytest.mark.parametrize("indexer", [[], [False, False], slice(0, -1), np.array([])])
def test_setitem_empty_indexer(indexer, val):
    # GH#45981
    df = DataFrame({"a": [1, 2], **val})
    expected = df.copy()
    df.loc[indexer] = 1.5
    tm.assert_frame_equal(df, expected)


class TestDeprecatedIndexers:
    @pytest.mark.parametrize("key", [{1}, {1: 1}])
    def test_getitem_dict_and_set_deprecated(self, key):
        # GH#42825 enforced in 2.0
        ser = Series([1, 2])
        with pytest.raises(TypeError, match="as an indexer is not supported"):
            ser.loc[key]

    @pytest.mark.parametrize("key", [{1}, {1: 1}, ({1}, 2), ({1: 1}, 2)])
    def test_getitem_dict_and_set_deprecated_multiindex(self, key):
        # GH#42825 enforced in 2.0
        ser = Series([1, 2], index=MultiIndex.from_tuples([(1, 2), (3, 4)]))
        with pytest.raises(TypeError, match="as an indexer is not supported"):
            ser.loc[key]

    @pytest.mark.parametrize("key", [{1}, {1: 1}])
    def test_setitem_dict_and_set_disallowed(self, key):
        # GH#42825 enforced in 2.0
        ser = Series([1, 2])
        with pytest.raises(TypeError, match="as an indexer is not supported"):
            ser.loc[key] = 1

    @pytest.mark.parametrize("key", [{1}, {1: 1}, ({1}, 2), ({1: 1}, 2)])
    def test_setitem_dict_and_set_disallowed_multiindex(self, key):
        # GH#42825 enforced in 2.0
        ser = Series([1, 2], index=MultiIndex.from_tuples([(1, 2), (3, 4)]))
        with pytest.raises(TypeError, match="as an indexer is not supported"):
            ser.loc[key] = 1


class TestSetitemValidation:
    # This is adapted from pandas/tests/arrays/masked/test_indexing.py
    # but checks for warnings instead of errors.
    def _check_setitem_invalid(self, ser, invalid, indexer, warn):
        msg = "Setting an item of incompatible dtype is deprecated"
        msg = re.escape(msg)

        orig_ser = ser.copy()

        with tm.assert_produces_warning(warn, match=msg):
            ser[indexer] = invalid
            ser = orig_ser.copy()

        with tm.assert_produces_warning(warn, match=msg):
            ser.iloc[indexer] = invalid
            ser = orig_ser.copy()

        with tm.assert_produces_warning(warn, match=msg):
            ser.loc[indexer] = invalid
            ser = orig_ser.copy()

        with tm.assert_produces_warning(warn, match=msg):
            ser[:] = invalid

    _invalid_scalars = [
        1 + 2j,
        "True",
        "1",
        "1.0",
        NaT,
        np.datetime64("NaT"),
        np.timedelta64("NaT"),
    ]
    _indexers = [0, [0], slice(0, 1), [True, False, False], slice(None, None, None)]

    @pytest.mark.parametrize(
        "invalid", _invalid_scalars + [1, 1.0, np.int64(1), np.float64(1)]
    )
    @pytest.mark.parametrize("indexer", _indexers)
    def test_setitem_validation_scalar_bool(self, invalid, indexer):
        ser = Series([True, False, False], dtype="bool")
        self._check_setitem_invalid(ser, invalid, indexer, FutureWarning)

    @pytest.mark.parametrize("invalid", _invalid_scalars + [True, 1.5, np.float64(1.5)])
    @pytest.mark.parametrize("indexer", _indexers)
    def test_setitem_validation_scalar_int(self, invalid, any_int_numpy_dtype, indexer):
        ser = Series([1, 2, 3], dtype=any_int_numpy_dtype)
        if isna(invalid) and invalid is not NaT and not np.isnat(invalid):
            warn = None
        else:
            warn = FutureWarning
        self._check_setitem_invalid(ser, invalid, indexer, warn)

    @pytest.mark.parametrize("invalid", _invalid_scalars + [True])
    @pytest.mark.parametrize("indexer", _indexers)
    def test_setitem_validation_scalar_float(self, invalid, float_numpy_dtype, indexer):
        ser = Series([1, 2, None], dtype=float_numpy_dtype)
        self._check_setitem_invalid(ser, invalid, indexer, FutureWarning)
