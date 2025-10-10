"""
Tests for Series cumulative operations.

See also
--------
tests.frame.test_cumulative
"""

import re

import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm

methods = {
    "cumsum": np.cumsum,
    "cumprod": np.cumprod,
    "cummin": np.minimum.accumulate,
    "cummax": np.maximum.accumulate,
}


class TestSeriesCumulativeOps:
    @pytest.mark.parametrize("func", [np.cumsum, np.cumprod])
    def test_datetime_series(self, datetime_series, func):
        tm.assert_numpy_array_equal(
            func(datetime_series).values,
            func(np.array(datetime_series)),
            check_dtype=True,
        )

        # with missing values
        ts = datetime_series.copy()
        ts[::2] = np.nan

        result = func(ts)[1::2]
        expected = func(np.array(ts.dropna()))

        tm.assert_numpy_array_equal(result.values, expected, check_dtype=False)

    @pytest.mark.parametrize("method", ["cummin", "cummax"])
    def test_cummin_cummax(self, datetime_series, method):
        ufunc = methods[method]

        result = getattr(datetime_series, method)().values
        expected = ufunc(np.array(datetime_series))

        tm.assert_numpy_array_equal(result, expected)
        ts = datetime_series.copy()
        ts[::2] = np.nan
        result = getattr(ts, method)()[1::2]
        expected = ufunc(ts.dropna())

        result.index = result.index._with_freq(None)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "ts",
        [
            pd.Timedelta(0),
            pd.Timestamp("1999-12-31"),
            pd.Timestamp("1999-12-31").tz_localize("US/Pacific"),
        ],
    )
    @pytest.mark.parametrize(
        "method, skipna, exp_tdi",
        [
            ["cummax", True, ["NaT", "2 days", "NaT", "2 days", "NaT", "3 days"]],
            ["cummin", True, ["NaT", "2 days", "NaT", "1 days", "NaT", "1 days"]],
            [
                "cummax",
                False,
                ["NaT", "NaT", "NaT", "NaT", "NaT", "NaT"],
            ],
            [
                "cummin",
                False,
                ["NaT", "NaT", "NaT", "NaT", "NaT", "NaT"],
            ],
        ],
    )
    def test_cummin_cummax_datetimelike(self, ts, method, skipna, exp_tdi):
        # with ts==pd.Timedelta(0), we are testing td64; with naive Timestamp
        #  we are testing datetime64[ns]; with Timestamp[US/Pacific]
        #  we are testing dt64tz
        tdi = pd.to_timedelta(["NaT", "2 days", "NaT", "1 days", "NaT", "3 days"])
        ser = pd.Series(tdi + ts)

        exp_tdi = pd.to_timedelta(exp_tdi)
        expected = pd.Series(exp_tdi + ts)
        result = getattr(ser, method)(skipna=skipna)
        tm.assert_series_equal(expected, result)

    @pytest.mark.parametrize(
        "func, exp",
        [
            ("cummin", pd.Period("2012-1-1", freq="D")),
            ("cummax", pd.Period("2012-1-2", freq="D")),
        ],
    )
    def test_cummin_cummax_period(self, func, exp):
        # GH#28385
        ser = pd.Series(
            [pd.Period("2012-1-1", freq="D"), pd.NaT, pd.Period("2012-1-2", freq="D")]
        )
        result = getattr(ser, func)(skipna=False)
        expected = pd.Series([pd.Period("2012-1-1", freq="D"), pd.NaT, pd.NaT])
        tm.assert_series_equal(result, expected)

        result = getattr(ser, func)(skipna=True)
        expected = pd.Series([pd.Period("2012-1-1", freq="D"), pd.NaT, exp])
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "arg",
        [
            [False, False, False, True, True, False, False],
            [False, False, False, False, False, False, False],
        ],
    )
    @pytest.mark.parametrize(
        "func", [lambda x: x, lambda x: ~x], ids=["identity", "inverse"]
    )
    @pytest.mark.parametrize("method", methods.keys())
    def test_cummethods_bool(self, arg, func, method):
        # GH#6270
        # checking Series method vs the ufunc applied to the values

        ser = func(pd.Series(arg))
        ufunc = methods[method]

        exp_vals = ufunc(ser.values)
        expected = pd.Series(exp_vals)

        result = getattr(ser, method)()

        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "method, expected",
        [
            ["cumsum", pd.Series([0, 1, np.nan, 1], dtype=object)],
            ["cumprod", pd.Series([False, 0, np.nan, 0])],
            ["cummin", pd.Series([False, False, np.nan, False])],
            ["cummax", pd.Series([False, True, np.nan, True])],
        ],
    )
    def test_cummethods_bool_in_object_dtype(self, method, expected):
        ser = pd.Series([False, True, np.nan, False])
        result = getattr(ser, method)()
        tm.assert_series_equal(result, expected)

    def test_cumprod_timedelta(self):
        # GH#48111
        ser = pd.Series([pd.Timedelta(days=1), pd.Timedelta(days=3)])
        with pytest.raises(TypeError, match="cumprod not supported for Timedelta"):
            ser.cumprod()

    @pytest.mark.parametrize(
        "data, op, skipna, expected_data",
        [
            ([], "cumsum", True, []),
            ([], "cumsum", False, []),
            (["x", "z", "y"], "cumsum", True, ["x", "xz", "xzy"]),
            (["x", "z", "y"], "cumsum", False, ["x", "xz", "xzy"]),
            (["x", pd.NA, "y"], "cumsum", True, ["x", pd.NA, "xy"]),
            (["x", pd.NA, "y"], "cumsum", False, ["x", pd.NA, pd.NA]),
            ([pd.NA, "x", "y"], "cumsum", True, [pd.NA, "x", "xy"]),
            ([pd.NA, "x", "y"], "cumsum", False, [pd.NA, pd.NA, pd.NA]),
            ([pd.NA, pd.NA, pd.NA], "cumsum", True, [pd.NA, pd.NA, pd.NA]),
            ([pd.NA, pd.NA, pd.NA], "cumsum", False, [pd.NA, pd.NA, pd.NA]),
            ([], "cummin", True, []),
            ([], "cummin", False, []),
            (["y", "z", "x"], "cummin", True, ["y", "y", "x"]),
            (["y", "z", "x"], "cummin", False, ["y", "y", "x"]),
            (["y", pd.NA, "x"], "cummin", True, ["y", pd.NA, "x"]),
            (["y", pd.NA, "x"], "cummin", False, ["y", pd.NA, pd.NA]),
            ([pd.NA, "y", "x"], "cummin", True, [pd.NA, "y", "x"]),
            ([pd.NA, "y", "x"], "cummin", False, [pd.NA, pd.NA, pd.NA]),
            ([pd.NA, pd.NA, pd.NA], "cummin", True, [pd.NA, pd.NA, pd.NA]),
            ([pd.NA, pd.NA, pd.NA], "cummin", False, [pd.NA, pd.NA, pd.NA]),
            ([], "cummax", True, []),
            ([], "cummax", False, []),
            (["x", "z", "y"], "cummax", True, ["x", "z", "z"]),
            (["x", "z", "y"], "cummax", False, ["x", "z", "z"]),
            (["x", pd.NA, "y"], "cummax", True, ["x", pd.NA, "y"]),
            (["x", pd.NA, "y"], "cummax", False, ["x", pd.NA, pd.NA]),
            ([pd.NA, "x", "y"], "cummax", True, [pd.NA, "x", "y"]),
            ([pd.NA, "x", "y"], "cummax", False, [pd.NA, pd.NA, pd.NA]),
            ([pd.NA, pd.NA, pd.NA], "cummax", True, [pd.NA, pd.NA, pd.NA]),
            ([pd.NA, pd.NA, pd.NA], "cummax", False, [pd.NA, pd.NA, pd.NA]),
        ],
    )
    def test_cum_methods_ea_strings(
        self, string_dtype_no_object, data, op, skipna, expected_data
    ):
        # https://github.com/pandas-dev/pandas/pull/60633 - pyarrow
        # https://github.com/pandas-dev/pandas/pull/60938 - Python
        ser = pd.Series(data, dtype=string_dtype_no_object)
        method = getattr(ser, op)
        expected = pd.Series(expected_data, dtype=string_dtype_no_object)
        result = method(skipna=skipna)
        tm.assert_series_equal(result, expected)

    def test_cumprod_pyarrow_strings(self, pyarrow_string_dtype, skipna):
        # https://github.com/pandas-dev/pandas/pull/60633
        ser = pd.Series(list("xyz"), dtype=pyarrow_string_dtype)
        msg = re.escape(f"operation 'cumprod' not supported for dtype '{ser.dtype}'")
        with pytest.raises(TypeError, match=msg):
            ser.cumprod(skipna=skipna)
