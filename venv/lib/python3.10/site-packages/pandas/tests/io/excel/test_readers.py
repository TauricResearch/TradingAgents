from __future__ import annotations

from datetime import (
    datetime,
    time,
)
from functools import partial
from io import BytesIO
import os
from pathlib import Path
import platform
import re
from urllib.error import URLError
from zipfile import BadZipFile

import numpy as np
import pytest

from pandas.compat import is_platform_windows
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Series,
    read_csv,
)
import pandas._testing as tm

if is_platform_windows():
    pytestmark = pytest.mark.single_cpu

read_ext_params = [".xls", ".xlsx", ".xlsm", ".xlsb", ".ods"]
engine_params = [
    # Add any engines to test here
    # When defusedxml is installed it triggers deprecation warnings for
    # xlrd and openpyxl, so catch those here
    pytest.param(
        "xlrd",
        marks=[
            td.skip_if_no("xlrd"),
        ],
    ),
    pytest.param(
        "openpyxl",
        marks=[
            td.skip_if_no("openpyxl"),
        ],
    ),
    pytest.param(
        None,
        marks=[
            td.skip_if_no("xlrd"),
        ],
    ),
    pytest.param("pyxlsb", marks=td.skip_if_no("pyxlsb")),
    pytest.param("odf", marks=td.skip_if_no("odf")),
    pytest.param("calamine", marks=td.skip_if_no("python_calamine")),
]


def _is_valid_engine_ext_pair(engine, read_ext: str) -> bool:
    """
    Filter out invalid (engine, ext) pairs instead of skipping, as that
    produces 500+ pytest.skips.
    """
    engine = engine.values[0]
    if engine == "openpyxl" and read_ext == ".xls":
        return False
    if engine == "odf" and read_ext != ".ods":
        return False
    if read_ext == ".ods" and engine not in {"odf", "calamine"}:
        return False
    if engine == "pyxlsb" and read_ext != ".xlsb":
        return False
    if read_ext == ".xlsb" and engine not in {"pyxlsb", "calamine"}:
        return False
    if engine == "xlrd" and read_ext != ".xls":
        return False
    return True


def _transfer_marks(engine, read_ext):
    """
    engine gives us a pytest.param object with some marks, read_ext is just
    a string.  We need to generate a new pytest.param inheriting the marks.
    """
    values = engine.values + (read_ext,)
    new_param = pytest.param(values, marks=engine.marks)
    return new_param


@pytest.fixture(
    params=[
        _transfer_marks(eng, ext)
        for eng in engine_params
        for ext in read_ext_params
        if _is_valid_engine_ext_pair(eng, ext)
    ],
    ids=str,
)
def engine_and_read_ext(request):
    """
    Fixture for Excel reader engine and read_ext, only including valid pairs.
    """
    return request.param


@pytest.fixture
def engine(engine_and_read_ext):
    engine, read_ext = engine_and_read_ext
    return engine


@pytest.fixture
def read_ext(engine_and_read_ext):
    engine, read_ext = engine_and_read_ext
    return read_ext


@pytest.fixture
def df_ref(datapath):
    """
    Obtain the reference data from read_csv with the Python engine.
    """
    filepath = datapath("io", "data", "csv", "test1.csv")
    df_ref = read_csv(filepath, index_col=0, parse_dates=True, engine="python")
    return df_ref


def get_exp_unit(read_ext: str, engine: str | None) -> str:
    return "ns"


def adjust_expected(expected: DataFrame, read_ext: str, engine: str) -> None:
    expected.index.name = None
    unit = get_exp_unit(read_ext, engine)
    # error: "Index" has no attribute "as_unit"
    expected.index = expected.index.as_unit(unit)  # type: ignore[attr-defined]


def xfail_datetimes_with_pyxlsb(engine, request):
    if engine == "pyxlsb":
        request.applymarker(
            pytest.mark.xfail(
                reason="Sheets containing datetimes not supported by pyxlsb"
            )
        )


class TestReaders:
    @pytest.fixture(autouse=True)
    def cd_and_set_engine(self, engine, datapath, monkeypatch):
        """
        Change directory and set engine for read_excel calls.
        """
        func = partial(pd.read_excel, engine=engine)
        monkeypatch.chdir(datapath("io", "data", "excel"))
        monkeypatch.setattr(pd, "read_excel", func)

    def test_engine_used(self, read_ext, engine, monkeypatch):
        # GH 38884
        def parser(self, *args, **kwargs):
            return self.engine

        monkeypatch.setattr(pd.ExcelFile, "parse", parser)

        expected_defaults = {
            "xlsx": "openpyxl",
            "xlsm": "openpyxl",
            "xlsb": "pyxlsb",
            "xls": "xlrd",
            "ods": "odf",
        }

        with open("test1" + read_ext, "rb") as f:
            result = pd.read_excel(f)

        if engine is not None:
            expected = engine
        else:
            expected = expected_defaults[read_ext[1:]]
        assert result == expected

    def test_engine_kwargs(self, read_ext, engine):
        # GH#52214
        expected_defaults = {
            "xlsx": {"foo": "abcd"},
            "xlsm": {"foo": 123},
            "xlsb": {"foo": "True"},
            "xls": {"foo": True},
            "ods": {"foo": "abcd"},
        }

        if engine in {"xlrd", "pyxlsb"}:
            msg = re.escape(r"open_workbook() got an unexpected keyword argument 'foo'")
        elif engine == "odf":
            msg = re.escape(r"load() got an unexpected keyword argument 'foo'")
        else:
            msg = re.escape(r"load_workbook() got an unexpected keyword argument 'foo'")

        if engine is not None:
            with pytest.raises(TypeError, match=msg):
                pd.read_excel(
                    "test1" + read_ext,
                    sheet_name="Sheet1",
                    index_col=0,
                    engine_kwargs=expected_defaults[read_ext[1:]],
                )

    def test_usecols_int(self, read_ext):
        # usecols as int
        msg = "Passing an integer for `usecols`"
        with pytest.raises(ValueError, match=msg):
            pd.read_excel(
                "test1" + read_ext, sheet_name="Sheet1", index_col=0, usecols=3
            )

        # usecols as int
        with pytest.raises(ValueError, match=msg):
            pd.read_excel(
                "test1" + read_ext,
                sheet_name="Sheet2",
                skiprows=[1],
                index_col=0,
                usecols=3,
            )

    def test_usecols_list(self, request, engine, read_ext, df_ref):
        xfail_datetimes_with_pyxlsb(engine, request)

        expected = df_ref[["B", "C"]]
        adjust_expected(expected, read_ext, engine)

        df1 = pd.read_excel(
            "test1" + read_ext, sheet_name="Sheet1", index_col=0, usecols=[0, 2, 3]
        )
        df2 = pd.read_excel(
            "test1" + read_ext,
            sheet_name="Sheet2",
            skiprows=[1],
            index_col=0,
            usecols=[0, 2, 3],
        )

        # TODO add index to xls file)
        tm.assert_frame_equal(df1, expected)
        tm.assert_frame_equal(df2, expected)

    def test_usecols_str(self, request, engine, read_ext, df_ref):
        xfail_datetimes_with_pyxlsb(engine, request)

        expected = df_ref[["A", "B", "C"]]
        adjust_expected(expected, read_ext, engine)

        df2 = pd.read_excel(
            "test1" + read_ext, sheet_name="Sheet1", index_col=0, usecols="A:D"
        )
        df3 = pd.read_excel(
            "test1" + read_ext,
            sheet_name="Sheet2",
            skiprows=[1],
            index_col=0,
            usecols="A:D",
        )

        # TODO add index to xls, read xls ignores index name ?
        tm.assert_frame_equal(df2, expected)
        tm.assert_frame_equal(df3, expected)

        expected = df_ref[["B", "C"]]
        adjust_expected(expected, read_ext, engine)

        df2 = pd.read_excel(
            "test1" + read_ext, sheet_name="Sheet1", index_col=0, usecols="A,C,D"
        )
        df3 = pd.read_excel(
            "test1" + read_ext,
            sheet_name="Sheet2",
            skiprows=[1],
            index_col=0,
            usecols="A,C,D",
        )
        # TODO add index to xls file
        tm.assert_frame_equal(df2, expected)
        tm.assert_frame_equal(df3, expected)

        df2 = pd.read_excel(
            "test1" + read_ext, sheet_name="Sheet1", index_col=0, usecols="A,C:D"
        )
        df3 = pd.read_excel(
            "test1" + read_ext,
            sheet_name="Sheet2",
            skiprows=[1],
            index_col=0,
            usecols="A,C:D",
        )
        tm.assert_frame_equal(df2, expected)
        tm.assert_frame_equal(df3, expected)

    @pytest.mark.parametrize(
        "usecols", [[0, 1, 3], [0, 3, 1], [1, 0, 3], [1, 3, 0], [3, 0, 1], [3, 1, 0]]
    )
    def test_usecols_diff_positional_int_columns_order(
        self, request, engine, read_ext, usecols, df_ref
    ):
        xfail_datetimes_with_pyxlsb(engine, request)

        expected = df_ref[["A", "C"]]
        adjust_expected(expected, read_ext, engine)

        result = pd.read_excel(
            "test1" + read_ext, sheet_name="Sheet1", index_col=0, usecols=usecols
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("usecols", [["B", "D"], ["D", "B"]])
    def test_usecols_diff_positional_str_columns_order(self, read_ext, usecols, df_ref):
        expected = df_ref[["B", "D"]]
        expected.index = range(len(expected))

        result = pd.read_excel("test1" + read_ext, sheet_name="Sheet1", usecols=usecols)
        tm.assert_frame_equal(result, expected)

    def test_read_excel_without_slicing(self, request, engine, read_ext, df_ref):
        xfail_datetimes_with_pyxlsb(engine, request)

        expected = df_ref
        adjust_expected(expected, read_ext, engine)

        result = pd.read_excel("test1" + read_ext, sheet_name="Sheet1", index_col=0)
        tm.assert_frame_equal(result, expected)

    def test_usecols_excel_range_str(self, request, engine, read_ext, df_ref):
        xfail_datetimes_with_pyxlsb(engine, request)

        expected = df_ref[["C", "D"]]
        adjust_expected(expected, read_ext, engine)

        result = pd.read_excel(
            "test1" + read_ext, sheet_name="Sheet1", index_col=0, usecols="A,D:E"
        )
        tm.assert_frame_equal(result, expected)

    def test_usecols_excel_range_str_invalid(self, read_ext):
        msg = "Invalid column name: E1"

        with pytest.raises(ValueError, match=msg):
            pd.read_excel("test1" + read_ext, sheet_name="Sheet1", usecols="D:E1")

    def test_index_col_label_error(self, read_ext):
        msg = "list indices must be integers.*, not str"

        with pytest.raises(TypeError, match=msg):
            pd.read_excel(
                "test1" + read_ext,
                sheet_name="Sheet1",
                index_col=["A"],
                usecols=["A", "C"],
            )

    def test_index_col_str(self, read_ext):
        # see gh-52716
        result = pd.read_excel("test1" + read_ext, sheet_name="Sheet3", index_col="A")
        expected = DataFrame(
            columns=["B", "C", "D", "E", "F"], index=Index([], name="A")
        )
        tm.assert_frame_equal(result, expected)

    def test_index_col_empty(self, read_ext):
        # see gh-9208
        result = pd.read_excel(
            "test1" + read_ext, sheet_name="Sheet3", index_col=["A", "B", "C"]
        )
        expected = DataFrame(
            columns=["D", "E", "F"],
            index=MultiIndex(levels=[[]] * 3, codes=[[]] * 3, names=["A", "B", "C"]),
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("index_col", [None, 2])
    def test_index_col_with_unnamed(self, read_ext, index_col):
        # see gh-18792
        result = pd.read_excel(
            "test1" + read_ext, sheet_name="Sheet4", index_col=index_col
        )
        expected = DataFrame(
            [["i1", "a", "x"], ["i2", "b", "y"]], columns=["Unnamed: 0", "col1", "col2"]
        )
        if index_col:
            expected = expected.set_index(expected.columns[index_col])

        tm.assert_frame_equal(result, expected)

    def test_usecols_pass_non_existent_column(self, read_ext):
        msg = (
            "Usecols do not match columns, "
            "columns expected but not found: "
            r"\['E'\]"
        )

        with pytest.raises(ValueError, match=msg):
            pd.read_excel("test1" + read_ext, usecols=["E"])

    def test_usecols_wrong_type(self, read_ext):
        msg = (
            "'usecols' must either be list-like of "
            "all strings, all unicode, all integers or a callable."
        )

        with pytest.raises(ValueError, match=msg):
            pd.read_excel("test1" + read_ext, usecols=["E1", 0])

    def test_excel_stop_iterator(self, read_ext):
        parsed = pd.read_excel("test2" + read_ext, sheet_name="Sheet1")
        expected = DataFrame([["aaaa", "bbbbb"]], columns=["Test", "Test1"])
        tm.assert_frame_equal(parsed, expected)

    def test_excel_cell_error_na(self, request, engine, read_ext):
        xfail_datetimes_with_pyxlsb(engine, request)

        # https://github.com/tafia/calamine/issues/355
        if engine == "calamine" and read_ext == ".ods":
            request.applymarker(
                pytest.mark.xfail(reason="Calamine can't extract error from ods files")
            )

        parsed = pd.read_excel("test3" + read_ext, sheet_name="Sheet1")
        expected = DataFrame([[np.nan]], columns=["Test"])
        tm.assert_frame_equal(parsed, expected)

    def test_excel_table(self, request, engine, read_ext, df_ref):
        xfail_datetimes_with_pyxlsb(engine, request)

        expected = df_ref
        adjust_expected(expected, read_ext, engine)

        df1 = pd.read_excel("test1" + read_ext, sheet_name="Sheet1", index_col=0)
        df2 = pd.read_excel(
            "test1" + read_ext, sheet_name="Sheet2", skiprows=[1], index_col=0
        )
        # TODO add index to file
        tm.assert_frame_equal(df1, expected)
        tm.assert_frame_equal(df2, expected)

        df3 = pd.read_excel(
            "test1" + read_ext, sheet_name="Sheet1", index_col=0, skipfooter=1
        )
        tm.assert_frame_equal(df3, df1.iloc[:-1])

    def test_reader_special_dtypes(self, request, engine, read_ext):
        xfail_datetimes_with_pyxlsb(engine, request)

        unit = get_exp_unit(read_ext, engine)
        expected = DataFrame.from_dict(
            {
                "IntCol": [1, 2, -3, 4, 0],
                "FloatCol": [1.25, 2.25, 1.83, 1.92, 0.0000000005],
                "BoolCol": [True, False, True, True, False],
                "StrCol": [1, 2, 3, 4, 5],
                "Str2Col": ["a", 3, "c", "d", "e"],
                "DateCol": Index(
                    [
                        datetime(2013, 10, 30),
                        datetime(2013, 10, 31),
                        datetime(1905, 1, 1),
                        datetime(2013, 12, 14),
                        datetime(2015, 3, 14),
                    ],
                    dtype=f"M8[{unit}]",
                ),
            },
        )
        basename = "test_types"

        # should read in correctly and infer types
        actual = pd.read_excel(basename + read_ext, sheet_name="Sheet1")
        tm.assert_frame_equal(actual, expected)

        # if not coercing number, then int comes in as float
        float_expected = expected.copy()
        float_expected.loc[float_expected.index[1], "Str2Col"] = 3.0
        actual = pd.read_excel(basename + read_ext, sheet_name="Sheet1")
        tm.assert_frame_equal(actual, float_expected)

        # check setting Index (assuming xls and xlsx are the same here)
        for icol, name in enumerate(expected.columns):
            actual = pd.read_excel(
                basename + read_ext, sheet_name="Sheet1", index_col=icol
            )
            exp = expected.set_index(name)
            tm.assert_frame_equal(actual, exp)

        expected["StrCol"] = expected["StrCol"].apply(str)
        actual = pd.read_excel(
            basename + read_ext, sheet_name="Sheet1", converters={"StrCol": str}
        )
        tm.assert_frame_equal(actual, expected)

    # GH8212 - support for converters and missing values
    def test_reader_converters(self, read_ext):
        basename = "test_converters"

        expected = DataFrame.from_dict(
            {
                "IntCol": [1, 2, -3, -1000, 0],
                "FloatCol": [12.5, np.nan, 18.3, 19.2, 0.000000005],
                "BoolCol": ["Found", "Found", "Found", "Not found", "Found"],
                "StrCol": ["1", np.nan, "3", "4", "5"],
            }
        )

        converters = {
            "IntCol": lambda x: int(x) if x != "" else -1000,
            "FloatCol": lambda x: 10 * x if x else np.nan,
            2: lambda x: "Found" if x != "" else "Not found",
            3: lambda x: str(x) if x else "",
        }

        # should read in correctly and set types of single cells (not array
        # dtypes)
        actual = pd.read_excel(
            basename + read_ext, sheet_name="Sheet1", converters=converters
        )
        tm.assert_frame_equal(actual, expected)

    def test_reader_dtype(self, read_ext):
        # GH 8212
        basename = "testdtype"
        actual = pd.read_excel(basename + read_ext)

        expected = DataFrame(
            {
                "a": [1, 2, 3, 4],
                "b": [2.5, 3.5, 4.5, 5.5],
                "c": [1, 2, 3, 4],
                "d": [1.0, 2.0, np.nan, 4.0],
            }
        )

        tm.assert_frame_equal(actual, expected)

        actual = pd.read_excel(
            basename + read_ext, dtype={"a": "float64", "b": "float32", "c": str}
        )

        expected["a"] = expected["a"].astype("float64")
        expected["b"] = expected["b"].astype("float32")
        expected["c"] = Series(["001", "002", "003", "004"], dtype="str")
        tm.assert_frame_equal(actual, expected)

        msg = "Unable to convert column d to type int64"
        with pytest.raises(ValueError, match=msg):
            pd.read_excel(basename + read_ext, dtype={"d": "int64"})

    @pytest.mark.parametrize(
        "dtype,expected",
        [
            (
                None,
                DataFrame(
                    {
                        "a": [1, 2, 3, 4],
                        "b": [2.5, 3.5, 4.5, 5.5],
                        "c": [1, 2, 3, 4],
                        "d": [1.0, 2.0, np.nan, 4.0],
                    }
                ),
            ),
            (
                {"a": "float64", "b": "float32", "c": str, "d": str},
                DataFrame(
                    {
                        "a": Series([1, 2, 3, 4], dtype="float64"),
                        "b": Series([2.5, 3.5, 4.5, 5.5], dtype="float32"),
                        "c": Series(["001", "002", "003", "004"], dtype="str"),
                        "d": Series(["1", "2", np.nan, "4"], dtype="str"),
                    },
                ),
            ),
        ],
    )
    def test_reader_dtype_str(self, read_ext, dtype, expected):
        # see gh-20377
        basename = "testdtype"

        actual = pd.read_excel(basename + read_ext, dtype=dtype)
        tm.assert_frame_equal(actual, expected)

    def test_dtype_backend(self, read_ext, dtype_backend, engine):
        # GH#36712
        if read_ext in (".xlsb", ".xls"):
            pytest.skip(f"No engine for filetype: '{read_ext}'")

        df = DataFrame(
            {
                "a": Series([1, 3], dtype="Int64"),
                "b": Series([2.5, 4.5], dtype="Float64"),
                "c": Series([True, False], dtype="boolean"),
                "d": Series(["a", "b"], dtype="string"),
                "e": Series([pd.NA, 6], dtype="Int64"),
                "f": Series([pd.NA, 7.5], dtype="Float64"),
                "g": Series([pd.NA, True], dtype="boolean"),
                "h": Series([pd.NA, "a"], dtype="string"),
                "i": Series([pd.Timestamp("2019-12-31")] * 2),
                "j": Series([pd.NA, pd.NA], dtype="Int64"),
            }
        )
        with tm.ensure_clean(read_ext) as file_path:
            df.to_excel(file_path, sheet_name="test", index=False)
            result = pd.read_excel(
                file_path, sheet_name="test", dtype_backend=dtype_backend
            )
        if dtype_backend == "pyarrow":
            import pyarrow as pa

            from pandas.arrays import ArrowExtensionArray

            expected = DataFrame(
                {
                    col: ArrowExtensionArray(pa.array(df[col], from_pandas=True))
                    for col in df.columns
                }
            )
            # pyarrow by default infers timestamp resolution as us, not ns
            expected["i"] = ArrowExtensionArray(
                expected["i"].array._pa_array.cast(pa.timestamp(unit="us"))
            )
            # pyarrow supports a null type, so don't have to default to Int64
            expected["j"] = ArrowExtensionArray(pa.array([None, None]))
        else:
            expected = df
            unit = get_exp_unit(read_ext, engine)
            expected["i"] = expected["i"].astype(f"M8[{unit}]")

        tm.assert_frame_equal(result, expected)

    def test_dtype_backend_and_dtype(self, read_ext):
        # GH#36712
        if read_ext in (".xlsb", ".xls"):
            pytest.skip(f"No engine for filetype: '{read_ext}'")

        df = DataFrame({"a": [np.nan, 1.0], "b": [2.5, np.nan]})
        with tm.ensure_clean(read_ext) as file_path:
            df.to_excel(file_path, sheet_name="test", index=False)
            result = pd.read_excel(
                file_path,
                sheet_name="test",
                dtype_backend="numpy_nullable",
                dtype="float64",
            )
        tm.assert_frame_equal(result, df)

    def test_dtype_backend_string(self, read_ext, string_storage):
        # GH#36712
        if read_ext in (".xlsb", ".xls"):
            pytest.skip(f"No engine for filetype: '{read_ext}'")

        with pd.option_context("mode.string_storage", string_storage):
            df = DataFrame(
                {
                    "a": np.array(["a", "b"], dtype=np.object_),
                    "b": np.array(["x", pd.NA], dtype=np.object_),
                }
            )

            with tm.ensure_clean(read_ext) as file_path:
                df.to_excel(file_path, sheet_name="test", index=False)
                result = pd.read_excel(
                    file_path, sheet_name="test", dtype_backend="numpy_nullable"
                )

            expected = DataFrame(
                {
                    "a": Series(["a", "b"], dtype=pd.StringDtype(string_storage)),
                    "b": Series(["x", None], dtype=pd.StringDtype(string_storage)),
                }
            )
            # the storage of the str columns' Index is also affected by the
            # string_storage setting -> ignore that for checking the result
            tm.assert_frame_equal(result, expected, check_column_type=False)

    @pytest.mark.parametrize("dtypes, exp_value", [({}, 1), ({"a.1": "int64"}, 1)])
    def test_dtype_mangle_dup_cols(self, read_ext, dtypes, exp_value):
        # GH#35211
        basename = "df_mangle_dup_col_dtypes"
        dtype_dict = {"a": object, **dtypes}
        dtype_dict_copy = dtype_dict.copy()
        # GH#42462
        result = pd.read_excel(basename + read_ext, dtype=dtype_dict)
        expected = DataFrame(
            {
                "a": Series([1], dtype=object),
                "a.1": Series([exp_value], dtype=object if not dtypes else None),
            }
        )
        assert dtype_dict == dtype_dict_copy, "dtype dict changed"
        tm.assert_frame_equal(result, expected)

    def test_reader_spaces(self, read_ext):
        # see gh-32207
        basename = "test_spaces"

        actual = pd.read_excel(basename + read_ext)
        expected = DataFrame(
            {
                "testcol": [
                    "this is great",
                    "4    spaces",
                    "1 trailing ",
                    " 1 leading",
                    "2  spaces  multiple  times",
                ]
            }
        )
        tm.assert_frame_equal(actual, expected)

    # gh-36122, gh-35802
    @pytest.mark.parametrize(
        "basename,expected",
        [
            ("gh-35802", DataFrame({"COLUMN": ["Test (1)"]})),
            ("gh-36122", DataFrame(columns=["got 2nd sa"])),
        ],
    )
    def test_read_excel_ods_nested_xml(self, engine, read_ext, basename, expected):
        # see gh-35802
        if engine != "odf":
            pytest.skip(f"Skipped for engine: {engine}")

        actual = pd.read_excel(basename + read_ext)
        tm.assert_frame_equal(actual, expected)

    def test_reading_all_sheets(self, read_ext):
        # Test reading all sheet names by setting sheet_name to None,
        # Ensure a dict is returned.
        # See PR #9450
        basename = "test_multisheet"
        dfs = pd.read_excel(basename + read_ext, sheet_name=None)
        # ensure this is not alphabetical to test order preservation
        expected_keys = ["Charlie", "Alpha", "Beta"]
        tm.assert_contains_all(expected_keys, dfs.keys())
        # Issue 9930
        # Ensure sheet order is preserved
        assert expected_keys == list(dfs.keys())

    def test_reading_multiple_specific_sheets(self, read_ext):
        # Test reading specific sheet names by specifying a mixed list
        # of integers and strings, and confirm that duplicated sheet
        # references (positions/names) are removed properly.
        # Ensure a dict is returned
        # See PR #9450
        basename = "test_multisheet"
        # Explicitly request duplicates. Only the set should be returned.
        expected_keys = [2, "Charlie", "Charlie"]
        dfs = pd.read_excel(basename + read_ext, sheet_name=expected_keys)
        expected_keys = list(set(expected_keys))
        tm.assert_contains_all(expected_keys, dfs.keys())
        assert len(expected_keys) == len(dfs.keys())

    def test_reading_all_sheets_with_blank(self, read_ext):
        # Test reading all sheet names by setting sheet_name to None,
        # In the case where some sheets are blank.
        # Issue #11711
        basename = "blank_with_header"
        dfs = pd.read_excel(basename + read_ext, sheet_name=None)
        expected_keys = ["Sheet1", "Sheet2", "Sheet3"]
        tm.assert_contains_all(expected_keys, dfs.keys())

    # GH6403
    def test_read_excel_blank(self, read_ext):
        actual = pd.read_excel("blank" + read_ext, sheet_name="Sheet1")
        tm.assert_frame_equal(actual, DataFrame())

    def test_read_excel_blank_with_header(self, read_ext):
        expected = DataFrame(columns=["col_1", "col_2"])
        actual = pd.read_excel("blank_with_header" + read_ext, sheet_name="Sheet1")
        tm.assert_frame_equal(actual, expected)

    def test_exception_message_includes_sheet_name(self, read_ext):
        # GH 48706
        with pytest.raises(ValueError, match=r" \(sheet: Sheet1\)$"):
            pd.read_excel("blank_with_header" + read_ext, header=[1], sheet_name=None)
        with pytest.raises(ZeroDivisionError, match=r" \(sheet: Sheet1\)$"):
            pd.read_excel("test1" + read_ext, usecols=lambda x: 1 / 0, sheet_name=None)

    @pytest.mark.filterwarnings("ignore:Cell A4 is marked:UserWarning:openpyxl")
    def test_date_conversion_overflow(self, request, engine, read_ext):
        # GH 10001 : pandas.ExcelFile ignore parse_dates=False
        xfail_datetimes_with_pyxlsb(engine, request)

        expected = DataFrame(
            [
                [pd.Timestamp("2016-03-12"), "Marc Johnson"],
                [pd.Timestamp("2016-03-16"), "Jack Black"],
                [1e20, "Timothy Brown"],
            ],
            columns=["DateColWithBigInt", "StringCol"],
        )

        if engine == "openpyxl":
            request.applymarker(
                pytest.mark.xfail(reason="Maybe not supported by openpyxl")
            )

        if engine is None and read_ext in (".xlsx", ".xlsm"):
            # GH 35029
            request.applymarker(
                pytest.mark.xfail(reason="Defaults to openpyxl, maybe not supported")
            )

        result = pd.read_excel("testdateoverflow" + read_ext)
        tm.assert_frame_equal(result, expected)

    def test_sheet_name(self, request, read_ext, engine, df_ref):
        xfail_datetimes_with_pyxlsb(engine, request)

        filename = "test1"
        sheet_name = "Sheet1"

        expected = df_ref
        adjust_expected(expected, read_ext, engine)

        df1 = pd.read_excel(
            filename + read_ext, sheet_name=sheet_name, index_col=0
        )  # doc
        df2 = pd.read_excel(filename + read_ext, index_col=0, sheet_name=sheet_name)

        tm.assert_frame_equal(df1, expected)
        tm.assert_frame_equal(df2, expected)

    def test_excel_read_buffer(self, read_ext):
        pth = "test1" + read_ext
        expected = pd.read_excel(pth, sheet_name="Sheet1", index_col=0)
        with open(pth, "rb") as f:
            actual = pd.read_excel(f, sheet_name="Sheet1", index_col=0)
            tm.assert_frame_equal(expected, actual)

    def test_bad_engine_raises(self):
        bad_engine = "foo"
        with pytest.raises(ValueError, match="Unknown engine: foo"):
            pd.read_excel("", engine=bad_engine)

    @pytest.mark.parametrize(
        "sheet_name",
        [3, [0, 3], [3, 0], "Sheet4", ["Sheet1", "Sheet4"], ["Sheet4", "Sheet1"]],
    )
    def test_bad_sheetname_raises(self, read_ext, sheet_name):
        # GH 39250
        msg = "Worksheet index 3 is invalid|Worksheet named 'Sheet4' not found"
        with pytest.raises(ValueError, match=msg):
            pd.read_excel("blank" + read_ext, sheet_name=sheet_name)

    def test_missing_file_raises(self, read_ext):
        bad_file = f"foo{read_ext}"
        # CI tests with other languages, translates to "No such file or directory"
        match = "|".join(
            [
                "(No such file or directory",
                "没有那个文件或目录",
                "File o directory non esistente)",
            ]
        )
        with pytest.raises(FileNotFoundError, match=match):
            pd.read_excel(bad_file)

    def test_corrupt_bytes_raises(self, engine):
        bad_stream = b"foo"
        if engine is None:
            error = ValueError
            msg = (
                "Excel file format cannot be determined, you must "
                "specify an engine manually."
            )
        elif engine == "xlrd":
            from xlrd import XLRDError

            error = XLRDError
            msg = (
                "Unsupported format, or corrupt file: Expected BOF "
                "record; found b'foo'"
            )
        elif engine == "calamine":
            from python_calamine import CalamineError

            error = CalamineError
            msg = "Cannot detect file format"
        else:
            error = BadZipFile
            msg = "File is not a zip file"
        with pytest.raises(error, match=msg):
            pd.read_excel(BytesIO(bad_stream))

    @pytest.mark.network
    @pytest.mark.single_cpu
    def test_read_from_http_url(self, httpserver, read_ext):
        with open("test1" + read_ext, "rb") as f:
            httpserver.serve_content(content=f.read())
        url_table = pd.read_excel(httpserver.url)
        local_table = pd.read_excel("test1" + read_ext)
        tm.assert_frame_equal(url_table, local_table)

    @td.skip_if_not_us_locale
    @pytest.mark.single_cpu
    def test_read_from_s3_url(self, read_ext, s3_public_bucket, s3so):
        # Bucket created in tests/io/conftest.py
        with open("test1" + read_ext, "rb") as f:
            s3_public_bucket.put_object(Key="test1" + read_ext, Body=f)

        url = f"s3://{s3_public_bucket.name}/test1" + read_ext

        url_table = pd.read_excel(url, storage_options=s3so)
        local_table = pd.read_excel("test1" + read_ext)
        tm.assert_frame_equal(url_table, local_table)

    @pytest.mark.single_cpu
    def test_read_from_s3_object(self, read_ext, s3_public_bucket, s3so):
        # GH 38788
        # Bucket created in tests/io/conftest.py
        with open("test1" + read_ext, "rb") as f:
            s3_public_bucket.put_object(Key="test1" + read_ext, Body=f)

        import s3fs

        s3 = s3fs.S3FileSystem(**s3so)

        with s3.open(f"s3://{s3_public_bucket.name}/test1" + read_ext) as f:
            url_table = pd.read_excel(f)

        local_table = pd.read_excel("test1" + read_ext)
        tm.assert_frame_equal(url_table, local_table)

    @pytest.mark.slow
    def test_read_from_file_url(self, read_ext, datapath):
        # FILE
        localtable = os.path.join(datapath("io", "data", "excel"), "test1" + read_ext)
        local_table = pd.read_excel(localtable)

        try:
            url_table = pd.read_excel("file://localhost/" + localtable)
        except URLError:
            # fails on some systems
            platform_info = " ".join(platform.uname()).strip()
            pytest.skip(f"failing on {platform_info}")

        tm.assert_frame_equal(url_table, local_table)

    def test_read_from_pathlib_path(self, read_ext):
        # GH12655
        str_path = "test1" + read_ext
        expected = pd.read_excel(str_path, sheet_name="Sheet1", index_col=0)

        path_obj = Path("test1" + read_ext)
        actual = pd.read_excel(path_obj, sheet_name="Sheet1", index_col=0)

        tm.assert_frame_equal(expected, actual)

    @td.skip_if_no("py.path")
    def test_read_from_py_localpath(self, read_ext):
        # GH12655
        from py.path import local as LocalPath

        str_path = os.path.join("test1" + read_ext)
        expected = pd.read_excel(str_path, sheet_name="Sheet1", index_col=0)

        path_obj = LocalPath().join("test1" + read_ext)
        actual = pd.read_excel(path_obj, sheet_name="Sheet1", index_col=0)

        tm.assert_frame_equal(expected, actual)

    def test_close_from_py_localpath(self, read_ext):
        # GH31467
        str_path = os.path.join("test1" + read_ext)
        with open(str_path, "rb") as f:
            x = pd.read_excel(f, sheet_name="Sheet1", index_col=0)
            del x
            # should not throw an exception because the passed file was closed
            f.read()

    def test_reader_seconds(self, request, engine, read_ext):
        xfail_datetimes_with_pyxlsb(engine, request)

        # GH 55045
        if engine == "calamine" and read_ext == ".ods":
            request.applymarker(
                pytest.mark.xfail(
                    reason="ODS file contains bad datetime (seconds as text)"
                )
            )

        # Test reading times with and without milliseconds. GH5945.
        expected = DataFrame.from_dict(
            {
                "Time": [
                    time(1, 2, 3),
                    time(2, 45, 56, 100000),
                    time(4, 29, 49, 200000),
                    time(6, 13, 42, 300000),
                    time(7, 57, 35, 400000),
                    time(9, 41, 28, 500000),
                    time(11, 25, 21, 600000),
                    time(13, 9, 14, 700000),
                    time(14, 53, 7, 800000),
                    time(16, 37, 0, 900000),
                    time(18, 20, 54),
                ]
            }
        )

        actual = pd.read_excel("times_1900" + read_ext, sheet_name="Sheet1")
        tm.assert_frame_equal(actual, expected)

        actual = pd.read_excel("times_1904" + read_ext, sheet_name="Sheet1")
        tm.assert_frame_equal(actual, expected)

    def test_read_excel_multiindex(self, request, engine, read_ext):
        # see gh-4679
        xfail_datetimes_with_pyxlsb(engine, request)

        unit = get_exp_unit(read_ext, engine)

        mi = MultiIndex.from_product([["foo", "bar"], ["a", "b"]])
        mi_file = "testmultiindex" + read_ext

        # "mi_column" sheet
        expected = DataFrame(
            [
                [1, 2.5, pd.Timestamp("2015-01-01"), True],
                [2, 3.5, pd.Timestamp("2015-01-02"), False],
                [3, 4.5, pd.Timestamp("2015-01-03"), False],
                [4, 5.5, pd.Timestamp("2015-01-04"), True],
            ],
            columns=mi,
        )
        expected[mi[2]] = expected[mi[2]].astype(f"M8[{unit}]")

        actual = pd.read_excel(
            mi_file, sheet_name="mi_column", header=[0, 1], index_col=0
        )
        tm.assert_frame_equal(actual, expected)

        # "mi_index" sheet
        expected.index = mi
        expected.columns = ["a", "b", "c", "d"]

        actual = pd.read_excel(mi_file, sheet_name="mi_index", index_col=[0, 1])
        tm.assert_frame_equal(actual, expected)

        # "both" sheet
        expected.columns = mi

        actual = pd.read_excel(
            mi_file, sheet_name="both", index_col=[0, 1], header=[0, 1]
        )
        tm.assert_frame_equal(actual, expected)

        # "mi_index_name" sheet
        expected.columns = ["a", "b", "c", "d"]
        expected.index = mi.set_names(["ilvl1", "ilvl2"])

        actual = pd.read_excel(mi_file, sheet_name="mi_index_name", index_col=[0, 1])
        tm.assert_frame_equal(actual, expected)

        # "mi_column_name" sheet
        expected.index = list(range(4))
        expected.columns = mi.set_names(["c1", "c2"])
        actual = pd.read_excel(
            mi_file, sheet_name="mi_column_name", header=[0, 1], index_col=0
        )
        tm.assert_frame_equal(actual, expected)

        # see gh-11317
        # "name_with_int" sheet
        expected.columns = mi.set_levels([1, 2], level=1).set_names(["c1", "c2"])

        actual = pd.read_excel(
            mi_file, sheet_name="name_with_int", index_col=0, header=[0, 1]
        )
        tm.assert_frame_equal(actual, expected)

        # "both_name" sheet
        expected.columns = mi.set_names(["c1", "c2"])
        expected.index = mi.set_names(["ilvl1", "ilvl2"])

        actual = pd.read_excel(
            mi_file, sheet_name="both_name", index_col=[0, 1], header=[0, 1]
        )
        tm.assert_frame_equal(actual, expected)

        # "both_skiprows" sheet
        actual = pd.read_excel(
            mi_file,
            sheet_name="both_name_skiprows",
            index_col=[0, 1],
            header=[0, 1],
            skiprows=2,
        )
        tm.assert_frame_equal(actual, expected)

    @pytest.mark.parametrize(
        "sheet_name,idx_lvl2",
        [
            ("both_name_blank_after_mi_name", [np.nan, "b", "a", "b"]),
            ("both_name_multiple_blanks", [np.nan] * 4),
        ],
    )
    def test_read_excel_multiindex_blank_after_name(
        self, request, engine, read_ext, sheet_name, idx_lvl2
    ):
        # GH34673
        xfail_datetimes_with_pyxlsb(engine, request)

        mi_file = "testmultiindex" + read_ext
        mi = MultiIndex.from_product([["foo", "bar"], ["a", "b"]], names=["c1", "c2"])

        unit = get_exp_unit(read_ext, engine)

        expected = DataFrame(
            [
                [1, 2.5, pd.Timestamp("2015-01-01"), True],
                [2, 3.5, pd.Timestamp("2015-01-02"), False],
                [3, 4.5, pd.Timestamp("2015-01-03"), False],
                [4, 5.5, pd.Timestamp("2015-01-04"), True],
            ],
            columns=mi,
            index=MultiIndex.from_arrays(
                (["foo", "foo", "bar", "bar"], idx_lvl2),
                names=["ilvl1", "ilvl2"],
            ),
        )
        expected[mi[2]] = expected[mi[2]].astype(f"M8[{unit}]")
        result = pd.read_excel(
            mi_file,
            sheet_name=sheet_name,
            index_col=[0, 1],
            header=[0, 1],
        )
        tm.assert_frame_equal(result, expected)

    def test_read_excel_multiindex_header_only(self, read_ext):
        # see gh-11733.
        #
        # Don't try to parse a header name if there isn't one.
        mi_file = "testmultiindex" + read_ext
        result = pd.read_excel(mi_file, sheet_name="index_col_none", header=[0, 1])

        exp_columns = MultiIndex.from_product([("A", "B"), ("key", "val")])
        expected = DataFrame([[1, 2, 3, 4]] * 2, columns=exp_columns)
        tm.assert_frame_equal(result, expected)

    def test_excel_old_index_format(self, read_ext):
        # see gh-4679
        filename = "test_index_name_pre17" + read_ext

        # We detect headers to determine if index names exist, so
        # that "index" name in the "names" version of the data will
        # now be interpreted as rows that include null data.
        data = np.array(
            [
                [np.nan, np.nan, np.nan, np.nan, np.nan],
                ["R0C0", "R0C1", "R0C2", "R0C3", "R0C4"],
                ["R1C0", "R1C1", "R1C2", "R1C3", "R1C4"],
                ["R2C0", "R2C1", "R2C2", "R2C3", "R2C4"],
                ["R3C0", "R3C1", "R3C2", "R3C3", "R3C4"],
                ["R4C0", "R4C1", "R4C2", "R4C3", "R4C4"],
            ],
            dtype=object,
        )
        columns = ["C_l0_g0", "C_l0_g1", "C_l0_g2", "C_l0_g3", "C_l0_g4"]
        mi = MultiIndex(
            levels=[
                ["R0", "R_l0_g0", "R_l0_g1", "R_l0_g2", "R_l0_g3", "R_l0_g4"],
                ["R1", "R_l1_g0", "R_l1_g1", "R_l1_g2", "R_l1_g3", "R_l1_g4"],
            ],
            codes=[[0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4, 5]],
            names=[None, None],
        )
        si = Index(
            ["R0", "R_l0_g0", "R_l0_g1", "R_l0_g2", "R_l0_g3", "R_l0_g4"], name=None
        )

        expected = DataFrame(data, index=si, columns=columns)

        actual = pd.read_excel(filename, sheet_name="single_names", index_col=0)
        tm.assert_frame_equal(actual, expected)

        expected.index = mi

        actual = pd.read_excel(filename, sheet_name="multi_names", index_col=[0, 1])
        tm.assert_frame_equal(actual, expected)

        # The analogous versions of the "names" version data
        # where there are explicitly no names for the indices.
        data = np.array(
            [
                ["R0C0", "R0C1", "R0C2", "R0C3", "R0C4"],
                ["R1C0", "R1C1", "R1C2", "R1C3", "R1C4"],
                ["R2C0", "R2C1", "R2C2", "R2C3", "R2C4"],
                ["R3C0", "R3C1", "R3C2", "R3C3", "R3C4"],
                ["R4C0", "R4C1", "R4C2", "R4C3", "R4C4"],
            ]
        )
        columns = ["C_l0_g0", "C_l0_g1", "C_l0_g2", "C_l0_g3", "C_l0_g4"]
        mi = MultiIndex(
            levels=[
                ["R_l0_g0", "R_l0_g1", "R_l0_g2", "R_l0_g3", "R_l0_g4"],
                ["R_l1_g0", "R_l1_g1", "R_l1_g2", "R_l1_g3", "R_l1_g4"],
            ],
            codes=[[0, 1, 2, 3, 4], [0, 1, 2, 3, 4]],
            names=[None, None],
        )
        si = Index(["R_l0_g0", "R_l0_g1", "R_l0_g2", "R_l0_g3", "R_l0_g4"], name=None)

        expected = DataFrame(data, index=si, columns=columns)

        actual = pd.read_excel(filename, sheet_name="single_no_names", index_col=0)
        tm.assert_frame_equal(actual, expected)

        expected.index = mi

        actual = pd.read_excel(filename, sheet_name="multi_no_names", index_col=[0, 1])
        tm.assert_frame_equal(actual, expected)

    def test_read_excel_bool_header_arg(self, read_ext):
        # GH 6114
        msg = "Passing a bool to header is invalid"
        for arg in [True, False]:
            with pytest.raises(TypeError, match=msg):
                pd.read_excel("test1" + read_ext, header=arg)

    def test_read_excel_skiprows(self, request, engine, read_ext):
        # GH 4903
        xfail_datetimes_with_pyxlsb(engine, request)

        unit = get_exp_unit(read_ext, engine)

        actual = pd.read_excel(
            "testskiprows" + read_ext, sheet_name="skiprows_list", skiprows=[0, 2]
        )
        expected = DataFrame(
            [
                [1, 2.5, pd.Timestamp("2015-01-01"), True],
                [2, 3.5, pd.Timestamp("2015-01-02"), False],
                [3, 4.5, pd.Timestamp("2015-01-03"), False],
                [4, 5.5, pd.Timestamp("2015-01-04"), True],
            ],
            columns=["a", "b", "c", "d"],
        )
        expected["c"] = expected["c"].astype(f"M8[{unit}]")
        tm.assert_frame_equal(actual, expected)

        actual = pd.read_excel(
            "testskiprows" + read_ext,
            sheet_name="skiprows_list",
            skiprows=np.array([0, 2]),
        )
        tm.assert_frame_equal(actual, expected)

        # GH36435
        actual = pd.read_excel(
            "testskiprows" + read_ext,
            sheet_name="skiprows_list",
            skiprows=lambda x: x in [0, 2],
        )
        tm.assert_frame_equal(actual, expected)

        actual = pd.read_excel(
            "testskiprows" + read_ext,
            sheet_name="skiprows_list",
            skiprows=3,
            names=["a", "b", "c", "d"],
        )
        expected = DataFrame(
            [
                # [1, 2.5, pd.Timestamp("2015-01-01"), True],
                [2, 3.5, pd.Timestamp("2015-01-02"), False],
                [3, 4.5, pd.Timestamp("2015-01-03"), False],
                [4, 5.5, pd.Timestamp("2015-01-04"), True],
            ],
            columns=["a", "b", "c", "d"],
        )
        expected["c"] = expected["c"].astype(f"M8[{unit}]")
        tm.assert_frame_equal(actual, expected)

    def test_read_excel_skiprows_callable_not_in(self, request, engine, read_ext):
        # GH 4903
        xfail_datetimes_with_pyxlsb(engine, request)
        unit = get_exp_unit(read_ext, engine)

        actual = pd.read_excel(
            "testskiprows" + read_ext,
            sheet_name="skiprows_list",
            skiprows=lambda x: x not in [1, 3, 5],
        )
        expected = DataFrame(
            [
                [1, 2.5, pd.Timestamp("2015-01-01"), True],
                # [2, 3.5, pd.Timestamp("2015-01-02"), False],
                [3, 4.5, pd.Timestamp("2015-01-03"), False],
                # [4, 5.5, pd.Timestamp("2015-01-04"), True],
            ],
            columns=["a", "b", "c", "d"],
        )
        expected["c"] = expected["c"].astype(f"M8[{unit}]")
        tm.assert_frame_equal(actual, expected)

    def test_read_excel_nrows(self, read_ext):
        # GH 16645
        num_rows_to_pull = 5
        actual = pd.read_excel("test1" + read_ext, nrows=num_rows_to_pull)
        expected = pd.read_excel("test1" + read_ext)
        expected = expected[:num_rows_to_pull]
        tm.assert_frame_equal(actual, expected)

    def test_read_excel_nrows_greater_than_nrows_in_file(self, read_ext):
        # GH 16645
        expected = pd.read_excel("test1" + read_ext)
        num_records_in_file = len(expected)
        num_rows_to_pull = num_records_in_file + 10
        actual = pd.read_excel("test1" + read_ext, nrows=num_rows_to_pull)
        tm.assert_frame_equal(actual, expected)

    def test_read_excel_nrows_non_integer_parameter(self, read_ext):
        # GH 16645
        msg = "'nrows' must be an integer >=0"
        with pytest.raises(ValueError, match=msg):
            pd.read_excel("test1" + read_ext, nrows="5")

    @pytest.mark.parametrize(
        "filename,sheet_name,header,index_col,skiprows",
        [
            ("testmultiindex", "mi_column", [0, 1], 0, None),
            ("testmultiindex", "mi_index", None, [0, 1], None),
            ("testmultiindex", "both", [0, 1], [0, 1], None),
            ("testmultiindex", "mi_column_name", [0, 1], 0, None),
            ("testskiprows", "skiprows_list", None, None, [0, 2]),
            ("testskiprows", "skiprows_list", None, None, lambda x: x in (0, 2)),
        ],
    )
    def test_read_excel_nrows_params(
        self, read_ext, filename, sheet_name, header, index_col, skiprows
    ):
        """
        For various parameters, we should get the same result whether we
        limit the rows during load (nrows=3) or after (df.iloc[:3]).
        """
        # GH 46894
        expected = pd.read_excel(
            filename + read_ext,
            sheet_name=sheet_name,
            header=header,
            index_col=index_col,
            skiprows=skiprows,
        ).iloc[:3]
        actual = pd.read_excel(
            filename + read_ext,
            sheet_name=sheet_name,
            header=header,
            index_col=index_col,
            skiprows=skiprows,
            nrows=3,
        )
        tm.assert_frame_equal(actual, expected)

    def test_deprecated_kwargs(self, read_ext):
        with pytest.raises(TypeError, match="but 3 positional arguments"):
            pd.read_excel("test1" + read_ext, "Sheet1", 0)

    def test_no_header_with_list_index_col(self, read_ext):
        # GH 31783
        file_name = "testmultiindex" + read_ext
        data = [("B", "B"), ("key", "val"), (3, 4), (3, 4)]
        idx = MultiIndex.from_tuples(
            [("A", "A"), ("key", "val"), (1, 2), (1, 2)], names=(0, 1)
        )
        expected = DataFrame(data, index=idx, columns=(2, 3))
        result = pd.read_excel(
            file_name, sheet_name="index_col_none", index_col=[0, 1], header=None
        )
        tm.assert_frame_equal(expected, result)

    def test_one_col_noskip_blank_line(self, read_ext):
        # GH 39808
        file_name = "one_col_blank_line" + read_ext
        data = [0.5, np.nan, 1, 2]
        expected = DataFrame(data, columns=["numbers"])
        result = pd.read_excel(file_name)
        tm.assert_frame_equal(result, expected)

    def test_multiheader_two_blank_lines(self, read_ext):
        # GH 40442
        file_name = "testmultiindex" + read_ext
        columns = MultiIndex.from_tuples([("a", "A"), ("b", "B")])
        data = [[np.nan, np.nan], [np.nan, np.nan], [1, 3], [2, 4]]
        expected = DataFrame(data, columns=columns)
        result = pd.read_excel(
            file_name, sheet_name="mi_column_empty_rows", header=[0, 1]
        )
        tm.assert_frame_equal(result, expected)

    def test_trailing_blanks(self, read_ext):
        """
        Sheets can contain blank cells with no data. Some of our readers
        were including those cells, creating many empty rows and columns
        """
        file_name = "trailing_blanks" + read_ext
        result = pd.read_excel(file_name)
        assert result.shape == (3, 3)

    def test_ignore_chartsheets_by_str(self, request, engine, read_ext):
        # GH 41448
        if read_ext == ".ods":
            pytest.skip("chartsheets do not exist in the ODF format")
        if engine == "pyxlsb":
            request.applymarker(
                pytest.mark.xfail(
                    reason="pyxlsb can't distinguish chartsheets from worksheets"
                )
            )
        with pytest.raises(ValueError, match="Worksheet named 'Chart1' not found"):
            pd.read_excel("chartsheet" + read_ext, sheet_name="Chart1")

    def test_ignore_chartsheets_by_int(self, request, engine, read_ext):
        # GH 41448
        if read_ext == ".ods":
            pytest.skip("chartsheets do not exist in the ODF format")
        if engine == "pyxlsb":
            request.applymarker(
                pytest.mark.xfail(
                    reason="pyxlsb can't distinguish chartsheets from worksheets"
                )
            )
        with pytest.raises(
            ValueError, match="Worksheet index 1 is invalid, 1 worksheets found"
        ):
            pd.read_excel("chartsheet" + read_ext, sheet_name=1)

    def test_euro_decimal_format(self, read_ext):
        # copied from read_csv
        result = pd.read_excel("test_decimal" + read_ext, decimal=",", skiprows=1)
        expected = DataFrame(
            [
                [1, 1521.1541, 187101.9543, "ABC", "poi", 4.738797819],
                [2, 121.12, 14897.76, "DEF", "uyt", 0.377320872],
                [3, 878.158, 108013.434, "GHI", "rez", 2.735694704],
            ],
            columns=["Id", "Number1", "Number2", "Text1", "Text2", "Number3"],
        )
        tm.assert_frame_equal(result, expected)


class TestExcelFileRead:
    def test_deprecate_bytes_input(self, engine, read_ext):
        # GH 53830
        msg = (
            "Passing bytes to 'read_excel' is deprecated and "
            "will be removed in a future version. To read from a "
            "byte string, wrap it in a `BytesIO` object."
        )

        with tm.assert_produces_warning(
            FutureWarning, match=msg, raise_on_extra_warnings=False
        ):
            with open("test1" + read_ext, "rb") as f:
                pd.read_excel(f.read(), engine=engine)

    @pytest.fixture(autouse=True)
    def cd_and_set_engine(self, engine, datapath, monkeypatch):
        """
        Change directory and set engine for ExcelFile objects.
        """
        func = partial(pd.ExcelFile, engine=engine)
        monkeypatch.chdir(datapath("io", "data", "excel"))
        monkeypatch.setattr(pd, "ExcelFile", func)

    def test_engine_used(self, read_ext, engine):
        expected_defaults = {
            "xlsx": "openpyxl",
            "xlsm": "openpyxl",
            "xlsb": "pyxlsb",
            "xls": "xlrd",
            "ods": "odf",
        }

        with pd.ExcelFile("test1" + read_ext) as excel:
            result = excel.engine

        if engine is not None:
            expected = engine
        else:
            expected = expected_defaults[read_ext[1:]]
        assert result == expected

    def test_excel_passes_na(self, read_ext):
        with pd.ExcelFile("test4" + read_ext) as excel:
            parsed = pd.read_excel(
                excel, sheet_name="Sheet1", keep_default_na=False, na_values=["apple"]
            )
        expected = DataFrame(
            [["NA"], [1], ["NA"], [np.nan], ["rabbit"]], columns=["Test"]
        )
        tm.assert_frame_equal(parsed, expected)

        with pd.ExcelFile("test4" + read_ext) as excel:
            parsed = pd.read_excel(
                excel, sheet_name="Sheet1", keep_default_na=True, na_values=["apple"]
            )
        expected = DataFrame(
            [[np.nan], [1], [np.nan], [np.nan], ["rabbit"]], columns=["Test"]
        )
        tm.assert_frame_equal(parsed, expected)

        # 13967
        with pd.ExcelFile("test5" + read_ext) as excel:
            parsed = pd.read_excel(
                excel, sheet_name="Sheet1", keep_default_na=False, na_values=["apple"]
            )
        expected = DataFrame(
            [["1.#QNAN"], [1], ["nan"], [np.nan], ["rabbit"]], columns=["Test"]
        )
        tm.assert_frame_equal(parsed, expected)

        with pd.ExcelFile("test5" + read_ext) as excel:
            parsed = pd.read_excel(
                excel, sheet_name="Sheet1", keep_default_na=True, na_values=["apple"]
            )
        expected = DataFrame(
            [[np.nan], [1], [np.nan], [np.nan], ["rabbit"]], columns=["Test"]
        )
        tm.assert_frame_equal(parsed, expected)

    @pytest.mark.parametrize("na_filter", [None, True, False])
    def test_excel_passes_na_filter(self, read_ext, na_filter):
        # gh-25453
        kwargs = {}

        if na_filter is not None:
            kwargs["na_filter"] = na_filter

        with pd.ExcelFile("test5" + read_ext) as excel:
            parsed = pd.read_excel(
                excel,
                sheet_name="Sheet1",
                keep_default_na=True,
                na_values=["apple"],
                **kwargs,
            )

        if na_filter is False:
            expected = [["1.#QNAN"], [1], ["nan"], ["apple"], ["rabbit"]]
        else:
            expected = [[np.nan], [1], [np.nan], [np.nan], ["rabbit"]]

        expected = DataFrame(expected, columns=["Test"])
        tm.assert_frame_equal(parsed, expected)

    def test_excel_table_sheet_by_index(self, request, engine, read_ext, df_ref):
        xfail_datetimes_with_pyxlsb(engine, request)

        expected = df_ref
        adjust_expected(expected, read_ext, engine)

        with pd.ExcelFile("test1" + read_ext) as excel:
            df1 = pd.read_excel(excel, sheet_name=0, index_col=0)
            df2 = pd.read_excel(excel, sheet_name=1, skiprows=[1], index_col=0)
        tm.assert_frame_equal(df1, expected)
        tm.assert_frame_equal(df2, expected)

        with pd.ExcelFile("test1" + read_ext) as excel:
            df1 = excel.parse(0, index_col=0)
            df2 = excel.parse(1, skiprows=[1], index_col=0)
        tm.assert_frame_equal(df1, expected)
        tm.assert_frame_equal(df2, expected)

        with pd.ExcelFile("test1" + read_ext) as excel:
            df3 = pd.read_excel(excel, sheet_name=0, index_col=0, skipfooter=1)
        tm.assert_frame_equal(df3, df1.iloc[:-1])

        with pd.ExcelFile("test1" + read_ext) as excel:
            df3 = excel.parse(0, index_col=0, skipfooter=1)

        tm.assert_frame_equal(df3, df1.iloc[:-1])

    def test_sheet_name(self, request, engine, read_ext, df_ref):
        xfail_datetimes_with_pyxlsb(engine, request)

        expected = df_ref
        adjust_expected(expected, read_ext, engine)

        filename = "test1"
        sheet_name = "Sheet1"

        with pd.ExcelFile(filename + read_ext) as excel:
            df1_parse = excel.parse(sheet_name=sheet_name, index_col=0)  # doc

        with pd.ExcelFile(filename + read_ext) as excel:
            df2_parse = excel.parse(index_col=0, sheet_name=sheet_name)

        tm.assert_frame_equal(df1_parse, expected)
        tm.assert_frame_equal(df2_parse, expected)

    @pytest.mark.parametrize(
        "sheet_name",
        [3, [0, 3], [3, 0], "Sheet4", ["Sheet1", "Sheet4"], ["Sheet4", "Sheet1"]],
    )
    def test_bad_sheetname_raises(self, read_ext, sheet_name):
        # GH 39250
        msg = "Worksheet index 3 is invalid|Worksheet named 'Sheet4' not found"
        with pytest.raises(ValueError, match=msg):
            with pd.ExcelFile("blank" + read_ext) as excel:
                excel.parse(sheet_name=sheet_name)

    def test_excel_read_buffer(self, engine, read_ext):
        pth = "test1" + read_ext
        expected = pd.read_excel(pth, sheet_name="Sheet1", index_col=0, engine=engine)

        with open(pth, "rb") as f:
            with pd.ExcelFile(f) as xls:
                actual = pd.read_excel(xls, sheet_name="Sheet1", index_col=0)

        tm.assert_frame_equal(expected, actual)

    def test_reader_closes_file(self, engine, read_ext):
        with open("test1" + read_ext, "rb") as f:
            with pd.ExcelFile(f) as xlsx:
                # parses okay
                pd.read_excel(xlsx, sheet_name="Sheet1", index_col=0, engine=engine)

        assert f.closed

    def test_conflicting_excel_engines(self, read_ext):
        # GH 26566
        msg = "Engine should not be specified when passing an ExcelFile"

        with pd.ExcelFile("test1" + read_ext) as xl:
            with pytest.raises(ValueError, match=msg):
                pd.read_excel(xl, engine="foo")

    def test_excel_read_binary(self, engine, read_ext):
        # GH 15914
        expected = pd.read_excel("test1" + read_ext, engine=engine)

        with open("test1" + read_ext, "rb") as f:
            data = f.read()

        actual = pd.read_excel(BytesIO(data), engine=engine)
        tm.assert_frame_equal(expected, actual)

    def test_excel_read_binary_via_read_excel(self, read_ext, engine):
        # GH 38424
        with open("test1" + read_ext, "rb") as f:
            result = pd.read_excel(f, engine=engine)
        expected = pd.read_excel("test1" + read_ext, engine=engine)
        tm.assert_frame_equal(result, expected)

    def test_read_excel_header_index_out_of_range(self, engine):
        # GH#43143
        with open("df_header_oob.xlsx", "rb") as f:
            with pytest.raises(ValueError, match="exceeds maximum"):
                pd.read_excel(f, header=[0, 1])

    @pytest.mark.parametrize("filename", ["df_empty.xlsx", "df_equals.xlsx"])
    def test_header_with_index_col(self, filename):
        # GH 33476
        idx = Index(["Z"], name="I2")
        cols = MultiIndex.from_tuples([("A", "B"), ("A", "B.1")], names=["I11", "I12"])
        expected = DataFrame([[1, 3]], index=idx, columns=cols, dtype="int64")
        result = pd.read_excel(
            filename, sheet_name="Sheet1", index_col=0, header=[0, 1]
        )
        tm.assert_frame_equal(expected, result)

    def test_read_datetime_multiindex(self, request, engine, read_ext):
        # GH 34748
        xfail_datetimes_with_pyxlsb(engine, request)

        f = "test_datetime_mi" + read_ext
        with pd.ExcelFile(f) as excel:
            actual = pd.read_excel(excel, header=[0, 1], index_col=0, engine=engine)

        unit = get_exp_unit(read_ext, engine)
        dti = pd.DatetimeIndex(["2020-02-29", "2020-03-01"], dtype=f"M8[{unit}]")
        expected_column_index = MultiIndex.from_arrays(
            [dti[:1], dti[1:]],
            names=[
                dti[0].to_pydatetime(),
                dti[1].to_pydatetime(),
            ],
        )
        expected = DataFrame([], index=[], columns=expected_column_index)

        tm.assert_frame_equal(expected, actual)

    def test_engine_invalid_option(self, read_ext):
        # read_ext includes the '.' hence the weird formatting
        with pytest.raises(ValueError, match="Value must be one of *"):
            with pd.option_context(f"io.excel{read_ext}.reader", "abc"):
                pass

    def test_ignore_chartsheets(self, request, engine, read_ext):
        # GH 41448
        if read_ext == ".ods":
            pytest.skip("chartsheets do not exist in the ODF format")
        if engine == "pyxlsb":
            request.applymarker(
                pytest.mark.xfail(
                    reason="pyxlsb can't distinguish chartsheets from worksheets"
                )
            )
        with pd.ExcelFile("chartsheet" + read_ext) as excel:
            assert excel.sheet_names == ["Sheet1"]

    def test_corrupt_files_closed(self, engine, read_ext):
        # GH41778
        errors = (BadZipFile,)
        if engine is None:
            pytest.skip(f"Invalid test for engine={engine}")
        elif engine == "xlrd":
            import xlrd

            errors = (BadZipFile, xlrd.biffh.XLRDError)
        elif engine == "calamine":
            from python_calamine import CalamineError

            errors = (CalamineError,)

        with tm.ensure_clean(f"corrupt{read_ext}") as file:
            Path(file).write_text("corrupt", encoding="utf-8")
            with tm.assert_produces_warning(False):
                try:
                    pd.ExcelFile(file, engine=engine)
                except errors:
                    pass
