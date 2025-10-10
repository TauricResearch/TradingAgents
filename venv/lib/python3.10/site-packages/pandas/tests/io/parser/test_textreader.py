"""
Tests the TextReader class in parsers.pyx, which
is integral to the C engine in parsers.py
"""
from io import (
    BytesIO,
    StringIO,
)

import numpy as np
import pytest

import pandas._libs.parsers as parser
from pandas._libs.parsers import TextReader
from pandas.errors import ParserWarning

from pandas import DataFrame
import pandas._testing as tm

from pandas.io.parsers import (
    TextFileReader,
    read_csv,
)
from pandas.io.parsers.c_parser_wrapper import ensure_dtype_objs


class TestTextReader:
    @pytest.fixture
    def csv_path(self, datapath):
        return datapath("io", "data", "csv", "test1.csv")

    def test_file_handle(self, csv_path):
        with open(csv_path, "rb") as f:
            reader = TextReader(f)
            reader.read()

    def test_file_handle_mmap(self, csv_path):
        # this was never using memory_map=True
        with open(csv_path, "rb") as f:
            reader = TextReader(f, header=None)
            reader.read()

    def test_StringIO(self, csv_path):
        with open(csv_path, "rb") as f:
            text = f.read()
        src = BytesIO(text)
        reader = TextReader(src, header=None)
        reader.read()

    def test_string_factorize(self):
        # should this be optional?
        data = "a\nb\na\nb\na"
        reader = TextReader(StringIO(data), header=None)
        result = reader.read()
        assert len(set(map(id, result[0]))) == 2

    def test_skipinitialspace(self):
        data = "a,   b\na,   b\na,   b\na,   b"

        reader = TextReader(StringIO(data), skipinitialspace=True, header=None)
        result = reader.read()

        tm.assert_numpy_array_equal(
            result[0], np.array(["a", "a", "a", "a"], dtype=np.object_)
        )
        tm.assert_numpy_array_equal(
            result[1], np.array(["b", "b", "b", "b"], dtype=np.object_)
        )

    def test_parse_booleans(self):
        data = "True\nFalse\nTrue\nTrue"

        reader = TextReader(StringIO(data), header=None)
        result = reader.read()

        assert result[0].dtype == np.bool_

    def test_delimit_whitespace(self):
        data = 'a  b\na\t\t "b"\n"a"\t \t b'

        reader = TextReader(StringIO(data), delim_whitespace=True, header=None)
        result = reader.read()

        tm.assert_numpy_array_equal(
            result[0], np.array(["a", "a", "a"], dtype=np.object_)
        )
        tm.assert_numpy_array_equal(
            result[1], np.array(["b", "b", "b"], dtype=np.object_)
        )

    def test_embedded_newline(self):
        data = 'a\n"hello\nthere"\nthis'

        reader = TextReader(StringIO(data), header=None)
        result = reader.read()

        expected = np.array(["a", "hello\nthere", "this"], dtype=np.object_)
        tm.assert_numpy_array_equal(result[0], expected)

    def test_euro_decimal(self):
        data = "12345,67\n345,678"

        reader = TextReader(StringIO(data), delimiter=":", decimal=",", header=None)
        result = reader.read()

        expected = np.array([12345.67, 345.678])
        tm.assert_almost_equal(result[0], expected)

    def test_integer_thousands(self):
        data = "123,456\n12,500"

        reader = TextReader(StringIO(data), delimiter=":", thousands=",", header=None)
        result = reader.read()

        expected = np.array([123456, 12500], dtype=np.int64)
        tm.assert_almost_equal(result[0], expected)

    def test_integer_thousands_alt(self):
        data = "123.456\n12.500"

        reader = TextFileReader(
            StringIO(data), delimiter=":", thousands=".", header=None
        )
        result = reader.read()

        expected = DataFrame([123456, 12500])
        tm.assert_frame_equal(result, expected)

    def test_skip_bad_lines(self):
        # too many lines, see #2430 for why
        data = "a:b:c\nd:e:f\ng:h:i\nj:k:l:m\nl:m:n\no:p:q:r"

        reader = TextReader(StringIO(data), delimiter=":", header=None)
        msg = r"Error tokenizing data\. C error: Expected 3 fields in line 4, saw 4"
        with pytest.raises(parser.ParserError, match=msg):
            reader.read()

        reader = TextReader(
            StringIO(data), delimiter=":", header=None, on_bad_lines=2  # Skip
        )
        result = reader.read()
        expected = {
            0: np.array(["a", "d", "g", "l"], dtype=object),
            1: np.array(["b", "e", "h", "m"], dtype=object),
            2: np.array(["c", "f", "i", "n"], dtype=object),
        }
        assert_array_dicts_equal(result, expected)

        with tm.assert_produces_warning(ParserWarning, match="Skipping line"):
            reader = TextReader(
                StringIO(data), delimiter=":", header=None, on_bad_lines=1  # Warn
            )
            reader.read()

    def test_header_not_enough_lines(self):
        data = "skip this\nskip this\na,b,c\n1,2,3\n4,5,6"

        reader = TextReader(StringIO(data), delimiter=",", header=2)
        header = reader.header
        expected = [["a", "b", "c"]]
        assert header == expected

        recs = reader.read()
        expected = {
            0: np.array([1, 4], dtype=np.int64),
            1: np.array([2, 5], dtype=np.int64),
            2: np.array([3, 6], dtype=np.int64),
        }
        assert_array_dicts_equal(recs, expected)

    def test_escapechar(self):
        data = '\\"hello world"\n\\"hello world"\n\\"hello world"'

        reader = TextReader(StringIO(data), delimiter=",", header=None, escapechar="\\")
        result = reader.read()
        expected = {0: np.array(['"hello world"'] * 3, dtype=object)}
        assert_array_dicts_equal(result, expected)

    def test_eof_has_eol(self):
        # handling of new line at EOF
        pass

    def test_na_substitution(self):
        pass

    def test_numpy_string_dtype(self):
        data = """\
a,1
aa,2
aaa,3
aaaa,4
aaaaa,5"""

        def _make_reader(**kwds):
            if "dtype" in kwds:
                kwds["dtype"] = ensure_dtype_objs(kwds["dtype"])
            return TextReader(StringIO(data), delimiter=",", header=None, **kwds)

        reader = _make_reader(dtype="S5,i4")
        result = reader.read()

        assert result[0].dtype == "S5"

        ex_values = np.array(["a", "aa", "aaa", "aaaa", "aaaaa"], dtype="S5")
        assert (result[0] == ex_values).all()
        assert result[1].dtype == "i4"

        reader = _make_reader(dtype="S4")
        result = reader.read()
        assert result[0].dtype == "S4"
        ex_values = np.array(["a", "aa", "aaa", "aaaa", "aaaa"], dtype="S4")
        assert (result[0] == ex_values).all()
        assert result[1].dtype == "S4"

    def test_pass_dtype(self):
        data = """\
one,two
1,a
2,b
3,c
4,d"""

        def _make_reader(**kwds):
            if "dtype" in kwds:
                kwds["dtype"] = ensure_dtype_objs(kwds["dtype"])
            return TextReader(StringIO(data), delimiter=",", **kwds)

        reader = _make_reader(dtype={"one": "u1", 1: "S1"})
        result = reader.read()
        assert result[0].dtype == "u1"
        assert result[1].dtype == "S1"

        reader = _make_reader(dtype={"one": np.uint8, 1: object})
        result = reader.read()
        assert result[0].dtype == "u1"
        assert result[1].dtype == "O"

        reader = _make_reader(dtype={"one": np.dtype("u1"), 1: np.dtype("O")})
        result = reader.read()
        assert result[0].dtype == "u1"
        assert result[1].dtype == "O"

    def test_usecols(self):
        data = """\
a,b,c
1,2,3
4,5,6
7,8,9
10,11,12"""

        def _make_reader(**kwds):
            return TextReader(StringIO(data), delimiter=",", **kwds)

        reader = _make_reader(usecols=(1, 2))
        result = reader.read()

        exp = _make_reader().read()
        assert len(result) == 2
        assert (result[1] == exp[1]).all()
        assert (result[2] == exp[2]).all()

    @pytest.mark.parametrize(
        "text, kwargs",
        [
            ("a,b,c\r1,2,3\r4,5,6\r7,8,9\r10,11,12", {"delimiter": ","}),
            (
                "a  b  c\r1  2  3\r4  5  6\r7  8  9\r10  11  12",
                {"delim_whitespace": True},
            ),
            ("a,b,c\r1,2,3\r4,5,6\r,88,9\r10,11,12", {"delimiter": ","}),
            (
                (
                    "A,B,C,D,E,F,G,H,I,J,K,L,M,N,O\r"
                    "AAAAA,BBBBB,0,0,0,0,0,0,0,0,0,0,0,0,0\r"
                    ",BBBBB,0,0,0,0,0,0,0,0,0,0,0,0,0"
                ),
                {"delimiter": ","},
            ),
            ("A  B  C\r  2  3\r4  5  6", {"delim_whitespace": True}),
            ("A B C\r2 3\r4 5 6", {"delim_whitespace": True}),
        ],
    )
    def test_cr_delimited(self, text, kwargs):
        nice_text = text.replace("\r", "\r\n")
        result = TextReader(StringIO(text), **kwargs).read()
        expected = TextReader(StringIO(nice_text), **kwargs).read()
        assert_array_dicts_equal(result, expected)

    def test_empty_field_eof(self):
        data = "a,b,c\n1,2,3\n4,,"

        result = TextReader(StringIO(data), delimiter=",").read()

        expected = {
            0: np.array([1, 4], dtype=np.int64),
            1: np.array(["2", ""], dtype=object),
            2: np.array(["3", ""], dtype=object),
        }
        assert_array_dicts_equal(result, expected)

    @pytest.mark.parametrize("repeat", range(10))
    def test_empty_field_eof_mem_access_bug(self, repeat):
        # GH5664
        a = DataFrame([["b"], [np.nan]], columns=["a"], index=["a", "c"])
        b = DataFrame([[1, 1, 1, 0], [1, 1, 1, 0]], columns=list("abcd"), index=[1, 1])
        c = DataFrame(
            [
                [1, 2, 3, 4],
                [6, np.nan, np.nan, np.nan],
                [8, 9, 10, 11],
                [13, 14, np.nan, np.nan],
            ],
            columns=list("abcd"),
            index=[0, 5, 7, 12],
        )

        df = read_csv(StringIO("a,b\nc\n"), skiprows=0, names=["a"], engine="c")
        tm.assert_frame_equal(df, a)

        df = read_csv(
            StringIO("1,1,1,1,0\n" * 2 + "\n" * 2), names=list("abcd"), engine="c"
        )
        tm.assert_frame_equal(df, b)

        df = read_csv(
            StringIO("0,1,2,3,4\n5,6\n7,8,9,10,11\n12,13,14"),
            names=list("abcd"),
            engine="c",
        )
        tm.assert_frame_equal(df, c)

    def test_empty_csv_input(self):
        # GH14867
        with read_csv(
            StringIO(), chunksize=20, header=None, names=["a", "b", "c"]
        ) as df:
            assert isinstance(df, TextFileReader)


def assert_array_dicts_equal(left, right):
    for k, v in left.items():
        tm.assert_numpy_array_equal(np.asarray(v), np.asarray(right[k]))
