from datetime import timedelta

import numpy as np
import pytest

import pandas as pd
from pandas import Timedelta
import pandas._testing as tm
from pandas.core.arrays import (
    DatetimeArray,
    TimedeltaArray,
)


class TestNonNano:
    @pytest.fixture(params=["s", "ms", "us"])
    def unit(self, request):
        return request.param

    @pytest.fixture
    def tda(self, unit):
        arr = np.arange(5, dtype=np.int64).view(f"m8[{unit}]")
        return TimedeltaArray._simple_new(arr, dtype=arr.dtype)

    def test_non_nano(self, unit):
        arr = np.arange(5, dtype=np.int64).view(f"m8[{unit}]")
        tda = TimedeltaArray._simple_new(arr, dtype=arr.dtype)

        assert tda.dtype == arr.dtype
        assert tda[0].unit == unit

    def test_as_unit_raises(self, tda):
        # GH#50616
        with pytest.raises(ValueError, match="Supported units"):
            tda.as_unit("D")

        tdi = pd.Index(tda)
        with pytest.raises(ValueError, match="Supported units"):
            tdi.as_unit("D")

    @pytest.mark.parametrize("field", TimedeltaArray._field_ops)
    def test_fields(self, tda, field):
        as_nano = tda._ndarray.astype("m8[ns]")
        tda_nano = TimedeltaArray._simple_new(as_nano, dtype=as_nano.dtype)

        result = getattr(tda, field)
        expected = getattr(tda_nano, field)
        tm.assert_numpy_array_equal(result, expected)

    def test_to_pytimedelta(self, tda):
        as_nano = tda._ndarray.astype("m8[ns]")
        tda_nano = TimedeltaArray._simple_new(as_nano, dtype=as_nano.dtype)

        result = tda.to_pytimedelta()
        expected = tda_nano.to_pytimedelta()
        tm.assert_numpy_array_equal(result, expected)

    def test_total_seconds(self, unit, tda):
        as_nano = tda._ndarray.astype("m8[ns]")
        tda_nano = TimedeltaArray._simple_new(as_nano, dtype=as_nano.dtype)

        result = tda.total_seconds()
        expected = tda_nano.total_seconds()
        tm.assert_numpy_array_equal(result, expected)

    def test_timedelta_array_total_seconds(self):
        # GH34290
        expected = Timedelta("2 min").total_seconds()

        result = pd.array([Timedelta("2 min")]).total_seconds()[0]
        assert result == expected

    def test_total_seconds_nanoseconds(self):
        # issue #48521
        start_time = pd.Series(["2145-11-02 06:00:00"]).astype("datetime64[ns]")
        end_time = pd.Series(["2145-11-02 07:06:00"]).astype("datetime64[ns]")
        expected = (end_time - start_time).values / np.timedelta64(1, "s")
        result = (end_time - start_time).dt.total_seconds().values
        assert result == expected

    @pytest.mark.parametrize(
        "nat", [np.datetime64("NaT", "ns"), np.datetime64("NaT", "us")]
    )
    def test_add_nat_datetimelike_scalar(self, nat, tda):
        result = tda + nat
        assert isinstance(result, DatetimeArray)
        assert result._creso == tda._creso
        assert result.isna().all()

        result = nat + tda
        assert isinstance(result, DatetimeArray)
        assert result._creso == tda._creso
        assert result.isna().all()

    def test_add_pdnat(self, tda):
        result = tda + pd.NaT
        assert isinstance(result, TimedeltaArray)
        assert result._creso == tda._creso
        assert result.isna().all()

        result = pd.NaT + tda
        assert isinstance(result, TimedeltaArray)
        assert result._creso == tda._creso
        assert result.isna().all()

    # TODO: 2022-07-11 this is the only test that gets to DTA.tz_convert
    #  or tz_localize with non-nano; implement tests specific to that.
    def test_add_datetimelike_scalar(self, tda, tz_naive_fixture):
        ts = pd.Timestamp("2016-01-01", tz=tz_naive_fixture).as_unit("ns")

        expected = tda.as_unit("ns") + ts
        res = tda + ts
        tm.assert_extension_array_equal(res, expected)
        res = ts + tda
        tm.assert_extension_array_equal(res, expected)

        ts += Timedelta(1)  # case where we can't cast losslessly

        exp_values = tda._ndarray + ts.asm8
        expected = (
            DatetimeArray._simple_new(exp_values, dtype=exp_values.dtype)
            .tz_localize("UTC")
            .tz_convert(ts.tz)
        )

        result = tda + ts
        tm.assert_extension_array_equal(result, expected)

        result = ts + tda
        tm.assert_extension_array_equal(result, expected)

    def test_mul_scalar(self, tda):
        other = 2
        result = tda * other
        expected = TimedeltaArray._simple_new(tda._ndarray * other, dtype=tda.dtype)
        tm.assert_extension_array_equal(result, expected)
        assert result._creso == tda._creso

    def test_mul_listlike(self, tda):
        other = np.arange(len(tda))
        result = tda * other
        expected = TimedeltaArray._simple_new(tda._ndarray * other, dtype=tda.dtype)
        tm.assert_extension_array_equal(result, expected)
        assert result._creso == tda._creso

    def test_mul_listlike_object(self, tda):
        other = np.arange(len(tda))
        result = tda * other.astype(object)
        expected = TimedeltaArray._simple_new(tda._ndarray * other, dtype=tda.dtype)
        tm.assert_extension_array_equal(result, expected)
        assert result._creso == tda._creso

    def test_div_numeric_scalar(self, tda):
        other = 2
        result = tda / other
        expected = TimedeltaArray._simple_new(tda._ndarray / other, dtype=tda.dtype)
        tm.assert_extension_array_equal(result, expected)
        assert result._creso == tda._creso

    def test_div_td_scalar(self, tda):
        other = timedelta(seconds=1)
        result = tda / other
        expected = tda._ndarray / np.timedelta64(1, "s")
        tm.assert_numpy_array_equal(result, expected)

    def test_div_numeric_array(self, tda):
        other = np.arange(len(tda))
        result = tda / other
        expected = TimedeltaArray._simple_new(tda._ndarray / other, dtype=tda.dtype)
        tm.assert_extension_array_equal(result, expected)
        assert result._creso == tda._creso

    def test_div_td_array(self, tda):
        other = tda._ndarray + tda._ndarray[-1]
        result = tda / other
        expected = tda._ndarray / other
        tm.assert_numpy_array_equal(result, expected)

    def test_add_timedeltaarraylike(self, tda):
        tda_nano = tda.astype("m8[ns]")

        expected = tda_nano * 2
        res = tda_nano + tda
        tm.assert_extension_array_equal(res, expected)
        res = tda + tda_nano
        tm.assert_extension_array_equal(res, expected)

        expected = tda_nano * 0
        res = tda - tda_nano
        tm.assert_extension_array_equal(res, expected)

        res = tda_nano - tda
        tm.assert_extension_array_equal(res, expected)


class TestTimedeltaArray:
    @pytest.mark.parametrize("dtype", [int, np.int32, np.int64, "uint32", "uint64"])
    def test_astype_int(self, dtype):
        arr = TimedeltaArray._from_sequence(
            [Timedelta("1h"), Timedelta("2h")], dtype="m8[ns]"
        )

        if np.dtype(dtype) != np.int64:
            with pytest.raises(TypeError, match=r"Do obj.astype\('int64'\)"):
                arr.astype(dtype)
            return

        result = arr.astype(dtype)
        expected = arr._ndarray.view("i8")
        tm.assert_numpy_array_equal(result, expected)

    def test_setitem_clears_freq(self):
        a = pd.timedelta_range("1h", periods=2, freq="h")._data
        a[0] = Timedelta("1h")
        assert a.freq is None

    @pytest.mark.parametrize(
        "obj",
        [
            Timedelta(seconds=1),
            Timedelta(seconds=1).to_timedelta64(),
            Timedelta(seconds=1).to_pytimedelta(),
        ],
    )
    def test_setitem_objects(self, obj):
        # make sure we accept timedelta64 and timedelta in addition to Timedelta
        tdi = pd.timedelta_range("2 Days", periods=4, freq="h")
        arr = tdi._data

        arr[0] = obj
        assert arr[0] == Timedelta(seconds=1)

    @pytest.mark.parametrize(
        "other",
        [
            1,
            np.int64(1),
            1.0,
            np.datetime64("NaT"),
            pd.Timestamp("2021-01-01"),
            "invalid",
            np.arange(10, dtype="i8") * 24 * 3600 * 10**9,
            (np.arange(10) * 24 * 3600 * 10**9).view("datetime64[ns]"),
            pd.Timestamp("2021-01-01").to_period("D"),
        ],
    )
    @pytest.mark.parametrize("index", [True, False])
    def test_searchsorted_invalid_types(self, other, index):
        data = np.arange(10, dtype="i8") * 24 * 3600 * 10**9
        arr = pd.TimedeltaIndex(data, freq="D")._data
        if index:
            arr = pd.Index(arr)

        msg = "|".join(
            [
                "searchsorted requires compatible dtype or scalar",
                "value should be a 'Timedelta', 'NaT', or array of those. Got",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            arr.searchsorted(other)


class TestUnaryOps:
    def test_abs(self):
        vals = np.array([-3600 * 10**9, "NaT", 7200 * 10**9], dtype="m8[ns]")
        arr = TimedeltaArray._from_sequence(vals)

        evals = np.array([3600 * 10**9, "NaT", 7200 * 10**9], dtype="m8[ns]")
        expected = TimedeltaArray._from_sequence(evals)

        result = abs(arr)
        tm.assert_timedelta_array_equal(result, expected)

        result2 = np.abs(arr)
        tm.assert_timedelta_array_equal(result2, expected)

    def test_pos(self):
        vals = np.array([-3600 * 10**9, "NaT", 7200 * 10**9], dtype="m8[ns]")
        arr = TimedeltaArray._from_sequence(vals)

        result = +arr
        tm.assert_timedelta_array_equal(result, arr)
        assert not tm.shares_memory(result, arr)

        result2 = np.positive(arr)
        tm.assert_timedelta_array_equal(result2, arr)
        assert not tm.shares_memory(result2, arr)

    def test_neg(self):
        vals = np.array([-3600 * 10**9, "NaT", 7200 * 10**9], dtype="m8[ns]")
        arr = TimedeltaArray._from_sequence(vals)

        evals = np.array([3600 * 10**9, "NaT", -7200 * 10**9], dtype="m8[ns]")
        expected = TimedeltaArray._from_sequence(evals)

        result = -arr
        tm.assert_timedelta_array_equal(result, expected)

        result2 = np.negative(arr)
        tm.assert_timedelta_array_equal(result2, expected)

    def test_neg_freq(self):
        tdi = pd.timedelta_range("2 Days", periods=4, freq="h")
        arr = tdi._data

        expected = -tdi._data

        result = -arr
        tm.assert_timedelta_array_equal(result, expected)

        result2 = np.negative(arr)
        tm.assert_timedelta_array_equal(result2, expected)
