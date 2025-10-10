"""
Tests that work on both the Python and C engines but do not have a
specific classification into the other test modules.
"""
from datetime import datetime
from inspect import signature
from io import StringIO
import os
from pathlib import Path
import sys

import numpy as np
import pytest

from pandas._config import using_string_dtype

from pandas.compat import HAS_PYARROW
from pandas.errors import (
    EmptyDataError,
    ParserError,
    ParserWarning,
)

from pandas import (
    DataFrame,
    Index,
    Timestamp,
    compat,
)
import pandas._testing as tm

from pandas.io.parsers import TextFileReader
from pandas.io.parsers.c_parser_wrapper import CParserWrapper

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)

xfail_pyarrow = pytest.mark.usefixtures("pyarrow_xfail")
skip_pyarrow = pytest.mark.usefixtures("pyarrow_skip")


def test_override_set_noconvert_columns():
    # see gh-17351
    #
    # Usecols needs to be sorted in _set_noconvert_columns based
    # on the test_usecols_with_parse_dates test from test_usecols.py
    class MyTextFileReader(TextFileReader):
        def __init__(self) -> None:
            self._currow = 0
            self.squeeze = False

    class MyCParserWrapper(CParserWrapper):
        def _set_noconvert_columns(self):
            if self.usecols_dtype == "integer":
                # self.usecols is a set, which is documented as unordered
                # but in practice, a CPython set of integers is sorted.
                # In other implementations this assumption does not hold.
                # The following code simulates a different order, which
                # before GH 17351 would cause the wrong columns to be
                # converted via the parse_dates parameter
                self.usecols = list(self.usecols)
                self.usecols.reverse()
            return CParserWrapper._set_noconvert_columns(self)

    data = """a,b,c,d,e
0,1,2014-01-01,09:00,4
0,1,2014-01-02,10:00,4"""

    parse_dates = [[1, 2]]
    cols = {
        "a": [0, 0],
        "c_d": [Timestamp("2014-01-01 09:00:00"), Timestamp("2014-01-02 10:00:00")],
    }
    expected = DataFrame(cols, columns=["c_d", "a"])

    parser = MyTextFileReader()
    parser.options = {
        "usecols": [0, 2, 3],
        "parse_dates": parse_dates,
        "delimiter": ",",
    }
    parser.engine = "c"
    parser._engine = MyCParserWrapper(StringIO(data), **parser.options)

    result = parser.read()
    tm.assert_frame_equal(result, expected)


def test_read_csv_local(all_parsers, csv1):
    prefix = "file:///" if compat.is_platform_windows() else "file://"
    parser = all_parsers

    fname = prefix + str(os.path.abspath(csv1))
    result = parser.read_csv(fname, index_col=0, parse_dates=True)
    # TODO: make unit check more specific
    if parser.engine == "pyarrow":
        result.index = result.index.as_unit("ns")
    expected = DataFrame(
        [
            [0.980269, 3.685731, -0.364216805298, -1.159738],
            [1.047916, -0.041232, -0.16181208307, 0.212549],
            [0.498581, 0.731168, -0.537677223318, 1.346270],
            [1.120202, 1.567621, 0.00364077397681, 0.675253],
            [-0.487094, 0.571455, -1.6116394093, 0.103469],
            [0.836649, 0.246462, 0.588542635376, 1.062782],
            [-0.157161, 1.340307, 1.1957779562, -1.097007],
        ],
        columns=["A", "B", "C", "D"],
        index=Index(
            [
                datetime(2000, 1, 3),
                datetime(2000, 1, 4),
                datetime(2000, 1, 5),
                datetime(2000, 1, 6),
                datetime(2000, 1, 7),
                datetime(2000, 1, 10),
                datetime(2000, 1, 11),
            ],
            name="index",
        ),
    )
    tm.assert_frame_equal(result, expected)


def test_1000_sep(all_parsers):
    parser = all_parsers
    data = """A|B|C
1|2,334|5
10|13|10.
"""
    expected = DataFrame({"A": [1, 10], "B": [2334, 13], "C": [5, 10.0]})

    if parser.engine == "pyarrow":
        msg = "The 'thousands' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), sep="|", thousands=",")
        return

    result = parser.read_csv(StringIO(data), sep="|", thousands=",")
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # ValueError: Found non-unique column index
def test_unnamed_columns(all_parsers):
    data = """A,B,C,,
1,2,3,4,5
6,7,8,9,10
11,12,13,14,15
"""
    parser = all_parsers
    expected = DataFrame(
        [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10], [11, 12, 13, 14, 15]],
        dtype=np.int64,
        columns=["A", "B", "C", "Unnamed: 3", "Unnamed: 4"],
    )
    result = parser.read_csv(StringIO(data))
    tm.assert_frame_equal(result, expected)


def test_csv_mixed_type(all_parsers):
    data = """A,B,C
a,1,2
b,3,4
c,4,5
"""
    parser = all_parsers
    expected = DataFrame({"A": ["a", "b", "c"], "B": [1, 3, 4], "C": [2, 4, 5]})
    result = parser.read_csv(StringIO(data))
    tm.assert_frame_equal(result, expected)


def test_read_csv_low_memory_no_rows_with_index(all_parsers):
    # see gh-21141
    parser = all_parsers

    if not parser.low_memory:
        pytest.skip("This is a low-memory specific test")

    data = """A,B,C
1,1,1,2
2,2,3,4
3,3,4,5
"""

    if parser.engine == "pyarrow":
        msg = "The 'nrows' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), low_memory=True, index_col=0, nrows=0)
        return

    result = parser.read_csv(StringIO(data), low_memory=True, index_col=0, nrows=0)
    expected = DataFrame(columns=["A", "B", "C"])
    tm.assert_frame_equal(result, expected)


def test_read_csv_dataframe(all_parsers, csv1):
    parser = all_parsers
    result = parser.read_csv(csv1, index_col=0, parse_dates=True)
    # TODO: make unit check more specific
    if parser.engine == "pyarrow":
        result.index = result.index.as_unit("ns")
    expected = DataFrame(
        [
            [0.980269, 3.685731, -0.364216805298, -1.159738],
            [1.047916, -0.041232, -0.16181208307, 0.212549],
            [0.498581, 0.731168, -0.537677223318, 1.346270],
            [1.120202, 1.567621, 0.00364077397681, 0.675253],
            [-0.487094, 0.571455, -1.6116394093, 0.103469],
            [0.836649, 0.246462, 0.588542635376, 1.062782],
            [-0.157161, 1.340307, 1.1957779562, -1.097007],
        ],
        columns=["A", "B", "C", "D"],
        index=Index(
            [
                datetime(2000, 1, 3),
                datetime(2000, 1, 4),
                datetime(2000, 1, 5),
                datetime(2000, 1, 6),
                datetime(2000, 1, 7),
                datetime(2000, 1, 10),
                datetime(2000, 1, 11),
            ],
            name="index",
        ),
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("nrows", [3, 3.0])
def test_read_nrows(all_parsers, nrows):
    # see gh-10476
    data = """index,A,B,C,D
foo,2,3,4,5
bar,7,8,9,10
baz,12,13,14,15
qux,12,13,14,15
foo2,12,13,14,15
bar2,12,13,14,15
"""
    expected = DataFrame(
        [["foo", 2, 3, 4, 5], ["bar", 7, 8, 9, 10], ["baz", 12, 13, 14, 15]],
        columns=["index", "A", "B", "C", "D"],
    )
    parser = all_parsers

    if parser.engine == "pyarrow":
        msg = "The 'nrows' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), nrows=nrows)
        return

    result = parser.read_csv(StringIO(data), nrows=nrows)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("nrows", [1.2, "foo", -1])
def test_read_nrows_bad(all_parsers, nrows):
    data = """index,A,B,C,D
foo,2,3,4,5
bar,7,8,9,10
baz,12,13,14,15
qux,12,13,14,15
foo2,12,13,14,15
bar2,12,13,14,15
"""
    msg = r"'nrows' must be an integer >=0"
    parser = all_parsers
    if parser.engine == "pyarrow":
        msg = "The 'nrows' option is not supported with the 'pyarrow' engine"

    with pytest.raises(ValueError, match=msg):
        parser.read_csv(StringIO(data), nrows=nrows)


def test_nrows_skipfooter_errors(all_parsers):
    msg = "'skipfooter' not supported with 'nrows'"
    data = "a\n1\n2\n3\n4\n5\n6"
    parser = all_parsers

    with pytest.raises(ValueError, match=msg):
        parser.read_csv(StringIO(data), skipfooter=1, nrows=5)


@skip_pyarrow
def test_missing_trailing_delimiters(all_parsers):
    parser = all_parsers
    data = """A,B,C,D
1,2,3,4
1,3,3,
1,4,5"""

    result = parser.read_csv(StringIO(data))
    expected = DataFrame(
        [[1, 2, 3, 4], [1, 3, 3, np.nan], [1, 4, 5, np.nan]],
        columns=["A", "B", "C", "D"],
    )
    tm.assert_frame_equal(result, expected)


def test_skip_initial_space(all_parsers):
    data = (
        '"09-Apr-2012", "01:10:18.300", 2456026.548822908, 12849, '
        "1.00361,  1.12551, 330.65659, 0355626618.16711,  73.48821, "
        "314.11625,  1917.09447,   179.71425,  80.000, 240.000, -350,  "
        "70.06056, 344.98370, 1,   1, -0.689265, -0.692787,  "
        "0.212036,    14.7674,   41.605,   -9999.0,   -9999.0,   "
        "-9999.0,   -9999.0,   -9999.0,  -9999.0, 000, 012, 128"
    )
    parser = all_parsers

    if parser.engine == "pyarrow":
        msg = "The 'skipinitialspace' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(
                StringIO(data),
                names=list(range(33)),
                header=None,
                na_values=["-9999.0"],
                skipinitialspace=True,
            )
        return

    result = parser.read_csv(
        StringIO(data),
        names=list(range(33)),
        header=None,
        na_values=["-9999.0"],
        skipinitialspace=True,
    )
    expected = DataFrame(
        [
            [
                "09-Apr-2012",
                "01:10:18.300",
                2456026.548822908,
                12849,
                1.00361,
                1.12551,
                330.65659,
                355626618.16711,
                73.48821,
                314.11625,
                1917.09447,
                179.71425,
                80.0,
                240.0,
                -350,
                70.06056,
                344.9837,
                1,
                1,
                -0.689265,
                -0.692787,
                0.212036,
                14.7674,
                41.605,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                0,
                12,
                128,
            ]
        ]
    )
    tm.assert_frame_equal(result, expected)


@skip_pyarrow
def test_trailing_delimiters(all_parsers):
    # see gh-2442
    data = """A,B,C
1,2,3,
4,5,6,
7,8,9,"""
    parser = all_parsers
    result = parser.read_csv(StringIO(data), index_col=False)

    expected = DataFrame({"A": [1, 4, 7], "B": [2, 5, 8], "C": [3, 6, 9]})
    tm.assert_frame_equal(result, expected)


def test_escapechar(all_parsers):
    # https://stackoverflow.com/questions/13824840/feature-request-for-
    # pandas-read-csv
    data = '''SEARCH_TERM,ACTUAL_URL
"bra tv board","http://www.ikea.com/se/sv/catalog/categories/departments/living_room/10475/?se%7cps%7cnonbranded%7cvardagsrum%7cgoogle%7ctv_bord"
"tv p\xc3\xa5 hjul","http://www.ikea.com/se/sv/catalog/categories/departments/living_room/10475/?se%7cps%7cnonbranded%7cvardagsrum%7cgoogle%7ctv_bord"
"SLAGBORD, \\"Bergslagen\\", IKEA:s 1700-tals series","http://www.ikea.com/se/sv/catalog/categories/departments/living_room/10475/?se%7cps%7cnonbranded%7cvardagsrum%7cgoogle%7ctv_bord"'''

    parser = all_parsers
    result = parser.read_csv(
        StringIO(data), escapechar="\\", quotechar='"', encoding="utf-8"
    )

    assert result["SEARCH_TERM"][2] == 'SLAGBORD, "Bergslagen", IKEA:s 1700-tals series'

    tm.assert_index_equal(result.columns, Index(["SEARCH_TERM", "ACTUAL_URL"]))


def test_ignore_leading_whitespace(all_parsers):
    # see gh-3374, gh-6607
    parser = all_parsers
    data = " a b c\n 1 2 3\n 4 5 6\n 7 8 9"

    if parser.engine == "pyarrow":
        msg = "the 'pyarrow' engine does not support regex separators"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), sep=r"\s+")
        return
    result = parser.read_csv(StringIO(data), sep=r"\s+")

    expected = DataFrame({"a": [1, 4, 7], "b": [2, 5, 8], "c": [3, 6, 9]})
    tm.assert_frame_equal(result, expected)


@skip_pyarrow
@pytest.mark.parametrize("usecols", [None, [0, 1], ["a", "b"]])
def test_uneven_lines_with_usecols(all_parsers, usecols):
    # see gh-12203
    parser = all_parsers
    data = r"""a,b,c
0,1,2
3,4,5,6,7
8,9,10"""

    if usecols is None:
        # Make sure that an error is still raised
        # when the "usecols" parameter is not provided.
        msg = r"Expected \d+ fields in line \d+, saw \d+"
        with pytest.raises(ParserError, match=msg):
            parser.read_csv(StringIO(data))
    else:
        expected = DataFrame({"a": [0, 3, 8], "b": [1, 4, 9]})

        result = parser.read_csv(StringIO(data), usecols=usecols)
        tm.assert_frame_equal(result, expected)


@skip_pyarrow
@pytest.mark.parametrize(
    "data,kwargs,expected",
    [
        # First, check to see that the response of parser when faced with no
        # provided columns raises the correct error, with or without usecols.
        ("", {}, None),
        ("", {"usecols": ["X"]}, None),
        (
            ",,",
            {"names": ["Dummy", "X", "Dummy_2"], "usecols": ["X"]},
            DataFrame(columns=["X"], index=[0], dtype=np.float64),
        ),
        (
            "",
            {"names": ["Dummy", "X", "Dummy_2"], "usecols": ["X"]},
            DataFrame(columns=["X"]),
        ),
    ],
)
def test_read_empty_with_usecols(all_parsers, data, kwargs, expected):
    # see gh-12493
    parser = all_parsers

    if expected is None:
        msg = "No columns to parse from file"
        with pytest.raises(EmptyDataError, match=msg):
            parser.read_csv(StringIO(data), **kwargs)
    else:
        result = parser.read_csv(StringIO(data), **kwargs)
        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        # gh-8661, gh-8679: this should ignore six lines, including
        # lines with trailing whitespace and blank lines.
        (
            {
                "header": None,
                "delim_whitespace": True,
                "skiprows": [0, 1, 2, 3, 5, 6],
                "skip_blank_lines": True,
            },
            DataFrame([[1.0, 2.0, 4.0], [5.1, np.nan, 10.0]]),
        ),
        # gh-8983: test skipping set of rows after a row with trailing spaces.
        (
            {
                "delim_whitespace": True,
                "skiprows": [1, 2, 3, 5, 6],
                "skip_blank_lines": True,
            },
            DataFrame({"A": [1.0, 5.1], "B": [2.0, np.nan], "C": [4.0, 10]}),
        ),
    ],
)
def test_trailing_spaces(all_parsers, kwargs, expected):
    data = "A B C  \nrandom line with trailing spaces    \nskip\n1,2,3\n1,2.,4.\nrandom line with trailing tabs\t\t\t\n   \n5.1,NaN,10.0\n"  # noqa: E501
    parser = all_parsers

    depr_msg = "The 'delim_whitespace' keyword in pd.read_csv is deprecated"

    if parser.engine == "pyarrow":
        msg = "The 'delim_whitespace' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(
                FutureWarning, match=depr_msg, check_stacklevel=False
            ):
                parser.read_csv(StringIO(data.replace(",", "  ")), **kwargs)
        return

    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_csv(StringIO(data.replace(",", "  ")), **kwargs)
    tm.assert_frame_equal(result, expected)


def test_raise_on_sep_with_delim_whitespace(all_parsers):
    # see gh-6607
    data = "a b c\n1 2 3"
    parser = all_parsers

    depr_msg = "The 'delim_whitespace' keyword in pd.read_csv is deprecated"
    with pytest.raises(ValueError, match="you can only specify one"):
        with tm.assert_produces_warning(
            FutureWarning, match=depr_msg, check_stacklevel=False
        ):
            parser.read_csv(StringIO(data), sep=r"\s", delim_whitespace=True)


def test_read_filepath_or_buffer(all_parsers):
    # see gh-43366
    parser = all_parsers

    with pytest.raises(TypeError, match="Expected file path name or file-like"):
        parser.read_csv(filepath_or_buffer=b"input")


@pytest.mark.parametrize("delim_whitespace", [True, False])
def test_single_char_leading_whitespace(all_parsers, delim_whitespace):
    # see gh-9710
    parser = all_parsers
    data = """\
MyColumn
a
b
a
b\n"""

    expected = DataFrame({"MyColumn": list("abab")})
    depr_msg = "The 'delim_whitespace' keyword in pd.read_csv is deprecated"

    if parser.engine == "pyarrow":
        msg = "The 'skipinitialspace' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(
                FutureWarning, match=depr_msg, check_stacklevel=False
            ):
                parser.read_csv(
                    StringIO(data),
                    skipinitialspace=True,
                    delim_whitespace=delim_whitespace,
                )
        return

    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_csv(
            StringIO(data), skipinitialspace=True, delim_whitespace=delim_whitespace
        )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "sep,skip_blank_lines,exp_data",
    [
        (",", True, [[1.0, 2.0, 4.0], [5.0, np.nan, 10.0], [-70.0, 0.4, 1.0]]),
        (r"\s+", True, [[1.0, 2.0, 4.0], [5.0, np.nan, 10.0], [-70.0, 0.4, 1.0]]),
        (
            ",",
            False,
            [
                [1.0, 2.0, 4.0],
                [np.nan, np.nan, np.nan],
                [np.nan, np.nan, np.nan],
                [5.0, np.nan, 10.0],
                [np.nan, np.nan, np.nan],
                [-70.0, 0.4, 1.0],
            ],
        ),
    ],
)
def test_empty_lines(all_parsers, sep, skip_blank_lines, exp_data, request):
    parser = all_parsers
    data = """\
A,B,C
1,2.,4.


5.,NaN,10.0

-70,.4,1
"""

    if sep == r"\s+":
        data = data.replace(",", "  ")

        if parser.engine == "pyarrow":
            msg = "the 'pyarrow' engine does not support regex separators"
            with pytest.raises(ValueError, match=msg):
                parser.read_csv(
                    StringIO(data), sep=sep, skip_blank_lines=skip_blank_lines
                )
            return

    result = parser.read_csv(StringIO(data), sep=sep, skip_blank_lines=skip_blank_lines)
    expected = DataFrame(exp_data, columns=["A", "B", "C"])
    tm.assert_frame_equal(result, expected)


@skip_pyarrow
def test_whitespace_lines(all_parsers):
    parser = all_parsers
    data = """

\t  \t\t
\t
A,B,C
\t    1,2.,4.
5.,NaN,10.0
"""
    expected = DataFrame([[1, 2.0, 4.0], [5.0, np.nan, 10.0]], columns=["A", "B", "C"])
    result = parser.read_csv(StringIO(data))
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "data,expected",
    [
        (
            """   A   B   C   D
a   1   2   3   4
b   1   2   3   4
c   1   2   3   4
""",
            DataFrame(
                [[1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4]],
                columns=["A", "B", "C", "D"],
                index=["a", "b", "c"],
            ),
        ),
        (
            "    a b c\n1 2 3 \n4 5  6\n 7 8 9",
            DataFrame([[1, 2, 3], [4, 5, 6], [7, 8, 9]], columns=["a", "b", "c"]),
        ),
    ],
)
def test_whitespace_regex_separator(all_parsers, data, expected):
    # see gh-6607
    parser = all_parsers
    if parser.engine == "pyarrow":
        msg = "the 'pyarrow' engine does not support regex separators"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), sep=r"\s+")
        return

    result = parser.read_csv(StringIO(data), sep=r"\s+")
    tm.assert_frame_equal(result, expected)


def test_sub_character(all_parsers, csv_dir_path):
    # see gh-16893
    filename = os.path.join(csv_dir_path, "sub_char.csv")
    expected = DataFrame([[1, 2, 3]], columns=["a", "\x1ab", "c"])

    parser = all_parsers
    result = parser.read_csv(filename)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("filename", ["sé-es-vé.csv", "ru-sй.csv", "中文文件名.csv"])
def test_filename_with_special_chars(all_parsers, filename):
    # see gh-15086.
    parser = all_parsers
    df = DataFrame({"a": [1, 2, 3]})

    with tm.ensure_clean(filename) as path:
        df.to_csv(path, index=False)

        result = parser.read_csv(path)
        tm.assert_frame_equal(result, df)


def test_read_table_same_signature_as_read_csv(all_parsers):
    # GH-34976
    parser = all_parsers

    table_sign = signature(parser.read_table)
    csv_sign = signature(parser.read_csv)

    assert table_sign.parameters.keys() == csv_sign.parameters.keys()
    assert table_sign.return_annotation == csv_sign.return_annotation

    for key, csv_param in csv_sign.parameters.items():
        table_param = table_sign.parameters[key]
        if key == "sep":
            assert csv_param.default == ","
            assert table_param.default == "\t"
            assert table_param.annotation == csv_param.annotation
            assert table_param.kind == csv_param.kind
            continue

        assert table_param == csv_param


def test_read_table_equivalency_to_read_csv(all_parsers):
    # see gh-21948
    # As of 0.25.0, read_table is undeprecated
    parser = all_parsers
    data = "a\tb\n1\t2\n3\t4"
    expected = parser.read_csv(StringIO(data), sep="\t")
    result = parser.read_table(StringIO(data))
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("read_func", ["read_csv", "read_table"])
def test_read_csv_and_table_sys_setprofile(all_parsers, read_func):
    # GH#41069
    parser = all_parsers
    data = "a b\n0 1"

    sys.setprofile(lambda *a, **k: None)
    result = getattr(parser, read_func)(StringIO(data))
    sys.setprofile(None)

    expected = DataFrame({"a b": ["0 1"]})
    tm.assert_frame_equal(result, expected)


@skip_pyarrow
def test_first_row_bom(all_parsers):
    # see gh-26545
    parser = all_parsers
    data = '''\ufeff"Head1"\t"Head2"\t"Head3"'''

    result = parser.read_csv(StringIO(data), delimiter="\t")
    expected = DataFrame(columns=["Head1", "Head2", "Head3"])
    tm.assert_frame_equal(result, expected)


@skip_pyarrow
def test_first_row_bom_unquoted(all_parsers):
    # see gh-36343
    parser = all_parsers
    data = """\ufeffHead1\tHead2\tHead3"""

    result = parser.read_csv(StringIO(data), delimiter="\t")
    expected = DataFrame(columns=["Head1", "Head2", "Head3"])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("nrows", range(1, 6))
def test_blank_lines_between_header_and_data_rows(all_parsers, nrows):
    # GH 28071
    ref = DataFrame(
        [[np.nan, np.nan], [np.nan, np.nan], [1, 2], [np.nan, np.nan], [3, 4]],
        columns=list("ab"),
    )
    csv = "\nheader\n\na,b\n\n\n1,2\n\n3,4"
    parser = all_parsers

    if parser.engine == "pyarrow":
        msg = "The 'nrows' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(
                StringIO(csv), header=3, nrows=nrows, skip_blank_lines=False
            )
        return

    df = parser.read_csv(StringIO(csv), header=3, nrows=nrows, skip_blank_lines=False)
    tm.assert_frame_equal(df, ref[:nrows])


@skip_pyarrow
def test_no_header_two_extra_columns(all_parsers):
    # GH 26218
    column_names = ["one", "two", "three"]
    ref = DataFrame([["foo", "bar", "baz"]], columns=column_names)
    stream = StringIO("foo,bar,baz,bam,blah")
    parser = all_parsers
    df = parser.read_csv_check_warnings(
        ParserWarning,
        "Length of header or names does not match length of data. "
        "This leads to a loss of data with index_col=False.",
        stream,
        header=None,
        names=column_names,
        index_col=False,
    )
    tm.assert_frame_equal(df, ref)


def test_read_csv_names_not_accepting_sets(all_parsers):
    # GH 34946
    data = """\
    1,2,3
    4,5,6\n"""
    parser = all_parsers
    with pytest.raises(ValueError, match="Names should be an ordered collection."):
        parser.read_csv(StringIO(data), names=set("QAZ"))


def test_read_table_delim_whitespace_default_sep(all_parsers):
    # GH: 35958
    f = StringIO("a  b  c\n1 -2 -3\n4  5   6")
    parser = all_parsers

    depr_msg = "The 'delim_whitespace' keyword in pd.read_table is deprecated"

    if parser.engine == "pyarrow":
        msg = "The 'delim_whitespace' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(
                FutureWarning, match=depr_msg, check_stacklevel=False
            ):
                parser.read_table(f, delim_whitespace=True)
        return
    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_table(f, delim_whitespace=True)
    expected = DataFrame({"a": [1, 4], "b": [-2, 5], "c": [-3, 6]})
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("delimiter", [",", "\t"])
def test_read_csv_delim_whitespace_non_default_sep(all_parsers, delimiter):
    # GH: 35958
    f = StringIO("a  b  c\n1 -2 -3\n4  5   6")
    parser = all_parsers
    msg = (
        "Specified a delimiter with both sep and "
        "delim_whitespace=True; you can only specify one."
    )
    depr_msg = "The 'delim_whitespace' keyword in pd.read_csv is deprecated"
    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(f, delim_whitespace=True, sep=delimiter)

        with pytest.raises(ValueError, match=msg):
            parser.read_csv(f, delim_whitespace=True, delimiter=delimiter)


def test_read_csv_delimiter_and_sep_no_default(all_parsers):
    # GH#39823
    f = StringIO("a,b\n1,2")
    parser = all_parsers
    msg = "Specified a sep and a delimiter; you can only specify one."
    with pytest.raises(ValueError, match=msg):
        parser.read_csv(f, sep=" ", delimiter=".")


@pytest.mark.parametrize("kwargs", [{"delimiter": "\n"}, {"sep": "\n"}])
def test_read_csv_line_break_as_separator(kwargs, all_parsers):
    # GH#43528
    parser = all_parsers
    data = """a,b,c
1,2,3
    """
    msg = (
        r"Specified \\n as separator or delimiter. This forces the python engine "
        r"which does not accept a line terminator. Hence it is not allowed to use "
        r"the line terminator as separator."
    )
    with pytest.raises(ValueError, match=msg):
        parser.read_csv(StringIO(data), **kwargs)


@pytest.mark.parametrize("delimiter", [",", "\t"])
def test_read_table_delim_whitespace_non_default_sep(all_parsers, delimiter):
    # GH: 35958
    f = StringIO("a  b  c\n1 -2 -3\n4  5   6")
    parser = all_parsers
    msg = (
        "Specified a delimiter with both sep and "
        "delim_whitespace=True; you can only specify one."
    )
    depr_msg = "The 'delim_whitespace' keyword in pd.read_table is deprecated"
    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        with pytest.raises(ValueError, match=msg):
            parser.read_table(f, delim_whitespace=True, sep=delimiter)

        with pytest.raises(ValueError, match=msg):
            parser.read_table(f, delim_whitespace=True, delimiter=delimiter)


@skip_pyarrow
def test_dict_keys_as_names(all_parsers):
    # GH: 36928
    data = "1,2"

    keys = {"a": int, "b": int}.keys()
    parser = all_parsers

    result = parser.read_csv(StringIO(data), names=keys)
    expected = DataFrame({"a": [1], "b": [2]})
    tm.assert_frame_equal(result, expected)


@pytest.mark.xfail(using_string_dtype() and HAS_PYARROW, reason="TODO(infer_string)")
@xfail_pyarrow  # UnicodeDecodeError: 'utf-8' codec can't decode byte 0xed in position 0
def test_encoding_surrogatepass(all_parsers):
    # GH39017
    parser = all_parsers
    content = b"\xed\xbd\xbf"
    decoded = content.decode("utf-8", errors="surrogatepass")
    expected = DataFrame({decoded: [decoded]}, index=[decoded * 2])
    expected.index.name = decoded * 2

    with tm.ensure_clean() as path:
        Path(path).write_bytes(
            content * 2 + b"," + content + b"\n" + content * 2 + b"," + content
        )
        df = parser.read_csv(path, encoding_errors="surrogatepass", index_col=0)
        tm.assert_frame_equal(df, expected)
        with pytest.raises(UnicodeDecodeError, match="'utf-8' codec can't decode byte"):
            parser.read_csv(path)


def test_malformed_second_line(all_parsers):
    # see GH14782
    parser = all_parsers
    data = "\na\nb\n"
    result = parser.read_csv(StringIO(data), skip_blank_lines=False, header=1)
    expected = DataFrame({"a": ["b"]})
    tm.assert_frame_equal(result, expected)


@skip_pyarrow
def test_short_single_line(all_parsers):
    # GH 47566
    parser = all_parsers
    columns = ["a", "b", "c"]
    data = "1,2"
    result = parser.read_csv(StringIO(data), header=None, names=columns)
    expected = DataFrame({"a": [1], "b": [2], "c": [np.nan]})
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # ValueError: Length mismatch: Expected axis has 2 elements
def test_short_multi_line(all_parsers):
    # GH 47566
    parser = all_parsers
    columns = ["a", "b", "c"]
    data = "1,2\n1,2"
    result = parser.read_csv(StringIO(data), header=None, names=columns)
    expected = DataFrame({"a": [1, 1], "b": [2, 2], "c": [np.nan, np.nan]})
    tm.assert_frame_equal(result, expected)


def test_read_seek(all_parsers):
    # GH48646
    parser = all_parsers
    prefix = "### DATA\n"
    content = "nkey,value\ntables,rectangular\n"
    with tm.ensure_clean() as path:
        Path(path).write_text(prefix + content, encoding="utf-8")
        with open(path, encoding="utf-8") as file:
            file.readline()
            actual = parser.read_csv(file)
        expected = parser.read_csv(StringIO(content))
    tm.assert_frame_equal(actual, expected)
