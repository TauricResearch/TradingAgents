from datetime import (
    time,
    timedelta,
)

import numpy as np
import pytest

from pandas.compat import IS64
from pandas.errors import OutOfBoundsTimedelta

import pandas as pd
from pandas import (
    Series,
    TimedeltaIndex,
    isna,
    to_timedelta,
)
import pandas._testing as tm
from pandas.core.arrays import TimedeltaArray


class TestTimedeltas:
    def test_to_timedelta_dt64_raises(self):
        # Passing datetime64-dtype data to TimedeltaIndex is no longer
        #  supported GH#29794
        msg = r"dtype datetime64\[ns\] cannot be converted to timedelta64\[ns\]"

        ser = Series([pd.NaT])
        with pytest.raises(TypeError, match=msg):
            to_timedelta(ser)
        with pytest.raises(TypeError, match=msg):
            ser.to_frame().apply(to_timedelta)

    @pytest.mark.parametrize("readonly", [True, False])
    def test_to_timedelta_readonly(self, readonly):
        # GH#34857
        arr = np.array([], dtype=object)
        if readonly:
            arr.setflags(write=False)
        result = to_timedelta(arr)
        expected = to_timedelta([])
        tm.assert_index_equal(result, expected)

    def test_to_timedelta_null(self):
        result = to_timedelta(["", ""])
        assert isna(result).all()

    def test_to_timedelta_same_np_timedelta64(self):
        # pass thru
        result = to_timedelta(np.array([np.timedelta64(1, "s")]))
        expected = pd.Index(np.array([np.timedelta64(1, "s")]))
        tm.assert_index_equal(result, expected)

    def test_to_timedelta_series(self):
        # Series
        expected = Series([timedelta(days=1), timedelta(days=1, seconds=1)])
        result = to_timedelta(Series(["1d", "1days 00:00:01"]))
        tm.assert_series_equal(result, expected)

    def test_to_timedelta_units(self):
        # with units
        result = TimedeltaIndex(
            [np.timedelta64(0, "ns"), np.timedelta64(10, "s").astype("m8[ns]")]
        )
        expected = to_timedelta([0, 10], unit="s")
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "dtype, unit",
        [
            ["int64", "s"],
            ["int64", "m"],
            ["int64", "h"],
            ["timedelta64[s]", "s"],
            ["timedelta64[D]", "D"],
        ],
    )
    def test_to_timedelta_units_dtypes(self, dtype, unit):
        # arrays of various dtypes
        arr = np.array([1] * 5, dtype=dtype)
        result = to_timedelta(arr, unit=unit)
        exp_dtype = "m8[ns]" if dtype == "int64" else "m8[s]"
        expected = TimedeltaIndex([np.timedelta64(1, unit)] * 5, dtype=exp_dtype)
        tm.assert_index_equal(result, expected)

    def test_to_timedelta_oob_non_nano(self):
        arr = np.array([pd.NaT._value + 1], dtype="timedelta64[m]")

        msg = (
            "Cannot convert -9223372036854775807 minutes to "
            r"timedelta64\[s\] without overflow"
        )
        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            to_timedelta(arr)

        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            TimedeltaIndex(arr)

        with pytest.raises(OutOfBoundsTimedelta, match=msg):
            TimedeltaArray._from_sequence(arr, dtype="m8[s]")

    @pytest.mark.parametrize(
        "arg", [np.arange(10).reshape(2, 5), pd.DataFrame(np.arange(10).reshape(2, 5))]
    )
    @pytest.mark.parametrize("errors", ["ignore", "raise", "coerce"])
    @pytest.mark.filterwarnings("ignore:errors='ignore' is deprecated:FutureWarning")
    def test_to_timedelta_dataframe(self, arg, errors):
        # GH 11776
        with pytest.raises(TypeError, match="1-d array"):
            to_timedelta(arg, errors=errors)

    def test_to_timedelta_invalid_errors(self):
        # bad value for errors parameter
        msg = "errors must be one of"
        with pytest.raises(ValueError, match=msg):
            to_timedelta(["foo"], errors="never")

    @pytest.mark.parametrize("arg", [[1, 2], 1])
    def test_to_timedelta_invalid_unit(self, arg):
        # these will error
        msg = "invalid unit abbreviation: foo"
        with pytest.raises(ValueError, match=msg):
            to_timedelta(arg, unit="foo")

    def test_to_timedelta_time(self):
        # time not supported ATM
        msg = (
            "Value must be Timedelta, string, integer, float, timedelta or convertible"
        )
        with pytest.raises(ValueError, match=msg):
            to_timedelta(time(second=1))
        assert to_timedelta(time(second=1), errors="coerce") is pd.NaT

    def test_to_timedelta_bad_value(self):
        msg = "Could not convert 'foo' to NumPy timedelta"
        with pytest.raises(ValueError, match=msg):
            to_timedelta(["foo", "bar"])

    def test_to_timedelta_bad_value_coerce(self):
        tm.assert_index_equal(
            TimedeltaIndex([pd.NaT, pd.NaT]),
            to_timedelta(["foo", "bar"], errors="coerce"),
        )

        tm.assert_index_equal(
            TimedeltaIndex(["1 day", pd.NaT, "1 min"]),
            to_timedelta(["1 day", "bar", "1 min"], errors="coerce"),
        )

    def test_to_timedelta_invalid_errors_ignore(self):
        # gh-13613: these should not error because errors='ignore'
        msg = "errors='ignore' is deprecated"
        invalid_data = "apple"

        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = to_timedelta(invalid_data, errors="ignore")
        assert invalid_data == result

        invalid_data = ["apple", "1 days"]
        expected = np.array(invalid_data, dtype=object)

        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = to_timedelta(invalid_data, errors="ignore")
        tm.assert_numpy_array_equal(expected, result)

        invalid_data = pd.Index(["apple", "1 days"])
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = to_timedelta(invalid_data, errors="ignore")
        tm.assert_index_equal(invalid_data, result)

        invalid_data = Series(["apple", "1 days"])
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = to_timedelta(invalid_data, errors="ignore")
        tm.assert_series_equal(invalid_data, result)

    @pytest.mark.parametrize(
        "val, errors",
        [
            ("1M", True),
            ("1 M", True),
            ("1Y", True),
            ("1 Y", True),
            ("1y", True),
            ("1 y", True),
            ("1m", False),
            ("1 m", False),
            ("1 day", False),
            ("2day", False),
        ],
    )
    def test_unambiguous_timedelta_values(self, val, errors):
        # GH36666 Deprecate use of strings denoting units with 'M', 'Y', 'm' or 'y'
        # in pd.to_timedelta
        msg = "Units 'M', 'Y' and 'y' do not represent unambiguous timedelta"
        if errors:
            with pytest.raises(ValueError, match=msg):
                to_timedelta(val)
        else:
            # check it doesn't raise
            to_timedelta(val)

    def test_to_timedelta_via_apply(self):
        # GH 5458
        expected = Series([np.timedelta64(1, "s")])
        result = Series(["00:00:01"]).apply(to_timedelta)
        tm.assert_series_equal(result, expected)

        result = Series([to_timedelta("00:00:01")])
        tm.assert_series_equal(result, expected)

    def test_to_timedelta_inference_without_warning(self):
        # GH#41731 inference produces a warning in the Series constructor,
        #  but _not_ in to_timedelta
        vals = ["00:00:01", pd.NaT]
        with tm.assert_produces_warning(None):
            result = to_timedelta(vals)

        expected = TimedeltaIndex([pd.Timedelta(seconds=1), pd.NaT])
        tm.assert_index_equal(result, expected)

    def test_to_timedelta_on_missing_values(self):
        # GH5438
        timedelta_NaT = np.timedelta64("NaT")

        actual = to_timedelta(Series(["00:00:01", np.nan]))
        expected = Series(
            [np.timedelta64(1000000000, "ns"), timedelta_NaT],
            dtype=f"{tm.ENDIAN}m8[ns]",
        )
        tm.assert_series_equal(actual, expected)

        ser = Series(["00:00:01", pd.NaT], dtype="m8[ns]")
        actual = to_timedelta(ser)
        tm.assert_series_equal(actual, expected)

    @pytest.mark.parametrize("val", [np.nan, pd.NaT, pd.NA])
    def test_to_timedelta_on_missing_values_scalar(self, val):
        actual = to_timedelta(val)
        assert actual._value == np.timedelta64("NaT").astype("int64")

    @pytest.mark.parametrize("val", [np.nan, pd.NaT, pd.NA])
    def test_to_timedelta_on_missing_values_list(self, val):
        actual = to_timedelta([val])
        assert actual[0]._value == np.timedelta64("NaT").astype("int64")

    @pytest.mark.xfail(not IS64, reason="Floating point error")
    def test_to_timedelta_float(self):
        # https://github.com/pandas-dev/pandas/issues/25077
        arr = np.arange(0, 1, 1e-6)[-10:]
        result = to_timedelta(arr, unit="s")
        expected_asi8 = np.arange(999990000, 10**9, 1000, dtype="int64")
        tm.assert_numpy_array_equal(result.asi8, expected_asi8)

    def test_to_timedelta_coerce_strings_unit(self):
        arr = np.array([1, 2, "error"], dtype=object)
        result = to_timedelta(arr, unit="ns", errors="coerce")
        expected = to_timedelta([1, 2, pd.NaT], unit="ns")
        tm.assert_index_equal(result, expected)

    def test_to_timedelta_ignore_strings_unit(self):
        arr = np.array([1, 2, "error"], dtype=object)
        msg = "errors='ignore' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = to_timedelta(arr, unit="ns", errors="ignore")
        tm.assert_numpy_array_equal(result, arr)

    @pytest.mark.parametrize(
        "expected_val, result_val", [[timedelta(days=2), 2], [None, None]]
    )
    def test_to_timedelta_nullable_int64_dtype(self, expected_val, result_val):
        # GH 35574
        expected = Series([timedelta(days=1), expected_val])
        result = to_timedelta(Series([1, result_val], dtype="Int64"), unit="days")

        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        ("input", "expected"),
        [
            ("8:53:08.71800000001", "8:53:08.718"),
            ("8:53:08.718001", "8:53:08.718001"),
            ("8:53:08.7180000001", "8:53:08.7180000001"),
            ("-8:53:08.71800000001", "-8:53:08.718"),
            ("8:53:08.7180000089", "8:53:08.718000008"),
        ],
    )
    @pytest.mark.parametrize("func", [pd.Timedelta, to_timedelta])
    def test_to_timedelta_precision_over_nanos(self, input, expected, func):
        # GH: 36738
        expected = pd.Timedelta(expected)
        result = func(input)
        assert result == expected

    def test_to_timedelta_zerodim(self, fixed_now_ts):
        # ndarray.item() incorrectly returns int for dt64[ns] and td64[ns]
        dt64 = fixed_now_ts.to_datetime64()
        arg = np.array(dt64)

        msg = (
            "Value must be Timedelta, string, integer, float, timedelta "
            "or convertible, not datetime64"
        )
        with pytest.raises(ValueError, match=msg):
            to_timedelta(arg)

        arg2 = arg.view("m8[ns]")
        result = to_timedelta(arg2)
        assert isinstance(result, pd.Timedelta)
        assert result._value == dt64.view("i8")

    def test_to_timedelta_numeric_ea(self, any_numeric_ea_dtype):
        # GH#48796
        ser = Series([1, pd.NA], dtype=any_numeric_ea_dtype)
        result = to_timedelta(ser)
        expected = Series([pd.Timedelta(1, unit="ns"), pd.NaT])
        tm.assert_series_equal(result, expected)

    def test_to_timedelta_fraction(self):
        result = to_timedelta(1.0 / 3, unit="h")
        expected = pd.Timedelta("0 days 00:19:59.999999998")
        assert result == expected


def test_from_numeric_arrow_dtype(any_numeric_ea_dtype):
    # GH 52425
    pytest.importorskip("pyarrow")
    ser = Series([1, 2], dtype=f"{any_numeric_ea_dtype.lower()}[pyarrow]")
    result = to_timedelta(ser)
    expected = Series([1, 2], dtype="timedelta64[ns]")
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("unit", ["ns", "ms"])
def test_from_timedelta_arrow_dtype(unit):
    # GH 54298
    pytest.importorskip("pyarrow")
    expected = Series([timedelta(1)], dtype=f"duration[{unit}][pyarrow]")
    result = to_timedelta(expected)
    tm.assert_series_equal(result, expected)
