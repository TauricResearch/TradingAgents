"""
Tests that work on both the Python and C engines but do not have a
specific classification into the other test modules.
"""
from io import StringIO

import numpy as np
import pytest

from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)

xfail_pyarrow = pytest.mark.usefixtures("pyarrow_xfail")
skip_pyarrow = pytest.mark.usefixtures("pyarrow_skip")


def test_int_conversion(all_parsers):
    data = """A,B
1.0,1
2.0,2
3.0,3
"""
    parser = all_parsers
    result = parser.read_csv(StringIO(data))

    expected = DataFrame([[1.0, 1], [2.0, 2], [3.0, 3]], columns=["A", "B"])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "data,kwargs,expected",
    [
        (
            "A,B\nTrue,1\nFalse,2\nTrue,3",
            {},
            DataFrame([[True, 1], [False, 2], [True, 3]], columns=["A", "B"]),
        ),
        (
            "A,B\nYES,1\nno,2\nyes,3\nNo,3\nYes,3",
            {"true_values": ["yes", "Yes", "YES"], "false_values": ["no", "NO", "No"]},
            DataFrame(
                [[True, 1], [False, 2], [True, 3], [False, 3], [True, 3]],
                columns=["A", "B"],
            ),
        ),
        (
            "A,B\nTRUE,1\nFALSE,2\nTRUE,3",
            {},
            DataFrame([[True, 1], [False, 2], [True, 3]], columns=["A", "B"]),
        ),
        (
            "A,B\nfoo,bar\nbar,foo",
            {"true_values": ["foo"], "false_values": ["bar"]},
            DataFrame([[True, False], [False, True]], columns=["A", "B"]),
        ),
    ],
)
def test_parse_bool(all_parsers, data, kwargs, expected):
    parser = all_parsers
    result = parser.read_csv(StringIO(data), **kwargs)
    tm.assert_frame_equal(result, expected)


def test_parse_integers_above_fp_precision(all_parsers):
    data = """Numbers
17007000002000191
17007000002000191
17007000002000191
17007000002000191
17007000002000192
17007000002000192
17007000002000192
17007000002000192
17007000002000192
17007000002000194"""
    parser = all_parsers
    result = parser.read_csv(StringIO(data))
    expected = DataFrame(
        {
            "Numbers": [
                17007000002000191,
                17007000002000191,
                17007000002000191,
                17007000002000191,
                17007000002000192,
                17007000002000192,
                17007000002000192,
                17007000002000192,
                17007000002000192,
                17007000002000194,
            ]
        }
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("sep", [" ", r"\s+"])
def test_integer_overflow_bug(all_parsers, sep):
    # see gh-2601
    data = "65248E10 11\n55555E55 22\n"
    parser = all_parsers
    if parser.engine == "pyarrow" and sep != " ":
        msg = "the 'pyarrow' engine does not support regex separators"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), header=None, sep=sep)
        return

    result = parser.read_csv(StringIO(data), header=None, sep=sep)
    expected = DataFrame([[6.5248e14, 11], [5.5555e59, 22]])
    tm.assert_frame_equal(result, expected)


def test_int64_min_issues(all_parsers):
    # see gh-2599
    parser = all_parsers
    data = "A,B\n0,0\n0,"
    result = parser.read_csv(StringIO(data))

    expected = DataFrame({"A": [0, 0], "B": [0, np.nan]})
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("conv", [None, np.int64, np.uint64])
def test_int64_overflow(all_parsers, conv, request):
    data = """ID
00013007854817840016671868
00013007854817840016749251
00013007854817840016754630
00013007854817840016781876
00013007854817840017028824
00013007854817840017963235
00013007854817840018860166"""
    parser = all_parsers

    if conv is None:
        # 13007854817840016671868 > UINT64_MAX, so this
        # will overflow and return object as the dtype.
        if parser.engine == "pyarrow":
            mark = pytest.mark.xfail(reason="parses to float64")
            request.applymarker(mark)

        result = parser.read_csv(StringIO(data))
        expected = DataFrame(
            [
                "00013007854817840016671868",
                "00013007854817840016749251",
                "00013007854817840016754630",
                "00013007854817840016781876",
                "00013007854817840017028824",
                "00013007854817840017963235",
                "00013007854817840018860166",
            ],
            columns=["ID"],
        )
        tm.assert_frame_equal(result, expected)
    else:
        # 13007854817840016671868 > UINT64_MAX, so attempts
        # to cast to either int64 or uint64 will result in
        # an OverflowError being raised.
        msg = "|".join(
            [
                "Python int too large to convert to C long",
                "long too big to convert",
                "int too big to convert",
            ]
        )
        err = OverflowError
        if parser.engine == "pyarrow":
            err = ValueError
            msg = "The 'converters' option is not supported with the 'pyarrow' engine"

        with pytest.raises(err, match=msg):
            parser.read_csv(StringIO(data), converters={"ID": conv})


@skip_pyarrow  # CSV parse error: Empty CSV file or block
@pytest.mark.parametrize(
    "val", [np.iinfo(np.uint64).max, np.iinfo(np.int64).max, np.iinfo(np.int64).min]
)
def test_int64_uint64_range(all_parsers, val):
    # These numbers fall right inside the int64-uint64
    # range, so they should be parsed as string.
    parser = all_parsers
    result = parser.read_csv(StringIO(str(val)), header=None)

    expected = DataFrame([val])
    tm.assert_frame_equal(result, expected)


@skip_pyarrow  # CSV parse error: Empty CSV file or block
@pytest.mark.parametrize(
    "val", [np.iinfo(np.uint64).max + 1, np.iinfo(np.int64).min - 1]
)
def test_outside_int64_uint64_range(all_parsers, val):
    # These numbers fall just outside the int64-uint64
    # range, so they should be parsed as string.
    parser = all_parsers
    result = parser.read_csv(StringIO(str(val)), header=None)

    expected = DataFrame([str(val)])
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # gets float64 dtype instead of object
@pytest.mark.parametrize("exp_data", [[str(-1), str(2**63)], [str(2**63), str(-1)]])
def test_numeric_range_too_wide(all_parsers, exp_data):
    # No numerical dtype can hold both negative and uint64
    # values, so they should be cast as string.
    parser = all_parsers
    data = "\n".join(exp_data)
    expected = DataFrame(exp_data)

    result = parser.read_csv(StringIO(data), header=None)
    tm.assert_frame_equal(result, expected)


def test_integer_precision(all_parsers):
    # Gh 7072
    s = """1,1;0;0;0;1;1;3844;3844;3844;1;1;1;1;1;1;0;0;1;1;0;0,,,4321583677327450765
5,1;0;0;0;1;1;843;843;843;1;1;1;1;1;1;0;0;1;1;0;0,64.0,;,4321113141090630389"""
    parser = all_parsers
    result = parser.read_csv(StringIO(s), header=None)[4]
    expected = Series([4321583677327450765, 4321113141090630389], name=4)
    tm.assert_series_equal(result, expected)
