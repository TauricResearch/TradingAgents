from datetime import (
    date,
    datetime,
    timedelta,
)
from functools import partial
from io import BytesIO
import os
import re

import numpy as np
import pytest

from pandas.compat import is_platform_windows
from pandas.compat._constants import PY310
from pandas.compat._optional import import_optional_dependency
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    date_range,
    option_context,
)
import pandas._testing as tm

from pandas.io.excel import (
    ExcelFile,
    ExcelWriter,
    _OpenpyxlWriter,
    _XlsxWriter,
    register_writer,
)
from pandas.io.excel._util import _writers

if is_platform_windows():
    pytestmark = pytest.mark.single_cpu


def get_exp_unit(path: str) -> str:
    return "ns"


@pytest.fixture
def frame(float_frame):
    """
    Returns the first ten items in fixture "float_frame".
    """
    return float_frame[:10]


@pytest.fixture(params=[True, False])
def merge_cells(request):
    return request.param


@pytest.fixture
def path(ext):
    """
    Fixture to open file for use in each test case.
    """
    with tm.ensure_clean(ext) as file_path:
        yield file_path


@pytest.fixture
def set_engine(engine, ext):
    """
    Fixture to set engine for use in each test case.

    Rather than requiring `engine=...` to be provided explicitly as an
    argument in each test, this fixture sets a global option to dictate
    which engine should be used to write Excel files. After executing
    the test it rolls back said change to the global option.
    """
    option_name = f"io.excel.{ext.strip('.')}.writer"
    with option_context(option_name, engine):
        yield


@pytest.mark.parametrize(
    "ext",
    [
        pytest.param(".xlsx", marks=[td.skip_if_no("openpyxl"), td.skip_if_no("xlrd")]),
        pytest.param(".xlsm", marks=[td.skip_if_no("openpyxl"), td.skip_if_no("xlrd")]),
        pytest.param(
            ".xlsx", marks=[td.skip_if_no("xlsxwriter"), td.skip_if_no("xlrd")]
        ),
        pytest.param(".ods", marks=td.skip_if_no("odf")),
    ],
)
class TestRoundTrip:
    @pytest.mark.parametrize(
        "header,expected",
        [(None, DataFrame([np.nan] * 4)), (0, DataFrame({"Unnamed: 0": [np.nan] * 3}))],
    )
    def test_read_one_empty_col_no_header(self, ext, header, expected):
        # xref gh-12292
        filename = "no_header"
        df = DataFrame([["", 1, 100], ["", 2, 200], ["", 3, 300], ["", 4, 400]])

        with tm.ensure_clean(ext) as path:
            df.to_excel(path, sheet_name=filename, index=False, header=False)
            result = pd.read_excel(
                path, sheet_name=filename, usecols=[0], header=header
            )

        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "header,expected",
        [(None, DataFrame([0] + [np.nan] * 4)), (0, DataFrame([np.nan] * 4))],
    )
    def test_read_one_empty_col_with_header(self, ext, header, expected):
        filename = "with_header"
        df = DataFrame([["", 1, 100], ["", 2, 200], ["", 3, 300], ["", 4, 400]])

        with tm.ensure_clean(ext) as path:
            df.to_excel(path, sheet_name="with_header", index=False, header=True)
            result = pd.read_excel(
                path, sheet_name=filename, usecols=[0], header=header
            )

        tm.assert_frame_equal(result, expected)

    def test_set_column_names_in_parameter(self, ext):
        # GH 12870 : pass down column names associated with
        # keyword argument names
        refdf = DataFrame([[1, "foo"], [2, "bar"], [3, "baz"]], columns=["a", "b"])

        with tm.ensure_clean(ext) as pth:
            with ExcelWriter(pth) as writer:
                refdf.to_excel(
                    writer, sheet_name="Data_no_head", header=False, index=False
                )
                refdf.to_excel(writer, sheet_name="Data_with_head", index=False)

            refdf.columns = ["A", "B"]

            with ExcelFile(pth) as reader:
                xlsdf_no_head = pd.read_excel(
                    reader, sheet_name="Data_no_head", header=None, names=["A", "B"]
                )
                xlsdf_with_head = pd.read_excel(
                    reader,
                    sheet_name="Data_with_head",
                    index_col=None,
                    names=["A", "B"],
                )

            tm.assert_frame_equal(xlsdf_no_head, refdf)
            tm.assert_frame_equal(xlsdf_with_head, refdf)

    def test_creating_and_reading_multiple_sheets(self, ext):
        # see gh-9450
        #
        # Test reading multiple sheets, from a runtime
        # created Excel file with multiple sheets.
        def tdf(col_sheet_name):
            d, i = [11, 22, 33], [1, 2, 3]
            return DataFrame(d, i, columns=[col_sheet_name])

        sheets = ["AAA", "BBB", "CCC"]

        dfs = [tdf(s) for s in sheets]
        dfs = dict(zip(sheets, dfs))

        with tm.ensure_clean(ext) as pth:
            with ExcelWriter(pth) as ew:
                for sheetname, df in dfs.items():
                    df.to_excel(ew, sheet_name=sheetname)

            dfs_returned = pd.read_excel(pth, sheet_name=sheets, index_col=0)

            for s in sheets:
                tm.assert_frame_equal(dfs[s], dfs_returned[s])

    def test_read_excel_multiindex_empty_level(self, ext):
        # see gh-12453
        with tm.ensure_clean(ext) as path:
            df = DataFrame(
                {
                    ("One", "x"): {0: 1},
                    ("Two", "X"): {0: 3},
                    ("Two", "Y"): {0: 7},
                    ("Zero", ""): {0: 0},
                }
            )

            expected = DataFrame(
                {
                    ("One", "x"): {0: 1},
                    ("Two", "X"): {0: 3},
                    ("Two", "Y"): {0: 7},
                    ("Zero", "Unnamed: 4_level_1"): {0: 0},
                }
            )

            df.to_excel(path)
            actual = pd.read_excel(path, header=[0, 1], index_col=0)
            tm.assert_frame_equal(actual, expected)

            df = DataFrame(
                {
                    ("Beg", ""): {0: 0},
                    ("Middle", "x"): {0: 1},
                    ("Tail", "X"): {0: 3},
                    ("Tail", "Y"): {0: 7},
                }
            )

            expected = DataFrame(
                {
                    ("Beg", "Unnamed: 1_level_1"): {0: 0},
                    ("Middle", "x"): {0: 1},
                    ("Tail", "X"): {0: 3},
                    ("Tail", "Y"): {0: 7},
                }
            )

            df.to_excel(path)
            actual = pd.read_excel(path, header=[0, 1], index_col=0)
            tm.assert_frame_equal(actual, expected)

    @pytest.mark.parametrize("c_idx_names", ["a", None])
    @pytest.mark.parametrize("r_idx_names", ["b", None])
    @pytest.mark.parametrize("c_idx_levels", [1, 3])
    @pytest.mark.parametrize("r_idx_levels", [1, 3])
    def test_excel_multindex_roundtrip(
        self, ext, c_idx_names, r_idx_names, c_idx_levels, r_idx_levels, request
    ):
        # see gh-4679
        with tm.ensure_clean(ext) as pth:
            # Empty name case current read in as
            # unnamed levels, not Nones.
            check_names = bool(r_idx_names) or r_idx_levels <= 1

            if c_idx_levels == 1:
                columns = Index(list("abcde"))
            else:
                columns = MultiIndex.from_arrays(
                    [range(5) for _ in range(c_idx_levels)],
                    names=[f"{c_idx_names}-{i}" for i in range(c_idx_levels)],
                )
            if r_idx_levels == 1:
                index = Index(list("ghijk"))
            else:
                index = MultiIndex.from_arrays(
                    [range(5) for _ in range(r_idx_levels)],
                    names=[f"{r_idx_names}-{i}" for i in range(r_idx_levels)],
                )
            df = DataFrame(
                1.1 * np.ones((5, 5)),
                columns=columns,
                index=index,
            )
            df.to_excel(pth)

            act = pd.read_excel(
                pth,
                index_col=list(range(r_idx_levels)),
                header=list(range(c_idx_levels)),
            )
            tm.assert_frame_equal(df, act, check_names=check_names)

            df.iloc[0, :] = np.nan
            df.to_excel(pth)

            act = pd.read_excel(
                pth,
                index_col=list(range(r_idx_levels)),
                header=list(range(c_idx_levels)),
            )
            tm.assert_frame_equal(df, act, check_names=check_names)

            df.iloc[-1, :] = np.nan
            df.to_excel(pth)
            act = pd.read_excel(
                pth,
                index_col=list(range(r_idx_levels)),
                header=list(range(c_idx_levels)),
            )
            tm.assert_frame_equal(df, act, check_names=check_names)

    def test_read_excel_parse_dates(self, ext):
        # see gh-11544, gh-12051
        df = DataFrame(
            {"col": [1, 2, 3], "date_strings": date_range("2012-01-01", periods=3)}
        )
        df2 = df.copy()
        df2["date_strings"] = df2["date_strings"].dt.strftime("%m/%d/%Y")

        with tm.ensure_clean(ext) as pth:
            df2.to_excel(pth)

            res = pd.read_excel(pth, index_col=0)
            tm.assert_frame_equal(df2, res)

            res = pd.read_excel(pth, parse_dates=["date_strings"], index_col=0)
            tm.assert_frame_equal(df, res)

            date_parser = lambda x: datetime.strptime(x, "%m/%d/%Y")
            with tm.assert_produces_warning(
                FutureWarning,
                match="use 'date_format' instead",
                raise_on_extra_warnings=False,
            ):
                res = pd.read_excel(
                    pth,
                    parse_dates=["date_strings"],
                    date_parser=date_parser,
                    index_col=0,
                )
            tm.assert_frame_equal(df, res)
            res = pd.read_excel(
                pth, parse_dates=["date_strings"], date_format="%m/%d/%Y", index_col=0
            )
            tm.assert_frame_equal(df, res)

    def test_multiindex_interval_datetimes(self, ext):
        # GH 30986
        midx = MultiIndex.from_arrays(
            [
                range(4),
                pd.interval_range(
                    start=pd.Timestamp("2020-01-01"), periods=4, freq="6ME"
                ),
            ]
        )
        df = DataFrame(range(4), index=midx)
        with tm.ensure_clean(ext) as pth:
            df.to_excel(pth)
            result = pd.read_excel(pth, index_col=[0, 1])
        expected = DataFrame(
            range(4),
            MultiIndex.from_arrays(
                [
                    range(4),
                    [
                        "(2020-01-31 00:00:00, 2020-07-31 00:00:00]",
                        "(2020-07-31 00:00:00, 2021-01-31 00:00:00]",
                        "(2021-01-31 00:00:00, 2021-07-31 00:00:00]",
                        "(2021-07-31 00:00:00, 2022-01-31 00:00:00]",
                    ],
                ]
            ),
        )
        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "engine,ext",
    [
        pytest.param(
            "openpyxl",
            ".xlsx",
            marks=[td.skip_if_no("openpyxl"), td.skip_if_no("xlrd")],
        ),
        pytest.param(
            "openpyxl",
            ".xlsm",
            marks=[td.skip_if_no("openpyxl"), td.skip_if_no("xlrd")],
        ),
        pytest.param(
            "xlsxwriter",
            ".xlsx",
            marks=[td.skip_if_no("xlsxwriter"), td.skip_if_no("xlrd")],
        ),
        pytest.param("odf", ".ods", marks=td.skip_if_no("odf")),
    ],
)
@pytest.mark.usefixtures("set_engine")
class TestExcelWriter:
    def test_excel_sheet_size(self, path):
        # GH 26080
        breaking_row_count = 2**20 + 1
        breaking_col_count = 2**14 + 1
        # purposely using two arrays to prevent memory issues while testing
        row_arr = np.zeros(shape=(breaking_row_count, 1))
        col_arr = np.zeros(shape=(1, breaking_col_count))
        row_df = DataFrame(row_arr)
        col_df = DataFrame(col_arr)

        msg = "sheet is too large"
        with pytest.raises(ValueError, match=msg):
            row_df.to_excel(path)

        with pytest.raises(ValueError, match=msg):
            col_df.to_excel(path)

    def test_excel_sheet_by_name_raise(self, path):
        gt = DataFrame(np.random.default_rng(2).standard_normal((10, 2)))
        gt.to_excel(path)

        with ExcelFile(path) as xl:
            df = pd.read_excel(xl, sheet_name=0, index_col=0)

        tm.assert_frame_equal(gt, df)

        msg = "Worksheet named '0' not found"
        with pytest.raises(ValueError, match=msg):
            pd.read_excel(xl, "0")

    def test_excel_writer_context_manager(self, frame, path):
        with ExcelWriter(path) as writer:
            frame.to_excel(writer, sheet_name="Data1")
            frame2 = frame.copy()
            frame2.columns = frame.columns[::-1]
            frame2.to_excel(writer, sheet_name="Data2")

        with ExcelFile(path) as reader:
            found_df = pd.read_excel(reader, sheet_name="Data1", index_col=0)
            found_df2 = pd.read_excel(reader, sheet_name="Data2", index_col=0)

            tm.assert_frame_equal(found_df, frame)
            tm.assert_frame_equal(found_df2, frame2)

    def test_roundtrip(self, frame, path):
        frame = frame.copy()
        frame.iloc[:5, frame.columns.get_loc("A")] = np.nan

        frame.to_excel(path, sheet_name="test1")
        frame.to_excel(path, sheet_name="test1", columns=["A", "B"])
        frame.to_excel(path, sheet_name="test1", header=False)
        frame.to_excel(path, sheet_name="test1", index=False)

        # test roundtrip
        frame.to_excel(path, sheet_name="test1")
        recons = pd.read_excel(path, sheet_name="test1", index_col=0)
        tm.assert_frame_equal(frame, recons)

        frame.to_excel(path, sheet_name="test1", index=False)
        recons = pd.read_excel(path, sheet_name="test1", index_col=None)
        recons.index = frame.index
        tm.assert_frame_equal(frame, recons)

        frame.to_excel(path, sheet_name="test1", na_rep="NA")
        recons = pd.read_excel(path, sheet_name="test1", index_col=0, na_values=["NA"])
        tm.assert_frame_equal(frame, recons)

        # GH 3611
        frame.to_excel(path, sheet_name="test1", na_rep="88")
        recons = pd.read_excel(path, sheet_name="test1", index_col=0, na_values=["88"])
        tm.assert_frame_equal(frame, recons)

        frame.to_excel(path, sheet_name="test1", na_rep="88")
        recons = pd.read_excel(
            path, sheet_name="test1", index_col=0, na_values=[88, 88.0]
        )
        tm.assert_frame_equal(frame, recons)

        # GH 6573
        frame.to_excel(path, sheet_name="Sheet1")
        recons = pd.read_excel(path, index_col=0)
        tm.assert_frame_equal(frame, recons)

        frame.to_excel(path, sheet_name="0")
        recons = pd.read_excel(path, index_col=0)
        tm.assert_frame_equal(frame, recons)

        # GH 8825 Pandas Series should provide to_excel method
        s = frame["A"]
        s.to_excel(path)
        recons = pd.read_excel(path, index_col=0)
        tm.assert_frame_equal(s.to_frame(), recons)

    def test_mixed(self, frame, path):
        mixed_frame = frame.copy()
        mixed_frame["foo"] = "bar"

        mixed_frame.to_excel(path, sheet_name="test1")
        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=0)
        tm.assert_frame_equal(mixed_frame, recons)

    def test_ts_frame(self, path):
        unit = get_exp_unit(path)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=5, freq="B"),
        )

        # freq doesn't round-trip
        index = pd.DatetimeIndex(np.asarray(df.index), freq=None)
        df.index = index

        expected = df[:]
        expected.index = expected.index.as_unit(unit)

        df.to_excel(path, sheet_name="test1")
        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=0)
        tm.assert_frame_equal(expected, recons)

    def test_basics_with_nan(self, frame, path):
        frame = frame.copy()
        frame.iloc[:5, frame.columns.get_loc("A")] = np.nan
        frame.to_excel(path, sheet_name="test1")
        frame.to_excel(path, sheet_name="test1", columns=["A", "B"])
        frame.to_excel(path, sheet_name="test1", header=False)
        frame.to_excel(path, sheet_name="test1", index=False)

    @pytest.mark.parametrize("np_type", [np.int8, np.int16, np.int32, np.int64])
    def test_int_types(self, np_type, path):
        # Test np.int values read come back as int
        # (rather than float which is Excel's format).
        df = DataFrame(
            np.random.default_rng(2).integers(-10, 10, size=(10, 2)), dtype=np_type
        )
        df.to_excel(path, sheet_name="test1")

        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=0)

        int_frame = df.astype(np.int64)
        tm.assert_frame_equal(int_frame, recons)

        recons2 = pd.read_excel(path, sheet_name="test1", index_col=0)
        tm.assert_frame_equal(int_frame, recons2)

    @pytest.mark.parametrize("np_type", [np.float16, np.float32, np.float64])
    def test_float_types(self, np_type, path):
        # Test np.float values read come back as float.
        df = DataFrame(np.random.default_rng(2).random(10), dtype=np_type)
        df.to_excel(path, sheet_name="test1")

        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=0).astype(
                np_type
            )

        tm.assert_frame_equal(df, recons)

    def test_bool_types(self, path):
        # Test np.bool_ values read come back as float.
        df = DataFrame([1, 0, True, False], dtype=np.bool_)
        df.to_excel(path, sheet_name="test1")

        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=0).astype(
                np.bool_
            )

        tm.assert_frame_equal(df, recons)

    def test_inf_roundtrip(self, path):
        df = DataFrame([(1, np.inf), (2, 3), (5, -np.inf)])
        df.to_excel(path, sheet_name="test1")

        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=0)

        tm.assert_frame_equal(df, recons)

    def test_sheets(self, frame, path):
        # freq doesn't round-trip
        unit = get_exp_unit(path)
        tsframe = DataFrame(
            np.random.default_rng(2).standard_normal((5, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=5, freq="B"),
        )
        index = pd.DatetimeIndex(np.asarray(tsframe.index), freq=None)
        tsframe.index = index

        expected = tsframe[:]
        expected.index = expected.index.as_unit(unit)

        frame = frame.copy()
        frame.iloc[:5, frame.columns.get_loc("A")] = np.nan

        frame.to_excel(path, sheet_name="test1")
        frame.to_excel(path, sheet_name="test1", columns=["A", "B"])
        frame.to_excel(path, sheet_name="test1", header=False)
        frame.to_excel(path, sheet_name="test1", index=False)

        # Test writing to separate sheets
        with ExcelWriter(path) as writer:
            frame.to_excel(writer, sheet_name="test1")
            tsframe.to_excel(writer, sheet_name="test2")
        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=0)
            tm.assert_frame_equal(frame, recons)
            recons = pd.read_excel(reader, sheet_name="test2", index_col=0)
        tm.assert_frame_equal(expected, recons)
        assert 2 == len(reader.sheet_names)
        assert "test1" == reader.sheet_names[0]
        assert "test2" == reader.sheet_names[1]

    def test_colaliases(self, frame, path):
        frame = frame.copy()
        frame.iloc[:5, frame.columns.get_loc("A")] = np.nan

        frame.to_excel(path, sheet_name="test1")
        frame.to_excel(path, sheet_name="test1", columns=["A", "B"])
        frame.to_excel(path, sheet_name="test1", header=False)
        frame.to_excel(path, sheet_name="test1", index=False)

        # column aliases
        col_aliases = Index(["AA", "X", "Y", "Z"])
        frame.to_excel(path, sheet_name="test1", header=col_aliases)
        with ExcelFile(path) as reader:
            rs = pd.read_excel(reader, sheet_name="test1", index_col=0)
        xp = frame.copy()
        xp.columns = col_aliases
        tm.assert_frame_equal(xp, rs)

    def test_roundtrip_indexlabels(self, merge_cells, frame, path):
        frame = frame.copy()
        frame.iloc[:5, frame.columns.get_loc("A")] = np.nan

        frame.to_excel(path, sheet_name="test1")
        frame.to_excel(path, sheet_name="test1", columns=["A", "B"])
        frame.to_excel(path, sheet_name="test1", header=False)
        frame.to_excel(path, sheet_name="test1", index=False)

        # test index_label
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 2))) >= 0
        df.to_excel(
            path, sheet_name="test1", index_label=["test"], merge_cells=merge_cells
        )
        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=0).astype(
                np.int64
            )
        df.index.names = ["test"]
        assert df.index.names == recons.index.names

        df = DataFrame(np.random.default_rng(2).standard_normal((10, 2))) >= 0
        df.to_excel(
            path,
            sheet_name="test1",
            index_label=["test", "dummy", "dummy2"],
            merge_cells=merge_cells,
        )
        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=0).astype(
                np.int64
            )
        df.index.names = ["test"]
        assert df.index.names == recons.index.names

        df = DataFrame(np.random.default_rng(2).standard_normal((10, 2))) >= 0
        df.to_excel(
            path, sheet_name="test1", index_label="test", merge_cells=merge_cells
        )
        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=0).astype(
                np.int64
            )
        df.index.names = ["test"]
        tm.assert_frame_equal(df, recons.astype(bool))

        frame.to_excel(
            path,
            sheet_name="test1",
            columns=["A", "B", "C", "D"],
            index=False,
            merge_cells=merge_cells,
        )
        # take 'A' and 'B' as indexes (same row as cols 'C', 'D')
        df = frame.copy()
        df = df.set_index(["A", "B"])

        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=[0, 1])
        tm.assert_frame_equal(df, recons)

    def test_excel_roundtrip_indexname(self, merge_cells, path):
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 4)))
        df.index.name = "foo"

        df.to_excel(path, merge_cells=merge_cells)

        with ExcelFile(path) as xf:
            result = pd.read_excel(xf, sheet_name=xf.sheet_names[0], index_col=0)

        tm.assert_frame_equal(result, df)
        assert result.index.name == "foo"

    def test_excel_roundtrip_datetime(self, merge_cells, path):
        # datetime.date, not sure what to test here exactly
        unit = get_exp_unit(path)

        # freq does not round-trip
        tsframe = DataFrame(
            np.random.default_rng(2).standard_normal((5, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=5, freq="B"),
        )
        index = pd.DatetimeIndex(np.asarray(tsframe.index), freq=None)
        tsframe.index = index

        tsf = tsframe.copy()

        tsf.index = [x.date() for x in tsframe.index]
        tsf.to_excel(path, sheet_name="test1", merge_cells=merge_cells)

        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=0)

        expected = tsframe[:]
        expected.index = expected.index.as_unit(unit)
        tm.assert_frame_equal(expected, recons)

    def test_excel_date_datetime_format(self, ext, path):
        # see gh-4133
        #
        # Excel output format strings
        unit = get_exp_unit(path)

        df = DataFrame(
            [
                [date(2014, 1, 31), date(1999, 9, 24)],
                [datetime(1998, 5, 26, 23, 33, 4), datetime(2014, 2, 28, 13, 5, 13)],
            ],
            index=["DATE", "DATETIME"],
            columns=["X", "Y"],
        )
        df_expected = DataFrame(
            [
                [datetime(2014, 1, 31), datetime(1999, 9, 24)],
                [datetime(1998, 5, 26, 23, 33, 4), datetime(2014, 2, 28, 13, 5, 13)],
            ],
            index=["DATE", "DATETIME"],
            columns=["X", "Y"],
        )
        df_expected = df_expected.astype(f"M8[{unit}]")

        with tm.ensure_clean(ext) as filename2:
            with ExcelWriter(path) as writer1:
                df.to_excel(writer1, sheet_name="test1")

            with ExcelWriter(
                filename2,
                date_format="DD.MM.YYYY",
                datetime_format="DD.MM.YYYY HH-MM-SS",
            ) as writer2:
                df.to_excel(writer2, sheet_name="test1")

            with ExcelFile(path) as reader1:
                rs1 = pd.read_excel(reader1, sheet_name="test1", index_col=0)

            with ExcelFile(filename2) as reader2:
                rs2 = pd.read_excel(reader2, sheet_name="test1", index_col=0)

        tm.assert_frame_equal(rs1, rs2)

        # Since the reader returns a datetime object for dates,
        # we need to use df_expected to check the result.
        tm.assert_frame_equal(rs2, df_expected)

    @pytest.mark.filterwarnings(
        "ignore:invalid value encountered in cast:RuntimeWarning"
    )
    def test_to_excel_interval_no_labels(self, path, using_infer_string):
        # see gh-19242
        #
        # Test writing Interval without labels.
        df = DataFrame(
            np.random.default_rng(2).integers(-10, 10, size=(20, 1)), dtype=np.int64
        )
        expected = df.copy()

        df["new"] = pd.cut(df[0], 10)
        expected["new"] = pd.cut(expected[0], 10).astype(
            str if not using_infer_string else "str"
        )

        df.to_excel(path, sheet_name="test1")
        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=0)
        tm.assert_frame_equal(expected, recons)

    def test_to_excel_interval_labels(self, path):
        # see gh-19242
        #
        # Test writing Interval with labels.
        df = DataFrame(
            np.random.default_rng(2).integers(-10, 10, size=(20, 1)), dtype=np.int64
        )
        expected = df.copy()
        intervals = pd.cut(
            df[0], 10, labels=["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
        )
        df["new"] = intervals
        expected["new"] = pd.Series(list(intervals))

        df.to_excel(path, sheet_name="test1")
        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=0)
        tm.assert_frame_equal(expected, recons)

    def test_to_excel_timedelta(self, path):
        # see gh-19242, gh-9155
        #
        # Test writing timedelta to xls.
        df = DataFrame(
            np.random.default_rng(2).integers(-10, 10, size=(20, 1)),
            columns=["A"],
            dtype=np.int64,
        )
        expected = df.copy()

        df["new"] = df["A"].apply(lambda x: timedelta(seconds=x))
        expected["new"] = expected["A"].apply(
            lambda x: timedelta(seconds=x).total_seconds() / 86400
        )

        df.to_excel(path, sheet_name="test1")
        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=0)
        tm.assert_frame_equal(expected, recons)

    def test_to_excel_periodindex(self, path):
        # xp has a PeriodIndex
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=5, freq="B"),
        )
        xp = df.resample("ME").mean().to_period("M")

        xp.to_excel(path, sheet_name="sht1")

        with ExcelFile(path) as reader:
            rs = pd.read_excel(reader, sheet_name="sht1", index_col=0)
        tm.assert_frame_equal(xp, rs.to_period("M"))

    def test_to_excel_multiindex(self, merge_cells, frame, path):
        arrays = np.arange(len(frame.index) * 2, dtype=np.int64).reshape(2, -1)
        new_index = MultiIndex.from_arrays(arrays, names=["first", "second"])
        frame.index = new_index

        frame.to_excel(path, sheet_name="test1", header=False)
        frame.to_excel(path, sheet_name="test1", columns=["A", "B"])

        # round trip
        frame.to_excel(path, sheet_name="test1", merge_cells=merge_cells)
        with ExcelFile(path) as reader:
            df = pd.read_excel(reader, sheet_name="test1", index_col=[0, 1])
        tm.assert_frame_equal(frame, df)

    # GH13511
    def test_to_excel_multiindex_nan_label(self, merge_cells, path):
        df = DataFrame(
            {
                "A": [None, 2, 3],
                "B": [10, 20, 30],
                "C": np.random.default_rng(2).random(3),
            }
        )
        df = df.set_index(["A", "B"])

        df.to_excel(path, merge_cells=merge_cells)
        df1 = pd.read_excel(path, index_col=[0, 1])
        tm.assert_frame_equal(df, df1)

    # Test for Issue 11328. If column indices are integers, make
    # sure they are handled correctly for either setting of
    # merge_cells
    def test_to_excel_multiindex_cols(self, merge_cells, frame, path):
        arrays = np.arange(len(frame.index) * 2, dtype=np.int64).reshape(2, -1)
        new_index = MultiIndex.from_arrays(arrays, names=["first", "second"])
        frame.index = new_index

        new_cols_index = MultiIndex.from_tuples([(40, 1), (40, 2), (50, 1), (50, 2)])
        frame.columns = new_cols_index
        header = [0, 1]
        if not merge_cells:
            header = 0

        # round trip
        frame.to_excel(path, sheet_name="test1", merge_cells=merge_cells)
        with ExcelFile(path) as reader:
            df = pd.read_excel(
                reader, sheet_name="test1", header=header, index_col=[0, 1]
            )
        if not merge_cells:
            fm = frame.columns._format_multi(sparsify=False, include_names=False)
            frame.columns = [".".join(map(str, q)) for q in zip(*fm)]
        tm.assert_frame_equal(frame, df)

    def test_to_excel_multiindex_dates(self, merge_cells, path):
        # try multiindex with dates
        unit = get_exp_unit(path)
        tsframe = DataFrame(
            np.random.default_rng(2).standard_normal((5, 4)),
            columns=Index(list("ABCD")),
            index=date_range("2000-01-01", periods=5, freq="B"),
        )
        tsframe.index = MultiIndex.from_arrays(
            [
                tsframe.index.as_unit(unit),
                np.arange(len(tsframe.index), dtype=np.int64),
            ],
            names=["time", "foo"],
        )

        tsframe.to_excel(path, sheet_name="test1", merge_cells=merge_cells)
        with ExcelFile(path) as reader:
            recons = pd.read_excel(reader, sheet_name="test1", index_col=[0, 1])

        tm.assert_frame_equal(tsframe, recons)
        assert recons.index.names == ("time", "foo")

    def test_to_excel_multiindex_no_write_index(self, path):
        # Test writing and re-reading a MI without the index. GH 5616.

        # Initial non-MI frame.
        frame1 = DataFrame({"a": [10, 20], "b": [30, 40], "c": [50, 60]})

        # Add a MI.
        frame2 = frame1.copy()
        multi_index = MultiIndex.from_tuples([(70, 80), (90, 100)])
        frame2.index = multi_index

        # Write out to Excel without the index.
        frame2.to_excel(path, sheet_name="test1", index=False)

        # Read it back in.
        with ExcelFile(path) as reader:
            frame3 = pd.read_excel(reader, sheet_name="test1")

        # Test that it is the same as the initial frame.
        tm.assert_frame_equal(frame1, frame3)

    def test_to_excel_empty_multiindex(self, path):
        # GH 19543.
        expected = DataFrame([], columns=[0, 1, 2])

        df = DataFrame([], index=MultiIndex.from_tuples([], names=[0, 1]), columns=[2])
        df.to_excel(path, sheet_name="test1")

        with ExcelFile(path) as reader:
            result = pd.read_excel(reader, sheet_name="test1")
        tm.assert_frame_equal(
            result, expected, check_index_type=False, check_dtype=False
        )

    def test_to_excel_float_format(self, path):
        df = DataFrame(
            [[0.123456, 0.234567, 0.567567], [12.32112, 123123.2, 321321.2]],
            index=["A", "B"],
            columns=["X", "Y", "Z"],
        )
        df.to_excel(path, sheet_name="test1", float_format="%.2f")

        with ExcelFile(path) as reader:
            result = pd.read_excel(reader, sheet_name="test1", index_col=0)

        expected = DataFrame(
            [[0.12, 0.23, 0.57], [12.32, 123123.20, 321321.20]],
            index=["A", "B"],
            columns=["X", "Y", "Z"],
        )
        tm.assert_frame_equal(result, expected)

    def test_to_excel_output_encoding(self, ext):
        # Avoid mixed inferred_type.
        df = DataFrame(
            [["\u0192", "\u0193", "\u0194"], ["\u0195", "\u0196", "\u0197"]],
            index=["A\u0192", "B"],
            columns=["X\u0193", "Y", "Z"],
        )

        with tm.ensure_clean("__tmp_to_excel_float_format__." + ext) as filename:
            df.to_excel(filename, sheet_name="TestSheet")
            result = pd.read_excel(filename, sheet_name="TestSheet", index_col=0)
            tm.assert_frame_equal(result, df)

    def test_to_excel_unicode_filename(self, ext):
        with tm.ensure_clean("\u0192u." + ext) as filename:
            try:
                with open(filename, "wb"):
                    pass
            except UnicodeEncodeError:
                pytest.skip("No unicode file names on this system")

            df = DataFrame(
                [[0.123456, 0.234567, 0.567567], [12.32112, 123123.2, 321321.2]],
                index=["A", "B"],
                columns=["X", "Y", "Z"],
            )
            df.to_excel(filename, sheet_name="test1", float_format="%.2f")

            with ExcelFile(filename) as reader:
                result = pd.read_excel(reader, sheet_name="test1", index_col=0)

        expected = DataFrame(
            [[0.12, 0.23, 0.57], [12.32, 123123.20, 321321.20]],
            index=["A", "B"],
            columns=["X", "Y", "Z"],
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("use_headers", [True, False])
    @pytest.mark.parametrize("r_idx_nlevels", [1, 2, 3])
    @pytest.mark.parametrize("c_idx_nlevels", [1, 2, 3])
    def test_excel_010_hemstring(
        self, merge_cells, c_idx_nlevels, r_idx_nlevels, use_headers, path
    ):
        def roundtrip(data, header=True, parser_hdr=0, index=True):
            data.to_excel(path, header=header, merge_cells=merge_cells, index=index)

            with ExcelFile(path) as xf:
                return pd.read_excel(
                    xf, sheet_name=xf.sheet_names[0], header=parser_hdr
                )

        # Basic test.
        parser_header = 0 if use_headers else None
        res = roundtrip(DataFrame([0]), use_headers, parser_header)

        assert res.shape == (1, 2)
        assert res.iloc[0, 0] is not np.nan

        # More complex tests with multi-index.
        nrows = 5
        ncols = 3

        # ensure limited functionality in 0.10
        # override of gh-2370 until sorted out in 0.11

        if c_idx_nlevels == 1:
            columns = Index([f"a-{i}" for i in range(ncols)], dtype=object)
        else:
            columns = MultiIndex.from_arrays(
                [range(ncols) for _ in range(c_idx_nlevels)],
                names=[f"i-{i}" for i in range(c_idx_nlevels)],
            )
        if r_idx_nlevels == 1:
            index = Index([f"b-{i}" for i in range(nrows)], dtype=object)
        else:
            index = MultiIndex.from_arrays(
                [range(nrows) for _ in range(r_idx_nlevels)],
                names=[f"j-{i}" for i in range(r_idx_nlevels)],
            )

        df = DataFrame(
            np.ones((nrows, ncols)),
            columns=columns,
            index=index,
        )

        # This if will be removed once multi-column Excel writing
        # is implemented. For now fixing gh-9794.
        if c_idx_nlevels > 1:
            msg = (
                "Writing to Excel with MultiIndex columns and no index "
                "\\('index'=False\\) is not yet implemented."
            )
            with pytest.raises(NotImplementedError, match=msg):
                roundtrip(df, use_headers, index=False)
        else:
            res = roundtrip(df, use_headers)

            if use_headers:
                assert res.shape == (nrows, ncols + r_idx_nlevels)
            else:
                # First row taken as columns.
                assert res.shape == (nrows - 1, ncols + r_idx_nlevels)

            # No NaNs.
            for r in range(len(res.index)):
                for c in range(len(res.columns)):
                    assert res.iloc[r, c] is not np.nan

    def test_duplicated_columns(self, path):
        # see gh-5235
        df = DataFrame([[1, 2, 3], [1, 2, 3], [1, 2, 3]], columns=["A", "B", "B"])
        df.to_excel(path, sheet_name="test1")
        expected = DataFrame(
            [[1, 2, 3], [1, 2, 3], [1, 2, 3]], columns=["A", "B", "B.1"]
        )

        # By default, we mangle.
        result = pd.read_excel(path, sheet_name="test1", index_col=0)
        tm.assert_frame_equal(result, expected)

        # see gh-11007, gh-10970
        df = DataFrame([[1, 2, 3, 4], [5, 6, 7, 8]], columns=["A", "B", "A", "B"])
        df.to_excel(path, sheet_name="test1")

        result = pd.read_excel(path, sheet_name="test1", index_col=0)
        expected = DataFrame(
            [[1, 2, 3, 4], [5, 6, 7, 8]], columns=["A", "B", "A.1", "B.1"]
        )
        tm.assert_frame_equal(result, expected)

        # see gh-10982
        df.to_excel(path, sheet_name="test1", index=False, header=False)
        result = pd.read_excel(path, sheet_name="test1", header=None)

        expected = DataFrame([[1, 2, 3, 4], [5, 6, 7, 8]])
        tm.assert_frame_equal(result, expected)

    def test_swapped_columns(self, path):
        # Test for issue #5427.
        write_frame = DataFrame({"A": [1, 1, 1], "B": [2, 2, 2]})
        write_frame.to_excel(path, sheet_name="test1", columns=["B", "A"])

        read_frame = pd.read_excel(path, sheet_name="test1", header=0)

        tm.assert_series_equal(write_frame["A"], read_frame["A"])
        tm.assert_series_equal(write_frame["B"], read_frame["B"])

    def test_invalid_columns(self, path):
        # see gh-10982
        write_frame = DataFrame({"A": [1, 1, 1], "B": [2, 2, 2]})

        with pytest.raises(KeyError, match="Not all names specified"):
            write_frame.to_excel(path, sheet_name="test1", columns=["B", "C"])

        with pytest.raises(
            KeyError, match="'passes columns are not ALL present dataframe'"
        ):
            write_frame.to_excel(path, sheet_name="test1", columns=["C", "D"])

    @pytest.mark.parametrize(
        "to_excel_index,read_excel_index_col",
        [
            (True, 0),  # Include index in write to file
            (False, None),  # Dont include index in write to file
        ],
    )
    def test_write_subset_columns(self, path, to_excel_index, read_excel_index_col):
        # GH 31677
        write_frame = DataFrame({"A": [1, 1, 1], "B": [2, 2, 2], "C": [3, 3, 3]})
        write_frame.to_excel(
            path, sheet_name="col_subset_bug", columns=["A", "B"], index=to_excel_index
        )

        expected = write_frame[["A", "B"]]
        read_frame = pd.read_excel(
            path, sheet_name="col_subset_bug", index_col=read_excel_index_col
        )

        tm.assert_frame_equal(expected, read_frame)

    def test_comment_arg(self, path):
        # see gh-18735
        #
        # Test the comment argument functionality to pd.read_excel.

        # Create file to read in.
        df = DataFrame({"A": ["one", "#one", "one"], "B": ["two", "two", "#two"]})
        df.to_excel(path, sheet_name="test_c")

        # Read file without comment arg.
        result1 = pd.read_excel(path, sheet_name="test_c", index_col=0)

        result1.iloc[1, 0] = None
        result1.iloc[1, 1] = None
        result1.iloc[2, 1] = None

        result2 = pd.read_excel(path, sheet_name="test_c", comment="#", index_col=0)
        tm.assert_frame_equal(result1, result2)

    def test_comment_default(self, path):
        # Re issue #18735
        # Test the comment argument default to pd.read_excel

        # Create file to read in
        df = DataFrame({"A": ["one", "#one", "one"], "B": ["two", "two", "#two"]})
        df.to_excel(path, sheet_name="test_c")

        # Read file with default and explicit comment=None
        result1 = pd.read_excel(path, sheet_name="test_c")
        result2 = pd.read_excel(path, sheet_name="test_c", comment=None)
        tm.assert_frame_equal(result1, result2)

    def test_comment_used(self, path):
        # see gh-18735
        #
        # Test the comment argument is working as expected when used.

        # Create file to read in.
        df = DataFrame({"A": ["one", "#one", "one"], "B": ["two", "two", "#two"]})
        df.to_excel(path, sheet_name="test_c")

        # Test read_frame_comment against manually produced expected output.
        expected = DataFrame({"A": ["one", None, "one"], "B": ["two", None, None]})
        result = pd.read_excel(path, sheet_name="test_c", comment="#", index_col=0)
        tm.assert_frame_equal(result, expected)

    def test_comment_empty_line(self, path):
        # Re issue #18735
        # Test that pd.read_excel ignores commented lines at the end of file

        df = DataFrame({"a": ["1", "#2"], "b": ["2", "3"]})
        df.to_excel(path, index=False)

        # Test that all-comment lines at EoF are ignored
        expected = DataFrame({"a": [1], "b": [2]})
        result = pd.read_excel(path, comment="#")
        tm.assert_frame_equal(result, expected)

    def test_datetimes(self, path):
        # Test writing and reading datetimes. For issue #9139. (xref #9185)
        unit = get_exp_unit(path)
        datetimes = [
            datetime(2013, 1, 13, 1, 2, 3),
            datetime(2013, 1, 13, 2, 45, 56),
            datetime(2013, 1, 13, 4, 29, 49),
            datetime(2013, 1, 13, 6, 13, 42),
            datetime(2013, 1, 13, 7, 57, 35),
            datetime(2013, 1, 13, 9, 41, 28),
            datetime(2013, 1, 13, 11, 25, 21),
            datetime(2013, 1, 13, 13, 9, 14),
            datetime(2013, 1, 13, 14, 53, 7),
            datetime(2013, 1, 13, 16, 37, 0),
            datetime(2013, 1, 13, 18, 20, 52),
        ]

        write_frame = DataFrame({"A": datetimes})
        write_frame.to_excel(path, sheet_name="Sheet1")
        read_frame = pd.read_excel(path, sheet_name="Sheet1", header=0)

        expected = write_frame.astype(f"M8[{unit}]")
        tm.assert_series_equal(expected["A"], read_frame["A"])

    def test_bytes_io(self, engine):
        # see gh-7074
        with BytesIO() as bio:
            df = DataFrame(np.random.default_rng(2).standard_normal((10, 2)))

            # Pass engine explicitly, as there is no file path to infer from.
            with ExcelWriter(bio, engine=engine) as writer:
                df.to_excel(writer)

            bio.seek(0)
            reread_df = pd.read_excel(bio, index_col=0)
            tm.assert_frame_equal(df, reread_df)

    def test_engine_kwargs(self, engine, path):
        # GH#52368
        df = DataFrame([{"A": 1, "B": 2}, {"A": 3, "B": 4}])

        msgs = {
            "odf": r"OpenDocumentSpreadsheet() got an unexpected keyword "
            r"argument 'foo'",
            "openpyxl": r"__init__() got an unexpected keyword argument 'foo'",
            "xlsxwriter": r"__init__() got an unexpected keyword argument 'foo'",
        }

        if PY310:
            msgs[
                "openpyxl"
            ] = "Workbook.__init__() got an unexpected keyword argument 'foo'"
            msgs[
                "xlsxwriter"
            ] = "Workbook.__init__() got an unexpected keyword argument 'foo'"

        # Handle change in error message for openpyxl (write and append mode)
        if engine == "openpyxl" and not os.path.exists(path):
            msgs[
                "openpyxl"
            ] = r"load_workbook() got an unexpected keyword argument 'foo'"

        with pytest.raises(TypeError, match=re.escape(msgs[engine])):
            df.to_excel(
                path,
                engine=engine,
                engine_kwargs={"foo": "bar"},
            )

    def test_write_lists_dict(self, path):
        # see gh-8188.
        df = DataFrame(
            {
                "mixed": ["a", ["b", "c"], {"d": "e", "f": 2}],
                "numeric": [1, 2, 3.0],
                "str": ["apple", "banana", "cherry"],
            }
        )
        df.to_excel(path, sheet_name="Sheet1")
        read = pd.read_excel(path, sheet_name="Sheet1", header=0, index_col=0)

        expected = df.copy()
        expected.mixed = expected.mixed.apply(str)
        expected.numeric = expected.numeric.astype("int64")

        tm.assert_frame_equal(read, expected)

    def test_render_as_column_name(self, path):
        # see gh-34331
        df = DataFrame({"render": [1, 2], "data": [3, 4]})
        df.to_excel(path, sheet_name="Sheet1")
        read = pd.read_excel(path, "Sheet1", index_col=0)
        expected = df
        tm.assert_frame_equal(read, expected)

    def test_true_and_false_value_options(self, path):
        # see gh-13347
        df = DataFrame([["foo", "bar"]], columns=["col1", "col2"], dtype=object)
        with option_context("future.no_silent_downcasting", True):
            expected = df.replace({"foo": True, "bar": False}).astype("bool")

        df.to_excel(path)
        read_frame = pd.read_excel(
            path, true_values=["foo"], false_values=["bar"], index_col=0
        )
        tm.assert_frame_equal(read_frame, expected)

    def test_freeze_panes(self, path):
        # see gh-15160
        expected = DataFrame([[1, 2], [3, 4]], columns=["col1", "col2"])
        expected.to_excel(path, sheet_name="Sheet1", freeze_panes=(1, 1))

        result = pd.read_excel(path, index_col=0)
        tm.assert_frame_equal(result, expected)

    def test_path_path_lib(self, engine, ext):
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=Index(list("ABCD")),
            index=Index([f"i-{i}" for i in range(30)]),
        )
        writer = partial(df.to_excel, engine=engine)

        reader = partial(pd.read_excel, index_col=0)
        result = tm.round_trip_pathlib(writer, reader, path=f"foo{ext}")
        tm.assert_frame_equal(result, df)

    def test_path_local_path(self, engine, ext):
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=Index(list("ABCD")),
            index=Index([f"i-{i}" for i in range(30)]),
        )
        writer = partial(df.to_excel, engine=engine)

        reader = partial(pd.read_excel, index_col=0)
        result = tm.round_trip_localpath(writer, reader, path=f"foo{ext}")
        tm.assert_frame_equal(result, df)

    def test_merged_cell_custom_objects(self, path):
        # see GH-27006
        mi = MultiIndex.from_tuples(
            [
                (pd.Period("2018"), pd.Period("2018Q1")),
                (pd.Period("2018"), pd.Period("2018Q2")),
            ]
        )
        expected = DataFrame(np.ones((2, 2), dtype="int64"), columns=mi)
        expected.to_excel(path)
        result = pd.read_excel(path, header=[0, 1], index_col=0)
        # need to convert PeriodIndexes to standard Indexes for assert equal
        expected.columns = expected.columns.set_levels(
            [[str(i) for i in mi.levels[0]], [str(i) for i in mi.levels[1]]],
            level=[0, 1],
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("dtype", [None, object])
    def test_raise_when_saving_timezones(self, dtype, tz_aware_fixture, path):
        # GH 27008, GH 7056
        tz = tz_aware_fixture
        data = pd.Timestamp("2019", tz=tz)
        df = DataFrame([data], dtype=dtype)
        with pytest.raises(ValueError, match="Excel does not support"):
            df.to_excel(path)

        data = data.to_pydatetime()
        df = DataFrame([data], dtype=dtype)
        with pytest.raises(ValueError, match="Excel does not support"):
            df.to_excel(path)

    def test_excel_duplicate_columns_with_names(self, path):
        # GH#39695
        df = DataFrame({"A": [0, 1], "B": [10, 11]})
        df.to_excel(path, columns=["A", "B", "A"], index=False)

        result = pd.read_excel(path)
        expected = DataFrame([[0, 10, 0], [1, 11, 1]], columns=["A", "B", "A.1"])
        tm.assert_frame_equal(result, expected)

    def test_if_sheet_exists_raises(self, ext):
        # GH 40230
        msg = "if_sheet_exists is only valid in append mode (mode='a')"

        with tm.ensure_clean(ext) as f:
            with pytest.raises(ValueError, match=re.escape(msg)):
                ExcelWriter(f, if_sheet_exists="replace")

    def test_excel_writer_empty_frame(self, engine, ext):
        # GH#45793
        with tm.ensure_clean(ext) as path:
            with ExcelWriter(path, engine=engine) as writer:
                DataFrame().to_excel(writer)
            result = pd.read_excel(path)
            expected = DataFrame()
            tm.assert_frame_equal(result, expected)

    def test_to_excel_empty_frame(self, engine, ext):
        # GH#45793
        with tm.ensure_clean(ext) as path:
            DataFrame().to_excel(path, engine=engine)
            result = pd.read_excel(path)
            expected = DataFrame()
            tm.assert_frame_equal(result, expected)


class TestExcelWriterEngineTests:
    @pytest.mark.parametrize(
        "klass,ext",
        [
            pytest.param(_XlsxWriter, ".xlsx", marks=td.skip_if_no("xlsxwriter")),
            pytest.param(_OpenpyxlWriter, ".xlsx", marks=td.skip_if_no("openpyxl")),
        ],
    )
    def test_ExcelWriter_dispatch(self, klass, ext):
        with tm.ensure_clean(ext) as path:
            with ExcelWriter(path) as writer:
                if ext == ".xlsx" and bool(
                    import_optional_dependency("xlsxwriter", errors="ignore")
                ):
                    # xlsxwriter has preference over openpyxl if both installed
                    assert isinstance(writer, _XlsxWriter)
                else:
                    assert isinstance(writer, klass)

    def test_ExcelWriter_dispatch_raises(self):
        with pytest.raises(ValueError, match="No engine"):
            ExcelWriter("nothing")

    def test_register_writer(self):
        class DummyClass(ExcelWriter):
            called_save = False
            called_write_cells = False
            called_sheets = False
            _supported_extensions = ("xlsx", "xls")
            _engine = "dummy"

            def book(self):
                pass

            def _save(self):
                type(self).called_save = True

            def _write_cells(self, *args, **kwargs):
                type(self).called_write_cells = True

            @property
            def sheets(self):
                type(self).called_sheets = True

            @classmethod
            def assert_called_and_reset(cls):
                assert cls.called_save
                assert cls.called_write_cells
                assert not cls.called_sheets
                cls.called_save = False
                cls.called_write_cells = False

        register_writer(DummyClass)

        with option_context("io.excel.xlsx.writer", "dummy"):
            path = "something.xlsx"
            with tm.ensure_clean(path) as filepath:
                with ExcelWriter(filepath) as writer:
                    assert isinstance(writer, DummyClass)
                df = DataFrame(
                    ["a"],
                    columns=Index(["b"], name="foo"),
                    index=Index(["c"], name="bar"),
                )
                df.to_excel(filepath)
            DummyClass.assert_called_and_reset()

        with tm.ensure_clean("something.xls") as filepath:
            df.to_excel(filepath, engine="dummy")
        DummyClass.assert_called_and_reset()


@td.skip_if_no("xlrd")
@td.skip_if_no("openpyxl")
class TestFSPath:
    def test_excelfile_fspath(self):
        with tm.ensure_clean("foo.xlsx") as path:
            df = DataFrame({"A": [1, 2]})
            df.to_excel(path)
            with ExcelFile(path) as xl:
                result = os.fspath(xl)
            assert result == path

    def test_excelwriter_fspath(self):
        with tm.ensure_clean("foo.xlsx") as path:
            with ExcelWriter(path) as writer:
                assert os.fspath(writer) == str(path)

    def test_to_excel_pos_args_deprecation(self):
        # GH-54229
        df = DataFrame({"a": [1, 2, 3]})
        msg = (
            r"Starting with pandas version 3.0 all arguments of to_excel except "
            r"for the argument 'excel_writer' will be keyword-only."
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            buf = BytesIO()
            writer = ExcelWriter(buf)
            df.to_excel(writer, "Sheet_name_1")


@pytest.mark.parametrize("klass", _writers.values())
def test_subclass_attr(klass):
    # testing that subclasses of ExcelWriter don't have public attributes (issue 49602)
    attrs_base = {name for name in dir(ExcelWriter) if not name.startswith("_")}
    attrs_klass = {name for name in dir(klass) if not name.startswith("_")}
    assert not attrs_base.symmetric_difference(attrs_klass)
