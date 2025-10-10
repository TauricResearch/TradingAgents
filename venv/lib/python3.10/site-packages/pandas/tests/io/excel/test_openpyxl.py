import contextlib
from pathlib import Path
import re

import numpy as np
import pytest

from pandas.compat import is_platform_windows

import pandas as pd
from pandas import DataFrame
import pandas._testing as tm

from pandas.io.excel import (
    ExcelWriter,
    _OpenpyxlWriter,
)
from pandas.io.excel._openpyxl import OpenpyxlReader

openpyxl = pytest.importorskip("openpyxl")

if is_platform_windows():
    pytestmark = pytest.mark.single_cpu


@pytest.fixture
def ext():
    return ".xlsx"


def test_to_excel_styleconverter():
    from openpyxl import styles

    hstyle = {
        "font": {"color": "00FF0000", "bold": True},
        "borders": {"top": "thin", "right": "thin", "bottom": "thin", "left": "thin"},
        "alignment": {"horizontal": "center", "vertical": "top"},
        "fill": {"patternType": "solid", "fgColor": {"rgb": "006666FF", "tint": 0.3}},
        "number_format": {"format_code": "0.00"},
        "protection": {"locked": True, "hidden": False},
    }

    font_color = styles.Color("00FF0000")
    font = styles.Font(bold=True, color=font_color)
    side = styles.Side(style=styles.borders.BORDER_THIN)
    border = styles.Border(top=side, right=side, bottom=side, left=side)
    alignment = styles.Alignment(horizontal="center", vertical="top")
    fill_color = styles.Color(rgb="006666FF", tint=0.3)
    fill = styles.PatternFill(patternType="solid", fgColor=fill_color)

    number_format = "0.00"

    protection = styles.Protection(locked=True, hidden=False)

    kw = _OpenpyxlWriter._convert_to_style_kwargs(hstyle)
    assert kw["font"] == font
    assert kw["border"] == border
    assert kw["alignment"] == alignment
    assert kw["fill"] == fill
    assert kw["number_format"] == number_format
    assert kw["protection"] == protection


def test_write_cells_merge_styled(ext):
    from pandas.io.formats.excel import ExcelCell

    sheet_name = "merge_styled"

    sty_b1 = {"font": {"color": "00FF0000"}}
    sty_a2 = {"font": {"color": "0000FF00"}}

    initial_cells = [
        ExcelCell(col=1, row=0, val=42, style=sty_b1),
        ExcelCell(col=0, row=1, val=99, style=sty_a2),
    ]

    sty_merged = {"font": {"color": "000000FF", "bold": True}}
    sty_kwargs = _OpenpyxlWriter._convert_to_style_kwargs(sty_merged)
    openpyxl_sty_merged = sty_kwargs["font"]
    merge_cells = [
        ExcelCell(
            col=0, row=0, val="pandas", mergestart=1, mergeend=1, style=sty_merged
        )
    ]

    with tm.ensure_clean(ext) as path:
        with _OpenpyxlWriter(path) as writer:
            writer._write_cells(initial_cells, sheet_name=sheet_name)
            writer._write_cells(merge_cells, sheet_name=sheet_name)

            wks = writer.sheets[sheet_name]
        xcell_b1 = wks["B1"]
        xcell_a2 = wks["A2"]
        assert xcell_b1.font == openpyxl_sty_merged
        assert xcell_a2.font == openpyxl_sty_merged


@pytest.mark.parametrize("iso_dates", [True, False])
def test_engine_kwargs_write(ext, iso_dates):
    # GH 42286 GH 43445
    engine_kwargs = {"iso_dates": iso_dates}
    with tm.ensure_clean(ext) as f:
        with ExcelWriter(f, engine="openpyxl", engine_kwargs=engine_kwargs) as writer:
            assert writer.book.iso_dates == iso_dates
            # ExcelWriter won't allow us to close without writing something
            DataFrame().to_excel(writer)


def test_engine_kwargs_append_invalid(ext):
    # GH 43445
    # test whether an invalid engine kwargs actually raises
    with tm.ensure_clean(ext) as f:
        DataFrame(["hello", "world"]).to_excel(f)
        with pytest.raises(
            TypeError,
            match=re.escape(
                "load_workbook() got an unexpected keyword argument 'apple_banana'"
            ),
        ):
            with ExcelWriter(
                f, engine="openpyxl", mode="a", engine_kwargs={"apple_banana": "fruit"}
            ) as writer:
                # ExcelWriter needs us to write something to close properly
                DataFrame(["good"]).to_excel(writer, sheet_name="Sheet2")


@pytest.mark.parametrize("data_only, expected", [(True, 0), (False, "=1+1")])
def test_engine_kwargs_append_data_only(ext, data_only, expected):
    # GH 43445
    # tests whether the data_only engine_kwarg actually works well for
    # openpyxl's load_workbook
    with tm.ensure_clean(ext) as f:
        DataFrame(["=1+1"]).to_excel(f)
        with ExcelWriter(
            f, engine="openpyxl", mode="a", engine_kwargs={"data_only": data_only}
        ) as writer:
            assert writer.sheets["Sheet1"]["B2"].value == expected
            # ExcelWriter needs us to writer something to close properly?
            DataFrame().to_excel(writer, sheet_name="Sheet2")

        # ensure that data_only also works for reading
        #  and that formulas/values roundtrip
        assert (
            pd.read_excel(
                f,
                sheet_name="Sheet1",
                engine="openpyxl",
                engine_kwargs={"data_only": data_only},
            ).iloc[0, 1]
            == expected
        )


@pytest.mark.parametrize("kwarg_name", ["read_only", "data_only"])
@pytest.mark.parametrize("kwarg_value", [True, False])
def test_engine_kwargs_append_reader(datapath, ext, kwarg_name, kwarg_value):
    # GH 55027
    # test that `read_only` and `data_only` can be passed to
    #  `openpyxl.reader.excel.load_workbook` via `engine_kwargs`
    filename = datapath("io", "data", "excel", "test1" + ext)
    with contextlib.closing(
        OpenpyxlReader(filename, engine_kwargs={kwarg_name: kwarg_value})
    ) as reader:
        assert getattr(reader.book, kwarg_name) == kwarg_value


@pytest.mark.parametrize(
    "mode,expected", [("w", ["baz"]), ("a", ["foo", "bar", "baz"])]
)
def test_write_append_mode(ext, mode, expected):
    df = DataFrame([1], columns=["baz"])

    with tm.ensure_clean(ext) as f:
        wb = openpyxl.Workbook()
        wb.worksheets[0].title = "foo"
        wb.worksheets[0]["A1"].value = "foo"
        wb.create_sheet("bar")
        wb.worksheets[1]["A1"].value = "bar"
        wb.save(f)

        with ExcelWriter(f, engine="openpyxl", mode=mode) as writer:
            df.to_excel(writer, sheet_name="baz", index=False)

        with contextlib.closing(openpyxl.load_workbook(f)) as wb2:
            result = [sheet.title for sheet in wb2.worksheets]
            assert result == expected

            for index, cell_value in enumerate(expected):
                assert wb2.worksheets[index]["A1"].value == cell_value


@pytest.mark.parametrize(
    "if_sheet_exists,num_sheets,expected",
    [
        ("new", 2, ["apple", "banana"]),
        ("replace", 1, ["pear"]),
        ("overlay", 1, ["pear", "banana"]),
    ],
)
def test_if_sheet_exists_append_modes(ext, if_sheet_exists, num_sheets, expected):
    # GH 40230
    df1 = DataFrame({"fruit": ["apple", "banana"]})
    df2 = DataFrame({"fruit": ["pear"]})

    with tm.ensure_clean(ext) as f:
        df1.to_excel(f, engine="openpyxl", sheet_name="foo", index=False)
        with ExcelWriter(
            f, engine="openpyxl", mode="a", if_sheet_exists=if_sheet_exists
        ) as writer:
            df2.to_excel(writer, sheet_name="foo", index=False)

        with contextlib.closing(openpyxl.load_workbook(f)) as wb:
            assert len(wb.sheetnames) == num_sheets
            assert wb.sheetnames[0] == "foo"
            result = pd.read_excel(wb, "foo", engine="openpyxl")
            assert list(result["fruit"]) == expected
            if len(wb.sheetnames) == 2:
                result = pd.read_excel(wb, wb.sheetnames[1], engine="openpyxl")
                tm.assert_frame_equal(result, df2)


@pytest.mark.parametrize(
    "startrow, startcol, greeting, goodbye",
    [
        (0, 0, ["poop", "world"], ["goodbye", "people"]),
        (0, 1, ["hello", "world"], ["poop", "people"]),
        (1, 0, ["hello", "poop"], ["goodbye", "people"]),
        (1, 1, ["hello", "world"], ["goodbye", "poop"]),
    ],
)
def test_append_overlay_startrow_startcol(ext, startrow, startcol, greeting, goodbye):
    df1 = DataFrame({"greeting": ["hello", "world"], "goodbye": ["goodbye", "people"]})
    df2 = DataFrame(["poop"])

    with tm.ensure_clean(ext) as f:
        df1.to_excel(f, engine="openpyxl", sheet_name="poo", index=False)
        with ExcelWriter(
            f, engine="openpyxl", mode="a", if_sheet_exists="overlay"
        ) as writer:
            # use startrow+1 because we don't have a header
            df2.to_excel(
                writer,
                index=False,
                header=False,
                startrow=startrow + 1,
                startcol=startcol,
                sheet_name="poo",
            )

        result = pd.read_excel(f, sheet_name="poo", engine="openpyxl")
        expected = DataFrame({"greeting": greeting, "goodbye": goodbye})
        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "if_sheet_exists,msg",
    [
        (
            "invalid",
            "'invalid' is not valid for if_sheet_exists. Valid options "
            "are 'error', 'new', 'replace' and 'overlay'.",
        ),
        (
            "error",
            "Sheet 'foo' already exists and if_sheet_exists is set to 'error'.",
        ),
        (
            None,
            "Sheet 'foo' already exists and if_sheet_exists is set to 'error'.",
        ),
    ],
)
def test_if_sheet_exists_raises(ext, if_sheet_exists, msg):
    # GH 40230
    df = DataFrame({"fruit": ["pear"]})
    with tm.ensure_clean(ext) as f:
        with pytest.raises(ValueError, match=re.escape(msg)):
            df.to_excel(f, sheet_name="foo", engine="openpyxl")
            with ExcelWriter(
                f, engine="openpyxl", mode="a", if_sheet_exists=if_sheet_exists
            ) as writer:
                df.to_excel(writer, sheet_name="foo")


def test_to_excel_with_openpyxl_engine(ext):
    # GH 29854
    with tm.ensure_clean(ext) as filename:
        df1 = DataFrame({"A": np.linspace(1, 10, 10)})
        df2 = DataFrame({"B": np.linspace(1, 20, 10)})
        df = pd.concat([df1, df2], axis=1)
        styled = df.style.map(
            lambda val: f"color: {'red' if val < 0 else 'black'}"
        ).highlight_max()

        styled.to_excel(filename, engine="openpyxl")


@pytest.mark.parametrize("read_only", [True, False])
def test_read_workbook(datapath, ext, read_only):
    # GH 39528
    filename = datapath("io", "data", "excel", "test1" + ext)
    with contextlib.closing(
        openpyxl.load_workbook(filename, read_only=read_only)
    ) as wb:
        result = pd.read_excel(wb, engine="openpyxl")
    expected = pd.read_excel(filename)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "header, expected_data",
    [
        (
            0,
            {
                "Title": [np.nan, "A", 1, 2, 3],
                "Unnamed: 1": [np.nan, "B", 4, 5, 6],
                "Unnamed: 2": [np.nan, "C", 7, 8, 9],
            },
        ),
        (2, {"A": [1, 2, 3], "B": [4, 5, 6], "C": [7, 8, 9]}),
    ],
)
@pytest.mark.parametrize(
    "filename", ["dimension_missing", "dimension_small", "dimension_large"]
)
# When read_only is None, use read_excel instead of a workbook
@pytest.mark.parametrize("read_only", [True, False, None])
def test_read_with_bad_dimension(
    datapath, ext, header, expected_data, filename, read_only
):
    # GH 38956, 39001 - no/incorrect dimension information
    path = datapath("io", "data", "excel", f"{filename}{ext}")
    if read_only is None:
        result = pd.read_excel(path, header=header)
    else:
        with contextlib.closing(
            openpyxl.load_workbook(path, read_only=read_only)
        ) as wb:
            result = pd.read_excel(wb, engine="openpyxl", header=header)
    expected = DataFrame(expected_data)
    tm.assert_frame_equal(result, expected)


def test_append_mode_file(ext):
    # GH 39576
    df = DataFrame()

    with tm.ensure_clean(ext) as f:
        df.to_excel(f, engine="openpyxl")

        with ExcelWriter(
            f, mode="a", engine="openpyxl", if_sheet_exists="new"
        ) as writer:
            df.to_excel(writer)

        # make sure that zip files are not concatenated by making sure that
        # "docProps/app.xml" only occurs twice in the file
        data = Path(f).read_bytes()
        first = data.find(b"docProps/app.xml")
        second = data.find(b"docProps/app.xml", first + 1)
        third = data.find(b"docProps/app.xml", second + 1)
        assert second != -1 and third == -1


# When read_only is None, use read_excel instead of a workbook
@pytest.mark.parametrize("read_only", [True, False, None])
def test_read_with_empty_trailing_rows(datapath, ext, read_only):
    # GH 39181
    path = datapath("io", "data", "excel", f"empty_trailing_rows{ext}")
    if read_only is None:
        result = pd.read_excel(path)
    else:
        with contextlib.closing(
            openpyxl.load_workbook(path, read_only=read_only)
        ) as wb:
            result = pd.read_excel(wb, engine="openpyxl")
    expected = DataFrame(
        {
            "Title": [np.nan, "A", 1, 2, 3],
            "Unnamed: 1": [np.nan, "B", 4, 5, 6],
            "Unnamed: 2": [np.nan, "C", 7, 8, 9],
        }
    )
    tm.assert_frame_equal(result, expected)


# When read_only is None, use read_excel instead of a workbook
@pytest.mark.parametrize("read_only", [True, False, None])
def test_read_empty_with_blank_row(datapath, ext, read_only):
    # GH 39547 - empty excel file with a row that has no data
    path = datapath("io", "data", "excel", f"empty_with_blank_row{ext}")
    if read_only is None:
        result = pd.read_excel(path)
    else:
        with contextlib.closing(
            openpyxl.load_workbook(path, read_only=read_only)
        ) as wb:
            result = pd.read_excel(wb, engine="openpyxl")
    expected = DataFrame()
    tm.assert_frame_equal(result, expected)


def test_book_and_sheets_consistent(ext):
    # GH#45687 - Ensure sheets is updated if user modifies book
    with tm.ensure_clean(ext) as f:
        with ExcelWriter(f, engine="openpyxl") as writer:
            assert writer.sheets == {}
            sheet = writer.book.create_sheet("test_name", 0)
            assert writer.sheets == {"test_name": sheet}


def test_ints_spelled_with_decimals(datapath, ext):
    # GH 46988 - openpyxl returns this sheet with floats
    path = datapath("io", "data", "excel", f"ints_spelled_with_decimals{ext}")
    result = pd.read_excel(path)
    expected = DataFrame(range(2, 12), columns=[1])
    tm.assert_frame_equal(result, expected)


def test_read_multiindex_header_no_index_names(datapath, ext):
    # GH#47487
    path = datapath("io", "data", "excel", f"multiindex_no_index_names{ext}")
    result = pd.read_excel(path, index_col=[0, 1, 2], header=[0, 1, 2])
    expected = DataFrame(
        [[np.nan, "x", "x", "x"], ["x", np.nan, np.nan, np.nan]],
        columns=pd.MultiIndex.from_tuples(
            [("X", "Y", "A1"), ("X", "Y", "A2"), ("XX", "YY", "B1"), ("XX", "YY", "B2")]
        ),
        index=pd.MultiIndex.from_tuples([("A", "AA", "AAA"), ("A", "BB", "BBB")]),
    )
    tm.assert_frame_equal(result, expected)
