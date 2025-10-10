from datetime import (
    date,
    datetime,
)
import re

import pytest

from pandas.compat import is_platform_windows

import pandas as pd
import pandas._testing as tm

from pandas.io.excel import ExcelWriter

odf = pytest.importorskip("odf")

if is_platform_windows():
    pytestmark = pytest.mark.single_cpu


@pytest.fixture
def ext():
    return ".ods"


def test_write_append_mode_raises(ext):
    msg = "Append mode is not supported with odf!"

    with tm.ensure_clean(ext) as f:
        with pytest.raises(ValueError, match=msg):
            ExcelWriter(f, engine="odf", mode="a")


@pytest.mark.parametrize("engine_kwargs", [None, {"kwarg": 1}])
def test_engine_kwargs(ext, engine_kwargs):
    # GH 42286
    # GH 43445
    # test for error: OpenDocumentSpreadsheet does not accept any arguments
    with tm.ensure_clean(ext) as f:
        if engine_kwargs is not None:
            error = re.escape(
                "OpenDocumentSpreadsheet() got an unexpected keyword argument 'kwarg'"
            )
            with pytest.raises(
                TypeError,
                match=error,
            ):
                ExcelWriter(f, engine="odf", engine_kwargs=engine_kwargs)
        else:
            with ExcelWriter(f, engine="odf", engine_kwargs=engine_kwargs) as _:
                pass


def test_book_and_sheets_consistent(ext):
    # GH#45687 - Ensure sheets is updated if user modifies book
    with tm.ensure_clean(ext) as f:
        with ExcelWriter(f) as writer:
            assert writer.sheets == {}
            table = odf.table.Table(name="test_name")
            writer.book.spreadsheet.addElement(table)
            assert writer.sheets == {"test_name": table}


@pytest.mark.parametrize(
    ["value", "cell_value_type", "cell_value_attribute", "cell_value"],
    argvalues=[
        (True, "boolean", "boolean-value", "true"),
        ("test string", "string", "string-value", "test string"),
        (1, "float", "value", "1"),
        (1.5, "float", "value", "1.5"),
        (
            datetime(2010, 10, 10, 10, 10, 10),
            "date",
            "date-value",
            "2010-10-10T10:10:10",
        ),
        (date(2010, 10, 10), "date", "date-value", "2010-10-10"),
    ],
)
def test_cell_value_type(ext, value, cell_value_type, cell_value_attribute, cell_value):
    # GH#54994 ODS: cell attributes should follow specification
    # http://docs.oasis-open.org/office/v1.2/os/OpenDocument-v1.2-os-part1.html#refTable13
    from odf.namespaces import OFFICENS
    from odf.table import (
        TableCell,
        TableRow,
    )

    table_cell_name = TableCell().qname

    with tm.ensure_clean(ext) as f:
        pd.DataFrame([[value]]).to_excel(f, header=False, index=False)

        with pd.ExcelFile(f) as wb:
            sheet = wb._reader.get_sheet_by_index(0)
            sheet_rows = sheet.getElementsByType(TableRow)
            sheet_cells = [
                x
                for x in sheet_rows[0].childNodes
                if hasattr(x, "qname") and x.qname == table_cell_name
            ]

            cell = sheet_cells[0]
            assert cell.attributes.get((OFFICENS, "value-type")) == cell_value_type
            assert cell.attributes.get((OFFICENS, cell_value_attribute)) == cell_value
