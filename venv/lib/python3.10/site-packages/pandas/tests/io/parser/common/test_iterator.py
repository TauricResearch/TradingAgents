"""
Tests that work on both the Python and C engines but do not have a
specific classification into the other test modules.
"""
from io import StringIO

import pytest

from pandas import (
    DataFrame,
    concat,
)
import pandas._testing as tm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)


def test_iterator(all_parsers):
    # see gh-6607
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

    expected = parser.read_csv(StringIO(data), **kwargs)

    if parser.engine == "pyarrow":
        msg = "The 'iterator' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), iterator=True, **kwargs)
        return

    with parser.read_csv(StringIO(data), iterator=True, **kwargs) as reader:
        first_chunk = reader.read(3)
        tm.assert_frame_equal(first_chunk, expected[:3])

        last_chunk = reader.read(5)
    tm.assert_frame_equal(last_chunk, expected[3:])


def test_iterator2(all_parsers):
    parser = all_parsers
    data = """A,B,C
foo,1,2,3
bar,4,5,6
baz,7,8,9
"""

    if parser.engine == "pyarrow":
        msg = "The 'iterator' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), iterator=True)
        return

    with parser.read_csv(StringIO(data), iterator=True) as reader:
        result = list(reader)

    expected = DataFrame(
        [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
        index=["foo", "bar", "baz"],
        columns=["A", "B", "C"],
    )
    tm.assert_frame_equal(result[0], expected)


def test_iterator_stop_on_chunksize(all_parsers):
    # gh-3967: stopping iteration when chunksize is specified
    parser = all_parsers
    data = """A,B,C
foo,1,2,3
bar,4,5,6
baz,7,8,9
"""
    if parser.engine == "pyarrow":
        msg = "The 'chunksize' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), chunksize=1)
        return

    with parser.read_csv(StringIO(data), chunksize=1) as reader:
        result = list(reader)

    assert len(result) == 3
    expected = DataFrame(
        [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
        index=["foo", "bar", "baz"],
        columns=["A", "B", "C"],
    )
    tm.assert_frame_equal(concat(result), expected)


@pytest.mark.parametrize(
    "kwargs", [{"iterator": True, "chunksize": 1}, {"iterator": True}, {"chunksize": 1}]
)
def test_iterator_skipfooter_errors(all_parsers, kwargs):
    msg = "'skipfooter' not supported for iteration"
    parser = all_parsers
    data = "a\n1\n2"

    if parser.engine == "pyarrow":
        msg = (
            "The '(chunksize|iterator)' option is not supported with the "
            "'pyarrow' engine"
        )

    with pytest.raises(ValueError, match=msg):
        with parser.read_csv(StringIO(data), skipfooter=1, **kwargs) as _:
            pass


def test_iteration_open_handle(all_parsers):
    parser = all_parsers
    kwargs = {"header": None}

    with tm.ensure_clean() as path:
        with open(path, "w", encoding="utf-8") as f:
            f.write("AAA\nBBB\nCCC\nDDD\nEEE\nFFF\nGGG")

        with open(path, encoding="utf-8") as f:
            for line in f:
                if "CCC" in line:
                    break

            result = parser.read_csv(f, **kwargs)
            expected = DataFrame({0: ["DDD", "EEE", "FFF", "GGG"]})
            tm.assert_frame_equal(result, expected)
