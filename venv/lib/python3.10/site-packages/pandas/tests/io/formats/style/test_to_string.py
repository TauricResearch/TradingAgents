from textwrap import dedent

import pytest

from pandas import (
    DataFrame,
    Series,
)

pytest.importorskip("jinja2")
from pandas.io.formats.style import Styler


@pytest.fixture
def df():
    return DataFrame(
        {"A": [0, 1], "B": [-0.61, -1.22], "C": Series(["ab", "cd"], dtype=object)}
    )


@pytest.fixture
def styler(df):
    return Styler(df, uuid_len=0, precision=2)


def test_basic_string(styler):
    result = styler.to_string()
    expected = dedent(
        """\
     A B C
    0 0 -0.61 ab
    1 1 -1.22 cd
    """
    )
    assert result == expected


def test_string_delimiter(styler):
    result = styler.to_string(delimiter=";")
    expected = dedent(
        """\
    ;A;B;C
    0;0;-0.61;ab
    1;1;-1.22;cd
    """
    )
    assert result == expected


def test_concat(styler):
    result = styler.concat(styler.data.agg(["sum"]).style).to_string()
    expected = dedent(
        """\
     A B C
    0 0 -0.61 ab
    1 1 -1.22 cd
    sum 1 -1.830000 abcd
    """
    )
    assert result == expected


def test_concat_recursion(styler):
    df = styler.data
    styler1 = styler
    styler2 = Styler(df.agg(["sum"]), uuid_len=0, precision=3)
    styler3 = Styler(df.agg(["sum"]), uuid_len=0, precision=4)
    result = styler1.concat(styler2.concat(styler3)).to_string()
    expected = dedent(
        """\
     A B C
    0 0 -0.61 ab
    1 1 -1.22 cd
    sum 1 -1.830 abcd
    sum 1 -1.8300 abcd
    """
    )
    assert result == expected


def test_concat_chain(styler):
    df = styler.data
    styler1 = styler
    styler2 = Styler(df.agg(["sum"]), uuid_len=0, precision=3)
    styler3 = Styler(df.agg(["sum"]), uuid_len=0, precision=4)
    result = styler1.concat(styler2).concat(styler3).to_string()
    expected = dedent(
        """\
     A B C
    0 0 -0.61 ab
    1 1 -1.22 cd
    sum 1 -1.830 abcd
    sum 1 -1.8300 abcd
    """
    )
    assert result == expected
