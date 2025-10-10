import numpy as np
import pytest

from pandas.errors import PerformanceWarning

import pandas as pd
from pandas import (
    Index,
    MultiIndex,
)
import pandas._testing as tm


def test_drop(idx):
    dropped = idx.drop([("foo", "two"), ("qux", "one")])

    index = MultiIndex.from_tuples([("foo", "two"), ("qux", "one")])
    dropped2 = idx.drop(index)

    expected = idx[[0, 2, 3, 5]]
    tm.assert_index_equal(dropped, expected)
    tm.assert_index_equal(dropped2, expected)

    dropped = idx.drop(["bar"])
    expected = idx[[0, 1, 3, 4, 5]]
    tm.assert_index_equal(dropped, expected)

    dropped = idx.drop("foo")
    expected = idx[[2, 3, 4, 5]]
    tm.assert_index_equal(dropped, expected)

    index = MultiIndex.from_tuples([("bar", "two")])
    with pytest.raises(KeyError, match=r"^\('bar', 'two'\)$"):
        idx.drop([("bar", "two")])
    with pytest.raises(KeyError, match=r"^\('bar', 'two'\)$"):
        idx.drop(index)
    with pytest.raises(KeyError, match=r"^'two'$"):
        idx.drop(["foo", "two"])

    # partially correct argument
    mixed_index = MultiIndex.from_tuples([("qux", "one"), ("bar", "two")])
    with pytest.raises(KeyError, match=r"^\('bar', 'two'\)$"):
        idx.drop(mixed_index)

    # error='ignore'
    dropped = idx.drop(index, errors="ignore")
    expected = idx[[0, 1, 2, 3, 4, 5]]
    tm.assert_index_equal(dropped, expected)

    dropped = idx.drop(mixed_index, errors="ignore")
    expected = idx[[0, 1, 2, 3, 5]]
    tm.assert_index_equal(dropped, expected)

    dropped = idx.drop(["foo", "two"], errors="ignore")
    expected = idx[[2, 3, 4, 5]]
    tm.assert_index_equal(dropped, expected)

    # mixed partial / full drop
    dropped = idx.drop(["foo", ("qux", "one")])
    expected = idx[[2, 3, 5]]
    tm.assert_index_equal(dropped, expected)

    # mixed partial / full drop / error='ignore'
    mixed_index = ["foo", ("qux", "one"), "two"]
    with pytest.raises(KeyError, match=r"^'two'$"):
        idx.drop(mixed_index)
    dropped = idx.drop(mixed_index, errors="ignore")
    expected = idx[[2, 3, 5]]
    tm.assert_index_equal(dropped, expected)


def test_droplevel_with_names(idx):
    index = idx[idx.get_loc("foo")]
    dropped = index.droplevel(0)
    assert dropped.name == "second"

    index = MultiIndex(
        levels=[Index(range(4)), Index(range(4)), Index(range(4))],
        codes=[
            np.array([0, 0, 1, 2, 2, 2, 3, 3]),
            np.array([0, 1, 0, 0, 0, 1, 0, 1]),
            np.array([1, 0, 1, 1, 0, 0, 1, 0]),
        ],
        names=["one", "two", "three"],
    )
    dropped = index.droplevel(0)
    assert dropped.names == ("two", "three")

    dropped = index.droplevel("two")
    expected = index.droplevel(1)
    assert dropped.equals(expected)


def test_droplevel_list():
    index = MultiIndex(
        levels=[Index(range(4)), Index(range(4)), Index(range(4))],
        codes=[
            np.array([0, 0, 1, 2, 2, 2, 3, 3]),
            np.array([0, 1, 0, 0, 0, 1, 0, 1]),
            np.array([1, 0, 1, 1, 0, 0, 1, 0]),
        ],
        names=["one", "two", "three"],
    )

    dropped = index[:2].droplevel(["three", "one"])
    expected = index[:2].droplevel(2).droplevel(0)
    assert dropped.equals(expected)

    dropped = index[:2].droplevel([])
    expected = index[:2]
    assert dropped.equals(expected)

    msg = (
        "Cannot remove 3 levels from an index with 3 levels: "
        "at least one level must be left"
    )
    with pytest.raises(ValueError, match=msg):
        index[:2].droplevel(["one", "two", "three"])

    with pytest.raises(KeyError, match="'Level four not found'"):
        index[:2].droplevel(["one", "four"])


def test_drop_not_lexsorted():
    # GH 12078

    # define the lexsorted version of the multi-index
    tuples = [("a", ""), ("b1", "c1"), ("b2", "c2")]
    lexsorted_mi = MultiIndex.from_tuples(tuples, names=["b", "c"])
    assert lexsorted_mi._is_lexsorted()

    # and the not-lexsorted version
    df = pd.DataFrame(
        columns=["a", "b", "c", "d"], data=[[1, "b1", "c1", 3], [1, "b2", "c2", 4]]
    )
    df = df.pivot_table(index="a", columns=["b", "c"], values="d")
    df = df.reset_index()
    not_lexsorted_mi = df.columns
    assert not not_lexsorted_mi._is_lexsorted()

    # compare the results
    tm.assert_index_equal(lexsorted_mi, not_lexsorted_mi)
    with tm.assert_produces_warning(PerformanceWarning):
        tm.assert_index_equal(lexsorted_mi.drop("a"), not_lexsorted_mi.drop("a"))


def test_drop_with_nan_in_index(nulls_fixture):
    # GH#18853
    mi = MultiIndex.from_tuples([("blah", nulls_fixture)], names=["name", "date"])
    msg = r"labels \[Timestamp\('2001-01-01 00:00:00'\)\] not found in level"
    with pytest.raises(KeyError, match=msg):
        mi.drop(pd.Timestamp("2001"), level="date")


@pytest.mark.filterwarnings("ignore::pandas.errors.PerformanceWarning")
def test_drop_with_non_monotonic_duplicates():
    # GH#33494
    mi = MultiIndex.from_tuples([(1, 2), (2, 3), (1, 2)])
    result = mi.drop((1, 2))
    expected = MultiIndex.from_tuples([(2, 3)])
    tm.assert_index_equal(result, expected)


def test_single_level_drop_partially_missing_elements():
    # GH 37820

    mi = MultiIndex.from_tuples([(1, 2), (2, 2), (3, 2)])
    msg = r"labels \[4\] not found in level"
    with pytest.raises(KeyError, match=msg):
        mi.drop(4, level=0)
    with pytest.raises(KeyError, match=msg):
        mi.drop([1, 4], level=0)
    msg = r"labels \[nan\] not found in level"
    with pytest.raises(KeyError, match=msg):
        mi.drop([np.nan], level=0)
    with pytest.raises(KeyError, match=msg):
        mi.drop([np.nan, 1, 2, 3], level=0)

    mi = MultiIndex.from_tuples([(np.nan, 1), (1, 2)])
    msg = r"labels \['a'\] not found in level"
    with pytest.raises(KeyError, match=msg):
        mi.drop([np.nan, 1, "a"], level=0)


def test_droplevel_multiindex_one_level():
    # GH#37208
    index = MultiIndex.from_tuples([(2,)], names=("b",))
    result = index.droplevel([])
    expected = Index([2], name="b")
    tm.assert_index_equal(result, expected)
