from datetime import (
    date,
    datetime,
)
from decimal import Decimal
import os

import numpy as np
import pytest

from pandas.compat.numpy import (
    np_version_gt2,
    np_version_gte1p24,
)
from pandas.errors import IndexingError

from pandas.core.dtypes.common import is_list_like

from pandas import (
    NA,
    Categorical,
    DataFrame,
    DatetimeIndex,
    Index,
    Interval,
    IntervalIndex,
    MultiIndex,
    NaT,
    Period,
    Series,
    Timedelta,
    Timestamp,
    array,
    concat,
    date_range,
    interval_range,
    period_range,
    timedelta_range,
)
import pandas._testing as tm

from pandas.tseries.offsets import BDay


class TestSetitemDT64Values:
    def test_setitem_none_nan(self):
        series = Series(date_range("1/1/2000", periods=10))
        series[3] = None
        assert series[3] is NaT

        series[3:5] = None
        assert series[4] is NaT

        series[5] = np.nan
        assert series[5] is NaT

        series[5:7] = np.nan
        assert series[6] is NaT

    def test_setitem_multiindex_empty_slice(self):
        # https://github.com/pandas-dev/pandas/issues/35878
        idx = MultiIndex.from_tuples([("a", 1), ("b", 2)])
        result = Series([1, 2], index=idx)
        expected = result.copy()
        result.loc[[]] = 0
        tm.assert_series_equal(result, expected)

    def test_setitem_with_string_index(self):
        # GH#23451
        # Set object dtype to avoid upcast when setting date.today()
        ser = Series([1, 2, 3], index=["Date", "b", "other"], dtype=object)
        ser["Date"] = date.today()
        assert ser.Date == date.today()
        assert ser["Date"] == date.today()

    def test_setitem_tuple_with_datetimetz_values(self):
        # GH#20441
        arr = date_range("2017", periods=4, tz="US/Eastern")
        index = [(0, 1), (0, 2), (0, 3), (0, 4)]
        result = Series(arr, index=index)
        expected = result.copy()
        result[(0, 1)] = np.nan
        expected.iloc[0] = np.nan
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("tz", ["US/Eastern", "UTC", "Asia/Tokyo"])
    def test_setitem_with_tz(self, tz, indexer_sli):
        orig = Series(date_range("2016-01-01", freq="h", periods=3, tz=tz))
        assert orig.dtype == f"datetime64[ns, {tz}]"

        exp = Series(
            [
                Timestamp("2016-01-01 00:00", tz=tz),
                Timestamp("2011-01-01 00:00", tz=tz),
                Timestamp("2016-01-01 02:00", tz=tz),
            ],
            dtype=orig.dtype,
        )

        # scalar
        ser = orig.copy()
        indexer_sli(ser)[1] = Timestamp("2011-01-01", tz=tz)
        tm.assert_series_equal(ser, exp)

        # vector
        vals = Series(
            [Timestamp("2011-01-01", tz=tz), Timestamp("2012-01-01", tz=tz)],
            index=[1, 2],
            dtype=orig.dtype,
        )
        assert vals.dtype == f"datetime64[ns, {tz}]"

        exp = Series(
            [
                Timestamp("2016-01-01 00:00", tz=tz),
                Timestamp("2011-01-01 00:00", tz=tz),
                Timestamp("2012-01-01 00:00", tz=tz),
            ],
            dtype=orig.dtype,
        )

        ser = orig.copy()
        indexer_sli(ser)[[1, 2]] = vals
        tm.assert_series_equal(ser, exp)

    def test_setitem_with_tz_dst(self, indexer_sli):
        # GH#14146 trouble setting values near DST boundary
        tz = "US/Eastern"
        orig = Series(date_range("2016-11-06", freq="h", periods=3, tz=tz))
        assert orig.dtype == f"datetime64[ns, {tz}]"

        exp = Series(
            [
                Timestamp("2016-11-06 00:00-04:00", tz=tz),
                Timestamp("2011-01-01 00:00-05:00", tz=tz),
                Timestamp("2016-11-06 01:00-05:00", tz=tz),
            ],
            dtype=orig.dtype,
        )

        # scalar
        ser = orig.copy()
        indexer_sli(ser)[1] = Timestamp("2011-01-01", tz=tz)
        tm.assert_series_equal(ser, exp)

        # vector
        vals = Series(
            [Timestamp("2011-01-01", tz=tz), Timestamp("2012-01-01", tz=tz)],
            index=[1, 2],
            dtype=orig.dtype,
        )
        assert vals.dtype == f"datetime64[ns, {tz}]"

        exp = Series(
            [
                Timestamp("2016-11-06 00:00", tz=tz),
                Timestamp("2011-01-01 00:00", tz=tz),
                Timestamp("2012-01-01 00:00", tz=tz),
            ],
            dtype=orig.dtype,
        )

        ser = orig.copy()
        indexer_sli(ser)[[1, 2]] = vals
        tm.assert_series_equal(ser, exp)

    def test_object_series_setitem_dt64array_exact_match(self):
        # make sure the dt64 isn't cast by numpy to integers
        # https://github.com/numpy/numpy/issues/12550

        ser = Series({"X": np.nan}, dtype=object)

        indexer = [True]

        # "exact_match" -> size of array being set matches size of ser
        value = np.array([4], dtype="M8[ns]")

        ser.iloc[indexer] = value

        expected = Series([value[0]], index=["X"], dtype=object)
        assert all(isinstance(x, np.datetime64) for x in expected.values)

        tm.assert_series_equal(ser, expected)


class TestSetitemScalarIndexer:
    def test_setitem_negative_out_of_bounds(self):
        ser = Series(["a"] * 10, index=["a"] * 10)

        # string index falls back to positional
        msg = "index -11|-1 is out of bounds for axis 0 with size 10"
        warn_msg = "Series.__setitem__ treating keys as positions is deprecated"
        with pytest.raises(IndexError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=warn_msg):
                ser[-11] = "foo"

    @pytest.mark.parametrize("indexer", [tm.loc, tm.at])
    @pytest.mark.parametrize("ser_index", [0, 1])
    def test_setitem_series_object_dtype(self, indexer, ser_index):
        # GH#38303
        ser = Series([0, 0], dtype="object")
        idxr = indexer(ser)
        idxr[0] = Series([42], index=[ser_index])
        expected = Series([Series([42], index=[ser_index]), 0], dtype="object")
        tm.assert_series_equal(ser, expected)

    @pytest.mark.parametrize("index, exp_value", [(0, 42), (1, np.nan)])
    def test_setitem_series(self, index, exp_value):
        # GH#38303
        ser = Series([0, 0])
        ser.loc[0] = Series([42], index=[index])
        expected = Series([exp_value, 0])
        tm.assert_series_equal(ser, expected)


class TestSetitemSlices:
    def test_setitem_slice_float_raises(self, datetime_series):
        msg = (
            "cannot do slice indexing on DatetimeIndex with these indexers "
            r"\[{key}\] of type float"
        )
        with pytest.raises(TypeError, match=msg.format(key=r"4\.0")):
            datetime_series[4.0:10.0] = 0

        with pytest.raises(TypeError, match=msg.format(key=r"4\.5")):
            datetime_series[4.5:10.0] = 0

    def test_setitem_slice(self):
        ser = Series(range(10), index=list(range(10)))
        ser[-12:] = 0
        assert (ser == 0).all()

        ser[:-12] = 5
        assert (ser == 0).all()

    def test_setitem_slice_integers(self):
        ser = Series(
            np.random.default_rng(2).standard_normal(8),
            index=[2, 4, 6, 8, 10, 12, 14, 16],
        )

        ser[:4] = 0
        assert (ser[:4] == 0).all()
        assert not (ser[4:] == 0).any()

    def test_setitem_slicestep(self):
        # caught this bug when writing tests
        series = Series(
            np.arange(20, dtype=np.float64), index=np.arange(20, dtype=np.int64)
        )

        series[::2] = 0
        assert (series[::2] == 0).all()

    def test_setitem_multiindex_slice(self, indexer_sli):
        # GH 8856
        mi = MultiIndex.from_product(([0, 1], list("abcde")))
        result = Series(np.arange(10, dtype=np.int64), mi)
        indexer_sli(result)[::4] = 100
        expected = Series([100, 1, 2, 3, 100, 5, 6, 7, 100, 9], mi)
        tm.assert_series_equal(result, expected)


class TestSetitemBooleanMask:
    def test_setitem_mask_cast(self):
        # GH#2746
        # need to upcast
        ser = Series([1, 2], index=[1, 2], dtype="int64")
        ser[[True, False]] = Series([0], index=[1], dtype="int64")
        expected = Series([0, 2], index=[1, 2], dtype="int64")

        tm.assert_series_equal(ser, expected)

    def test_setitem_mask_align_and_promote(self):
        # GH#8387: test that changing types does not break alignment
        ts = Series(
            np.random.default_rng(2).standard_normal(100), index=np.arange(100, 0, -1)
        ).round(5)
        mask = ts > 0
        left = ts.copy()
        right = ts[mask].copy().map(str)
        with tm.assert_produces_warning(
            FutureWarning, match="item of incompatible dtype"
        ):
            left[mask] = right
        expected = ts.map(lambda t: str(t) if t > 0 else t)
        tm.assert_series_equal(left, expected)

    def test_setitem_mask_promote_strs(self):
        ser = Series([0, 1, 2, 0])
        mask = ser > 0
        ser2 = ser[mask].map(str)
        with tm.assert_produces_warning(
            FutureWarning, match="item of incompatible dtype"
        ):
            ser[mask] = ser2

        expected = Series([0, "1", "2", 0])
        tm.assert_series_equal(ser, expected)

    def test_setitem_mask_promote(self):
        ser = Series([0, "foo", "bar", 0])
        mask = Series([False, True, True, False])
        ser2 = ser[mask]
        ser[mask] = ser2

        expected = Series([0, "foo", "bar", 0])
        tm.assert_series_equal(ser, expected)

    def test_setitem_boolean(self, string_series):
        mask = string_series > string_series.median()

        # similar indexed series
        result = string_series.copy()
        result[mask] = string_series * 2
        expected = string_series * 2
        tm.assert_series_equal(result[mask], expected[mask])

        # needs alignment
        result = string_series.copy()
        result[mask] = (string_series * 2)[0:5]
        expected = (string_series * 2)[0:5].reindex_like(string_series)
        expected[-mask] = string_series[mask]
        tm.assert_series_equal(result[mask], expected[mask])

    def test_setitem_boolean_corner(self, datetime_series):
        ts = datetime_series
        mask_shifted = ts.shift(1, freq=BDay()) > ts.median()

        msg = (
            r"Unalignable boolean Series provided as indexer \(index of "
            r"the boolean Series and of the indexed object do not match"
        )
        with pytest.raises(IndexingError, match=msg):
            ts[mask_shifted] = 1

        with pytest.raises(IndexingError, match=msg):
            ts.loc[mask_shifted] = 1

    def test_setitem_boolean_different_order(self, string_series):
        ordered = string_series.sort_values()

        copy = string_series.copy()
        copy[ordered > 0] = 0

        expected = string_series.copy()
        expected[expected > 0] = 0

        tm.assert_series_equal(copy, expected)

    @pytest.mark.parametrize("func", [list, np.array, Series])
    def test_setitem_boolean_python_list(self, func):
        # GH19406
        ser = Series([None, "b", None])
        mask = func([True, False, True])
        ser[mask] = ["a", "c"]
        expected = Series(["a", "b", "c"])
        tm.assert_series_equal(ser, expected)

    def test_setitem_boolean_nullable_int_types(self, any_numeric_ea_dtype):
        # GH: 26468
        ser = Series([5, 6, 7, 8], dtype=any_numeric_ea_dtype)
        ser[ser > 6] = Series(range(4), dtype=any_numeric_ea_dtype)
        expected = Series([5, 6, 2, 3], dtype=any_numeric_ea_dtype)
        tm.assert_series_equal(ser, expected)

        ser = Series([5, 6, 7, 8], dtype=any_numeric_ea_dtype)
        ser.loc[ser > 6] = Series(range(4), dtype=any_numeric_ea_dtype)
        tm.assert_series_equal(ser, expected)

        ser = Series([5, 6, 7, 8], dtype=any_numeric_ea_dtype)
        loc_ser = Series(range(4), dtype=any_numeric_ea_dtype)
        ser.loc[ser > 6] = loc_ser.loc[loc_ser > 1]
        tm.assert_series_equal(ser, expected)

    def test_setitem_with_bool_mask_and_values_matching_n_trues_in_length(self):
        # GH#30567
        ser = Series([None] * 10)
        mask = [False] * 3 + [True] * 5 + [False] * 2
        ser[mask] = range(5)
        result = ser
        expected = Series([None] * 3 + list(range(5)) + [None] * 2, dtype=object)
        tm.assert_series_equal(result, expected)

    def test_setitem_nan_with_bool(self):
        # GH 13034
        result = Series([True, False, True])
        with tm.assert_produces_warning(
            FutureWarning, match="item of incompatible dtype"
        ):
            result[0] = np.nan
        expected = Series([np.nan, False, True], dtype=object)
        tm.assert_series_equal(result, expected)

    def test_setitem_mask_smallint_upcast(self):
        orig = Series([1, 2, 3], dtype="int8")
        alt = np.array([999, 1000, 1001], dtype=np.int64)

        mask = np.array([True, False, True])

        ser = orig.copy()
        with tm.assert_produces_warning(
            FutureWarning, match="item of incompatible dtype"
        ):
            ser[mask] = Series(alt)
        expected = Series([999, 2, 1001])
        tm.assert_series_equal(ser, expected)

        ser2 = orig.copy()
        with tm.assert_produces_warning(
            FutureWarning, match="item of incompatible dtype"
        ):
            ser2.mask(mask, alt, inplace=True)
        tm.assert_series_equal(ser2, expected)

        ser3 = orig.copy()
        res = ser3.where(~mask, Series(alt))
        tm.assert_series_equal(res, expected)

    def test_setitem_mask_smallint_no_upcast(self):
        # like test_setitem_mask_smallint_upcast, but while we can't hold 'alt',
        #  we *can* hold alt[mask] without casting
        orig = Series([1, 2, 3], dtype="uint8")
        alt = Series([245, 1000, 246], dtype=np.int64)

        mask = np.array([True, False, True])

        ser = orig.copy()
        ser[mask] = alt
        expected = Series([245, 2, 246], dtype="uint8")
        tm.assert_series_equal(ser, expected)

        ser2 = orig.copy()
        ser2.mask(mask, alt, inplace=True)
        tm.assert_series_equal(ser2, expected)

        # TODO: ser.where(~mask, alt) unnecessarily upcasts to int64
        ser3 = orig.copy()
        res = ser3.where(~mask, alt)
        tm.assert_series_equal(res, expected, check_dtype=False)


class TestSetitemViewCopySemantics:
    def test_setitem_invalidates_datetime_index_freq(self, using_copy_on_write):
        # GH#24096 altering a datetime64tz Series inplace invalidates the
        #  `freq` attribute on the underlying DatetimeIndex

        dti = date_range("20130101", periods=3, tz="US/Eastern")
        ts = dti[1]
        ser = Series(dti)
        assert ser._values is not dti
        if using_copy_on_write:
            assert ser._values._ndarray.base is dti._data._ndarray.base
        else:
            assert ser._values._ndarray.base is not dti._data._ndarray.base
        assert dti.freq == "D"
        ser.iloc[1] = NaT
        assert ser._values.freq is None

        # check that the DatetimeIndex was not altered in place
        assert ser._values is not dti
        assert ser._values._ndarray.base is not dti._data._ndarray.base
        assert dti[1] == ts
        assert dti.freq == "D"

    def test_dt64tz_setitem_does_not_mutate_dti(self, using_copy_on_write):
        # GH#21907, GH#24096
        dti = date_range("2016-01-01", periods=10, tz="US/Pacific")
        ts = dti[0]
        ser = Series(dti)
        assert ser._values is not dti
        if using_copy_on_write:
            assert ser._values._ndarray.base is dti._data._ndarray.base
            assert ser._mgr.arrays[0]._ndarray.base is dti._data._ndarray.base
        else:
            assert ser._values._ndarray.base is not dti._data._ndarray.base
            assert ser._mgr.arrays[0]._ndarray.base is not dti._data._ndarray.base

        assert ser._mgr.arrays[0] is not dti

        ser[::3] = NaT
        assert ser[0] is NaT
        assert dti[0] == ts


class TestSetitemCallable:
    def test_setitem_callable_key(self):
        # GH#12533
        ser = Series([1, 2, 3, 4], index=list("ABCD"))
        ser[lambda x: "A"] = -1

        expected = Series([-1, 2, 3, 4], index=list("ABCD"))
        tm.assert_series_equal(ser, expected)

    def test_setitem_callable_other(self):
        # GH#13299
        inc = lambda x: x + 1

        # set object dtype to avoid upcast when setting inc
        ser = Series([1, 2, -1, 4], dtype=object)
        ser[ser < 0] = inc

        expected = Series([1, 2, inc, 4])
        tm.assert_series_equal(ser, expected)


class TestSetitemWithExpansion:
    def test_setitem_empty_series(self):
        # GH#10193
        key = Timestamp("2012-01-01")
        series = Series(dtype=object)
        series[key] = 47
        expected = Series(47, [key])
        tm.assert_series_equal(series, expected)

    def test_setitem_empty_series_datetimeindex_preserves_freq(self):
        # GH#33573 our index should retain its freq
        dti = DatetimeIndex([], freq="D", dtype="M8[ns]")
        series = Series([], index=dti, dtype=object)
        key = Timestamp("2012-01-01")
        series[key] = 47
        expected = Series(47, DatetimeIndex([key], freq="D").as_unit("ns"))
        tm.assert_series_equal(series, expected)
        assert series.index.freq == expected.index.freq

    def test_setitem_empty_series_timestamp_preserves_dtype(self):
        # GH 21881
        timestamp = Timestamp(1412526600000000000)
        series = Series([timestamp], index=["timestamp"], dtype=object)
        expected = series["timestamp"]

        series = Series([], dtype=object)
        series["anything"] = 300.0
        series["timestamp"] = timestamp
        result = series["timestamp"]
        assert result == expected

    @pytest.mark.parametrize(
        "td",
        [
            Timedelta("9 days"),
            Timedelta("9 days").to_timedelta64(),
            Timedelta("9 days").to_pytimedelta(),
        ],
    )
    def test_append_timedelta_does_not_cast(self, td, using_infer_string, request):
        # GH#22717 inserting a Timedelta should _not_ cast to int64
        if using_infer_string and not isinstance(td, Timedelta):
            # TODO: GH#56010
            request.applymarker(pytest.mark.xfail(reason="inferred as string"))

        expected = Series(["x", td], index=[0, "td"], dtype=object)

        ser = Series(["x"])
        ser["td"] = td
        tm.assert_series_equal(ser, expected)
        assert isinstance(ser["td"], Timedelta)

        ser = Series(["x"])
        ser.loc["td"] = Timedelta("9 days")
        tm.assert_series_equal(ser, expected)
        assert isinstance(ser["td"], Timedelta)

    def test_setitem_with_expansion_type_promotion(self):
        # GH#12599
        ser = Series(dtype=object)
        ser["a"] = Timestamp("2016-01-01")
        ser["b"] = 3.0
        ser["c"] = "foo"
        expected = Series([Timestamp("2016-01-01"), 3.0, "foo"], index=["a", "b", "c"])
        tm.assert_series_equal(ser, expected)

    def test_setitem_not_contained(self, string_series):
        # set item that's not contained
        ser = string_series.copy()
        assert "foobar" not in ser.index
        ser["foobar"] = 1

        app = Series([1], index=["foobar"], name="series")
        expected = concat([string_series, app])
        tm.assert_series_equal(ser, expected)

    def test_setitem_keep_precision(self, any_numeric_ea_dtype):
        # GH#32346
        ser = Series([1, 2], dtype=any_numeric_ea_dtype)
        ser[2] = 10
        expected = Series([1, 2, 10], dtype=any_numeric_ea_dtype)
        tm.assert_series_equal(ser, expected)

    @pytest.mark.parametrize(
        "na, target_na, dtype, target_dtype, indexer, warn",
        [
            (NA, NA, "Int64", "Int64", 1, None),
            (NA, NA, "Int64", "Int64", 2, None),
            (NA, np.nan, "int64", "float64", 1, None),
            (NA, np.nan, "int64", "float64", 2, None),
            (NaT, NaT, "int64", "object", 1, FutureWarning),
            (NaT, NaT, "int64", "object", 2, None),
            (np.nan, NA, "Int64", "Int64", 1, None),
            (np.nan, NA, "Int64", "Int64", 2, None),
            (np.nan, NA, "Float64", "Float64", 1, None),
            (np.nan, NA, "Float64", "Float64", 2, None),
            (np.nan, np.nan, "int64", "float64", 1, None),
            (np.nan, np.nan, "int64", "float64", 2, None),
        ],
    )
    def test_setitem_enlarge_with_na(
        self, na, target_na, dtype, target_dtype, indexer, warn
    ):
        # GH#32346
        ser = Series([1, 2], dtype=dtype)
        with tm.assert_produces_warning(warn, match="incompatible dtype"):
            ser[indexer] = na
        expected_values = [1, target_na] if indexer == 1 else [1, 2, target_na]
        expected = Series(expected_values, dtype=target_dtype)
        tm.assert_series_equal(ser, expected)

    def test_setitem_enlargement_object_none(self, nulls_fixture, using_infer_string):
        # GH#48665
        ser = Series(["a", "b"])
        ser[3] = nulls_fixture
        dtype = (
            "str"
            if using_infer_string and not isinstance(nulls_fixture, Decimal)
            else object
        )
        expected = Series(["a", "b", nulls_fixture], index=[0, 1, 3], dtype=dtype)
        tm.assert_series_equal(ser, expected)
        if using_infer_string:
            ser[3] is np.nan
        else:
            assert ser[3] is nulls_fixture


def test_setitem_scalar_into_readonly_backing_data():
    # GH#14359: test that you cannot mutate a read only buffer

    array = np.zeros(5)
    array.flags.writeable = False  # make the array immutable
    series = Series(array, copy=False)

    for n in series.index:
        msg = "assignment destination is read-only"
        with pytest.raises(ValueError, match=msg):
            series[n] = 1

        assert array[n] == 0


def test_setitem_slice_into_readonly_backing_data():
    # GH#14359: test that you cannot mutate a read only buffer

    array = np.zeros(5)
    array.flags.writeable = False  # make the array immutable
    series = Series(array, copy=False)

    msg = "assignment destination is read-only"
    with pytest.raises(ValueError, match=msg):
        series[1:3] = 1

    assert not array.any()


def test_setitem_categorical_assigning_ops():
    orig = Series(Categorical(["b", "b"], categories=["a", "b"]))
    ser = orig.copy()
    ser[:] = "a"
    exp = Series(Categorical(["a", "a"], categories=["a", "b"]))
    tm.assert_series_equal(ser, exp)

    ser = orig.copy()
    ser[1] = "a"
    exp = Series(Categorical(["b", "a"], categories=["a", "b"]))
    tm.assert_series_equal(ser, exp)

    ser = orig.copy()
    ser[ser.index > 0] = "a"
    exp = Series(Categorical(["b", "a"], categories=["a", "b"]))
    tm.assert_series_equal(ser, exp)

    ser = orig.copy()
    ser[[False, True]] = "a"
    exp = Series(Categorical(["b", "a"], categories=["a", "b"]))
    tm.assert_series_equal(ser, exp)

    ser = orig.copy()
    ser.index = ["x", "y"]
    ser["y"] = "a"
    exp = Series(Categorical(["b", "a"], categories=["a", "b"]), index=["x", "y"])
    tm.assert_series_equal(ser, exp)


def test_setitem_nan_into_categorical():
    # ensure that one can set something to np.nan
    ser = Series(Categorical([1, 2, 3]))
    exp = Series(Categorical([1, np.nan, 3], categories=[1, 2, 3]))
    ser[1] = np.nan
    tm.assert_series_equal(ser, exp)


class TestSetitemCasting:
    @pytest.mark.parametrize("unique", [True, False])
    @pytest.mark.parametrize("val", [3, 3.0, "3"], ids=type)
    def test_setitem_non_bool_into_bool(self, val, indexer_sli, unique):
        # dont cast these 3-like values to bool
        ser = Series([True, False])
        if not unique:
            ser.index = [1, 1]

        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            indexer_sli(ser)[1] = val
        assert type(ser.iloc[1]) == type(val)

        expected = Series([True, val], dtype=object, index=ser.index)
        if not unique and indexer_sli is not tm.iloc:
            expected = Series([val, val], dtype=object, index=[1, 1])
        tm.assert_series_equal(ser, expected)

    def test_setitem_boolean_array_into_npbool(self):
        # GH#45462
        ser = Series([True, False, True])
        values = ser._values
        arr = array([True, False, None])

        ser[:2] = arr[:2]  # no NAs -> can set inplace
        assert ser._values is values

        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            ser[1:] = arr[1:]  # has an NA -> cast to boolean dtype
        expected = Series(arr)
        tm.assert_series_equal(ser, expected)


class SetitemCastingEquivalents:
    """
    Check each of several methods that _should_ be equivalent to `obj[key] = val`

    We assume that
        - obj.index is the default Index(range(len(obj)))
        - the setitem does not expand the obj
    """

    @pytest.fixture
    def is_inplace(self, obj, expected):
        """
        Whether we expect the setting to be in-place or not.
        """
        return expected.dtype == obj.dtype

    def check_indexer(self, obj, key, expected, val, indexer, is_inplace):
        orig = obj
        obj = obj.copy()
        arr = obj._values

        indexer(obj)[key] = val
        tm.assert_series_equal(obj, expected)

        self._check_inplace(is_inplace, orig, arr, obj)

    def _check_inplace(self, is_inplace, orig, arr, obj):
        if is_inplace is None:
            # We are not (yet) checking whether setting is inplace or not
            pass
        elif is_inplace:
            if arr.dtype.kind in ["m", "M"]:
                # We may not have the same DTA/TDA, but will have the same
                #  underlying data
                assert arr._ndarray is obj._values._ndarray
            else:
                assert obj._values is arr
        else:
            # otherwise original array should be unchanged
            tm.assert_equal(arr, orig._values)

    def test_int_key(self, obj, key, expected, warn, val, indexer_sli, is_inplace):
        if not isinstance(key, int):
            pytest.skip("Not relevant for int key")

        with tm.assert_produces_warning(warn, match="incompatible dtype"):
            self.check_indexer(obj, key, expected, val, indexer_sli, is_inplace)

        if indexer_sli is tm.loc:
            with tm.assert_produces_warning(warn, match="incompatible dtype"):
                self.check_indexer(obj, key, expected, val, tm.at, is_inplace)
        elif indexer_sli is tm.iloc:
            with tm.assert_produces_warning(warn, match="incompatible dtype"):
                self.check_indexer(obj, key, expected, val, tm.iat, is_inplace)

        rng = range(key, key + 1)
        with tm.assert_produces_warning(warn, match="incompatible dtype"):
            self.check_indexer(obj, rng, expected, val, indexer_sli, is_inplace)

        if indexer_sli is not tm.loc:
            # Note: no .loc because that handles slice edges differently
            slc = slice(key, key + 1)
            with tm.assert_produces_warning(warn, match="incompatible dtype"):
                self.check_indexer(obj, slc, expected, val, indexer_sli, is_inplace)

        ilkey = [key]
        with tm.assert_produces_warning(warn, match="incompatible dtype"):
            self.check_indexer(obj, ilkey, expected, val, indexer_sli, is_inplace)

        indkey = np.array(ilkey)
        with tm.assert_produces_warning(warn, match="incompatible dtype"):
            self.check_indexer(obj, indkey, expected, val, indexer_sli, is_inplace)

        genkey = (x for x in [key])
        with tm.assert_produces_warning(warn, match="incompatible dtype"):
            self.check_indexer(obj, genkey, expected, val, indexer_sli, is_inplace)

    def test_slice_key(self, obj, key, expected, warn, val, indexer_sli, is_inplace):
        if not isinstance(key, slice):
            pytest.skip("Not relevant for slice key")

        if indexer_sli is not tm.loc:
            # Note: no .loc because that handles slice edges differently
            with tm.assert_produces_warning(warn, match="incompatible dtype"):
                self.check_indexer(obj, key, expected, val, indexer_sli, is_inplace)

        ilkey = list(range(len(obj)))[key]
        with tm.assert_produces_warning(warn, match="incompatible dtype"):
            self.check_indexer(obj, ilkey, expected, val, indexer_sli, is_inplace)

        indkey = np.array(ilkey)
        with tm.assert_produces_warning(warn, match="incompatible dtype"):
            self.check_indexer(obj, indkey, expected, val, indexer_sli, is_inplace)

        genkey = (x for x in indkey)
        with tm.assert_produces_warning(warn, match="incompatible dtype"):
            self.check_indexer(obj, genkey, expected, val, indexer_sli, is_inplace)

    def test_mask_key(self, obj, key, expected, warn, val, indexer_sli):
        # setitem with boolean mask
        mask = np.zeros(obj.shape, dtype=bool)
        mask[key] = True

        obj = obj.copy()

        if is_list_like(val) and len(val) < mask.sum():
            msg = "boolean index did not match indexed array along dimension"
            with pytest.raises(IndexError, match=msg):
                indexer_sli(obj)[mask] = val
            return

        with tm.assert_produces_warning(warn, match="incompatible dtype"):
            indexer_sli(obj)[mask] = val
        tm.assert_series_equal(obj, expected)

    def test_series_where(self, obj, key, expected, warn, val, is_inplace):
        mask = np.zeros(obj.shape, dtype=bool)
        mask[key] = True

        if is_list_like(val) and len(val) < len(obj):
            # Series.where is not valid here
            msg = "operands could not be broadcast together with shapes"
            with pytest.raises(ValueError, match=msg):
                obj.where(~mask, val)
            return

        orig = obj
        obj = obj.copy()
        arr = obj._values

        res = obj.where(~mask, val)

        if val is NA and res.dtype == object:
            expected = expected.fillna(NA)
        elif val is None and res.dtype == object:
            assert expected.dtype == object
            expected = expected.copy()
            expected[expected.isna()] = None
        tm.assert_series_equal(res, expected)

        self._check_inplace(is_inplace, orig, arr, obj)

    def test_index_where(self, obj, key, expected, warn, val):
        mask = np.zeros(obj.shape, dtype=bool)
        mask[key] = True

        res = Index(obj, dtype=obj.dtype).where(~mask, val)
        expected_idx = Index(expected, dtype=expected.dtype)
        tm.assert_index_equal(res, expected_idx)

    def test_index_putmask(self, obj, key, expected, warn, val):
        mask = np.zeros(obj.shape, dtype=bool)
        mask[key] = True

        res = Index(obj, dtype=obj.dtype).putmask(mask, val)
        tm.assert_index_equal(res, Index(expected, dtype=expected.dtype))


@pytest.mark.parametrize(
    "obj,expected,key,warn",
    [
        pytest.param(
            # GH#45568 setting a valid NA value into IntervalDtype[int] should
            #  cast to IntervalDtype[float]
            Series(interval_range(1, 5)),
            Series(
                [Interval(1, 2), np.nan, Interval(3, 4), Interval(4, 5)],
                dtype="interval[float64]",
            ),
            1,
            FutureWarning,
            id="interval_int_na_value",
        ),
        pytest.param(
            # these induce dtype changes
            Series([2, 3, 4, 5, 6, 7, 8, 9, 10]),
            Series([np.nan, 3, np.nan, 5, np.nan, 7, np.nan, 9, np.nan]),
            slice(None, None, 2),
            None,
            id="int_series_slice_key_step",
        ),
        pytest.param(
            Series([True, True, False, False]),
            Series([np.nan, True, np.nan, False], dtype=object),
            slice(None, None, 2),
            FutureWarning,
            id="bool_series_slice_key_step",
        ),
        pytest.param(
            # these induce dtype changes
            Series(np.arange(10)),
            Series([np.nan, np.nan, np.nan, np.nan, np.nan, 5, 6, 7, 8, 9]),
            slice(None, 5),
            None,
            id="int_series_slice_key",
        ),
        pytest.param(
            # changes dtype GH#4463
            Series([1, 2, 3]),
            Series([np.nan, 2, 3]),
            0,
            None,
            id="int_series_int_key",
        ),
        pytest.param(
            # changes dtype GH#4463
            Series([False]),
            Series([np.nan], dtype=object),
            # TODO: maybe go to float64 since we are changing the _whole_ Series?
            0,
            FutureWarning,
            id="bool_series_int_key_change_all",
        ),
        pytest.param(
            # changes dtype GH#4463
            Series([False, True]),
            Series([np.nan, True], dtype=object),
            0,
            FutureWarning,
            id="bool_series_int_key",
        ),
    ],
)
class TestSetitemCastingEquivalents(SetitemCastingEquivalents):
    @pytest.fixture(params=[np.nan, np.float64("NaN"), None, NA])
    def val(self, request):
        """
        NA values that should generally be valid_na for *all* dtypes.

        Include both python float NaN and np.float64; only np.float64 has a
        `dtype` attribute.
        """
        return request.param


class TestSetitemTimedelta64IntoNumeric(SetitemCastingEquivalents):
    # timedelta64 should not be treated as integers when setting into
    #  numeric Series

    @pytest.fixture
    def val(self):
        td = np.timedelta64(4, "ns")
        return td
        # TODO: could also try np.full((1,), td)

    @pytest.fixture(params=[complex, int, float])
    def dtype(self, request):
        return request.param

    @pytest.fixture
    def obj(self, dtype):
        arr = np.arange(5).astype(dtype)
        ser = Series(arr)
        return ser

    @pytest.fixture
    def expected(self, dtype):
        arr = np.arange(5).astype(dtype)
        ser = Series(arr)
        ser = ser.astype(object)
        ser.iloc[0] = np.timedelta64(4, "ns")
        return ser

    @pytest.fixture
    def key(self):
        return 0

    @pytest.fixture
    def warn(self):
        return FutureWarning


class TestSetitemDT64IntoInt(SetitemCastingEquivalents):
    # GH#39619 dont cast dt64 to int when doing this setitem

    @pytest.fixture(params=["M8[ns]", "m8[ns]"])
    def dtype(self, request):
        return request.param

    @pytest.fixture
    def scalar(self, dtype):
        val = np.datetime64("2021-01-18 13:25:00", "ns")
        if dtype == "m8[ns]":
            val = val - val
        return val

    @pytest.fixture
    def expected(self, scalar):
        expected = Series([scalar, scalar, 3], dtype=object)
        assert isinstance(expected[0], type(scalar))
        return expected

    @pytest.fixture
    def obj(self):
        return Series([1, 2, 3])

    @pytest.fixture
    def key(self):
        return slice(None, -1)

    @pytest.fixture(params=[None, list, np.array])
    def val(self, scalar, request):
        box = request.param
        if box is None:
            return scalar
        return box([scalar, scalar])

    @pytest.fixture
    def warn(self):
        return FutureWarning


class TestSetitemNAPeriodDtype(SetitemCastingEquivalents):
    # Setting compatible NA values into Series with PeriodDtype

    @pytest.fixture
    def expected(self, key):
        exp = Series(period_range("2000-01-01", periods=10, freq="D"))
        exp._values.view("i8")[key] = NaT._value
        assert exp[key] is NaT or all(x is NaT for x in exp[key])
        return exp

    @pytest.fixture
    def obj(self):
        return Series(period_range("2000-01-01", periods=10, freq="D"))

    @pytest.fixture(params=[3, slice(3, 5)])
    def key(self, request):
        return request.param

    @pytest.fixture(params=[None, np.nan])
    def val(self, request):
        return request.param

    @pytest.fixture
    def warn(self):
        return None


class TestSetitemNADatetimeLikeDtype(SetitemCastingEquivalents):
    # some nat-like values should be cast to datetime64/timedelta64 when
    #  inserting into a datetime64/timedelta64 series.  Others should coerce
    #  to object and retain their dtypes.
    # GH#18586 for td64 and boolean mask case

    @pytest.fixture(
        params=["m8[ns]", "M8[ns]", "datetime64[ns, UTC]", "datetime64[ns, US/Central]"]
    )
    def dtype(self, request):
        return request.param

    @pytest.fixture
    def obj(self, dtype):
        i8vals = date_range("2016-01-01", periods=3).asi8
        idx = Index(i8vals, dtype=dtype)
        assert idx.dtype == dtype
        return Series(idx)

    @pytest.fixture(
        params=[
            None,
            np.nan,
            NaT,
            np.timedelta64("NaT", "ns"),
            np.datetime64("NaT", "ns"),
        ]
    )
    def val(self, request):
        return request.param

    @pytest.fixture
    def is_inplace(self, val, obj):
        # td64   -> cast to object iff val is datetime64("NaT")
        # dt64   -> cast to object iff val is timedelta64("NaT")
        # dt64tz -> cast to object with anything _but_ NaT
        return val is NaT or val is None or val is np.nan or obj.dtype == val.dtype

    @pytest.fixture
    def expected(self, obj, val, is_inplace):
        dtype = obj.dtype if is_inplace else object
        expected = Series([val] + list(obj[1:]), dtype=dtype)
        return expected

    @pytest.fixture
    def key(self):
        return 0

    @pytest.fixture
    def warn(self, is_inplace):
        return None if is_inplace else FutureWarning


class TestSetitemMismatchedTZCastsToObject(SetitemCastingEquivalents):
    # GH#24024
    @pytest.fixture
    def obj(self):
        return Series(date_range("2000", periods=2, tz="US/Central"))

    @pytest.fixture
    def val(self):
        return Timestamp("2000", tz="US/Eastern")

    @pytest.fixture
    def key(self):
        return 0

    @pytest.fixture
    def expected(self, obj, val):
        # pre-2.0 this would cast to object, in 2.0 we cast the val to
        #  the target tz
        expected = Series(
            [
                val.tz_convert("US/Central"),
                Timestamp("2000-01-02 00:00:00-06:00", tz="US/Central"),
            ],
            dtype=obj.dtype,
        )
        return expected

    @pytest.fixture
    def warn(self):
        return None


@pytest.mark.parametrize(
    "obj,expected,warn",
    [
        # For numeric series, we should coerce to NaN.
        (Series([1, 2, 3]), Series([np.nan, 2, 3]), None),
        (Series([1.0, 2.0, 3.0]), Series([np.nan, 2.0, 3.0]), None),
        # For datetime series, we should coerce to NaT.
        (
            Series([datetime(2000, 1, 1), datetime(2000, 1, 2), datetime(2000, 1, 3)]),
            Series([NaT, datetime(2000, 1, 2), datetime(2000, 1, 3)]),
            None,
        ),
        # For objects, we should preserve the None value.
        (Series(["foo", "bar", "baz"]), Series([None, "bar", "baz"]), None),
    ],
)
class TestSeriesNoneCoercion(SetitemCastingEquivalents):
    @pytest.fixture
    def key(self):
        return 0

    @pytest.fixture
    def val(self):
        return None


class TestSetitemFloatIntervalWithIntIntervalValues(SetitemCastingEquivalents):
    # GH#44201 Cast to shared IntervalDtype rather than object

    def test_setitem_example(self):
        # Just a case here to make obvious what this test class is aimed at
        idx = IntervalIndex.from_breaks(range(4))
        obj = Series(idx)
        val = Interval(0.5, 1.5)

        with tm.assert_produces_warning(
            FutureWarning, match="Setting an item of incompatible dtype"
        ):
            obj[0] = val
        assert obj.dtype == "Interval[float64, right]"

    @pytest.fixture
    def obj(self):
        idx = IntervalIndex.from_breaks(range(4))
        return Series(idx)

    @pytest.fixture
    def val(self):
        return Interval(0.5, 1.5)

    @pytest.fixture
    def key(self):
        return 0

    @pytest.fixture
    def expected(self, obj, val):
        data = [val] + list(obj[1:])
        idx = IntervalIndex(data, dtype="Interval[float64]")
        return Series(idx)

    @pytest.fixture
    def warn(self):
        return FutureWarning


class TestSetitemRangeIntoIntegerSeries(SetitemCastingEquivalents):
    # GH#44261 Setting a range with sufficiently-small integers into
    #  small-itemsize integer dtypes should not need to upcast

    @pytest.fixture
    def obj(self, any_int_numpy_dtype):
        dtype = np.dtype(any_int_numpy_dtype)
        ser = Series(range(5), dtype=dtype)
        return ser

    @pytest.fixture
    def val(self):
        return range(2, 4)

    @pytest.fixture
    def key(self):
        return slice(0, 2)

    @pytest.fixture
    def expected(self, any_int_numpy_dtype):
        dtype = np.dtype(any_int_numpy_dtype)
        exp = Series([2, 3, 2, 3, 4], dtype=dtype)
        return exp

    @pytest.fixture
    def warn(self):
        return None


@pytest.mark.parametrize(
    "val, warn",
    [
        (np.array([2.0, 3.0]), None),
        (np.array([2.5, 3.5]), FutureWarning),
        (
            np.array([2**65, 2**65 + 1], dtype=np.float64),
            FutureWarning,
        ),  # all ints, but can't cast
    ],
)
class TestSetitemFloatNDarrayIntoIntegerSeries(SetitemCastingEquivalents):
    @pytest.fixture
    def obj(self):
        return Series(range(5), dtype=np.int64)

    @pytest.fixture
    def key(self):
        return slice(0, 2)

    @pytest.fixture
    def expected(self, val):
        if val[0] == 2:
            # NB: this condition is based on currently-hardcoded "val" cases
            dtype = np.int64
        else:
            dtype = np.float64
        res_values = np.array(range(5), dtype=dtype)
        res_values[:2] = val
        return Series(res_values)


@pytest.mark.parametrize("val", [512, np.int16(512)])
class TestSetitemIntoIntegerSeriesNeedsUpcast(SetitemCastingEquivalents):
    @pytest.fixture
    def obj(self):
        return Series([1, 2, 3], dtype=np.int8)

    @pytest.fixture
    def key(self):
        return 1

    @pytest.fixture
    def expected(self):
        return Series([1, 512, 3], dtype=np.int16)

    @pytest.fixture
    def warn(self):
        return FutureWarning


@pytest.mark.parametrize("val", [2**33 + 1.0, 2**33 + 1.1, 2**62])
class TestSmallIntegerSetitemUpcast(SetitemCastingEquivalents):
    # https://github.com/pandas-dev/pandas/issues/39584#issuecomment-941212124
    @pytest.fixture
    def obj(self):
        return Series([1, 2, 3], dtype="i4")

    @pytest.fixture
    def key(self):
        return 0

    @pytest.fixture
    def expected(self, val):
        if val % 1 != 0:
            dtype = "f8"
        else:
            dtype = "i8"
        return Series([val, 2, 3], dtype=dtype)

    @pytest.fixture
    def warn(self):
        return FutureWarning


class CoercionTest(SetitemCastingEquivalents):
    # Tests ported from tests.indexing.test_coercion

    @pytest.fixture
    def key(self):
        return 1

    @pytest.fixture
    def expected(self, obj, key, val, exp_dtype):
        vals = list(obj)
        vals[key] = val
        return Series(vals, dtype=exp_dtype)


@pytest.mark.parametrize(
    "val,exp_dtype,warn",
    [(np.int32(1), np.int8, None), (np.int16(2**9), np.int16, FutureWarning)],
)
class TestCoercionInt8(CoercionTest):
    # previously test_setitem_series_int8 in tests.indexing.test_coercion
    @pytest.fixture
    def obj(self):
        return Series([1, 2, 3, 4], dtype=np.int8)


@pytest.mark.parametrize("val", [1, 1.1, 1 + 1j, True])
@pytest.mark.parametrize("exp_dtype", [object])
class TestCoercionObject(CoercionTest):
    # previously test_setitem_series_object in tests.indexing.test_coercion
    @pytest.fixture
    def obj(self):
        return Series(["a", "b", "c", "d"], dtype=object)

    @pytest.fixture
    def warn(self):
        return None


@pytest.mark.parametrize(
    "val,exp_dtype,warn",
    [
        (1, np.complex128, None),
        (1.1, np.complex128, None),
        (1 + 1j, np.complex128, None),
        (True, object, FutureWarning),
    ],
)
class TestCoercionComplex(CoercionTest):
    # previously test_setitem_series_complex128 in tests.indexing.test_coercion
    @pytest.fixture
    def obj(self):
        return Series([1 + 1j, 2 + 2j, 3 + 3j, 4 + 4j])


@pytest.mark.parametrize(
    "val,exp_dtype,warn",
    [
        (1, object, FutureWarning),
        ("3", object, FutureWarning),
        (3, object, FutureWarning),
        (1.1, object, FutureWarning),
        (1 + 1j, object, FutureWarning),
        (True, bool, None),
    ],
)
class TestCoercionBool(CoercionTest):
    # previously test_setitem_series_bool in tests.indexing.test_coercion
    @pytest.fixture
    def obj(self):
        return Series([True, False, True, False], dtype=bool)


@pytest.mark.parametrize(
    "val,exp_dtype,warn",
    [
        (1, np.int64, None),
        (1.1, np.float64, FutureWarning),
        (1 + 1j, np.complex128, FutureWarning),
        (True, object, FutureWarning),
    ],
)
class TestCoercionInt64(CoercionTest):
    # previously test_setitem_series_int64 in tests.indexing.test_coercion
    @pytest.fixture
    def obj(self):
        return Series([1, 2, 3, 4])


@pytest.mark.parametrize(
    "val,exp_dtype,warn",
    [
        (1, np.float64, None),
        (1.1, np.float64, None),
        (1 + 1j, np.complex128, FutureWarning),
        (True, object, FutureWarning),
    ],
)
class TestCoercionFloat64(CoercionTest):
    # previously test_setitem_series_float64 in tests.indexing.test_coercion
    @pytest.fixture
    def obj(self):
        return Series([1.1, 2.2, 3.3, 4.4])


@pytest.mark.parametrize(
    "val,exp_dtype,warn",
    [
        (1, np.float32, None),
        pytest.param(
            1.1,
            np.float32,
            None,
            marks=pytest.mark.xfail(
                (
                    not np_version_gte1p24
                    or (
                        np_version_gte1p24
                        and not np_version_gt2
                        and os.environ.get("NPY_PROMOTION_STATE", "legacy") != "weak"
                    )
                ),
                reason="np.float32(1.1) ends up as 1.100000023841858, so "
                "np_can_hold_element raises and we cast to float64",
            ),
        ),
        (1 + 1j, np.complex128, FutureWarning),
        (True, object, FutureWarning),
        (np.uint8(2), np.float32, None),
        (np.uint32(2), np.float32, None),
        # float32 cannot hold np.iinfo(np.uint32).max exactly
        # (closest it can hold is 4294967300.0 which off by 5.0), so
        # we cast to float64
        (np.uint32(np.iinfo(np.uint32).max), np.float64, FutureWarning),
        (np.uint64(2), np.float32, None),
        (np.int64(2), np.float32, None),
    ],
)
class TestCoercionFloat32(CoercionTest):
    @pytest.fixture
    def obj(self):
        return Series([1.1, 2.2, 3.3, 4.4], dtype=np.float32)

    def test_slice_key(self, obj, key, expected, warn, val, indexer_sli, is_inplace):
        super().test_slice_key(obj, key, expected, warn, val, indexer_sli, is_inplace)

        if isinstance(val, float):
            # the xfail would xpass bc test_slice_key short-circuits
            raise AssertionError("xfail not relevant for this test.")


@pytest.mark.parametrize(
    "val,exp_dtype,warn",
    [
        (Timestamp("2012-01-01"), "datetime64[ns]", None),
        (1, object, FutureWarning),
        ("x", object, FutureWarning),
    ],
)
class TestCoercionDatetime64(CoercionTest):
    # previously test_setitem_series_datetime64 in tests.indexing.test_coercion

    @pytest.fixture
    def obj(self):
        return Series(date_range("2011-01-01", freq="D", periods=4))

    @pytest.fixture
    def warn(self):
        return None


@pytest.mark.parametrize(
    "val,exp_dtype,warn",
    [
        (Timestamp("2012-01-01", tz="US/Eastern"), "datetime64[ns, US/Eastern]", None),
        # pre-2.0, a mis-matched tz would end up casting to object
        (Timestamp("2012-01-01", tz="US/Pacific"), "datetime64[ns, US/Eastern]", None),
        (Timestamp("2012-01-01"), object, FutureWarning),
        (1, object, FutureWarning),
    ],
)
class TestCoercionDatetime64TZ(CoercionTest):
    # previously test_setitem_series_datetime64tz in tests.indexing.test_coercion
    @pytest.fixture
    def obj(self):
        tz = "US/Eastern"
        return Series(date_range("2011-01-01", freq="D", periods=4, tz=tz))

    @pytest.fixture
    def warn(self):
        return None


@pytest.mark.parametrize(
    "val,exp_dtype,warn",
    [
        (Timedelta("12 day"), "timedelta64[ns]", None),
        (1, object, FutureWarning),
        ("x", object, FutureWarning),
    ],
)
class TestCoercionTimedelta64(CoercionTest):
    # previously test_setitem_series_timedelta64 in tests.indexing.test_coercion
    @pytest.fixture
    def obj(self):
        return Series(timedelta_range("1 day", periods=4))

    @pytest.fixture
    def warn(self):
        return None


@pytest.mark.parametrize(
    "val", ["foo", Period("2016", freq="Y"), Interval(1, 2, closed="both")]
)
@pytest.mark.parametrize("exp_dtype", [object])
class TestPeriodIntervalCoercion(CoercionTest):
    # GH#45768
    @pytest.fixture(
        params=[
            period_range("2016-01-01", periods=3, freq="D"),
            interval_range(1, 5),
        ]
    )
    def obj(self, request):
        return Series(request.param)

    @pytest.fixture
    def warn(self):
        return FutureWarning


def test_20643():
    # closed by GH#45121
    orig = Series([0, 1, 2], index=["a", "b", "c"])

    expected = Series([0, 2.7, 2], index=["a", "b", "c"])

    ser = orig.copy()
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        ser.at["b"] = 2.7
    tm.assert_series_equal(ser, expected)

    ser = orig.copy()
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        ser.loc["b"] = 2.7
    tm.assert_series_equal(ser, expected)

    ser = orig.copy()
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        ser["b"] = 2.7
    tm.assert_series_equal(ser, expected)

    ser = orig.copy()
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        ser.iat[1] = 2.7
    tm.assert_series_equal(ser, expected)

    ser = orig.copy()
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        ser.iloc[1] = 2.7
    tm.assert_series_equal(ser, expected)

    orig_df = orig.to_frame("A")
    expected_df = expected.to_frame("A")

    df = orig_df.copy()
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        df.at["b", "A"] = 2.7
    tm.assert_frame_equal(df, expected_df)

    df = orig_df.copy()
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        df.loc["b", "A"] = 2.7
    tm.assert_frame_equal(df, expected_df)

    df = orig_df.copy()
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        df.iloc[1, 0] = 2.7
    tm.assert_frame_equal(df, expected_df)

    df = orig_df.copy()
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        df.iat[1, 0] = 2.7
    tm.assert_frame_equal(df, expected_df)


def test_20643_comment():
    # https://github.com/pandas-dev/pandas/issues/20643#issuecomment-431244590
    # fixed sometime prior to GH#45121
    orig = Series([0, 1, 2], index=["a", "b", "c"])
    expected = Series([np.nan, 1, 2], index=["a", "b", "c"])

    ser = orig.copy()
    ser.iat[0] = None
    tm.assert_series_equal(ser, expected)

    ser = orig.copy()
    ser.iloc[0] = None
    tm.assert_series_equal(ser, expected)


def test_15413():
    # fixed by GH#45121
    ser = Series([1, 2, 3])

    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        ser[ser == 2] += 0.5
    expected = Series([1, 2.5, 3])
    tm.assert_series_equal(ser, expected)

    ser = Series([1, 2, 3])
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        ser[1] += 0.5
    tm.assert_series_equal(ser, expected)

    ser = Series([1, 2, 3])
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        ser.loc[1] += 0.5
    tm.assert_series_equal(ser, expected)

    ser = Series([1, 2, 3])
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        ser.iloc[1] += 0.5
    tm.assert_series_equal(ser, expected)

    ser = Series([1, 2, 3])
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        ser.iat[1] += 0.5
    tm.assert_series_equal(ser, expected)

    ser = Series([1, 2, 3])
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        ser.at[1] += 0.5
    tm.assert_series_equal(ser, expected)


def test_32878_int_itemsize():
    # Fixed by GH#45121
    arr = np.arange(5).astype("i4")
    ser = Series(arr)
    val = np.int64(np.iinfo(np.int64).max)
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        ser[0] = val
    expected = Series([val, 1, 2, 3, 4], dtype=np.int64)
    tm.assert_series_equal(ser, expected)


def test_32878_complex_itemsize():
    arr = np.arange(5).astype("c8")
    ser = Series(arr)
    val = np.finfo(np.float64).max
    val = val.astype("c16")

    # GH#32878 used to coerce val to inf+0.000000e+00j
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        ser[0] = val
    assert ser[0] == val
    expected = Series([val, 1, 2, 3, 4], dtype="c16")
    tm.assert_series_equal(ser, expected)


def test_37692(indexer_al):
    # GH#37692
    ser = Series([1, 2, 3], index=["a", "b", "c"])
    with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
        indexer_al(ser)["b"] = "test"
    expected = Series([1, "test", 3], index=["a", "b", "c"], dtype=object)
    tm.assert_series_equal(ser, expected)


def test_setitem_bool_int_float_consistency(indexer_sli):
    # GH#21513
    # bool-with-int and bool-with-float both upcast to object
    #  int-with-float and float-with-int are both non-casting so long
    #  as the setitem can be done losslessly
    for dtype in [np.float64, np.int64]:
        ser = Series(0, index=range(3), dtype=dtype)
        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            indexer_sli(ser)[0] = True
        assert ser.dtype == object

        ser = Series(0, index=range(3), dtype=bool)
        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            ser[0] = dtype(1)
        assert ser.dtype == object

    # 1.0 can be held losslessly, so no casting
    ser = Series(0, index=range(3), dtype=np.int64)
    indexer_sli(ser)[0] = np.float64(1.0)
    assert ser.dtype == np.int64

    # 1 can be held losslessly, so no casting
    ser = Series(0, index=range(3), dtype=np.float64)
    indexer_sli(ser)[0] = np.int64(1)


def test_setitem_positional_with_casting():
    # GH#45070 case where in __setitem__ we get a KeyError, then when
    #  we fallback we *also* get a ValueError if we try to set inplace.
    ser = Series([1, 2, 3], index=["a", "b", "c"])

    warn_msg = "Series.__setitem__ treating keys as positions is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=warn_msg):
        ser[0] = "X"
    expected = Series(["X", 2, 3], index=["a", "b", "c"], dtype=object)
    tm.assert_series_equal(ser, expected)


def test_setitem_positional_float_into_int_coerces():
    # Case where we hit a KeyError and then trying to set in-place incorrectly
    #  casts a float to an int
    ser = Series([1, 2, 3], index=["a", "b", "c"])

    warn_msg = "Series.__setitem__ treating keys as positions is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=warn_msg):
        ser[0] = 1.5
    expected = Series([1.5, 2, 3], index=["a", "b", "c"])
    tm.assert_series_equal(ser, expected)


def test_setitem_int_not_positional():
    # GH#42215 deprecated falling back to positional on __setitem__ with an
    #  int not contained in the index; enforced in 2.0
    ser = Series([1, 2, 3, 4], index=[1.1, 2.1, 3.0, 4.1])
    assert not ser.index._should_fallback_to_positional
    # assert not ser.index.astype(object)._should_fallback_to_positional

    # 3.0 is in our index, so post-enforcement behavior is unchanged
    ser[3] = 10
    expected = Series([1, 2, 10, 4], index=ser.index)
    tm.assert_series_equal(ser, expected)

    # pre-enforcement `ser[5] = 5` raised IndexError
    ser[5] = 5
    expected = Series([1, 2, 10, 4, 5], index=[1.1, 2.1, 3.0, 4.1, 5.0])
    tm.assert_series_equal(ser, expected)

    ii = IntervalIndex.from_breaks(range(10))[::2]
    ser2 = Series(range(len(ii)), index=ii)
    exp_index = ii.astype(object).append(Index([4]))
    expected2 = Series([0, 1, 2, 3, 4, 9], index=exp_index)
    # pre-enforcement `ser2[4] = 9` interpreted 4 as positional
    ser2[4] = 9
    tm.assert_series_equal(ser2, expected2)

    mi = MultiIndex.from_product([ser.index, ["A", "B"]])
    ser3 = Series(range(len(mi)), index=mi)
    expected3 = ser3.copy()
    expected3.loc[4] = 99
    # pre-enforcement `ser3[4] = 99` interpreted 4 as positional
    ser3[4] = 99
    tm.assert_series_equal(ser3, expected3)


def test_setitem_with_bool_indexer():
    # GH#42530

    df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    result = df.pop("b").copy()
    result[[True, False, False]] = 9
    expected = Series(data=[9, 5, 6], name="b")
    tm.assert_series_equal(result, expected)

    df.loc[[True, False, False], "a"] = 10
    expected = DataFrame({"a": [10, 2, 3]})
    tm.assert_frame_equal(df, expected)


@pytest.mark.parametrize("size", range(2, 6))
@pytest.mark.parametrize(
    "mask", [[True, False, False, False, False], [True, False], [False]]
)
@pytest.mark.parametrize(
    "item", [2.0, np.nan, np.finfo(float).max, np.finfo(float).min]
)
# Test numpy arrays, lists and tuples as the input to be
# broadcast
@pytest.mark.parametrize(
    "box", [lambda x: np.array([x]), lambda x: [x], lambda x: (x,)]
)
def test_setitem_bool_indexer_dont_broadcast_length1_values(size, mask, item, box):
    # GH#44265
    # see also tests.series.indexing.test_where.test_broadcast

    selection = np.resize(mask, size)

    data = np.arange(size, dtype=float)

    ser = Series(data)

    if selection.sum() != 1:
        msg = (
            "cannot set using a list-like indexer with a different "
            "length than the value"
        )
        with pytest.raises(ValueError, match=msg):
            # GH#44265
            ser[selection] = box(item)
    else:
        # In this corner case setting is equivalent to setting with the unboxed
        #  item
        ser[selection] = box(item)

        expected = Series(np.arange(size, dtype=float))
        expected[selection] = item
        tm.assert_series_equal(ser, expected)


def test_setitem_empty_mask_dont_upcast_dt64():
    dti = date_range("2016-01-01", periods=3)
    ser = Series(dti)
    orig = ser.copy()
    mask = np.zeros(3, dtype=bool)

    ser[mask] = "foo"
    assert ser.dtype == dti.dtype  # no-op -> dont upcast
    tm.assert_series_equal(ser, orig)

    ser.mask(mask, "foo", inplace=True)
    assert ser.dtype == dti.dtype  # no-op -> dont upcast
    tm.assert_series_equal(ser, orig)
