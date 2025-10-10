import numpy as np
import pytest

import pandas as pd
from pandas import Series
import pandas._testing as tm


class TestSeriesRound:
    def test_round(self, datetime_series):
        datetime_series.index.name = "index_name"
        result = datetime_series.round(2)
        expected = Series(
            np.round(datetime_series.values, 2), index=datetime_series.index, name="ts"
        )
        tm.assert_series_equal(result, expected)
        assert result.name == datetime_series.name

    def test_round_numpy(self, any_float_dtype):
        # See GH#12600
        ser = Series([1.53, 1.36, 0.06], dtype=any_float_dtype)
        out = np.round(ser, decimals=0)
        expected = Series([2.0, 1.0, 0.0], dtype=any_float_dtype)
        tm.assert_series_equal(out, expected)

        msg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=msg):
            np.round(ser, decimals=0, out=ser)

    def test_round_numpy_with_nan(self, any_float_dtype):
        # See GH#14197
        ser = Series([1.53, np.nan, 0.06], dtype=any_float_dtype)
        with tm.assert_produces_warning(None):
            result = ser.round()
        expected = Series([2.0, np.nan, 0.0], dtype=any_float_dtype)
        tm.assert_series_equal(result, expected)

    def test_round_builtin(self, any_float_dtype):
        ser = Series(
            [1.123, 2.123, 3.123],
            index=range(3),
            dtype=any_float_dtype,
        )
        result = round(ser)
        expected_rounded0 = Series(
            [1.0, 2.0, 3.0], index=range(3), dtype=any_float_dtype
        )
        tm.assert_series_equal(result, expected_rounded0)

        decimals = 2
        expected_rounded = Series(
            [1.12, 2.12, 3.12], index=range(3), dtype=any_float_dtype
        )
        result = round(ser, decimals)
        tm.assert_series_equal(result, expected_rounded)

    @pytest.mark.parametrize("method", ["round", "floor", "ceil"])
    @pytest.mark.parametrize("freq", ["s", "5s", "min", "5min", "h", "5h"])
    def test_round_nat(self, method, freq, unit):
        # GH14940, GH#56158
        ser = Series([pd.NaT], dtype=f"M8[{unit}]")
        expected = Series(pd.NaT, dtype=f"M8[{unit}]")
        round_method = getattr(ser.dt, method)
        result = round_method(freq)
        tm.assert_series_equal(result, expected)

    def test_round_ea_boolean(self):
        # GH#55936
        ser = Series([True, False], dtype="boolean")
        expected = ser.copy()
        result = ser.round(2)
        tm.assert_series_equal(result, expected)
        result.iloc[0] = False
        tm.assert_series_equal(ser, expected)

    def test_round_dtype_object(self):
        # GH#61206
        ser = Series([0.2], dtype="object")
        msg = "Expected numeric dtype, got object instead."
        with pytest.raises(TypeError, match=msg):
            ser.round()
