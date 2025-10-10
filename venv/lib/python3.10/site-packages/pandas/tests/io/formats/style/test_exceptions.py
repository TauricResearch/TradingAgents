import pytest

jinja2 = pytest.importorskip("jinja2")

from pandas import (
    DataFrame,
    MultiIndex,
)

from pandas.io.formats.style import Styler


@pytest.fixture
def df():
    return DataFrame(
        data=[[0, -0.609], [1, -1.228]],
        columns=["A", "B"],
        index=["x", "y"],
    )


@pytest.fixture
def styler(df):
    return Styler(df, uuid_len=0)


def test_concat_bad_columns(styler):
    msg = "`other.data` must have same columns as `Styler.data"
    with pytest.raises(ValueError, match=msg):
        styler.concat(DataFrame([[1, 2]]).style)


def test_concat_bad_type(styler):
    msg = "`other` must be of type `Styler`"
    with pytest.raises(TypeError, match=msg):
        styler.concat(DataFrame([[1, 2]]))


def test_concat_bad_index_levels(styler, df):
    df = df.copy()
    df.index = MultiIndex.from_tuples([(0, 0), (1, 1)])
    msg = "number of index levels must be same in `other`"
    with pytest.raises(ValueError, match=msg):
        styler.concat(df.style)
