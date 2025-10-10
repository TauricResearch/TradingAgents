import contextlib

import pytest

from pandas.compat import is_platform_windows

from pandas import DataFrame
import pandas._testing as tm

from pandas.io.excel import ExcelWriter

xlsxwriter = pytest.importorskip("xlsxwriter")

if is_platform_windows():
    pytestmark = pytest.mark.single_cpu


@pytest.fixture
def ext():
    return ".xlsx"


def test_column_format(ext):
    # Test that column formats are applied to cells. Test for issue #9167.
    # Applicable to xlsxwriter only.
    openpyxl = pytest.importorskip("openpyxl")

    with tm.ensure_clean(ext) as path:
        frame = DataFrame({"A": [123456, 123456], "B": [123456, 123456]})

        with ExcelWriter(path) as writer:
            frame.to_excel(writer)

            # Add a number format to col B and ensure it is applied to cells.
            num_format = "#,##0"
            write_workbook = writer.book
            write_worksheet = write_workbook.worksheets()[0]
            col_format = write_workbook.add_format({"num_format": num_format})
            write_worksheet.set_column("B:B", None, col_format)

        with contextlib.closing(openpyxl.load_workbook(path)) as read_workbook:
            try:
                read_worksheet = read_workbook["Sheet1"]
            except TypeError:
                # compat
                read_worksheet = read_workbook.get_sheet_by_name(name="Sheet1")

        # Get the number format from the cell.
        try:
            cell = read_worksheet["B2"]
        except TypeError:
            # compat
            cell = read_worksheet.cell("B2")

        try:
            read_num_format = cell.number_format
        except AttributeError:
            read_num_format = cell.style.number_format._format_code

        assert read_num_format == num_format


def test_write_append_mode_raises(ext):
    msg = "Append mode is not supported with xlsxwriter!"

    with tm.ensure_clean(ext) as f:
        with pytest.raises(ValueError, match=msg):
            ExcelWriter(f, engine="xlsxwriter", mode="a")


@pytest.mark.parametrize("nan_inf_to_errors", [True, False])
def test_engine_kwargs(ext, nan_inf_to_errors):
    # GH 42286
    engine_kwargs = {"options": {"nan_inf_to_errors": nan_inf_to_errors}}
    with tm.ensure_clean(ext) as f:
        with ExcelWriter(f, engine="xlsxwriter", engine_kwargs=engine_kwargs) as writer:
            assert writer.book.nan_inf_to_errors == nan_inf_to_errors


def test_book_and_sheets_consistent(ext):
    # GH#45687 - Ensure sheets is updated if user modifies book
    with tm.ensure_clean(ext) as f:
        with ExcelWriter(f, engine="xlsxwriter") as writer:
            assert writer.sheets == {}
            sheet = writer.book.add_worksheet("test_name")
            assert writer.sheets == {"test_name": sheet}
