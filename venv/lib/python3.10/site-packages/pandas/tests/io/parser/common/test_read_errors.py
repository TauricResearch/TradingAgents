"""
Tests that work on the Python, C and PyArrow engines but do not have a
specific classification into the other test modules.
"""
import codecs
import csv
from io import StringIO
import os
from pathlib import Path

import numpy as np
import pytest

from pandas.compat import PY311
from pandas.errors import (
    EmptyDataError,
    ParserError,
    ParserWarning,
)

from pandas import DataFrame
import pandas._testing as tm

xfail_pyarrow = pytest.mark.usefixtures("pyarrow_xfail")
skip_pyarrow = pytest.mark.usefixtures("pyarrow_skip")


def test_empty_decimal_marker(all_parsers):
    data = """A|B|C
1|2,334|5
10|13|10.
"""
    # Parsers support only length-1 decimals
    msg = "Only length-1 decimal markers supported"
    parser = all_parsers

    if parser.engine == "pyarrow":
        msg = (
            "only single character unicode strings can be "
            "converted to Py_UCS4, got length 0"
        )

    with pytest.raises(ValueError, match=msg):
        parser.read_csv(StringIO(data), decimal="")


def test_bad_stream_exception(all_parsers, csv_dir_path):
    # see gh-13652
    #
    # This test validates that both the Python engine and C engine will
    # raise UnicodeDecodeError instead of C engine raising ParserError
    # and swallowing the exception that caused read to fail.
    path = os.path.join(csv_dir_path, "sauron.SHIFT_JIS.csv")
    codec = codecs.lookup("utf-8")
    utf8 = codecs.lookup("utf-8")
    parser = all_parsers
    msg = "'utf-8' codec can't decode byte"

    # Stream must be binary UTF8.
    with open(path, "rb") as handle, codecs.StreamRecoder(
        handle, utf8.encode, utf8.decode, codec.streamreader, codec.streamwriter
    ) as stream:
        with pytest.raises(UnicodeDecodeError, match=msg):
            parser.read_csv(stream)


def test_malformed(all_parsers):
    # see gh-6607
    parser = all_parsers
    data = """ignore
A,B,C
1,2,3 # comment
1,2,3,4,5
2,3,4
"""
    msg = "Expected 3 fields in line 4, saw 5"
    err = ParserError
    if parser.engine == "pyarrow":
        msg = "The 'comment' option is not supported with the 'pyarrow' engine"
        err = ValueError
    with pytest.raises(err, match=msg):
        parser.read_csv(StringIO(data), header=1, comment="#")


@pytest.mark.parametrize("nrows", [5, 3, None])
def test_malformed_chunks(all_parsers, nrows):
    data = """ignore
A,B,C
skip
1,2,3
3,5,10 # comment
1,2,3,4,5
2,3,4
"""
    parser = all_parsers

    if parser.engine == "pyarrow":
        msg = "The 'iterator' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(
                StringIO(data),
                header=1,
                comment="#",
                iterator=True,
                chunksize=1,
                skiprows=[2],
            )
        return

    msg = "Expected 3 fields in line 6, saw 5"
    with parser.read_csv(
        StringIO(data), header=1, comment="#", iterator=True, chunksize=1, skiprows=[2]
    ) as reader:
        with pytest.raises(ParserError, match=msg):
            reader.read(nrows)


@xfail_pyarrow  # does not raise
def test_catch_too_many_names(all_parsers):
    # see gh-5156
    data = """\
1,2,3
4,,6
7,8,9
10,11,12\n"""
    parser = all_parsers
    msg = (
        "Too many columns specified: expected 4 and found 3"
        if parser.engine == "c"
        else "Number of passed names did not match "
        "number of header fields in the file"
    )

    with pytest.raises(ValueError, match=msg):
        parser.read_csv(StringIO(data), header=0, names=["a", "b", "c", "d"])


@skip_pyarrow  # CSV parse error: Empty CSV file or block
@pytest.mark.parametrize("nrows", [0, 1, 2, 3, 4, 5])
def test_raise_on_no_columns(all_parsers, nrows):
    parser = all_parsers
    data = "\n" * nrows

    msg = "No columns to parse from file"
    with pytest.raises(EmptyDataError, match=msg):
        parser.read_csv(StringIO(data))


def test_unexpected_keyword_parameter_exception(all_parsers):
    # GH-34976
    parser = all_parsers

    msg = "{}\\(\\) got an unexpected keyword argument 'foo'"
    with pytest.raises(TypeError, match=msg.format("read_csv")):
        parser.read_csv("foo.csv", foo=1)
    with pytest.raises(TypeError, match=msg.format("read_table")):
        parser.read_table("foo.tsv", foo=1)


def test_suppress_error_output(all_parsers):
    # see gh-15925
    parser = all_parsers
    data = "a\n1\n1,2,3\n4\n5,6,7"
    expected = DataFrame({"a": [1, 4]})

    result = parser.read_csv(StringIO(data), on_bad_lines="skip")
    tm.assert_frame_equal(result, expected)


def test_error_bad_lines(all_parsers):
    # see gh-15925
    parser = all_parsers
    data = "a\n1\n1,2,3\n4\n5,6,7"

    msg = "Expected 1 fields in line 3, saw 3"

    if parser.engine == "pyarrow":
        # "CSV parse error: Expected 1 columns, got 3: 1,2,3"
        pytest.skip(reason="https://github.com/apache/arrow/issues/38676")

    with pytest.raises(ParserError, match=msg):
        parser.read_csv(StringIO(data), on_bad_lines="error")


def test_warn_bad_lines(all_parsers):
    # see gh-15925
    parser = all_parsers
    data = "a\n1\n1,2,3\n4\n5,6,7"
    expected = DataFrame({"a": [1, 4]})
    match_msg = "Skipping line"

    expected_warning = ParserWarning
    if parser.engine == "pyarrow":
        match_msg = "Expected 1 columns, but found 3: 1,2,3"
        expected_warning = (ParserWarning, DeprecationWarning)

    with tm.assert_produces_warning(
        expected_warning, match=match_msg, check_stacklevel=False
    ):
        result = parser.read_csv(StringIO(data), on_bad_lines="warn")
    tm.assert_frame_equal(result, expected)


def test_read_csv_wrong_num_columns(all_parsers):
    # Too few columns.
    data = """A,B,C,D,E,F
1,2,3,4,5,6
6,7,8,9,10,11,12
11,12,13,14,15,16
"""
    parser = all_parsers
    msg = "Expected 6 fields in line 3, saw 7"

    if parser.engine == "pyarrow":
        # Expected 6 columns, got 7: 6,7,8,9,10,11,12
        pytest.skip(reason="https://github.com/apache/arrow/issues/38676")

    with pytest.raises(ParserError, match=msg):
        parser.read_csv(StringIO(data))


def test_null_byte_char(request, all_parsers):
    # see gh-2741
    data = "\x00,foo"
    names = ["a", "b"]
    parser = all_parsers

    if parser.engine == "c" or (parser.engine == "python" and PY311):
        if parser.engine == "python" and PY311:
            request.applymarker(
                pytest.mark.xfail(
                    reason="In Python 3.11, this is read as an empty character not null"
                )
            )
        expected = DataFrame([[np.nan, "foo"]], columns=names)
        out = parser.read_csv(StringIO(data), names=names)
        tm.assert_frame_equal(out, expected)
    else:
        if parser.engine == "pyarrow":
            # CSV parse error: Empty CSV file or block: "
            # cannot infer number of columns"
            pytest.skip(reason="https://github.com/apache/arrow/issues/38676")
        else:
            msg = "NULL byte detected"
        with pytest.raises(ParserError, match=msg):
            parser.read_csv(StringIO(data), names=names)


@pytest.mark.filterwarnings("always::ResourceWarning")
def test_open_file(request, all_parsers):
    # GH 39024
    parser = all_parsers

    msg = "Could not determine delimiter"
    err = csv.Error
    if parser.engine == "c":
        msg = "the 'c' engine does not support sep=None with delim_whitespace=False"
        err = ValueError
    elif parser.engine == "pyarrow":
        msg = (
            "the 'pyarrow' engine does not support sep=None with delim_whitespace=False"
        )
        err = ValueError

    with tm.ensure_clean() as path:
        file = Path(path)
        file.write_bytes(b"\xe4\na\n1")

        with tm.assert_produces_warning(None):
            # should not trigger a ResourceWarning
            with pytest.raises(err, match=msg):
                parser.read_csv(file, sep=None, encoding_errors="replace")


def test_invalid_on_bad_line(all_parsers):
    parser = all_parsers
    data = "a\n1\n1,2,3\n4\n5,6,7"
    with pytest.raises(ValueError, match="Argument abc is invalid for on_bad_lines"):
        parser.read_csv(StringIO(data), on_bad_lines="abc")


def test_bad_header_uniform_error(all_parsers):
    parser = all_parsers
    data = "+++123456789...\ncol1,col2,col3,col4\n1,2,3,4\n"
    msg = "Expected 2 fields in line 2, saw 4"
    if parser.engine == "c":
        msg = (
            "Could not construct index. Requested to use 1 "
            "number of columns, but 3 left to parse."
        )
    elif parser.engine == "pyarrow":
        # "CSV parse error: Expected 1 columns, got 4: col1,col2,col3,col4"
        pytest.skip(reason="https://github.com/apache/arrow/issues/38676")

    with pytest.raises(ParserError, match=msg):
        parser.read_csv(StringIO(data), index_col=0, on_bad_lines="error")


def test_on_bad_lines_warn_correct_formatting(all_parsers):
    # see gh-15925
    parser = all_parsers
    data = """1,2
a,b
a,b,c
a,b,d
a,b
"""
    expected = DataFrame({"1": "a", "2": ["b"] * 2})
    match_msg = "Skipping line"

    expected_warning = ParserWarning
    if parser.engine == "pyarrow":
        match_msg = "Expected 2 columns, but found 3: a,b,c"
        expected_warning = (ParserWarning, DeprecationWarning)

    with tm.assert_produces_warning(
        expected_warning, match=match_msg, check_stacklevel=False
    ):
        result = parser.read_csv(StringIO(data), on_bad_lines="warn")
    tm.assert_frame_equal(result, expected)
