"""
Tests encoding functionality during parsing
for all of the parsers defined in parsers.py
"""
from io import (
    BytesIO,
    TextIOWrapper,
)
import os
import tempfile
import uuid

import numpy as np
import pytest

from pandas import (
    DataFrame,
    read_csv,
)
import pandas._testing as tm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)

skip_pyarrow = pytest.mark.usefixtures("pyarrow_skip")


def test_bytes_io_input(all_parsers):
    encoding = "cp1255"
    parser = all_parsers

    data = BytesIO("שלום:1234\n562:123".encode(encoding))
    result = parser.read_csv(data, sep=":", encoding=encoding)

    expected = DataFrame([[562, 123]], columns=["שלום", "1234"])
    tm.assert_frame_equal(result, expected)


@skip_pyarrow  # CSV parse error: Empty CSV file or block
def test_read_csv_unicode(all_parsers):
    parser = all_parsers
    data = BytesIO("\u0141aski, Jan;1".encode())

    result = parser.read_csv(data, sep=";", encoding="utf-8", header=None)
    expected = DataFrame([["\u0141aski, Jan", 1]])
    tm.assert_frame_equal(result, expected)


@skip_pyarrow
@pytest.mark.parametrize("sep", [",", "\t"])
@pytest.mark.parametrize("encoding", ["utf-16", "utf-16le", "utf-16be"])
def test_utf16_bom_skiprows(all_parsers, sep, encoding):
    # see gh-2298
    parser = all_parsers
    data = """skip this
skip this too
A,B,C
1,2,3
4,5,6""".replace(
        ",", sep
    )
    path = f"__{uuid.uuid4()}__.csv"
    kwargs = {"sep": sep, "skiprows": 2}
    utf8 = "utf-8"

    with tm.ensure_clean(path) as path:
        bytes_data = data.encode(encoding)

        with open(path, "wb") as f:
            f.write(bytes_data)

        with TextIOWrapper(BytesIO(data.encode(utf8)), encoding=utf8) as bytes_buffer:
            result = parser.read_csv(path, encoding=encoding, **kwargs)
            expected = parser.read_csv(bytes_buffer, encoding=utf8, **kwargs)
        tm.assert_frame_equal(result, expected)


def test_utf16_example(all_parsers, csv_dir_path):
    path = os.path.join(csv_dir_path, "utf16_ex.txt")
    parser = all_parsers
    result = parser.read_csv(path, encoding="utf-16", sep="\t")
    assert len(result) == 50


def test_unicode_encoding(all_parsers, csv_dir_path):
    path = os.path.join(csv_dir_path, "unicode_series.csv")
    parser = all_parsers

    result = parser.read_csv(path, header=None, encoding="latin-1")
    result = result.set_index(0)
    got = result[1][1632]

    expected = "\xc1 k\xf6ldum klaka (Cold Fever) (1994)"
    assert got == expected


@pytest.mark.parametrize(
    "data,kwargs,expected",
    [
        # Basic test
        ("a\n1", {}, DataFrame({"a": [1]})),
        # "Regular" quoting
        ('"a"\n1', {"quotechar": '"'}, DataFrame({"a": [1]})),
        # Test in a data row instead of header
        ("b\n1", {"names": ["a"]}, DataFrame({"a": ["b", "1"]})),
        # Test in empty data row with skipping
        ("\n1", {"names": ["a"], "skip_blank_lines": True}, DataFrame({"a": [1]})),
        # Test in empty data row without skipping
        (
            "\n1",
            {"names": ["a"], "skip_blank_lines": False},
            DataFrame({"a": [np.nan, 1]}),
        ),
    ],
)
def test_utf8_bom(all_parsers, data, kwargs, expected, request):
    # see gh-4793
    parser = all_parsers
    bom = "\ufeff"
    utf8 = "utf-8"

    def _encode_data_with_bom(_data):
        bom_data = (bom + _data).encode(utf8)
        return BytesIO(bom_data)

    if (
        parser.engine == "pyarrow"
        and data == "\n1"
        and kwargs.get("skip_blank_lines", True)
    ):
        # CSV parse error: Empty CSV file or block: cannot infer number of columns
        pytest.skip(reason="https://github.com/apache/arrow/issues/38676")

    result = parser.read_csv(_encode_data_with_bom(data), encoding=utf8, **kwargs)
    tm.assert_frame_equal(result, expected)


def test_read_csv_utf_aliases(all_parsers, utf_value, encoding_fmt):
    # see gh-13549
    expected = DataFrame({"mb_num": [4.8], "multibyte": ["test"]})
    parser = all_parsers

    encoding = encoding_fmt.format(utf_value)
    data = "mb_num,multibyte\n4.8,test".encode(encoding)

    result = parser.read_csv(BytesIO(data), encoding=encoding)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "file_path,encoding",
    [
        (("io", "data", "csv", "test1.csv"), "utf-8"),
        (("io", "parser", "data", "unicode_series.csv"), "latin-1"),
        (("io", "parser", "data", "sauron.SHIFT_JIS.csv"), "shiftjis"),
    ],
)
def test_binary_mode_file_buffers(all_parsers, file_path, encoding, datapath):
    # gh-23779: Python csv engine shouldn't error on files opened in binary.
    # gh-31575: Python csv engine shouldn't error on files opened in raw binary.
    parser = all_parsers

    fpath = datapath(*file_path)
    expected = parser.read_csv(fpath, encoding=encoding)

    with open(fpath, encoding=encoding) as fa:
        result = parser.read_csv(fa)
        assert not fa.closed
    tm.assert_frame_equal(expected, result)

    with open(fpath, mode="rb") as fb:
        result = parser.read_csv(fb, encoding=encoding)
        assert not fb.closed
    tm.assert_frame_equal(expected, result)

    with open(fpath, mode="rb", buffering=0) as fb:
        result = parser.read_csv(fb, encoding=encoding)
        assert not fb.closed
    tm.assert_frame_equal(expected, result)


@pytest.mark.parametrize("pass_encoding", [True, False])
def test_encoding_temp_file(all_parsers, utf_value, encoding_fmt, pass_encoding):
    # see gh-24130
    parser = all_parsers
    encoding = encoding_fmt.format(utf_value)

    if parser.engine == "pyarrow" and pass_encoding is True and utf_value in [16, 32]:
        # FIXME: this is bad!
        pytest.skip("These cases freeze")

    expected = DataFrame({"foo": ["bar"]})

    with tm.ensure_clean(mode="w+", encoding=encoding, return_filelike=True) as f:
        f.write("foo\nbar")
        f.seek(0)

        result = parser.read_csv(f, encoding=encoding if pass_encoding else None)
        tm.assert_frame_equal(result, expected)


def test_encoding_named_temp_file(all_parsers):
    # see gh-31819
    parser = all_parsers
    encoding = "shift-jis"

    title = "てすと"
    data = "こむ"

    expected = DataFrame({title: [data]})

    with tempfile.NamedTemporaryFile() as f:
        f.write(f"{title}\n{data}".encode(encoding))

        f.seek(0)

        result = parser.read_csv(f, encoding=encoding)
        tm.assert_frame_equal(result, expected)
        assert not f.closed


@pytest.mark.parametrize(
    "encoding", ["utf-8", "utf-16", "utf-16-be", "utf-16-le", "utf-32"]
)
def test_parse_encoded_special_characters(encoding):
    # GH16218 Verify parsing of data with encoded special characters
    # Data contains a Unicode 'FULLWIDTH COLON' (U+FF1A) at position (0,"a")
    data = "a\tb\n：foo\t0\nbar\t1\nbaz\t2"  # noqa: RUF001
    encoded_data = BytesIO(data.encode(encoding))
    result = read_csv(encoded_data, delimiter="\t", encoding=encoding)

    expected = DataFrame(
        data=[["：foo", 0], ["bar", 1], ["baz", 2]],  # noqa: RUF001
        columns=["a", "b"],
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("encoding", ["utf-8", None, "utf-16", "cp1255", "latin-1"])
def test_encoding_memory_map(all_parsers, encoding):
    # GH40986
    parser = all_parsers
    expected = DataFrame(
        {
            "name": ["Raphael", "Donatello", "Miguel Angel", "Leonardo"],
            "mask": ["red", "purple", "orange", "blue"],
            "weapon": ["sai", "bo staff", "nunchunk", "katana"],
        }
    )
    with tm.ensure_clean() as file:
        expected.to_csv(file, index=False, encoding=encoding)

        if parser.engine == "pyarrow":
            msg = "The 'memory_map' option is not supported with the 'pyarrow' engine"
            with pytest.raises(ValueError, match=msg):
                parser.read_csv(file, encoding=encoding, memory_map=True)
            return

        df = parser.read_csv(file, encoding=encoding, memory_map=True)
    tm.assert_frame_equal(df, expected)


def test_chunk_splits_multibyte_char(all_parsers):
    """
    Chunk splits a multibyte character with memory_map=True

    GH 43540
    """
    parser = all_parsers
    # DEFAULT_CHUNKSIZE = 262144, defined in parsers.pyx
    df = DataFrame(data=["a" * 127] * 2048)

    # Put two-bytes utf-8 encoded character "ą" at the end of chunk
    # utf-8 encoding of "ą" is b'\xc4\x85'
    df.iloc[2047] = "a" * 127 + "ą"
    with tm.ensure_clean("bug-gh43540.csv") as fname:
        df.to_csv(fname, index=False, header=False, encoding="utf-8")

        if parser.engine == "pyarrow":
            msg = "The 'memory_map' option is not supported with the 'pyarrow' engine"
            with pytest.raises(ValueError, match=msg):
                parser.read_csv(fname, header=None, memory_map=True)
            return

        dfr = parser.read_csv(fname, header=None, memory_map=True)
    tm.assert_frame_equal(dfr, df)


def test_readcsv_memmap_utf8(all_parsers):
    """
    GH 43787

    Test correct handling of UTF-8 chars when memory_map=True and encoding is UTF-8
    """
    lines = []
    line_length = 128
    start_char = " "
    end_char = "\U00010080"
    # This for loop creates a list of 128-char strings
    # consisting of consecutive Unicode chars
    for lnum in range(ord(start_char), ord(end_char), line_length):
        line = "".join([chr(c) for c in range(lnum, lnum + 0x80)]) + "\n"
        try:
            line.encode("utf-8")
        except UnicodeEncodeError:
            continue
        lines.append(line)
    parser = all_parsers
    df = DataFrame(lines)
    with tm.ensure_clean("utf8test.csv") as fname:
        df.to_csv(fname, index=False, header=False, encoding="utf-8")

        if parser.engine == "pyarrow":
            msg = "The 'memory_map' option is not supported with the 'pyarrow' engine"
            with pytest.raises(ValueError, match=msg):
                parser.read_csv(fname, header=None, memory_map=True, encoding="utf-8")
            return

        dfr = parser.read_csv(fname, header=None, memory_map=True, encoding="utf-8")
    tm.assert_frame_equal(df, dfr)


@pytest.mark.usefixtures("pyarrow_xfail")
@pytest.mark.parametrize("mode", ["w+b", "w+t"])
def test_not_readable(all_parsers, mode):
    # GH43439
    parser = all_parsers
    content = b"abcd"
    if "t" in mode:
        content = "abcd"
    with tempfile.SpooledTemporaryFile(mode=mode, encoding="utf-8") as handle:
        handle.write(content)
        handle.seek(0)
        df = parser.read_csv(handle)
    expected = DataFrame([], columns=["abcd"])
    tm.assert_frame_equal(df, expected)
