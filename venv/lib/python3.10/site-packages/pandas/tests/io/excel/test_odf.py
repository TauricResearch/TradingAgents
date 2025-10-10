import functools

import numpy as np
import pytest

from pandas.compat import is_platform_windows

import pandas as pd
import pandas._testing as tm

pytest.importorskip("odf")

if is_platform_windows():
    pytestmark = pytest.mark.single_cpu


@pytest.fixture(autouse=True)
def cd_and_set_engine(monkeypatch, datapath):
    func = functools.partial(pd.read_excel, engine="odf")
    monkeypatch.setattr(pd, "read_excel", func)
    monkeypatch.chdir(datapath("io", "data", "excel"))


def test_read_invalid_types_raises():
    # the invalid_value_type.ods required manually editing
    # of the included content.xml file
    with pytest.raises(ValueError, match="Unrecognized type awesome_new_type"):
        pd.read_excel("invalid_value_type.ods")


def test_read_writer_table():
    # Also test reading tables from an text OpenDocument file
    # (.odt)
    index = pd.Index(["Row 1", "Row 2", "Row 3"], name="Header")
    expected = pd.DataFrame(
        [[1, np.nan, 7], [2, np.nan, 8], [3, np.nan, 9]],
        index=index,
        columns=["Column 1", "Unnamed: 2", "Column 3"],
    )

    result = pd.read_excel("writertable.odt", sheet_name="Table1", index_col=0)

    tm.assert_frame_equal(result, expected)


def test_read_newlines_between_xml_elements_table():
    # GH#45598
    expected = pd.DataFrame(
        [[1.0, 4.0, 7], [np.nan, np.nan, 8], [3.0, 6.0, 9]],
        columns=["Column 1", "Column 2", "Column 3"],
    )

    result = pd.read_excel("test_newlines.ods")

    tm.assert_frame_equal(result, expected)


def test_read_unempty_cells():
    expected = pd.DataFrame(
        [1, np.nan, 3, np.nan, 5],
        columns=["Column 1"],
    )

    result = pd.read_excel("test_unempty_cells.ods")

    tm.assert_frame_equal(result, expected)


def test_read_cell_annotation():
    expected = pd.DataFrame(
        ["test", np.nan, "test 3"],
        columns=["Column 1"],
    )

    result = pd.read_excel("test_cell_annotation.ods")

    tm.assert_frame_equal(result, expected)
