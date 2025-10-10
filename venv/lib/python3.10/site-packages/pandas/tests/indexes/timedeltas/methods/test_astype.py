from datetime import timedelta

import numpy as np
import pytest

import pandas as pd
from pandas import (
    Index,
    NaT,
    Timedelta,
    TimedeltaIndex,
    timedelta_range,
)
import pandas._testing as tm
from pandas.core.arrays import TimedeltaArray


class TestTimedeltaIndex:
    def test_astype_object(self):
        idx = timedelta_range(start="1 days", periods=4, freq="D", name="idx")
        expected_list = [
            Timedelta("1 days"),
            Timedelta("2 days"),
            Timedelta("3 days"),
            Timedelta("4 days"),
        ]
        result = idx.astype(object)
        expected = Index(expected_list, dtype=object, name="idx")
        tm.assert_index_equal(result, expected)
        assert idx.tolist() == expected_list

    def test_astype_object_with_nat(self):
        idx = TimedeltaIndex(
            [timedelta(days=1), timedelta(days=2), NaT, timedelta(days=4)], name="idx"
        )
        expected_list = [
            Timedelta("1 days"),
            Timedelta("2 days"),
            NaT,
            Timedelta("4 days"),
        ]
        result = idx.astype(object)
        expected = Index(expected_list, dtype=object, name="idx")
        tm.assert_index_equal(result, expected)
        assert idx.tolist() == expected_list

    def test_astype(self, using_infer_string):
        # GH 13149, GH 13209
        idx = TimedeltaIndex([1e14, "NaT", NaT, np.nan], name="idx")

        result = idx.astype(object)
        expected = Index(
            [Timedelta("1 days 03:46:40")] + [NaT] * 3, dtype=object, name="idx"
        )
        tm.assert_index_equal(result, expected)

        result = idx.astype(np.int64)
        expected = Index(
            [100000000000000] + [-9223372036854775808] * 3, dtype=np.int64, name="idx"
        )
        tm.assert_index_equal(result, expected)

        result = idx.astype(str)
        if using_infer_string:
            expected = Index(
                [str(x) if x is not NaT else None for x in idx], name="idx", dtype="str"
            )
        else:
            expected = Index([str(x) for x in idx], name="idx", dtype=object)
        tm.assert_index_equal(result, expected)

        rng = timedelta_range("1 days", periods=10)
        result = rng.astype("i8")
        tm.assert_index_equal(result, Index(rng.asi8))
        tm.assert_numpy_array_equal(rng.asi8, result.values)

    def test_astype_uint(self):
        arr = timedelta_range("1h", periods=2)

        with pytest.raises(TypeError, match=r"Do obj.astype\('int64'\)"):
            arr.astype("uint64")
        with pytest.raises(TypeError, match=r"Do obj.astype\('int64'\)"):
            arr.astype("uint32")

    def test_astype_timedelta64(self):
        # GH 13149, GH 13209
        idx = TimedeltaIndex([1e14, "NaT", NaT, np.nan])

        msg = (
            r"Cannot convert from timedelta64\[ns\] to timedelta64. "
            "Supported resolutions are 's', 'ms', 'us', 'ns'"
        )
        with pytest.raises(ValueError, match=msg):
            idx.astype("timedelta64")

        result = idx.astype("timedelta64[ns]")
        tm.assert_index_equal(result, idx)
        assert result is not idx

        result = idx.astype("timedelta64[ns]", copy=False)
        tm.assert_index_equal(result, idx)
        assert result is idx

    def test_astype_to_td64d_raises(self, index_or_series):
        # We don't support "D" reso
        scalar = Timedelta(days=31)
        td = index_or_series(
            [scalar, scalar, scalar + timedelta(minutes=5, seconds=3), NaT],
            dtype="m8[ns]",
        )
        msg = (
            r"Cannot convert from timedelta64\[ns\] to timedelta64\[D\]. "
            "Supported resolutions are 's', 'ms', 'us', 'ns'"
        )
        with pytest.raises(ValueError, match=msg):
            td.astype("timedelta64[D]")

    def test_astype_ms_to_s(self, index_or_series):
        scalar = Timedelta(days=31)
        td = index_or_series(
            [scalar, scalar, scalar + timedelta(minutes=5, seconds=3), NaT],
            dtype="m8[ns]",
        )

        exp_values = np.asarray(td).astype("m8[s]")
        exp_tda = TimedeltaArray._simple_new(exp_values, dtype=exp_values.dtype)
        expected = index_or_series(exp_tda)
        assert expected.dtype == "m8[s]"
        result = td.astype("timedelta64[s]")
        tm.assert_equal(result, expected)

    def test_astype_freq_conversion(self):
        # pre-2.0 td64 astype converted to float64. now for supported units
        #  (s, ms, us, ns) this converts to the requested dtype.
        # This matches TDA and Series
        tdi = timedelta_range("1 Day", periods=30)

        res = tdi.astype("m8[s]")
        exp_values = np.asarray(tdi).astype("m8[s]")
        exp_tda = TimedeltaArray._simple_new(
            exp_values, dtype=exp_values.dtype, freq=tdi.freq
        )
        expected = Index(exp_tda)
        assert expected.dtype == "m8[s]"
        tm.assert_index_equal(res, expected)

        # check this matches Series and TimedeltaArray
        res = tdi._data.astype("m8[s]")
        tm.assert_equal(res, expected._values)

        res = tdi.to_series().astype("m8[s]")
        tm.assert_equal(res._values, expected._values._with_freq(None))

    @pytest.mark.parametrize("dtype", [float, "datetime64", "datetime64[ns]"])
    def test_astype_raises(self, dtype):
        # GH 13149, GH 13209
        idx = TimedeltaIndex([1e14, "NaT", NaT, np.nan])
        msg = "Cannot cast TimedeltaIndex to dtype"
        with pytest.raises(TypeError, match=msg):
            idx.astype(dtype)

    def test_astype_category(self):
        obj = timedelta_range("1h", periods=2, freq="h")

        result = obj.astype("category")
        expected = pd.CategoricalIndex([Timedelta("1h"), Timedelta("2h")])
        tm.assert_index_equal(result, expected)

        result = obj._data.astype("category")
        expected = expected.values
        tm.assert_categorical_equal(result, expected)

    def test_astype_array_fallback(self):
        obj = timedelta_range("1h", periods=2)
        result = obj.astype(bool)
        expected = Index(np.array([True, True]))
        tm.assert_index_equal(result, expected)

        result = obj._data.astype(bool)
        expected = np.array([True, True])
        tm.assert_numpy_array_equal(result, expected)
