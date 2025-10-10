"""
Tests that work on both the Python and C engines but do not have a
specific classification into the other test modules.
"""
import csv
from io import StringIO

import pytest

from pandas import DataFrame
import pandas._testing as tm

from pandas.io.parsers import TextParser

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)

xfail_pyarrow = pytest.mark.usefixtures("pyarrow_xfail")


@xfail_pyarrow
def test_read_data_list(all_parsers):
    parser = all_parsers
    kwargs = {"index_col": 0}
    data = "A,B,C\nfoo,1,2,3\nbar,4,5,6"

    data_list = [["A", "B", "C"], ["foo", "1", "2", "3"], ["bar", "4", "5", "6"]]
    expected = parser.read_csv(StringIO(data), **kwargs)

    with TextParser(data_list, chunksize=2, **kwargs) as parser:
        result = parser.read()

    tm.assert_frame_equal(result, expected)


def test_reader_list(all_parsers):
    data = """index,A,B,C,D
foo,2,3,4,5
bar,7,8,9,10
baz,12,13,14,15
qux,12,13,14,15
foo2,12,13,14,15
bar2,12,13,14,15
"""
    parser = all_parsers
    kwargs = {"index_col": 0}

    lines = list(csv.reader(StringIO(data)))
    with TextParser(lines, chunksize=2, **kwargs) as reader:
        chunks = list(reader)

    expected = parser.read_csv(StringIO(data), **kwargs)

    tm.assert_frame_equal(chunks[0], expected[:2])
    tm.assert_frame_equal(chunks[1], expected[2:4])
    tm.assert_frame_equal(chunks[2], expected[4:])


def test_reader_list_skiprows(all_parsers):
    data = """index,A,B,C,D
foo,2,3,4,5
bar,7,8,9,10
baz,12,13,14,15
qux,12,13,14,15
foo2,12,13,14,15
bar2,12,13,14,15
"""
    parser = all_parsers
    kwargs = {"index_col": 0}

    lines = list(csv.reader(StringIO(data)))
    with TextParser(lines, chunksize=2, skiprows=[1], **kwargs) as reader:
        chunks = list(reader)

    expected = parser.read_csv(StringIO(data), **kwargs)

    tm.assert_frame_equal(chunks[0], expected[1:3])


def test_read_csv_parse_simple_list(all_parsers):
    parser = all_parsers
    data = """foo
bar baz
qux foo
foo
bar"""

    result = parser.read_csv(StringIO(data), header=None)
    expected = DataFrame(["foo", "bar baz", "qux foo", "foo", "bar"])
    tm.assert_frame_equal(result, expected)
