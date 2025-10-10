"""
Series.__getitem__ test classes are organized by the type of key passed.
"""
from datetime import (
    date,
    datetime,
    time,
)

import numpy as np
import pytest

from pandas._libs.tslibs import (
    conversion,
    timezones,
)

from pandas.core.dtypes.common import is_scalar

import pandas as pd
from pandas import (
    Categorical,
    DataFrame,
    DatetimeIndex,
    Index,
    Series,
    Timestamp,
    date_range,
    period_range,
    timedelta_range,
)
import pandas._testing as tm
from pandas.core.indexing import IndexingError

from pandas.tseries.offsets import BDay


class TestSeriesGetitemScalars:
    def test_getitem_object_index_float_string(self):
        # GH#17286
        ser = Series([1] * 4, index=Index(["a", "b", "c", 1.0]))
        assert ser["a"] == 1
        assert ser[1.0] == 1

    def test_getitem_float_keys_tuple_values(self):
        # see GH#13509

        # unique Index
        ser = Series([(1, 1), (2, 2), (3, 3)], index=[0.0, 0.1, 0.2], name="foo")
        result = ser[0.0]
        assert result == (1, 1)

        # non-unique Index
        expected = Series([(1, 1), (2, 2)], index=[0.0, 0.0], name="foo")
        ser = Series([(1, 1), (2, 2), (3, 3)], index=[0.0, 0.0, 0.2], name="foo")

        result = ser[0.0]
        tm.assert_series_equal(result, expected)

    def test_getitem_unrecognized_scalar(self):
        # GH#32684 a scalar key that is not recognized by lib.is_scalar

        # a series that might be produced via `frame.dtypes`
        ser = Series([1, 2], index=[np.dtype("O"), np.dtype("i8")])

        key = ser.index[1]

        result = ser[key]
        assert result == 2

    def test_getitem_negative_out_of_bounds(self):
        ser = Series(["a"] * 10, index=["a"] * 10)

        msg = "index -11 is out of bounds for axis 0 with size 10|index out of bounds"
        warn_msg = "Series.__getitem__ treating keys as positions is deprecated"
        with pytest.raises(IndexError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=warn_msg):
                ser[-11]

    def test_getitem_out_of_bounds_indexerror(self, datetime_series):
        # don't segfault, GH#495
        msg = r"index \d+ is out of bounds for axis 0 with size \d+"
        warn_msg = "Series.__getitem__ treating keys as positions is deprecated"
        with pytest.raises(IndexError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=warn_msg):
                datetime_series[len(datetime_series)]

    def test_getitem_out_of_bounds_empty_rangeindex_keyerror(self):
        # GH#917
        # With a RangeIndex, an int key gives a KeyError
        ser = Series([], dtype=object)
        with pytest.raises(KeyError, match="-1"):
            ser[-1]

    def test_getitem_keyerror_with_integer_index(self, any_int_numpy_dtype):
        dtype = any_int_numpy_dtype
        ser = Series(
            np.random.default_rng(2).standard_normal(6),
            index=Index([0, 0, 1, 1, 2, 2], dtype=dtype),
        )

        with pytest.raises(KeyError, match=r"^5$"):
            ser[5]

        with pytest.raises(KeyError, match=r"^'c'$"):
            ser["c"]

        # not monotonic
        ser = Series(
            np.random.default_rng(2).standard_normal(6), index=[2, 2, 0, 0, 1, 1]
        )

        with pytest.raises(KeyError, match=r"^5$"):
            ser[5]

        with pytest.raises(KeyError, match=r"^'c'$"):
            ser["c"]

    def test_getitem_int64(self, datetime_series):
        idx = np.int64(5)
        msg = "Series.__getitem__ treating keys as positions is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = datetime_series[idx]
        assert res == datetime_series.iloc[5]

    def test_getitem_full_range(self):
        # github.com/pandas-dev/pandas/commit/4f433773141d2eb384325714a2776bcc5b2e20f7
        ser = Series(range(5), index=list(range(5)))
        result = ser[list(range(5))]
        tm.assert_series_equal(result, ser)

    # ------------------------------------------------------------------
    # Series with DatetimeIndex

    @pytest.mark.parametrize("tzstr", ["Europe/Berlin", "dateutil/Europe/Berlin"])
    def test_getitem_pydatetime_tz(self, tzstr):
        tz = timezones.maybe_get_tz(tzstr)

        index = date_range(
            start="2012-12-24 16:00", end="2012-12-24 18:00", freq="h", tz=tzstr
        )
        ts = Series(index=index, data=index.hour)
        time_pandas = Timestamp("2012-12-24 17:00", tz=tzstr)

        dt = datetime(2012, 12, 24, 17, 0)
        time_datetime = conversion.localize_pydatetime(dt, tz)
        assert ts[time_pandas] == ts[time_datetime]

    @pytest.mark.parametrize("tz", ["US/Eastern", "dateutil/US/Eastern"])
    def test_string_index_alias_tz_aware(self, tz):
        rng = date_range("1/1/2000", periods=10, tz=tz)
        ser = Series(np.random.default_rng(2).standard_normal(len(rng)), index=rng)

        result = ser["1/3/2000"]
        tm.assert_almost_equal(result, ser.iloc[2])

    def test_getitem_time_object(self):
        rng = date_range("1/1/2000", "1/5/2000", freq="5min")
        ts = Series(np.random.default_rng(2).standard_normal(len(rng)), index=rng)

        mask = (rng.hour == 9) & (rng.minute == 30)
        result = ts[time(9, 30)]
        expected = ts[mask]
        result.index = result.index._with_freq(None)
        tm.assert_series_equal(result, expected)

    # ------------------------------------------------------------------
    # Series with CategoricalIndex

    def test_getitem_scalar_categorical_index(self):
        cats = Categorical([Timestamp("12-31-1999"), Timestamp("12-31-2000")])

        ser = Series([1, 2], index=cats)

        expected = ser.iloc[0]
        result = ser[cats[0]]
        assert result == expected

    def test_getitem_numeric_categorical_listlike_matches_scalar(self):
        # GH#15470
        ser = Series(["a", "b", "c"], index=pd.CategoricalIndex([2, 1, 0]))

        # 0 is treated as a label
        assert ser[0] == "c"

        # the listlike analogue should also be treated as labels
        res = ser[[0]]
        expected = ser.iloc[-1:]
        tm.assert_series_equal(res, expected)

        res2 = ser[[0, 1, 2]]
        tm.assert_series_equal(res2, ser.iloc[::-1])

    def test_getitem_integer_categorical_not_positional(self):
        # GH#14865
        ser = Series(["a", "b", "c"], index=Index([1, 2, 3], dtype="category"))
        assert ser.get(3) == "c"
        assert ser[3] == "c"

    def test_getitem_str_with_timedeltaindex(self):
        rng = timedelta_range("1 day 10:11:12", freq="h", periods=500)
        ser = Series(np.arange(len(rng)), index=rng)

        key = "6 days, 23:11:12"
        indexer = rng.get_loc(key)
        assert indexer == 133

        result = ser[key]
        assert result == ser.iloc[133]

        msg = r"^Timedelta\('50 days 00:00:00'\)$"
        with pytest.raises(KeyError, match=msg):
            rng.get_loc("50 days")
        with pytest.raises(KeyError, match=msg):
            ser["50 days"]

    def test_getitem_bool_index_positional(self):
        # GH#48653
        ser = Series({True: 1, False: 0})
        msg = "Series.__getitem__ treating keys as positions is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = ser[0]
        assert result == 1


class TestSeriesGetitemSlices:
    def test_getitem_partial_str_slice_with_datetimeindex(self):
        # GH#34860
        arr = date_range("1/1/2008", "1/1/2009")
        ser = arr.to_series()
        result = ser["2008"]

        rng = date_range(start="2008-01-01", end="2008-12-31")
        expected = Series(rng, index=rng)

        tm.assert_series_equal(result, expected)

    def test_getitem_slice_strings_with_datetimeindex(self):
        idx = DatetimeIndex(
            ["1/1/2000", "1/2/2000", "1/2/2000", "1/3/2000", "1/4/2000"]
        )

        ts = Series(np.random.default_rng(2).standard_normal(len(idx)), index=idx)

        result = ts["1/2/2000":]
        expected = ts[1:]
        tm.assert_series_equal(result, expected)

        result = ts["1/2/2000":"1/3/2000"]
        expected = ts[1:4]
        tm.assert_series_equal(result, expected)

    def test_getitem_partial_str_slice_with_timedeltaindex(self):
        rng = timedelta_range("1 day 10:11:12", freq="h", periods=500)
        ser = Series(np.arange(len(rng)), index=rng)

        result = ser["5 day":"6 day"]
        expected = ser.iloc[86:134]
        tm.assert_series_equal(result, expected)

        result = ser["5 day":]
        expected = ser.iloc[86:]
        tm.assert_series_equal(result, expected)

        result = ser[:"6 day"]
        expected = ser.iloc[:134]
        tm.assert_series_equal(result, expected)

    def test_getitem_partial_str_slice_high_reso_with_timedeltaindex(self):
        # higher reso
        rng = timedelta_range("1 day 10:11:12", freq="us", periods=2000)
        ser = Series(np.arange(len(rng)), index=rng)

        result = ser["1 day 10:11:12":]
        expected = ser.iloc[0:]
        tm.assert_series_equal(result, expected)

        result = ser["1 day 10:11:12.001":]
        expected = ser.iloc[1000:]
        tm.assert_series_equal(result, expected)

        result = ser["1 days, 10:11:12.001001"]
        assert result == ser.iloc[1001]

    def test_getitem_slice_2d(self, datetime_series):
        # GH#30588 multi-dimensional indexing deprecated
        with pytest.raises(ValueError, match="Multi-dimensional indexing"):
            datetime_series[:, np.newaxis]

    def test_getitem_median_slice_bug(self):
        index = date_range("20090415", "20090519", freq="2B")
        ser = Series(np.random.default_rng(2).standard_normal(13), index=index)

        indexer = [slice(6, 7, None)]
        msg = "Indexing with a single-item list"
        with pytest.raises(ValueError, match=msg):
            # GH#31299
            ser[indexer]
        # but we're OK with a single-element tuple
        result = ser[(indexer[0],)]
        expected = ser[indexer[0]]
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "slc, positions",
        [
            [slice(date(2018, 1, 1), None), [0, 1, 2]],
            [slice(date(2019, 1, 2), None), [2]],
            [slice(date(2020, 1, 1), None), []],
            [slice(None, date(2020, 1, 1)), [0, 1, 2]],
            [slice(None, date(2019, 1, 1)), [0]],
        ],
    )
    def test_getitem_slice_date(self, slc, positions):
        # https://github.com/pandas-dev/pandas/issues/31501
        ser = Series(
            [0, 1, 2],
            DatetimeIndex(["2019-01-01", "2019-01-01T06:00:00", "2019-01-02"]),
        )
        result = ser[slc]
        expected = ser.take(positions)
        tm.assert_series_equal(result, expected)

    def test_getitem_slice_float_raises(self, datetime_series):
        msg = (
            "cannot do slice indexing on DatetimeIndex with these indexers "
            r"\[{key}\] of type float"
        )
        with pytest.raises(TypeError, match=msg.format(key=r"4\.0")):
            datetime_series[4.0:10.0]

        with pytest.raises(TypeError, match=msg.format(key=r"4\.5")):
            datetime_series[4.5:10.0]

    def test_getitem_slice_bug(self):
        ser = Series(range(10), index=list(range(10)))
        result = ser[-12:]
        tm.assert_series_equal(result, ser)

        result = ser[-7:]
        tm.assert_series_equal(result, ser[3:])

        result = ser[:-12]
        tm.assert_series_equal(result, ser[:0])

    def test_getitem_slice_integers(self):
        ser = Series(
            np.random.default_rng(2).standard_normal(8),
            index=[2, 4, 6, 8, 10, 12, 14, 16],
        )

        result = ser[:4]
        expected = Series(ser.values[:4], index=[2, 4, 6, 8])
        tm.assert_series_equal(result, expected)


class TestSeriesGetitemListLike:
    @pytest.mark.parametrize("box", [list, np.array, Index, Series])
    def test_getitem_no_matches(self, box):
        # GH#33462 we expect the same behavior for list/ndarray/Index/Series
        ser = Series(["A", "B"])

        key = Series(["C"])
        key = box(key)

        msg = r"None of \[Index\(\['C'\], dtype='object|str'\)\] are in the \[index\]"
        with pytest.raises(KeyError, match=msg):
            ser[key]

    def test_getitem_intlist_intindex_periodvalues(self):
        ser = Series(period_range("2000-01-01", periods=10, freq="D"))

        result = ser[[2, 4]]
        exp = Series(
            [pd.Period("2000-01-03", freq="D"), pd.Period("2000-01-05", freq="D")],
            index=[2, 4],
            dtype="Period[D]",
        )
        tm.assert_series_equal(result, exp)
        assert result.dtype == "Period[D]"

    @pytest.mark.parametrize("box", [list, np.array, Index])
    def test_getitem_intlist_intervalindex_non_int(self, box):
        # GH#33404 fall back to positional since ints are unambiguous
        dti = date_range("2000-01-03", periods=3)._with_freq(None)
        ii = pd.IntervalIndex.from_breaks(dti)
        ser = Series(range(len(ii)), index=ii)

        expected = ser.iloc[:1]
        key = box([0])
        msg = "Series.__getitem__ treating keys as positions is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = ser[key]
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("box", [list, np.array, Index])
    @pytest.mark.parametrize("dtype", [np.int64, np.float64, np.uint64])
    def test_getitem_intlist_multiindex_numeric_level(self, dtype, box):
        # GH#33404 do _not_ fall back to positional since ints are ambiguous
        idx = Index(range(4)).astype(dtype)
        dti = date_range("2000-01-03", periods=3)
        mi = pd.MultiIndex.from_product([idx, dti])
        ser = Series(range(len(mi))[::-1], index=mi)

        key = box([5])
        with pytest.raises(KeyError, match="5"):
            ser[key]

    def test_getitem_uint_array_key(self, any_unsigned_int_numpy_dtype):
        # GH #37218
        ser = Series([1, 2, 3])
        key = np.array([4], dtype=any_unsigned_int_numpy_dtype)

        with pytest.raises(KeyError, match="4"):
            ser[key]
        with pytest.raises(KeyError, match="4"):
            ser.loc[key]


class TestGetitemBooleanMask:
    def test_getitem_boolean(self, string_series):
        ser = string_series
        mask = ser > ser.median()

        # passing list is OK
        result = ser[list(mask)]
        expected = ser[mask]
        tm.assert_series_equal(result, expected)
        tm.assert_index_equal(result.index, ser.index[mask])

    def test_getitem_boolean_empty(self):
        ser = Series([], dtype=np.int64)
        ser.index.name = "index_name"
        ser = ser[ser.isna()]
        assert ser.index.name == "index_name"
        assert ser.dtype == np.int64

        # GH#5877
        # indexing with empty series
        ser = Series(["A", "B"], dtype=object)
        expected = Series(dtype=object, index=Index([], dtype="int64"))
        result = ser[Series([], dtype=object)]
        tm.assert_series_equal(result, expected)

        # invalid because of the boolean indexer
        # that's empty or not-aligned
        msg = (
            r"Unalignable boolean Series provided as indexer \(index of "
            r"the boolean Series and of the indexed object do not match"
        )
        with pytest.raises(IndexingError, match=msg):
            ser[Series([], dtype=bool)]

        with pytest.raises(IndexingError, match=msg):
            ser[Series([True], dtype=bool)]

    def test_getitem_boolean_object(self, string_series):
        # using column from DataFrame

        ser = string_series
        mask = ser > ser.median()
        omask = mask.astype(object)

        # getitem
        result = ser[omask]
        expected = ser[mask]
        tm.assert_series_equal(result, expected)

        # setitem
        s2 = ser.copy()
        cop = ser.copy()
        cop[omask] = 5
        s2[mask] = 5
        tm.assert_series_equal(cop, s2)

        # nans raise exception
        omask[5:10] = np.nan
        msg = "Cannot mask with non-boolean array containing NA / NaN values"
        with pytest.raises(ValueError, match=msg):
            ser[omask]
        with pytest.raises(ValueError, match=msg):
            ser[omask] = 5

    def test_getitem_boolean_dt64_copies(self):
        # GH#36210
        dti = date_range("2016-01-01", periods=4, tz="US/Pacific")
        key = np.array([True, True, False, False])

        ser = Series(dti._data)

        res = ser[key]
        assert res._values._ndarray.base is None

        # compare with numeric case for reference
        ser2 = Series(range(4))
        res2 = ser2[key]
        assert res2._values.base is None

    def test_getitem_boolean_corner(self, datetime_series):
        ts = datetime_series
        mask_shifted = ts.shift(1, freq=BDay()) > ts.median()

        msg = (
            r"Unalignable boolean Series provided as indexer \(index of "
            r"the boolean Series and of the indexed object do not match"
        )
        with pytest.raises(IndexingError, match=msg):
            ts[mask_shifted]

        with pytest.raises(IndexingError, match=msg):
            ts.loc[mask_shifted]

    def test_getitem_boolean_different_order(self, string_series):
        ordered = string_series.sort_values()

        sel = string_series[ordered > 0]
        exp = string_series[string_series > 0]
        tm.assert_series_equal(sel, exp)

    def test_getitem_boolean_contiguous_preserve_freq(self):
        rng = date_range("1/1/2000", "3/1/2000", freq="B")

        mask = np.zeros(len(rng), dtype=bool)
        mask[10:20] = True

        masked = rng[mask]
        expected = rng[10:20]
        assert expected.freq == rng.freq
        tm.assert_index_equal(masked, expected)

        mask[22] = True
        masked = rng[mask]
        assert masked.freq is None


class TestGetitemCallable:
    def test_getitem_callable(self):
        # GH#12533
        ser = Series(4, index=list("ABCD"))
        result = ser[lambda x: "A"]
        assert result == ser.loc["A"]

        result = ser[lambda x: ["A", "B"]]
        expected = ser.loc[["A", "B"]]
        tm.assert_series_equal(result, expected)

        result = ser[lambda x: [True, False, True, True]]
        expected = ser.iloc[[0, 2, 3]]
        tm.assert_series_equal(result, expected)


def test_getitem_generator(string_series):
    gen = (x > 0 for x in string_series)
    result = string_series[gen]
    result2 = string_series[iter(string_series > 0)]
    expected = string_series[string_series > 0]
    tm.assert_series_equal(result, expected)
    tm.assert_series_equal(result2, expected)


@pytest.mark.parametrize(
    "series",
    [
        Series([0, 1]),
        Series(date_range("2012-01-01", periods=2)),
        Series(date_range("2012-01-01", periods=2, tz="CET")),
    ],
)
def test_getitem_ndim_deprecated(series):
    with pytest.raises(ValueError, match="Multi-dimensional indexing"):
        series[:, None]


def test_getitem_multilevel_scalar_slice_not_implemented(
    multiindex_year_month_day_dataframe_random_data,
):
    # not implementing this for now
    df = multiindex_year_month_day_dataframe_random_data
    ser = df["A"]

    msg = r"\(2000, slice\(3, 4, None\)\)"
    with pytest.raises(TypeError, match=msg):
        ser[2000, 3:4]


def test_getitem_dataframe_raises():
    rng = list(range(10))
    ser = Series(10, index=rng)
    df = DataFrame(rng, index=rng)
    msg = (
        "Indexing a Series with DataFrame is not supported, "
        "use the appropriate DataFrame column"
    )
    with pytest.raises(TypeError, match=msg):
        ser[df > 5]


def test_getitem_assignment_series_alignment():
    # https://github.com/pandas-dev/pandas/issues/37427
    # with getitem, when assigning with a Series, it is not first aligned
    ser = Series(range(10))
    idx = np.array([2, 4, 9])
    ser[idx] = Series([10, 11, 12])
    expected = Series([0, 1, 10, 3, 11, 5, 6, 7, 8, 12])
    tm.assert_series_equal(ser, expected)


def test_getitem_duplicate_index_mistyped_key_raises_keyerror():
    # GH#29189 float_index.get_loc(None) should raise KeyError, not TypeError
    ser = Series([2, 5, 6, 8], index=[2.0, 4.0, 4.0, 5.0])
    with pytest.raises(KeyError, match="None"):
        ser[None]

    with pytest.raises(KeyError, match="None"):
        ser.index.get_loc(None)

    with pytest.raises(KeyError, match="None"):
        ser.index._engine.get_loc(None)


def test_getitem_1tuple_slice_without_multiindex():
    ser = Series(range(5))
    key = (slice(3),)

    result = ser[key]
    expected = ser[key[0]]
    tm.assert_series_equal(result, expected)


def test_getitem_preserve_name(datetime_series):
    result = datetime_series[datetime_series > 0]
    assert result.name == datetime_series.name

    msg = "Series.__getitem__ treating keys as positions is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = datetime_series[[0, 2, 4]]
    assert result.name == datetime_series.name

    result = datetime_series[5:10]
    assert result.name == datetime_series.name


def test_getitem_with_integer_labels():
    # integer indexes, be careful
    ser = Series(
        np.random.default_rng(2).standard_normal(10), index=list(range(0, 20, 2))
    )
    inds = [0, 2, 5, 7, 8]
    arr_inds = np.array([0, 2, 5, 7, 8])
    with pytest.raises(KeyError, match="not in index"):
        ser[inds]

    with pytest.raises(KeyError, match="not in index"):
        ser[arr_inds]


def test_getitem_missing(datetime_series):
    # missing
    d = datetime_series.index[0] - BDay()
    msg = r"Timestamp\('1999-12-31 00:00:00'\)"
    with pytest.raises(KeyError, match=msg):
        datetime_series[d]


def test_getitem_fancy(string_series, object_series):
    msg = "Series.__getitem__ treating keys as positions is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        slice1 = string_series[[1, 2, 3]]
        slice2 = object_series[[1, 2, 3]]
    assert string_series.index[2] == slice1.index[1]
    assert object_series.index[2] == slice2.index[1]
    assert string_series.iloc[2] == slice1.iloc[1]
    assert object_series.iloc[2] == slice2.iloc[1]


def test_getitem_box_float64(datetime_series):
    msg = "Series.__getitem__ treating keys as positions is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        value = datetime_series[5]
    assert isinstance(value, np.float64)


def test_getitem_unordered_dup():
    obj = Series(range(5), index=["c", "a", "a", "b", "b"])
    assert is_scalar(obj["c"])
    assert obj["c"] == 0


def test_getitem_dups():
    ser = Series(range(5), index=["A", "A", "B", "C", "C"], dtype=np.int64)
    expected = Series([3, 4], index=["C", "C"], dtype=np.int64)
    result = ser["C"]
    tm.assert_series_equal(result, expected)


def test_getitem_categorical_str():
    # GH#31765
    ser = Series(range(5), index=Categorical(["a", "b", "c", "a", "b"]))
    result = ser["a"]
    expected = ser.iloc[[0, 3]]
    tm.assert_series_equal(result, expected)


def test_slice_can_reorder_not_uniquely_indexed():
    ser = Series(1, index=["a", "a", "b", "b", "c"])
    ser[::-1]  # it works!


@pytest.mark.parametrize("index_vals", ["aabcd", "aadcb"])
def test_duplicated_index_getitem_positional_indexer(index_vals):
    # GH 11747
    s = Series(range(5), index=list(index_vals))

    msg = "Series.__getitem__ treating keys as positions is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = s[3]
    assert result == 3


class TestGetitemDeprecatedIndexers:
    @pytest.mark.parametrize("key", [{1}, {1: 1}])
    def test_getitem_dict_and_set_deprecated(self, key):
        # GH#42825 enforced in 2.0
        ser = Series([1, 2, 3])
        with pytest.raises(TypeError, match="as an indexer is not supported"):
            ser[key]

    @pytest.mark.parametrize("key", [{1}, {1: 1}])
    def test_setitem_dict_and_set_disallowed(self, key):
        # GH#42825 enforced in 2.0
        ser = Series([1, 2, 3])
        with pytest.raises(TypeError, match="as an indexer is not supported"):
            ser[key] = 1
