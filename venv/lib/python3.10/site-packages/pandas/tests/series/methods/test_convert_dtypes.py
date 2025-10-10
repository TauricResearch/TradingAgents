from itertools import product

import numpy as np
import pytest

from pandas._config import using_string_dtype

from pandas._libs import lib

import pandas as pd
import pandas._testing as tm

# Each test case consists of a tuple with the data and dtype to create the
# test Series, the default dtype for the expected result (which is valid
# for most cases), and the specific cases where the result deviates from
# this default. Those overrides are defined as a dict with (keyword, val) as
# dictionary key. In case of multiple items, the last override takes precedence.


@pytest.fixture(
    params=[
        (
            # data
            [1, 2, 3],
            # original dtype
            np.dtype("int32"),
            # default expected dtype
            "Int32",
            # exceptions on expected dtype
            {("convert_integer", False): np.dtype("int32")},
        ),
        (
            [1, 2, 3],
            np.dtype("int64"),
            "Int64",
            {("convert_integer", False): np.dtype("int64")},
        ),
        (
            ["x", "y", "z"],
            np.dtype("O"),
            pd.StringDtype(),
            {("convert_string", False): np.dtype("O")},
        ),
        (
            [True, False, np.nan],
            np.dtype("O"),
            pd.BooleanDtype(),
            {("convert_boolean", False): np.dtype("O")},
        ),
        (
            ["h", "i", np.nan],
            np.dtype("O"),
            pd.StringDtype(),
            {("convert_string", False): np.dtype("O")},
        ),
        (  # GH32117
            ["h", "i", 1],
            np.dtype("O"),
            np.dtype("O"),
            {},
        ),
        (
            [10, np.nan, 20],
            np.dtype("float"),
            "Int64",
            {
                ("convert_integer", False, "convert_floating", True): "Float64",
                ("convert_integer", False, "convert_floating", False): np.dtype(
                    "float"
                ),
            },
        ),
        (
            [np.nan, 100.5, 200],
            np.dtype("float"),
            "Float64",
            {("convert_floating", False): np.dtype("float")},
        ),
        (
            [3, 4, 5],
            "Int8",
            "Int8",
            {},
        ),
        (
            [[1, 2], [3, 4], [5]],
            None,
            np.dtype("O"),
            {},
        ),
        (
            [4, 5, 6],
            np.dtype("uint32"),
            "UInt32",
            {("convert_integer", False): np.dtype("uint32")},
        ),
        (
            [-10, 12, 13],
            np.dtype("i1"),
            "Int8",
            {("convert_integer", False): np.dtype("i1")},
        ),
        (
            [1.2, 1.3],
            np.dtype("float32"),
            "Float32",
            {("convert_floating", False): np.dtype("float32")},
        ),
        (
            [1, 2.0],
            object,
            "Int64",
            {
                ("convert_integer", False): "Float64",
                ("convert_integer", False, "convert_floating", False): np.dtype(
                    "float"
                ),
                ("infer_objects", False): np.dtype("object"),
            },
        ),
        (
            [1, 2.5],
            object,
            "Float64",
            {
                ("convert_floating", False): np.dtype("float"),
                ("infer_objects", False): np.dtype("object"),
            },
        ),
        (["a", "b"], pd.CategoricalDtype(), pd.CategoricalDtype(), {}),
        (
            pd.to_datetime(["2020-01-14 10:00", "2020-01-15 11:11"]).as_unit("s"),
            pd.DatetimeTZDtype(tz="UTC"),
            pd.DatetimeTZDtype(tz="UTC"),
            {},
        ),
        (
            pd.to_datetime(["2020-01-14 10:00", "2020-01-15 11:11"]).as_unit("ms"),
            pd.DatetimeTZDtype(tz="UTC"),
            pd.DatetimeTZDtype(tz="UTC"),
            {},
        ),
        (
            pd.to_datetime(["2020-01-14 10:00", "2020-01-15 11:11"]).as_unit("us"),
            pd.DatetimeTZDtype(tz="UTC"),
            pd.DatetimeTZDtype(tz="UTC"),
            {},
        ),
        (
            pd.to_datetime(["2020-01-14 10:00", "2020-01-15 11:11"]).as_unit("ns"),
            pd.DatetimeTZDtype(tz="UTC"),
            pd.DatetimeTZDtype(tz="UTC"),
            {},
        ),
        (
            pd.to_datetime(["2020-01-14 10:00", "2020-01-15 11:11"]).as_unit("ns"),
            "datetime64[ns]",
            np.dtype("datetime64[ns]"),
            {},
        ),
        (
            pd.to_datetime(["2020-01-14 10:00", "2020-01-15 11:11"]).as_unit("ns"),
            object,
            np.dtype("datetime64[ns]"),
            {("infer_objects", False): np.dtype("object")},
        ),
        (
            pd.period_range("1/1/2011", freq="M", periods=3),
            None,
            pd.PeriodDtype("M"),
            {},
        ),
        (
            pd.arrays.IntervalArray([pd.Interval(0, 1), pd.Interval(1, 5)]),
            None,
            pd.IntervalDtype("int64", "right"),
            {},
        ),
    ]
)
def test_cases(request):
    return request.param


class TestSeriesConvertDtypes:
    @pytest.mark.xfail(using_string_dtype(), reason="TODO(infer_string)", strict=False)
    @pytest.mark.parametrize("params", product(*[(True, False)] * 5))
    def test_convert_dtypes(
        self,
        test_cases,
        params,
        using_infer_string,
    ):
        data, maindtype, expected_default, expected_other = test_cases
        if (
            hasattr(data, "dtype")
            and lib.is_np_dtype(data.dtype, "M")
            and isinstance(maindtype, pd.DatetimeTZDtype)
        ):
            # this astype is deprecated in favor of tz_localize
            msg = "Cannot use .astype to convert from timezone-naive dtype"
            with pytest.raises(TypeError, match=msg):
                pd.Series(data, dtype=maindtype)
            return

        if maindtype is not None:
            series = pd.Series(data, dtype=maindtype)
        else:
            series = pd.Series(data)

        result = series.convert_dtypes(*params)

        param_names = [
            "infer_objects",
            "convert_string",
            "convert_integer",
            "convert_boolean",
            "convert_floating",
        ]
        params_dict = dict(zip(param_names, params))

        expected_dtype = expected_default
        for spec, dtype in expected_other.items():
            if all(params_dict[key] is val for key, val in zip(spec[::2], spec[1::2])):
                expected_dtype = dtype
        if (
            using_infer_string
            and expected_default == "string"
            and expected_dtype == object
            and params[0]
            and not params[1]
        ):
            # If convert_string=False and infer_objects=True, we end up with the
            # default string dtype instead of preserving object for string data
            expected_dtype = pd.StringDtype(na_value=np.nan)

        expected = pd.Series(data, dtype=expected_dtype)
        tm.assert_series_equal(result, expected)

        # Test that it is a copy
        copy = series.copy(deep=True)

        if result.notna().sum() > 0 and result.dtype in ["interval[int64, right]"]:
            with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
                result[result.notna()] = np.nan
        else:
            result[result.notna()] = np.nan

        # Make sure original not changed
        tm.assert_series_equal(series, copy)

    def test_convert_string_dtype(self, nullable_string_dtype):
        # https://github.com/pandas-dev/pandas/issues/31731 -> converting columns
        # that are already string dtype
        df = pd.DataFrame(
            {"A": ["a", "b", pd.NA], "B": ["ä", "ö", "ü"]}, dtype=nullable_string_dtype
        )
        result = df.convert_dtypes()
        tm.assert_frame_equal(df, result)

    def test_convert_bool_dtype(self):
        # GH32287
        df = pd.DataFrame({"A": pd.array([True])})
        tm.assert_frame_equal(df, df.convert_dtypes())

    def test_convert_byte_string_dtype(self):
        # GH-43183
        byte_str = b"binary-string"

        df = pd.DataFrame(data={"A": byte_str}, index=[0])
        result = df.convert_dtypes()
        expected = df
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "infer_objects, dtype", [(True, "Int64"), (False, "object")]
    )
    def test_convert_dtype_object_with_na(self, infer_objects, dtype):
        # GH#48791
        ser = pd.Series([1, pd.NA])
        result = ser.convert_dtypes(infer_objects=infer_objects)
        expected = pd.Series([1, pd.NA], dtype=dtype)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "infer_objects, dtype", [(True, "Float64"), (False, "object")]
    )
    def test_convert_dtype_object_with_na_float(self, infer_objects, dtype):
        # GH#48791
        ser = pd.Series([1.5, pd.NA])
        result = ser.convert_dtypes(infer_objects=infer_objects)
        expected = pd.Series([1.5, pd.NA], dtype=dtype)
        tm.assert_series_equal(result, expected)

    def test_convert_dtypes_pyarrow_to_np_nullable(self):
        # GH 53648
        pytest.importorskip("pyarrow")
        ser = pd.Series(range(2), dtype="int32[pyarrow]")
        result = ser.convert_dtypes(dtype_backend="numpy_nullable")
        expected = pd.Series(range(2), dtype="Int32")
        tm.assert_series_equal(result, expected)

    def test_convert_dtypes_pyarrow_null(self):
        # GH#55346
        pa = pytest.importorskip("pyarrow")
        ser = pd.Series([None, None])
        result = ser.convert_dtypes(dtype_backend="pyarrow")
        expected = pd.Series([None, None], dtype=pd.ArrowDtype(pa.null()))
        tm.assert_series_equal(result, expected)
