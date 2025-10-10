"""
Tests the usecols functionality during parsing
for all of the parsers defined in parsers.py
"""
from io import StringIO

import numpy as np
import pytest

from pandas.errors import ParserError

from pandas import (
    DataFrame,
    Index,
    array,
)
import pandas._testing as tm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)

_msg_validate_usecols_arg = (
    "'usecols' must either be list-like "
    "of all strings, all unicode, all "
    "integers or a callable."
)
_msg_validate_usecols_names = (
    "Usecols do not match columns, columns expected but not found: {0}"
)
_msg_pyarrow_requires_names = (
    "The pyarrow engine does not allow 'usecols' to be integer column "
    "positions. Pass a list of string column names instead."
)

xfail_pyarrow = pytest.mark.usefixtures("pyarrow_xfail")
skip_pyarrow = pytest.mark.usefixtures("pyarrow_skip")

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame is deprecated:DeprecationWarning"
)


def test_raise_on_mixed_dtype_usecols(all_parsers):
    # See gh-12678
    data = """a,b,c
        1000,2000,3000
        4000,5000,6000
        """
    usecols = [0, "b", 2]
    parser = all_parsers

    with pytest.raises(ValueError, match=_msg_validate_usecols_arg):
        parser.read_csv(StringIO(data), usecols=usecols)


@pytest.mark.parametrize("usecols", [(1, 2), ("b", "c")])
def test_usecols(all_parsers, usecols, request):
    data = """\
a,b,c
1,2,3
4,5,6
7,8,9
10,11,12"""
    parser = all_parsers
    if parser.engine == "pyarrow" and isinstance(usecols[0], int):
        with pytest.raises(ValueError, match=_msg_pyarrow_requires_names):
            parser.read_csv(StringIO(data), usecols=usecols)
        return

    result = parser.read_csv(StringIO(data), usecols=usecols)

    expected = DataFrame([[2, 3], [5, 6], [8, 9], [11, 12]], columns=["b", "c"])
    tm.assert_frame_equal(result, expected)


def test_usecols_with_names(all_parsers):
    data = """\
a,b,c
1,2,3
4,5,6
7,8,9
10,11,12"""
    parser = all_parsers
    names = ["foo", "bar"]

    if parser.engine == "pyarrow":
        with pytest.raises(ValueError, match=_msg_pyarrow_requires_names):
            parser.read_csv(StringIO(data), names=names, usecols=[1, 2], header=0)
        return

    result = parser.read_csv(StringIO(data), names=names, usecols=[1, 2], header=0)

    expected = DataFrame([[2, 3], [5, 6], [8, 9], [11, 12]], columns=names)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "names,usecols", [(["b", "c"], [1, 2]), (["a", "b", "c"], ["b", "c"])]
)
def test_usecols_relative_to_names(all_parsers, names, usecols):
    data = """\
1,2,3
4,5,6
7,8,9
10,11,12"""
    parser = all_parsers
    if parser.engine == "pyarrow" and not isinstance(usecols[0], int):
        # ArrowKeyError: Column 'fb' in include_columns does not exist
        pytest.skip(reason="https://github.com/apache/arrow/issues/38676")

    result = parser.read_csv(StringIO(data), names=names, header=None, usecols=usecols)

    expected = DataFrame([[2, 3], [5, 6], [8, 9], [11, 12]], columns=["b", "c"])
    tm.assert_frame_equal(result, expected)


def test_usecols_relative_to_names2(all_parsers):
    # see gh-5766
    data = """\
1,2,3
4,5,6
7,8,9
10,11,12"""
    parser = all_parsers

    result = parser.read_csv(
        StringIO(data), names=["a", "b"], header=None, usecols=[0, 1]
    )

    expected = DataFrame([[1, 2], [4, 5], [7, 8], [10, 11]], columns=["a", "b"])
    tm.assert_frame_equal(result, expected)


# regex mismatch: "Length mismatch: Expected axis has 1 elements"
@xfail_pyarrow
def test_usecols_name_length_conflict(all_parsers):
    data = """\
1,2,3
4,5,6
7,8,9
10,11,12"""
    parser = all_parsers
    msg = "Number of passed names did not match number of header fields in the file"
    with pytest.raises(ValueError, match=msg):
        parser.read_csv(StringIO(data), names=["a", "b"], header=None, usecols=[1])


def test_usecols_single_string(all_parsers):
    # see gh-20558
    parser = all_parsers
    data = """foo, bar, baz
1000, 2000, 3000
4000, 5000, 6000"""

    with pytest.raises(ValueError, match=_msg_validate_usecols_arg):
        parser.read_csv(StringIO(data), usecols="foo")


@skip_pyarrow  # CSV parse error in one case, AttributeError in another
@pytest.mark.parametrize(
    "data", ["a,b,c,d\n1,2,3,4\n5,6,7,8", "a,b,c,d\n1,2,3,4,\n5,6,7,8,"]
)
def test_usecols_index_col_false(all_parsers, data):
    # see gh-9082
    parser = all_parsers
    usecols = ["a", "c", "d"]
    expected = DataFrame({"a": [1, 5], "c": [3, 7], "d": [4, 8]})

    result = parser.read_csv(StringIO(data), usecols=usecols, index_col=False)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("index_col", ["b", 0])
@pytest.mark.parametrize("usecols", [["b", "c"], [1, 2]])
def test_usecols_index_col_conflict(all_parsers, usecols, index_col, request):
    # see gh-4201: test that index_col as integer reflects usecols
    parser = all_parsers
    data = "a,b,c,d\nA,a,1,one\nB,b,2,two"

    if parser.engine == "pyarrow" and isinstance(usecols[0], int):
        with pytest.raises(ValueError, match=_msg_pyarrow_requires_names):
            parser.read_csv(StringIO(data), usecols=usecols, index_col=index_col)
        return

    expected = DataFrame({"c": [1, 2]}, index=Index(["a", "b"], name="b"))

    result = parser.read_csv(StringIO(data), usecols=usecols, index_col=index_col)
    tm.assert_frame_equal(result, expected)


def test_usecols_index_col_conflict2(all_parsers):
    # see gh-4201: test that index_col as integer reflects usecols
    parser = all_parsers
    data = "a,b,c,d\nA,a,1,one\nB,b,2,two"

    expected = DataFrame({"b": ["a", "b"], "c": [1, 2], "d": ("one", "two")})
    expected = expected.set_index(["b", "c"])

    result = parser.read_csv(
        StringIO(data), usecols=["b", "c", "d"], index_col=["b", "c"]
    )
    tm.assert_frame_equal(result, expected)


@skip_pyarrow  # CSV parse error: Expected 3 columns, got 4
def test_usecols_implicit_index_col(all_parsers):
    # see gh-2654
    parser = all_parsers
    data = "a,b,c\n4,apple,bat,5.7\n8,orange,cow,10"

    result = parser.read_csv(StringIO(data), usecols=["a", "b"])
    expected = DataFrame({"a": ["apple", "orange"], "b": ["bat", "cow"]}, index=[4, 8])
    tm.assert_frame_equal(result, expected)


def test_usecols_index_col_middle(all_parsers):
    # GH#9098
    parser = all_parsers
    data = """a,b,c,d
1,2,3,4
"""
    result = parser.read_csv(StringIO(data), usecols=["b", "c", "d"], index_col="c")
    expected = DataFrame({"b": [2], "d": [4]}, index=Index([3], name="c"))
    tm.assert_frame_equal(result, expected)


def test_usecols_index_col_end(all_parsers):
    # GH#9098
    parser = all_parsers
    data = """a,b,c,d
1,2,3,4
"""
    result = parser.read_csv(StringIO(data), usecols=["b", "c", "d"], index_col="d")
    expected = DataFrame({"b": [2], "c": [3]}, index=Index([4], name="d"))
    tm.assert_frame_equal(result, expected)


def test_usecols_regex_sep(all_parsers):
    # see gh-2733
    parser = all_parsers
    data = "a  b  c\n4  apple  bat  5.7\n8  orange  cow  10"

    if parser.engine == "pyarrow":
        msg = "the 'pyarrow' engine does not support regex separators"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), sep=r"\s+", usecols=("a", "b"))
        return

    result = parser.read_csv(StringIO(data), sep=r"\s+", usecols=("a", "b"))

    expected = DataFrame({"a": ["apple", "orange"], "b": ["bat", "cow"]}, index=[4, 8])
    tm.assert_frame_equal(result, expected)


def test_usecols_with_whitespace(all_parsers):
    parser = all_parsers
    data = "a  b  c\n4  apple  bat  5.7\n8  orange  cow  10"

    depr_msg = "The 'delim_whitespace' keyword in pd.read_csv is deprecated"

    if parser.engine == "pyarrow":
        msg = "The 'delim_whitespace' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(
                FutureWarning, match=depr_msg, check_stacklevel=False
            ):
                parser.read_csv(
                    StringIO(data), delim_whitespace=True, usecols=("a", "b")
                )
        return

    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_csv(
            StringIO(data), delim_whitespace=True, usecols=("a", "b")
        )
    expected = DataFrame({"a": ["apple", "orange"], "b": ["bat", "cow"]}, index=[4, 8])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "usecols,expected",
    [
        # Column selection by index.
        ([0, 1], DataFrame(data=[[1000, 2000], [4000, 5000]], columns=["2", "0"])),
        # Column selection by name.
        (
            ["0", "1"],
            DataFrame(data=[[2000, 3000], [5000, 6000]], columns=["0", "1"]),
        ),
    ],
)
def test_usecols_with_integer_like_header(all_parsers, usecols, expected, request):
    parser = all_parsers
    data = """2,0,1
1000,2000,3000
4000,5000,6000"""

    if parser.engine == "pyarrow" and isinstance(usecols[0], int):
        with pytest.raises(ValueError, match=_msg_pyarrow_requires_names):
            parser.read_csv(StringIO(data), usecols=usecols)
        return

    result = parser.read_csv(StringIO(data), usecols=usecols)
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # mismatched shape
def test_empty_usecols(all_parsers):
    data = "a,b,c\n1,2,3\n4,5,6"
    expected = DataFrame(columns=Index([]))
    parser = all_parsers

    result = parser.read_csv(StringIO(data), usecols=set())
    tm.assert_frame_equal(result, expected)


def test_np_array_usecols(all_parsers):
    # see gh-12546
    parser = all_parsers
    data = "a,b,c\n1,2,3"
    usecols = np.array(["a", "b"])

    expected = DataFrame([[1, 2]], columns=usecols)
    result = parser.read_csv(StringIO(data), usecols=usecols)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "usecols,expected",
    [
        (
            lambda x: x.upper() in ["AAA", "BBB", "DDD"],
            DataFrame(
                {
                    "AaA": {
                        0: 0.056674972999999997,
                        1: 2.6132309819999997,
                        2: 3.5689350380000002,
                    },
                    "bBb": {0: 8, 1: 2, 2: 7},
                    "ddd": {0: "a", 1: "b", 2: "a"},
                }
            ),
        ),
        (lambda x: False, DataFrame(columns=Index([]))),
    ],
)
def test_callable_usecols(all_parsers, usecols, expected):
    # see gh-14154
    data = """AaA,bBb,CCC,ddd
0.056674973,8,True,a
2.613230982,2,False,b
3.568935038,7,False,a"""
    parser = all_parsers

    if parser.engine == "pyarrow":
        msg = "The pyarrow engine does not allow 'usecols' to be a callable"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), usecols=usecols)
        return

    result = parser.read_csv(StringIO(data), usecols=usecols)
    tm.assert_frame_equal(result, expected)


# ArrowKeyError: Column 'fa' in include_columns does not exist in CSV file
@skip_pyarrow
@pytest.mark.parametrize("usecols", [["a", "c"], lambda x: x in ["a", "c"]])
def test_incomplete_first_row(all_parsers, usecols):
    # see gh-6710
    data = "1,2\n1,2,3"
    parser = all_parsers
    names = ["a", "b", "c"]
    expected = DataFrame({"a": [1, 1], "c": [np.nan, 3]})

    result = parser.read_csv(StringIO(data), names=names, usecols=usecols)
    tm.assert_frame_equal(result, expected)


@skip_pyarrow  # CSV parse error: Expected 3 columns, got 4
@pytest.mark.parametrize(
    "data,usecols,kwargs,expected",
    [
        # see gh-8985
        (
            "19,29,39\n" * 2 + "10,20,30,40",
            [0, 1, 2],
            {"header": None},
            DataFrame([[19, 29, 39], [19, 29, 39], [10, 20, 30]]),
        ),
        # see gh-9549
        (
            ("A,B,C\n1,2,3\n3,4,5\n1,2,4,5,1,6\n1,2,3,,,1,\n1,2,3\n5,6,7"),
            ["A", "B", "C"],
            {},
            DataFrame(
                {
                    "A": [1, 3, 1, 1, 1, 5],
                    "B": [2, 4, 2, 2, 2, 6],
                    "C": [3, 5, 4, 3, 3, 7],
                }
            ),
        ),
    ],
)
def test_uneven_length_cols(all_parsers, data, usecols, kwargs, expected):
    # see gh-8985
    parser = all_parsers
    result = parser.read_csv(StringIO(data), usecols=usecols, **kwargs)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "usecols,kwargs,expected,msg",
    [
        (
            ["a", "b", "c", "d"],
            {},
            DataFrame({"a": [1, 5], "b": [2, 6], "c": [3, 7], "d": [4, 8]}),
            None,
        ),
        (
            ["a", "b", "c", "f"],
            {},
            None,
            _msg_validate_usecols_names.format(r"\['f'\]"),
        ),
        (["a", "b", "f"], {}, None, _msg_validate_usecols_names.format(r"\['f'\]")),
        (
            ["a", "b", "f", "g"],
            {},
            None,
            _msg_validate_usecols_names.format(r"\[('f', 'g'|'g', 'f')\]"),
        ),
        # see gh-14671
        (
            None,
            {"header": 0, "names": ["A", "B", "C", "D"]},
            DataFrame({"A": [1, 5], "B": [2, 6], "C": [3, 7], "D": [4, 8]}),
            None,
        ),
        (
            ["A", "B", "C", "f"],
            {"header": 0, "names": ["A", "B", "C", "D"]},
            None,
            _msg_validate_usecols_names.format(r"\['f'\]"),
        ),
        (
            ["A", "B", "f"],
            {"names": ["A", "B", "C", "D"]},
            None,
            _msg_validate_usecols_names.format(r"\['f'\]"),
        ),
    ],
)
def test_raises_on_usecols_names_mismatch(
    all_parsers, usecols, kwargs, expected, msg, request
):
    data = "a,b,c,d\n1,2,3,4\n5,6,7,8"
    kwargs.update(usecols=usecols)
    parser = all_parsers

    if parser.engine == "pyarrow" and not (
        usecols is not None and expected is not None
    ):
        # everything but the first case
        # ArrowKeyError: Column 'f' in include_columns does not exist in CSV file
        pytest.skip(reason="https://github.com/apache/arrow/issues/38676")

    if expected is None:
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), **kwargs)
    else:
        result = parser.read_csv(StringIO(data), **kwargs)
        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("usecols", [["A", "C"], [0, 2]])
def test_usecols_subset_names_mismatch_orig_columns(all_parsers, usecols, request):
    data = "a,b,c,d\n1,2,3,4\n5,6,7,8"
    names = ["A", "B", "C", "D"]
    parser = all_parsers

    if parser.engine == "pyarrow":
        if isinstance(usecols[0], int):
            with pytest.raises(ValueError, match=_msg_pyarrow_requires_names):
                parser.read_csv(StringIO(data), header=0, names=names, usecols=usecols)
            return
        # "pyarrow.lib.ArrowKeyError: Column 'A' in include_columns does not exist"
        pytest.skip(reason="https://github.com/apache/arrow/issues/38676")

    result = parser.read_csv(StringIO(data), header=0, names=names, usecols=usecols)
    expected = DataFrame({"A": [1, 5], "C": [3, 7]})
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("names", [None, ["a", "b"]])
def test_usecols_indices_out_of_bounds(all_parsers, names):
    # GH#25623 & GH 41130; enforced in 2.0
    parser = all_parsers
    data = """
a,b
1,2
    """

    err = ParserError
    msg = "Defining usecols with out-of-bounds"
    if parser.engine == "pyarrow":
        err = ValueError
        msg = _msg_pyarrow_requires_names

    with pytest.raises(err, match=msg):
        parser.read_csv(StringIO(data), usecols=[0, 2], names=names, header=0)


def test_usecols_additional_columns(all_parsers):
    # GH#46997
    parser = all_parsers
    usecols = lambda header: header.strip() in ["a", "b", "c"]

    if parser.engine == "pyarrow":
        msg = "The pyarrow engine does not allow 'usecols' to be a callable"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO("a,b\nx,y,z"), index_col=False, usecols=usecols)
        return
    result = parser.read_csv(StringIO("a,b\nx,y,z"), index_col=False, usecols=usecols)
    expected = DataFrame({"a": ["x"], "b": "y"})
    tm.assert_frame_equal(result, expected)


def test_usecols_additional_columns_integer_columns(all_parsers):
    # GH#46997
    parser = all_parsers
    usecols = lambda header: header.strip() in ["0", "1"]
    if parser.engine == "pyarrow":
        msg = "The pyarrow engine does not allow 'usecols' to be a callable"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO("0,1\nx,y,z"), index_col=False, usecols=usecols)
        return
    result = parser.read_csv(StringIO("0,1\nx,y,z"), index_col=False, usecols=usecols)
    expected = DataFrame({"0": ["x"], "1": "y"})
    tm.assert_frame_equal(result, expected)


def test_usecols_dtype(all_parsers):
    parser = all_parsers
    data = """
col1,col2,col3
a,1,x
b,2,y
"""
    result = parser.read_csv(
        StringIO(data),
        usecols=["col1", "col2"],
        dtype={"col1": "string", "col2": "uint8", "col3": "string"},
    )
    expected = DataFrame(
        {"col1": array(["a", "b"]), "col2": np.array([1, 2], dtype="uint8")}
    )
    tm.assert_frame_equal(result, expected)
