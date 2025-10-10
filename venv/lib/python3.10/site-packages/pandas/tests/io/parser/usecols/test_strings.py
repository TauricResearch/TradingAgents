"""
Tests the usecols functionality during parsing
for all of the parsers defined in parsers.py
"""
from io import StringIO

import pytest

from pandas import DataFrame
import pandas._testing as tm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)


def test_usecols_with_unicode_strings(all_parsers):
    # see gh-13219
    data = """AAA,BBB,CCC,DDD
0.056674973,8,True,a
2.613230982,2,False,b
3.568935038,7,False,a"""
    parser = all_parsers

    exp_data = {
        "AAA": {
            0: 0.056674972999999997,
            1: 2.6132309819999997,
            2: 3.5689350380000002,
        },
        "BBB": {0: 8, 1: 2, 2: 7},
    }
    expected = DataFrame(exp_data)

    result = parser.read_csv(StringIO(data), usecols=["AAA", "BBB"])
    tm.assert_frame_equal(result, expected)


def test_usecols_with_single_byte_unicode_strings(all_parsers):
    # see gh-13219
    data = """A,B,C,D
0.056674973,8,True,a
2.613230982,2,False,b
3.568935038,7,False,a"""
    parser = all_parsers

    exp_data = {
        "A": {
            0: 0.056674972999999997,
            1: 2.6132309819999997,
            2: 3.5689350380000002,
        },
        "B": {0: 8, 1: 2, 2: 7},
    }
    expected = DataFrame(exp_data)

    result = parser.read_csv(StringIO(data), usecols=["A", "B"])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("usecols", [["AAA", b"BBB"], [b"AAA", "BBB"]])
def test_usecols_with_mixed_encoding_strings(all_parsers, usecols):
    data = """AAA,BBB,CCC,DDD
0.056674973,8,True,a
2.613230982,2,False,b
3.568935038,7,False,a"""
    parser = all_parsers
    _msg_validate_usecols_arg = (
        "'usecols' must either be list-like "
        "of all strings, all unicode, all "
        "integers or a callable."
    )
    with pytest.raises(ValueError, match=_msg_validate_usecols_arg):
        parser.read_csv(StringIO(data), usecols=usecols)


@pytest.mark.parametrize("usecols", [["あああ", "いい"], ["あああ", "いい"]])
def test_usecols_with_multi_byte_characters(all_parsers, usecols):
    data = """あああ,いい,ううう,ええええ
0.056674973,8,True,a
2.613230982,2,False,b
3.568935038,7,False,a"""
    parser = all_parsers

    exp_data = {
        "あああ": {
            0: 0.056674972999999997,
            1: 2.6132309819999997,
            2: 3.5689350380000002,
        },
        "いい": {0: 8, 1: 2, 2: 7},
    }
    expected = DataFrame(exp_data)

    result = parser.read_csv(StringIO(data), usecols=usecols)
    tm.assert_frame_equal(result, expected)
