import datetime

import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm


class TestConvertDtypes:
    @pytest.mark.parametrize(
        "convert_integer, expected", [(False, np.dtype("int32")), (True, "Int32")]
    )
    def test_convert_dtypes(self, convert_integer, expected, string_storage):
        # Specific types are tested in tests/series/test_dtypes.py
        # Just check that it works for DataFrame here
        df = pd.DataFrame(
            {
                "a": pd.Series([1, 2, 3], dtype=np.dtype("int32")),
                "b": pd.Series(["x", "y", "z"], dtype=np.dtype("O")),
            }
        )
        with pd.option_context("string_storage", string_storage):
            result = df.convert_dtypes(True, True, convert_integer, False)
        expected = pd.DataFrame(
            {
                "a": pd.Series([1, 2, 3], dtype=expected),
                "b": pd.Series(["x", "y", "z"], dtype=f"string[{string_storage}]"),
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_convert_empty(self):
        # Empty DataFrame can pass convert_dtypes, see GH#40393
        empty_df = pd.DataFrame()
        tm.assert_frame_equal(empty_df, empty_df.convert_dtypes())

    def test_convert_dtypes_retain_column_names(self):
        # GH#41435
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        df.columns.name = "cols"

        result = df.convert_dtypes()
        tm.assert_index_equal(result.columns, df.columns)
        assert result.columns.name == "cols"

    def test_pyarrow_dtype_backend(self):
        pa = pytest.importorskip("pyarrow")
        df = pd.DataFrame(
            {
                "a": pd.Series([1, 2, 3], dtype=np.dtype("int32")),
                "b": pd.Series(["x", "y", None], dtype=np.dtype("O")),
                "c": pd.Series([True, False, None], dtype=np.dtype("O")),
                "d": pd.Series([np.nan, 100.5, 200], dtype=np.dtype("float")),
                "e": pd.Series(pd.date_range("2022", periods=3)),
                "f": pd.Series(pd.date_range("2022", periods=3, tz="UTC").as_unit("s")),
                "g": pd.Series(pd.timedelta_range("1D", periods=3)),
            }
        )
        result = df.convert_dtypes(dtype_backend="pyarrow")
        expected = pd.DataFrame(
            {
                "a": pd.arrays.ArrowExtensionArray(
                    pa.array([1, 2, 3], type=pa.int32())
                ),
                "b": pd.arrays.ArrowExtensionArray(pa.array(["x", "y", None])),
                "c": pd.arrays.ArrowExtensionArray(pa.array([True, False, None])),
                "d": pd.arrays.ArrowExtensionArray(pa.array([None, 100.5, 200.0])),
                "e": pd.arrays.ArrowExtensionArray(
                    pa.array(
                        [
                            datetime.datetime(2022, 1, 1),
                            datetime.datetime(2022, 1, 2),
                            datetime.datetime(2022, 1, 3),
                        ],
                        type=pa.timestamp(unit="ns"),
                    )
                ),
                "f": pd.arrays.ArrowExtensionArray(
                    pa.array(
                        [
                            datetime.datetime(2022, 1, 1),
                            datetime.datetime(2022, 1, 2),
                            datetime.datetime(2022, 1, 3),
                        ],
                        type=pa.timestamp(unit="s", tz="UTC"),
                    )
                ),
                "g": pd.arrays.ArrowExtensionArray(
                    pa.array(
                        [
                            datetime.timedelta(1),
                            datetime.timedelta(2),
                            datetime.timedelta(3),
                        ],
                        type=pa.duration("ns"),
                    )
                ),
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_pyarrow_dtype_backend_already_pyarrow(self):
        pytest.importorskip("pyarrow")
        expected = pd.DataFrame([1, 2, 3], dtype="int64[pyarrow]")
        result = expected.convert_dtypes(dtype_backend="pyarrow")
        tm.assert_frame_equal(result, expected)

    def test_pyarrow_dtype_backend_from_pandas_nullable(self):
        pa = pytest.importorskip("pyarrow")
        df = pd.DataFrame(
            {
                "a": pd.Series([1, 2, None], dtype="Int32"),
                "b": pd.Series(["x", "y", None], dtype="string[python]"),
                "c": pd.Series([True, False, None], dtype="boolean"),
                "d": pd.Series([None, 100.5, 200], dtype="Float64"),
            }
        )
        result = df.convert_dtypes(dtype_backend="pyarrow")
        expected = pd.DataFrame(
            {
                "a": pd.arrays.ArrowExtensionArray(
                    pa.array([1, 2, None], type=pa.int32())
                ),
                "b": pd.arrays.ArrowExtensionArray(pa.array(["x", "y", None])),
                "c": pd.arrays.ArrowExtensionArray(pa.array([True, False, None])),
                "d": pd.arrays.ArrowExtensionArray(pa.array([None, 100.5, 200.0])),
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_pyarrow_dtype_empty_object(self):
        # GH 50970
        pytest.importorskip("pyarrow")
        expected = pd.DataFrame(columns=[0])
        result = expected.convert_dtypes(dtype_backend="pyarrow")
        tm.assert_frame_equal(result, expected)

    def test_pyarrow_engine_lines_false(self):
        # GH 48893
        df = pd.DataFrame({"a": [1, 2, 3]})
        msg = (
            "dtype_backend numpy is invalid, only 'numpy_nullable' and "
            "'pyarrow' are allowed."
        )
        with pytest.raises(ValueError, match=msg):
            df.convert_dtypes(dtype_backend="numpy")

    def test_pyarrow_backend_no_conversion(self):
        # GH#52872
        pytest.importorskip("pyarrow")
        df = pd.DataFrame({"a": [1, 2], "b": 1.5, "c": True, "d": "x"})
        expected = df.copy()
        result = df.convert_dtypes(
            convert_floating=False,
            convert_integer=False,
            convert_boolean=False,
            convert_string=False,
            dtype_backend="pyarrow",
        )
        tm.assert_frame_equal(result, expected)

    def test_convert_dtypes_pyarrow_to_np_nullable(self):
        # GH 53648
        pytest.importorskip("pyarrow")
        ser = pd.DataFrame(range(2), dtype="int32[pyarrow]")
        result = ser.convert_dtypes(dtype_backend="numpy_nullable")
        expected = pd.DataFrame(range(2), dtype="Int32")
        tm.assert_frame_equal(result, expected)

    def test_convert_dtypes_pyarrow_timestamp(self):
        # GH 54191
        pytest.importorskip("pyarrow")
        ser = pd.Series(pd.date_range("2020-01-01", "2020-01-02", freq="1min"))
        expected = ser.astype("timestamp[ms][pyarrow]")
        result = expected.convert_dtypes(dtype_backend="pyarrow")
        tm.assert_series_equal(result, expected)

    def test_convert_dtypes_avoid_block_splitting(self):
        # GH#55341
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": "a"})
        result = df.convert_dtypes(convert_integer=False)
        expected = pd.DataFrame(
            {
                "a": [1, 2, 3],
                "b": [4, 5, 6],
                "c": pd.Series(["a"] * 3, dtype="string[python]"),
            }
        )
        tm.assert_frame_equal(result, expected)
        assert result._mgr.nblocks == 2

    def test_convert_dtypes_from_arrow(self):
        # GH#56581
        df = pd.DataFrame([["a", datetime.time(18, 12)]], columns=["a", "b"])
        result = df.convert_dtypes()
        expected = df.astype({"a": "string[python]"})
        tm.assert_frame_equal(result, expected)
