from datetime import timedelta

import numpy as np
import pytest

import pandas as pd
from pandas import (
    Timedelta,
    TimedeltaIndex,
    timedelta_range,
    to_timedelta,
)
import pandas._testing as tm
from pandas.core.arrays.timedeltas import TimedeltaArray


class TestTimedeltaIndex:
    def test_closed_deprecated(self):
        # GH#52628
        msg = "The 'closed' keyword"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            TimedeltaIndex([], closed=True)

    def test_array_of_dt64_nat_raises(self):
        # GH#39462
        nat = np.datetime64("NaT", "ns")
        arr = np.array([nat], dtype=object)

        msg = "Invalid type for timedelta scalar"
        with pytest.raises(TypeError, match=msg):
            TimedeltaIndex(arr)

        with pytest.raises(TypeError, match=msg):
            TimedeltaArray._from_sequence(arr, dtype="m8[ns]")

        with pytest.raises(TypeError, match=msg):
            to_timedelta(arr)

    @pytest.mark.parametrize("unit", ["Y", "y", "M"])
    def test_unit_m_y_raises(self, unit):
        msg = "Units 'M', 'Y', and 'y' are no longer supported"
        depr_msg = "The 'unit' keyword in TimedeltaIndex construction is deprecated"
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=depr_msg):
                TimedeltaIndex([1, 3, 7], unit)

    def test_int64_nocopy(self):
        # GH#23539 check that a copy isn't made when we pass int64 data
        #  and copy=False
        arr = np.arange(10, dtype=np.int64)
        tdi = TimedeltaIndex(arr, copy=False)
        assert tdi._data._ndarray.base is arr

    def test_infer_from_tdi(self):
        # GH#23539
        # fast-path for inferring a frequency if the passed data already
        #  has one
        tdi = timedelta_range("1 second", periods=10**7, freq="1s")

        result = TimedeltaIndex(tdi, freq="infer")
        assert result.freq == tdi.freq

        # check that inferred_freq was not called by checking that the
        #  value has not been cached
        assert "inferred_freq" not in getattr(result, "_cache", {})

    def test_infer_from_tdi_mismatch(self):
        # GH#23539
        # fast-path for invalidating a frequency if the passed data already
        #  has one and it does not match the `freq` input
        tdi = timedelta_range("1 second", periods=100, freq="1s")

        depr_msg = "TimedeltaArray.__init__ is deprecated"
        msg = (
            "Inferred frequency .* from passed values does "
            "not conform to passed frequency"
        )
        with pytest.raises(ValueError, match=msg):
            TimedeltaIndex(tdi, freq="D")

        with pytest.raises(ValueError, match=msg):
            # GH#23789
            with tm.assert_produces_warning(FutureWarning, match=depr_msg):
                TimedeltaArray(tdi, freq="D")

        with pytest.raises(ValueError, match=msg):
            TimedeltaIndex(tdi._data, freq="D")

        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=depr_msg):
                TimedeltaArray(tdi._data, freq="D")

    def test_dt64_data_invalid(self):
        # GH#23539
        # passing tz-aware DatetimeIndex raises, naive or ndarray[datetime64]
        #  raise as of GH#29794
        dti = pd.date_range("2016-01-01", periods=3)

        msg = "cannot be converted to timedelta64"
        with pytest.raises(TypeError, match=msg):
            TimedeltaIndex(dti.tz_localize("Europe/Brussels"))

        with pytest.raises(TypeError, match=msg):
            TimedeltaIndex(dti)

        with pytest.raises(TypeError, match=msg):
            TimedeltaIndex(np.asarray(dti))

    def test_float64_ns_rounded(self):
        # GH#23539 without specifying a unit, floats are regarded as nanos,
        #  and fractional portions are truncated
        tdi = TimedeltaIndex([2.3, 9.7])
        expected = TimedeltaIndex([2, 9])
        tm.assert_index_equal(tdi, expected)

        # integral floats are non-lossy
        tdi = TimedeltaIndex([2.0, 9.0])
        expected = TimedeltaIndex([2, 9])
        tm.assert_index_equal(tdi, expected)

        # NaNs get converted to NaT
        tdi = TimedeltaIndex([2.0, np.nan])
        expected = TimedeltaIndex([Timedelta(nanoseconds=2), pd.NaT])
        tm.assert_index_equal(tdi, expected)

    def test_float64_unit_conversion(self):
        # GH#23539
        tdi = to_timedelta([1.5, 2.25], unit="D")
        expected = TimedeltaIndex([Timedelta(days=1.5), Timedelta(days=2.25)])
        tm.assert_index_equal(tdi, expected)

    def test_construction_base_constructor(self):
        arr = [Timedelta("1 days"), pd.NaT, Timedelta("3 days")]
        tm.assert_index_equal(pd.Index(arr), TimedeltaIndex(arr))
        tm.assert_index_equal(pd.Index(np.array(arr)), TimedeltaIndex(np.array(arr)))

        arr = [np.nan, pd.NaT, Timedelta("1 days")]
        tm.assert_index_equal(pd.Index(arr), TimedeltaIndex(arr))
        tm.assert_index_equal(pd.Index(np.array(arr)), TimedeltaIndex(np.array(arr)))

    @pytest.mark.filterwarnings(
        "ignore:The 'unit' keyword in TimedeltaIndex construction:FutureWarning"
    )
    def test_constructor(self):
        expected = TimedeltaIndex(
            [
                "1 days",
                "1 days 00:00:05",
                "2 days",
                "2 days 00:00:02",
                "0 days 00:00:03",
            ]
        )
        result = TimedeltaIndex(
            [
                "1 days",
                "1 days, 00:00:05",
                np.timedelta64(2, "D"),
                timedelta(days=2, seconds=2),
                pd.offsets.Second(3),
            ]
        )
        tm.assert_index_equal(result, expected)

        expected = TimedeltaIndex(
            ["0 days 00:00:00", "0 days 00:00:01", "0 days 00:00:02"]
        )
        result = TimedeltaIndex(range(3), unit="s")
        tm.assert_index_equal(result, expected)
        expected = TimedeltaIndex(
            ["0 days 00:00:00", "0 days 00:00:05", "0 days 00:00:09"]
        )
        result = TimedeltaIndex([0, 5, 9], unit="s")
        tm.assert_index_equal(result, expected)
        expected = TimedeltaIndex(
            ["0 days 00:00:00.400", "0 days 00:00:00.450", "0 days 00:00:01.200"]
        )
        result = TimedeltaIndex([400, 450, 1200], unit="ms")
        tm.assert_index_equal(result, expected)

    def test_constructor_iso(self):
        # GH #21877
        expected = timedelta_range("1s", periods=9, freq="s")
        durations = [f"P0DT0H0M{i}S" for i in range(1, 10)]
        result = to_timedelta(durations)
        tm.assert_index_equal(result, expected)

    def test_timedelta_range_fractional_period(self):
        msg = "Non-integer 'periods' in pd.date_range, pd.timedelta_range"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rng = timedelta_range("1 days", periods=10.5)
        exp = timedelta_range("1 days", periods=10)
        tm.assert_index_equal(rng, exp)

    def test_constructor_coverage(self):
        msg = "periods must be a number, got foo"
        with pytest.raises(TypeError, match=msg):
            timedelta_range(start="1 days", periods="foo", freq="D")

        msg = (
            r"TimedeltaIndex\(\.\.\.\) must be called with a collection of some kind, "
            "'1 days' was passed"
        )
        with pytest.raises(TypeError, match=msg):
            TimedeltaIndex("1 days")

        # generator expression
        gen = (timedelta(i) for i in range(10))
        result = TimedeltaIndex(gen)
        expected = TimedeltaIndex([timedelta(i) for i in range(10)])
        tm.assert_index_equal(result, expected)

        # NumPy string array
        strings = np.array(["1 days", "2 days", "3 days"])
        result = TimedeltaIndex(strings)
        expected = to_timedelta([1, 2, 3], unit="d")
        tm.assert_index_equal(result, expected)

        from_ints = TimedeltaIndex(expected.asi8)
        tm.assert_index_equal(from_ints, expected)

        # non-conforming freq
        msg = (
            "Inferred frequency None from passed values does not conform to "
            "passed frequency D"
        )
        with pytest.raises(ValueError, match=msg):
            TimedeltaIndex(["1 days", "2 days", "4 days"], freq="D")

        msg = (
            "Of the four parameters: start, end, periods, and freq, exactly "
            "three must be specified"
        )
        with pytest.raises(ValueError, match=msg):
            timedelta_range(periods=10, freq="D")

    def test_constructor_name(self):
        idx = timedelta_range(start="1 days", periods=1, freq="D", name="TEST")
        assert idx.name == "TEST"

        # GH10025
        idx2 = TimedeltaIndex(idx, name="something else")
        assert idx2.name == "something else"

    def test_constructor_no_precision_raises(self):
        # GH-24753, GH-24739

        msg = "with no precision is not allowed"
        with pytest.raises(ValueError, match=msg):
            TimedeltaIndex(["2000"], dtype="timedelta64")

        msg = "The 'timedelta64' dtype has no unit. Please pass in"
        with pytest.raises(ValueError, match=msg):
            pd.Index(["2000"], dtype="timedelta64")

    def test_constructor_wrong_precision_raises(self):
        msg = "Supported timedelta64 resolutions are 's', 'ms', 'us', 'ns'"
        with pytest.raises(ValueError, match=msg):
            TimedeltaIndex(["2000"], dtype="timedelta64[D]")

        # "timedelta64[us]" was unsupported pre-2.0, but now this works.
        tdi = TimedeltaIndex(["2000"], dtype="timedelta64[us]")
        assert tdi.dtype == "m8[us]"

    def test_explicit_none_freq(self):
        # Explicitly passing freq=None is respected
        tdi = timedelta_range(1, periods=5)
        assert tdi.freq is not None

        result = TimedeltaIndex(tdi, freq=None)
        assert result.freq is None

        result = TimedeltaIndex(tdi._data, freq=None)
        assert result.freq is None

        msg = "TimedeltaArray.__init__ is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            tda = TimedeltaArray(tdi, freq=None)
        assert tda.freq is None

    def test_from_categorical(self):
        tdi = timedelta_range(1, periods=5)

        cat = pd.Categorical(tdi)

        result = TimedeltaIndex(cat)
        tm.assert_index_equal(result, tdi)

        ci = pd.CategoricalIndex(tdi)
        result = TimedeltaIndex(ci)
        tm.assert_index_equal(result, tdi)
