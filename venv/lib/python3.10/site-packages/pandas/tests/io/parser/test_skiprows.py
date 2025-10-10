"""
Tests that skipped rows are properly handled during
parsing for all of the parsers defined in parsers.py
"""

from datetime import datetime
from io import StringIO

import numpy as np
import pytest

from pandas.errors import EmptyDataError

from pandas import (
    DataFrame,
    Index,
)
import pandas._testing as tm

xfail_pyarrow = pytest.mark.usefixtures("pyarrow_xfail")
pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)


@xfail_pyarrow  # ValueError: skiprows argument must be an integer
@pytest.mark.parametrize("skiprows", [list(range(6)), 6])
def test_skip_rows_bug(all_parsers, skiprows):
    # see gh-505
    parser = all_parsers
    text = """#foo,a,b,c
#foo,a,b,c
#foo,a,b,c
#foo,a,b,c
#foo,a,b,c
#foo,a,b,c
1/1/2000,1.,2.,3.
1/2/2000,4,5,6
1/3/2000,7,8,9
"""
    result = parser.read_csv(
        StringIO(text), skiprows=skiprows, header=None, index_col=0, parse_dates=True
    )
    index = Index(
        [datetime(2000, 1, 1), datetime(2000, 1, 2), datetime(2000, 1, 3)], name=0
    )

    expected = DataFrame(
        np.arange(1.0, 10.0).reshape((3, 3)), columns=[1, 2, 3], index=index
    )
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # ValueError: skiprows argument must be an integer
def test_deep_skip_rows(all_parsers):
    # see gh-4382
    parser = all_parsers
    data = "a,b,c\n" + "\n".join(
        [",".join([str(i), str(i + 1), str(i + 2)]) for i in range(10)]
    )
    condensed_data = "a,b,c\n" + "\n".join(
        [",".join([str(i), str(i + 1), str(i + 2)]) for i in [0, 1, 2, 3, 4, 6, 8, 9]]
    )

    result = parser.read_csv(StringIO(data), skiprows=[6, 8])
    condensed_result = parser.read_csv(StringIO(condensed_data))
    tm.assert_frame_equal(result, condensed_result)


@xfail_pyarrow  # AssertionError: DataFrame are different
def test_skip_rows_blank(all_parsers):
    # see gh-9832
    parser = all_parsers
    text = """#foo,a,b,c
#foo,a,b,c

#foo,a,b,c
#foo,a,b,c

1/1/2000,1.,2.,3.
1/2/2000,4,5,6
1/3/2000,7,8,9
"""
    data = parser.read_csv(
        StringIO(text), skiprows=6, header=None, index_col=0, parse_dates=True
    )
    index = Index(
        [datetime(2000, 1, 1), datetime(2000, 1, 2), datetime(2000, 1, 3)], name=0
    )

    expected = DataFrame(
        np.arange(1.0, 10.0).reshape((3, 3)), columns=[1, 2, 3], index=index
    )
    tm.assert_frame_equal(data, expected)


@pytest.mark.parametrize(
    "data,kwargs,expected",
    [
        (
            """id,text,num_lines
1,"line 11
line 12",2
2,"line 21
line 22",2
3,"line 31",1""",
            {"skiprows": [1]},
            DataFrame(
                [[2, "line 21\nline 22", 2], [3, "line 31", 1]],
                columns=["id", "text", "num_lines"],
            ),
        ),
        (
            "a,b,c\n~a\n b~,~e\n d~,~f\n f~\n1,2,~12\n 13\n 14~",
            {"quotechar": "~", "skiprows": [2]},
            DataFrame([["a\n b", "e\n d", "f\n f"]], columns=["a", "b", "c"]),
        ),
        (
            (
                "Text,url\n~example\n "
                "sentence\n one~,url1\n~"
                "example\n sentence\n two~,url2\n~"
                "example\n sentence\n three~,url3"
            ),
            {"quotechar": "~", "skiprows": [1, 3]},
            DataFrame([["example\n sentence\n two", "url2"]], columns=["Text", "url"]),
        ),
    ],
)
@xfail_pyarrow  # ValueError: skiprows argument must be an integer
def test_skip_row_with_newline(all_parsers, data, kwargs, expected):
    # see gh-12775 and gh-10911
    parser = all_parsers
    result = parser.read_csv(StringIO(data), **kwargs)
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # ValueError: skiprows argument must be an integer
def test_skip_row_with_quote(all_parsers):
    # see gh-12775 and gh-10911
    parser = all_parsers
    data = """id,text,num_lines
1,"line '11' line 12",2
2,"line '21' line 22",2
3,"line '31' line 32",1"""

    exp_data = [[2, "line '21' line 22", 2], [3, "line '31' line 32", 1]]
    expected = DataFrame(exp_data, columns=["id", "text", "num_lines"])

    result = parser.read_csv(StringIO(data), skiprows=[1])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "data,exp_data",
    [
        (
            """id,text,num_lines
1,"line \n'11' line 12",2
2,"line \n'21' line 22",2
3,"line \n'31' line 32",1""",
            [[2, "line \n'21' line 22", 2], [3, "line \n'31' line 32", 1]],
        ),
        (
            """id,text,num_lines
1,"line '11\n' line 12",2
2,"line '21\n' line 22",2
3,"line '31\n' line 32",1""",
            [[2, "line '21\n' line 22", 2], [3, "line '31\n' line 32", 1]],
        ),
        (
            """id,text,num_lines
1,"line '11\n' \r\tline 12",2
2,"line '21\n' \r\tline 22",2
3,"line '31\n' \r\tline 32",1""",
            [[2, "line '21\n' \r\tline 22", 2], [3, "line '31\n' \r\tline 32", 1]],
        ),
    ],
)
@xfail_pyarrow  # ValueError: skiprows argument must be an integer
def test_skip_row_with_newline_and_quote(all_parsers, data, exp_data):
    # see gh-12775 and gh-10911
    parser = all_parsers
    result = parser.read_csv(StringIO(data), skiprows=[1])

    expected = DataFrame(exp_data, columns=["id", "text", "num_lines"])
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # ValueError: The 'delim_whitespace' option is not supported
@pytest.mark.parametrize(
    "lineterminator", ["\n", "\r\n", "\r"]  # "LF"  # "CRLF"  # "CR"
)
def test_skiprows_lineterminator(all_parsers, lineterminator, request):
    # see gh-9079
    parser = all_parsers
    data = "\n".join(
        [
            "SMOSMANIA ThetaProbe-ML2X ",
            "2007/01/01 01:00   0.2140 U M ",
            "2007/01/01 02:00   0.2141 M O ",
            "2007/01/01 04:00   0.2142 D M ",
        ]
    )
    expected = DataFrame(
        [
            ["2007/01/01", "01:00", 0.2140, "U", "M"],
            ["2007/01/01", "02:00", 0.2141, "M", "O"],
            ["2007/01/01", "04:00", 0.2142, "D", "M"],
        ],
        columns=["date", "time", "var", "flag", "oflag"],
    )

    if parser.engine == "python" and lineterminator == "\r":
        mark = pytest.mark.xfail(reason="'CR' not respect with the Python parser yet")
        request.applymarker(mark)

    data = data.replace("\n", lineterminator)

    depr_msg = "The 'delim_whitespace' keyword in pd.read_csv is deprecated"
    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_csv(
            StringIO(data),
            skiprows=1,
            delim_whitespace=True,
            names=["date", "time", "var", "flag", "oflag"],
        )
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # AssertionError: DataFrame are different
def test_skiprows_infield_quote(all_parsers):
    # see gh-14459
    parser = all_parsers
    data = 'a"\nb"\na\n1'
    expected = DataFrame({"a": [1]})

    result = parser.read_csv(StringIO(data), skiprows=2)
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # ValueError: skiprows argument must be an integer
@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({}, DataFrame({"1": [3, 5]})),
        ({"header": 0, "names": ["foo"]}, DataFrame({"foo": [3, 5]})),
    ],
)
def test_skip_rows_callable(all_parsers, kwargs, expected):
    parser = all_parsers
    data = "a\n1\n2\n3\n4\n5"

    result = parser.read_csv(StringIO(data), skiprows=lambda x: x % 2 == 0, **kwargs)
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # ValueError: skiprows argument must be an integer
def test_skip_rows_callable_not_in(all_parsers):
    parser = all_parsers
    data = "0,a\n1,b\n2,c\n3,d\n4,e"
    expected = DataFrame([[1, "b"], [3, "d"]])

    result = parser.read_csv(
        StringIO(data), header=None, skiprows=lambda x: x not in [1, 3]
    )
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # ValueError: skiprows argument must be an integer
def test_skip_rows_skip_all(all_parsers):
    parser = all_parsers
    data = "a\n1\n2\n3\n4\n5"
    msg = "No columns to parse from file"

    with pytest.raises(EmptyDataError, match=msg):
        parser.read_csv(StringIO(data), skiprows=lambda x: True)


@xfail_pyarrow  # ValueError: skiprows argument must be an integer
def test_skip_rows_bad_callable(all_parsers):
    msg = "by zero"
    parser = all_parsers
    data = "a\n1\n2\n3\n4\n5"

    with pytest.raises(ZeroDivisionError, match=msg):
        parser.read_csv(StringIO(data), skiprows=lambda x: 1 / 0)


@xfail_pyarrow  # ValueError: skiprows argument must be an integer
def test_skip_rows_and_n_rows(all_parsers):
    # GH#44021
    data = """a,b
1,a
2,b
3,c
4,d
5,e
6,f
7,g
8,h
"""
    parser = all_parsers
    result = parser.read_csv(StringIO(data), nrows=5, skiprows=[2, 4, 6])
    expected = DataFrame({"a": [1, 3, 5, 7, 8], "b": ["a", "c", "e", "g", "h"]})
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow
def test_skip_rows_with_chunks(all_parsers):
    # GH 55677
    data = """col_a
10
20
30
40
50
60
70
80
90
100
"""
    parser = all_parsers
    reader = parser.read_csv(
        StringIO(data), engine=parser, skiprows=lambda x: x in [1, 4, 5], chunksize=4
    )
    df1 = next(reader)
    df2 = next(reader)

    tm.assert_frame_equal(df1, DataFrame({"col_a": [20, 30, 60, 70]}))
    tm.assert_frame_equal(df2, DataFrame({"col_a": [80, 90, 100]}, index=[4, 5, 6]))
