import numpy as np
import pytest

from pandas._config import using_string_dtype

from pandas.compat import WARNING_CHECK_DISABLED
from pandas.errors import ChainedAssignmentError
import pandas.util._test_decorators as td

from pandas import (
    DataFrame,
    NaT,
    Series,
    date_range,
)
import pandas._testing as tm


class TestDataFrameInterpolate:
    def test_interpolate_complex(self):
        # GH#53635
        ser = Series([complex("1+1j"), float("nan"), complex("2+2j")])
        assert ser.dtype.kind == "c"

        res = ser.interpolate()
        expected = Series([ser[0], ser[0] * 1.5, ser[2]])
        tm.assert_series_equal(res, expected)

        df = ser.to_frame()
        res = df.interpolate()
        expected = expected.to_frame()
        tm.assert_frame_equal(res, expected)

    def test_interpolate_datetimelike_values(self, frame_or_series):
        # GH#11312, GH#51005
        orig = Series(date_range("2012-01-01", periods=5))
        ser = orig.copy()
        ser[2] = NaT

        res = frame_or_series(ser).interpolate()
        expected = frame_or_series(orig)
        tm.assert_equal(res, expected)

        # datetime64tz cast
        ser_tz = ser.dt.tz_localize("US/Pacific")
        res_tz = frame_or_series(ser_tz).interpolate()
        expected_tz = frame_or_series(orig.dt.tz_localize("US/Pacific"))
        tm.assert_equal(res_tz, expected_tz)

        # timedelta64 cast
        ser_td = ser - ser[0]
        res_td = frame_or_series(ser_td).interpolate()
        expected_td = frame_or_series(orig - orig[0])
        tm.assert_equal(res_td, expected_td)

    def test_interpolate_inplace(self, frame_or_series, using_array_manager, request):
        # GH#44749
        if using_array_manager and frame_or_series is DataFrame:
            mark = pytest.mark.xfail(reason=".values-based in-place check is invalid")
            request.applymarker(mark)

        obj = frame_or_series([1, np.nan, 2])
        orig = obj.values

        obj.interpolate(inplace=True)
        expected = frame_or_series([1, 1.5, 2])
        tm.assert_equal(obj, expected)

        # check we operated *actually* inplace
        assert np.shares_memory(orig, obj.values)
        assert orig.squeeze()[1] == 1.5

    def test_interp_basic(self, using_copy_on_write, using_infer_string):
        df = DataFrame(
            {
                "A": [1, 2, np.nan, 4],
                "B": [1, 4, 9, np.nan],
                "C": [1, 2, 3, 5],
                "D": list("abcd"),
            }
        )
        expected = DataFrame(
            {
                "A": [1.0, 2.0, 3.0, 4.0],
                "B": [1.0, 4.0, 9.0, 9.0],
                "C": [1, 2, 3, 5],
                "D": list("abcd"),
            }
        )
        if using_infer_string:
            dtype = "str" if using_infer_string else "object"
            msg = f"[Cc]annot interpolate with {dtype} dtype"
            with pytest.raises(TypeError, match=msg):
                df.interpolate()
            return

        msg = "DataFrame.interpolate with object dtype"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.interpolate()
        tm.assert_frame_equal(result, expected)

        # check we didn't operate inplace GH#45791
        cvalues = df["C"]._values
        dvalues = df["D"].values
        if using_copy_on_write:
            assert np.shares_memory(cvalues, result["C"]._values)
            assert np.shares_memory(dvalues, result["D"]._values)
        else:
            assert not np.shares_memory(cvalues, result["C"]._values)
            assert not np.shares_memory(dvalues, result["D"]._values)

        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = df.interpolate(inplace=True)
        assert res is None
        tm.assert_frame_equal(df, expected)

        # check we DID operate inplace
        assert tm.shares_memory(df["C"]._values, cvalues)
        assert tm.shares_memory(df["D"]._values, dvalues)

    @pytest.mark.xfail(
        using_string_dtype(), reason="interpolate doesn't work for string"
    )
    def test_interp_basic_with_non_range_index(self, using_infer_string):
        df = DataFrame(
            {
                "A": [1, 2, np.nan, 4],
                "B": [1, 4, 9, np.nan],
                "C": [1, 2, 3, 5],
                "D": list("abcd"),
            }
        )

        msg = "DataFrame.interpolate with object dtype"
        warning = FutureWarning if not using_infer_string else None
        with tm.assert_produces_warning(warning, match=msg):
            result = df.set_index("C").interpolate()
        expected = df.set_index("C")
        expected.loc[3, "A"] = 3
        expected.loc[5, "B"] = 9
        tm.assert_frame_equal(result, expected)

    def test_interp_empty(self):
        # https://github.com/pandas-dev/pandas/issues/35598
        df = DataFrame()
        result = df.interpolate()
        assert result is not df
        expected = df
        tm.assert_frame_equal(result, expected)

    def test_interp_bad_method(self):
        df = DataFrame(
            {
                "A": [1, 2, np.nan, 4],
                "B": [1, 4, 9, np.nan],
                "C": [1, 2, 3, 5],
            }
        )
        msg = (
            r"method must be one of \['linear', 'time', 'index', 'values', "
            r"'nearest', 'zero', 'slinear', 'quadratic', 'cubic', "
            r"'barycentric', 'krogh', 'spline', 'polynomial', "
            r"'from_derivatives', 'piecewise_polynomial', 'pchip', 'akima', "
            r"'cubicspline'\]. Got 'not_a_method' instead."
        )
        with pytest.raises(ValueError, match=msg):
            df.interpolate(method="not_a_method")

    def test_interp_combo(self):
        df = DataFrame(
            {
                "A": [1.0, 2.0, np.nan, 4.0],
                "B": [1, 4, 9, np.nan],
                "C": [1, 2, 3, 5],
                "D": list("abcd"),
            }
        )

        result = df["A"].interpolate()
        expected = Series([1.0, 2.0, 3.0, 4.0], name="A")
        tm.assert_series_equal(result, expected)

        msg = "The 'downcast' keyword in Series.interpolate is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df["A"].interpolate(downcast="infer")
        expected = Series([1, 2, 3, 4], name="A")
        tm.assert_series_equal(result, expected)

    def test_inerpolate_invalid_downcast(self):
        # GH#53103
        df = DataFrame(
            {
                "A": [1.0, 2.0, np.nan, 4.0],
                "B": [1, 4, 9, np.nan],
                "C": [1, 2, 3, 5],
                "D": list("abcd"),
            }
        )

        msg = "downcast must be either None or 'infer'"
        msg2 = "The 'downcast' keyword in DataFrame.interpolate is deprecated"
        msg3 = "The 'downcast' keyword in Series.interpolate is deprecated"
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=msg2):
                df.interpolate(downcast="int64")
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=msg3):
                df["A"].interpolate(downcast="int64")

    def test_interp_nan_idx(self):
        df = DataFrame({"A": [1, 2, np.nan, 4], "B": [np.nan, 2, 3, 4]})
        df = df.set_index("A")
        msg = (
            "Interpolation with NaNs in the index has not been implemented. "
            "Try filling those NaNs before interpolating."
        )
        with pytest.raises(NotImplementedError, match=msg):
            df.interpolate(method="values")

    def test_interp_various(self):
        pytest.importorskip("scipy")
        df = DataFrame(
            {"A": [1, 2, np.nan, 4, 5, np.nan, 7], "C": [1, 2, 3, 5, 8, 13, 21]}
        )
        df = df.set_index("C")
        expected = df.copy()
        result = df.interpolate(method="polynomial", order=1)

        expected.loc[3, "A"] = 2.66666667
        expected.loc[13, "A"] = 5.76923076
        tm.assert_frame_equal(result, expected)

        result = df.interpolate(method="cubic")
        # GH #15662.
        expected.loc[3, "A"] = 2.81547781
        expected.loc[13, "A"] = 5.52964175
        tm.assert_frame_equal(result, expected)

        result = df.interpolate(method="nearest")
        expected.loc[3, "A"] = 2
        expected.loc[13, "A"] = 5
        tm.assert_frame_equal(result, expected, check_dtype=False)

        result = df.interpolate(method="quadratic")
        expected.loc[3, "A"] = 2.82150771
        expected.loc[13, "A"] = 6.12648668
        tm.assert_frame_equal(result, expected)

        result = df.interpolate(method="slinear")
        expected.loc[3, "A"] = 2.66666667
        expected.loc[13, "A"] = 5.76923077
        tm.assert_frame_equal(result, expected)

        result = df.interpolate(method="zero")
        expected.loc[3, "A"] = 2.0
        expected.loc[13, "A"] = 5
        tm.assert_frame_equal(result, expected, check_dtype=False)

    def test_interp_alt_scipy(self):
        pytest.importorskip("scipy")
        df = DataFrame(
            {"A": [1, 2, np.nan, 4, 5, np.nan, 7], "C": [1, 2, 3, 5, 8, 13, 21]}
        )
        result = df.interpolate(method="barycentric")
        expected = df.copy()
        expected.loc[2, "A"] = 3
        expected.loc[5, "A"] = 6
        tm.assert_frame_equal(result, expected)

        msg = "The 'downcast' keyword in DataFrame.interpolate is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.interpolate(method="barycentric", downcast="infer")
        tm.assert_frame_equal(result, expected.astype(np.int64))

        result = df.interpolate(method="krogh")
        expectedk = df.copy()
        expectedk["A"] = expected["A"]
        tm.assert_frame_equal(result, expectedk)

        result = df.interpolate(method="pchip")
        expected.loc[2, "A"] = 3
        expected.loc[5, "A"] = 6.0

        tm.assert_frame_equal(result, expected)

    def test_interp_rowwise(self):
        df = DataFrame(
            {
                0: [1, 2, np.nan, 4],
                1: [2, 3, 4, np.nan],
                2: [np.nan, 4, 5, 6],
                3: [4, np.nan, 6, 7],
                4: [1, 2, 3, 4],
            }
        )
        result = df.interpolate(axis=1)
        expected = df.copy()
        expected.loc[3, 1] = 5
        expected.loc[0, 2] = 3
        expected.loc[1, 3] = 3
        expected[4] = expected[4].astype(np.float64)
        tm.assert_frame_equal(result, expected)

        result = df.interpolate(axis=1, method="values")
        tm.assert_frame_equal(result, expected)

        result = df.interpolate(axis=0)
        expected = df.interpolate()
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "axis_name, axis_number",
        [
            pytest.param("rows", 0, id="rows_0"),
            pytest.param("index", 0, id="index_0"),
            pytest.param("columns", 1, id="columns_1"),
        ],
    )
    def test_interp_axis_names(self, axis_name, axis_number):
        # GH 29132: test axis names
        data = {0: [0, np.nan, 6], 1: [1, np.nan, 7], 2: [2, 5, 8]}

        df = DataFrame(data, dtype=np.float64)
        result = df.interpolate(axis=axis_name, method="linear")
        expected = df.interpolate(axis=axis_number, method="linear")
        tm.assert_frame_equal(result, expected)

    def test_rowwise_alt(self):
        df = DataFrame(
            {
                0: [0, 0.5, 1.0, np.nan, 4, 8, np.nan, np.nan, 64],
                1: [1, 2, 3, 4, 3, 2, 1, 0, -1],
            }
        )
        df.interpolate(axis=0)
        # TODO: assert something?

    @pytest.mark.parametrize(
        "check_scipy", [False, pytest.param(True, marks=td.skip_if_no("scipy"))]
    )
    def test_interp_leading_nans(self, check_scipy):
        df = DataFrame(
            {"A": [np.nan, np.nan, 0.5, 0.25, 0], "B": [np.nan, -3, -3.5, np.nan, -4]}
        )
        result = df.interpolate()
        expected = df.copy()
        expected.loc[3, "B"] = -3.75
        tm.assert_frame_equal(result, expected)

        if check_scipy:
            result = df.interpolate(method="polynomial", order=1)
            tm.assert_frame_equal(result, expected)

    def test_interp_raise_on_only_mixed(self, axis):
        df = DataFrame(
            {
                "A": [1, 2, np.nan, 4],
                "B": ["a", "b", "c", "d"],
                "C": [np.nan, 2, 5, 7],
                "D": [np.nan, np.nan, 9, 9],
                "E": [1, 2, 3, 4],
            }
        )
        msg = (
            "Cannot interpolate with all object-dtype columns "
            "in the DataFrame. Try setting at least one "
            "column to a numeric dtype."
        )
        with pytest.raises(TypeError, match=msg):
            df.astype("object").interpolate(axis=axis)

    def test_interp_raise_on_all_object_dtype(self):
        # GH 22985
        df = DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]}, dtype="object")
        msg = (
            "Cannot interpolate with all object-dtype columns "
            "in the DataFrame. Try setting at least one "
            "column to a numeric dtype."
        )
        with pytest.raises(TypeError, match=msg):
            df.interpolate()

    def test_interp_inplace(self, using_copy_on_write):
        df = DataFrame({"a": [1.0, 2.0, np.nan, 4.0]})
        expected = DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
        expected_cow = df.copy()
        result = df.copy()

        if using_copy_on_write:
            with tm.raises_chained_assignment_error():
                return_value = result["a"].interpolate(inplace=True)
            assert return_value is None
            tm.assert_frame_equal(result, expected_cow)
        else:
            with tm.assert_produces_warning(
                FutureWarning if not WARNING_CHECK_DISABLED else None,
                match="inplace method",
            ):
                return_value = result["a"].interpolate(inplace=True)
            assert return_value is None
            tm.assert_frame_equal(result, expected)

        result = df.copy()
        msg = "The 'downcast' keyword in Series.interpolate is deprecated"

        if using_copy_on_write:
            with tm.assert_produces_warning(
                (FutureWarning, ChainedAssignmentError), match=msg
            ):
                return_value = result["a"].interpolate(inplace=True, downcast="infer")
            assert return_value is None
            tm.assert_frame_equal(result, expected_cow)
        else:
            with tm.assert_produces_warning(FutureWarning, match=msg):
                return_value = result["a"].interpolate(inplace=True, downcast="infer")
            assert return_value is None
            tm.assert_frame_equal(result, expected.astype("int64"))

    def test_interp_inplace_row(self):
        # GH 10395
        result = DataFrame(
            {"a": [1.0, 2.0, 3.0, 4.0], "b": [np.nan, 2.0, 3.0, 4.0], "c": [3, 2, 2, 2]}
        )
        expected = result.interpolate(method="linear", axis=1, inplace=False)
        return_value = result.interpolate(method="linear", axis=1, inplace=True)
        assert return_value is None
        tm.assert_frame_equal(result, expected)

    def test_interp_ignore_all_good(self):
        # GH
        df = DataFrame(
            {
                "A": [1, 2, np.nan, 4],
                "B": [1, 2, 3, 4],
                "C": [1.0, 2.0, np.nan, 4.0],
                "D": [1.0, 2.0, 3.0, 4.0],
            }
        )
        expected = DataFrame(
            {
                "A": np.array([1, 2, 3, 4], dtype="float64"),
                "B": np.array([1, 2, 3, 4], dtype="int64"),
                "C": np.array([1.0, 2.0, 3, 4.0], dtype="float64"),
                "D": np.array([1.0, 2.0, 3.0, 4.0], dtype="float64"),
            }
        )

        msg = "The 'downcast' keyword in DataFrame.interpolate is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.interpolate(downcast=None)
        tm.assert_frame_equal(result, expected)

        # all good
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df[["B", "D"]].interpolate(downcast=None)
        tm.assert_frame_equal(result, df[["B", "D"]])

    def test_interp_time_inplace_axis(self):
        # GH 9687
        periods = 5
        idx = date_range(start="2014-01-01", periods=periods)
        data = np.random.default_rng(2).random((periods, periods))
        data[data < 0.5] = np.nan
        expected = DataFrame(index=idx, columns=idx, data=data)

        result = expected.interpolate(axis=0, method="time")
        return_value = expected.interpolate(axis=0, method="time", inplace=True)
        assert return_value is None
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("axis_name, axis_number", [("index", 0), ("columns", 1)])
    def test_interp_string_axis(self, axis_name, axis_number):
        # https://github.com/pandas-dev/pandas/issues/25190
        x = np.linspace(0, 100, 1000)
        y = np.sin(x)
        df = DataFrame(
            data=np.tile(y, (10, 1)), index=np.arange(10), columns=x
        ).reindex(columns=x * 1.005)
        result = df.interpolate(method="linear", axis=axis_name)
        expected = df.interpolate(method="linear", axis=axis_number)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("multiblock", [True, False])
    @pytest.mark.parametrize("method", ["ffill", "bfill", "pad"])
    def test_interp_fillna_methods(
        self, request, axis, multiblock, method, using_array_manager
    ):
        # GH 12918
        if using_array_manager and axis in (1, "columns"):
            # TODO(ArrayManager) support axis=1
            td.mark_array_manager_not_yet_implemented(request)

        df = DataFrame(
            {
                "A": [1.0, 2.0, 3.0, 4.0, np.nan, 5.0],
                "B": [2.0, 4.0, 6.0, np.nan, 8.0, 10.0],
                "C": [3.0, 6.0, 9.0, np.nan, np.nan, 30.0],
            }
        )
        if multiblock:
            df["D"] = np.nan
            df["E"] = 1.0

        method2 = method if method != "pad" else "ffill"
        expected = getattr(df, method2)(axis=axis)
        msg = f"DataFrame.interpolate with method={method} is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.interpolate(method=method, axis=axis)
        tm.assert_frame_equal(result, expected)

    def test_interpolate_empty_df(self):
        # GH#53199
        df = DataFrame()
        expected = df.copy()
        result = df.interpolate(inplace=True)
        assert result is None
        tm.assert_frame_equal(df, expected)

    def test_interpolate_ea(self, any_int_ea_dtype):
        # GH#55347
        df = DataFrame({"a": [1, None, None, None, 3]}, dtype=any_int_ea_dtype)
        orig = df.copy()
        result = df.interpolate(limit=2)
        expected = DataFrame({"a": [1, 1.5, 2.0, None, 3]}, dtype="Float64")
        tm.assert_frame_equal(result, expected)
        tm.assert_frame_equal(df, orig)

    @pytest.mark.parametrize(
        "dtype",
        [
            "Float64",
            "Float32",
            pytest.param("float32[pyarrow]", marks=td.skip_if_no("pyarrow")),
            pytest.param("float64[pyarrow]", marks=td.skip_if_no("pyarrow")),
        ],
    )
    def test_interpolate_ea_float(self, dtype):
        # GH#55347
        df = DataFrame({"a": [1, None, None, None, 3]}, dtype=dtype)
        orig = df.copy()
        result = df.interpolate(limit=2)
        expected = DataFrame({"a": [1, 1.5, 2.0, None, 3]}, dtype=dtype)
        tm.assert_frame_equal(result, expected)
        tm.assert_frame_equal(df, orig)

    @pytest.mark.parametrize(
        "dtype",
        ["int64", "uint64", "int32", "int16", "int8", "uint32", "uint16", "uint8"],
    )
    def test_interpolate_arrow(self, dtype):
        # GH#55347
        pytest.importorskip("pyarrow")
        df = DataFrame({"a": [1, None, None, None, 3]}, dtype=dtype + "[pyarrow]")
        result = df.interpolate(limit=2)
        expected = DataFrame({"a": [1, 1.5, 2.0, None, 3]}, dtype="float64[pyarrow]")
        tm.assert_frame_equal(result, expected)
