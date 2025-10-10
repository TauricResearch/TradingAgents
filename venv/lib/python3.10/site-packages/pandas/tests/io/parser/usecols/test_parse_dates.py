"""
Tests the usecols functionality during parsing
for all of the parsers defined in parsers.py
"""
from io import StringIO

import pytest

from pandas import (
    DataFrame,
    Index,
    Timestamp,
)
import pandas._testing as tm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)
xfail_pyarrow = pytest.mark.usefixtures("pyarrow_xfail")
skip_pyarrow = pytest.mark.usefixtures("pyarrow_skip")

_msg_pyarrow_requires_names = (
    "The pyarrow engine does not allow 'usecols' to be integer column "
    "positions. Pass a list of string column names instead."
)


@pytest.mark.parametrize("usecols", [[0, 2, 3], [3, 0, 2]])
def test_usecols_with_parse_dates(all_parsers, usecols):
    # see gh-9755
    data = """a,b,c,d,e
0,1,2014-01-01,09:00,4
0,1,2014-01-02,10:00,4"""
    parser = all_parsers
    parse_dates = [[1, 2]]

    depr_msg = (
        "Support for nested sequences for 'parse_dates' in pd.read_csv is deprecated"
    )

    cols = {
        "a": [0, 0],
        "c_d": [Timestamp("2014-01-01 09:00:00"), Timestamp("2014-01-02 10:00:00")],
    }
    expected = DataFrame(cols, columns=["c_d", "a"])
    if parser.engine == "pyarrow":
        with pytest.raises(ValueError, match=_msg_pyarrow_requires_names):
            with tm.assert_produces_warning(
                FutureWarning, match=depr_msg, check_stacklevel=False
            ):
                parser.read_csv(
                    StringIO(data), usecols=usecols, parse_dates=parse_dates
                )
        return
    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_csv(
            StringIO(data), usecols=usecols, parse_dates=parse_dates
        )
    tm.assert_frame_equal(result, expected)


@skip_pyarrow  # pyarrow.lib.ArrowKeyError: Column 'fdate' in include_columns
def test_usecols_with_parse_dates2(all_parsers):
    # see gh-13604
    parser = all_parsers
    data = """2008-02-07 09:40,1032.43
2008-02-07 09:50,1042.54
2008-02-07 10:00,1051.65"""

    names = ["date", "values"]
    usecols = names[:]
    parse_dates = [0]

    index = Index(
        [
            Timestamp("2008-02-07 09:40"),
            Timestamp("2008-02-07 09:50"),
            Timestamp("2008-02-07 10:00"),
        ],
        name="date",
    )
    cols = {"values": [1032.43, 1042.54, 1051.65]}
    expected = DataFrame(cols, index=index)

    result = parser.read_csv(
        StringIO(data),
        parse_dates=parse_dates,
        index_col=0,
        usecols=usecols,
        header=None,
        names=names,
    )
    tm.assert_frame_equal(result, expected)


def test_usecols_with_parse_dates3(all_parsers):
    # see gh-14792
    parser = all_parsers
    data = """a,b,c,d,e,f,g,h,i,j
2016/09/21,1,1,2,3,4,5,6,7,8"""

    usecols = list("abcdefghij")
    parse_dates = [0]

    cols = {
        "a": Timestamp("2016-09-21").as_unit("ns"),
        "b": [1],
        "c": [1],
        "d": [2],
        "e": [3],
        "f": [4],
        "g": [5],
        "h": [6],
        "i": [7],
        "j": [8],
    }
    expected = DataFrame(cols, columns=usecols)

    result = parser.read_csv(StringIO(data), usecols=usecols, parse_dates=parse_dates)
    tm.assert_frame_equal(result, expected)


def test_usecols_with_parse_dates4(all_parsers):
    data = "a,b,c,d,e,f,g,h,i,j\n2016/09/21,1,1,2,3,4,5,6,7,8"
    usecols = list("abcdefghij")
    parse_dates = [[0, 1]]
    parser = all_parsers

    cols = {
        "a_b": "2016/09/21 1",
        "c": [1],
        "d": [2],
        "e": [3],
        "f": [4],
        "g": [5],
        "h": [6],
        "i": [7],
        "j": [8],
    }
    expected = DataFrame(cols, columns=["a_b"] + list("cdefghij"))

    depr_msg = (
        "Support for nested sequences for 'parse_dates' in pd.read_csv is deprecated"
    )
    with tm.assert_produces_warning(
        (FutureWarning, DeprecationWarning), match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_csv(
            StringIO(data),
            usecols=usecols,
            parse_dates=parse_dates,
        )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("usecols", [[0, 2, 3], [3, 0, 2]])
@pytest.mark.parametrize(
    "names",
    [
        list("abcde"),  # Names span all columns in original data.
        list("acd"),  # Names span only the selected columns.
    ],
)
def test_usecols_with_parse_dates_and_names(all_parsers, usecols, names, request):
    # see gh-9755
    s = """0,1,2014-01-01,09:00,4
0,1,2014-01-02,10:00,4"""
    parse_dates = [[1, 2]]
    parser = all_parsers

    if parser.engine == "pyarrow" and not (len(names) == 3 and usecols[0] == 0):
        mark = pytest.mark.xfail(
            reason="Length mismatch in some cases, UserWarning in other"
        )
        request.applymarker(mark)

    cols = {
        "a": [0, 0],
        "c_d": [Timestamp("2014-01-01 09:00:00"), Timestamp("2014-01-02 10:00:00")],
    }
    expected = DataFrame(cols, columns=["c_d", "a"])

    depr_msg = (
        "Support for nested sequences for 'parse_dates' in pd.read_csv is deprecated"
    )
    with tm.assert_produces_warning(
        (FutureWarning, DeprecationWarning), match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_csv(
            StringIO(s), names=names, parse_dates=parse_dates, usecols=usecols
        )
    tm.assert_frame_equal(result, expected)
