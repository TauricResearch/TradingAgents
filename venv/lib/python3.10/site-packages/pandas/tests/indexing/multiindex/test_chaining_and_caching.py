import numpy as np
import pytest

from pandas._libs import index as libindex
from pandas.errors import SettingWithCopyError
import pandas.util._test_decorators as td

from pandas import (
    DataFrame,
    MultiIndex,
    Series,
)
import pandas._testing as tm


def test_detect_chained_assignment(using_copy_on_write, warn_copy_on_write):
    # Inplace ops, originally from:
    # https://stackoverflow.com/questions/20508968/series-fillna-in-a-multiindex-dataframe-does-not-fill-is-this-a-bug
    a = [12, 23]
    b = [123, None]
    c = [1234, 2345]
    d = [12345, 23456]
    tuples = [("eyes", "left"), ("eyes", "right"), ("ears", "left"), ("ears", "right")]
    events = {
        ("eyes", "left"): a,
        ("eyes", "right"): b,
        ("ears", "left"): c,
        ("ears", "right"): d,
    }
    multiind = MultiIndex.from_tuples(tuples, names=["part", "side"])
    zed = DataFrame(events, index=["a", "b"], columns=multiind)

    if using_copy_on_write:
        with tm.raises_chained_assignment_error():
            zed["eyes"]["right"].fillna(value=555, inplace=True)
    elif warn_copy_on_write:
        with tm.assert_produces_warning(None):
            zed["eyes"]["right"].fillna(value=555, inplace=True)
    else:
        msg = "A value is trying to be set on a copy of a slice from a DataFrame"
        with pytest.raises(SettingWithCopyError, match=msg):
            with tm.assert_produces_warning(None):
                zed["eyes"]["right"].fillna(value=555, inplace=True)


@td.skip_array_manager_invalid_test  # with ArrayManager df.loc[0] is not a view
def test_cache_updating(using_copy_on_write, warn_copy_on_write):
    # 5216
    # make sure that we don't try to set a dead cache
    a = np.random.default_rng(2).random((10, 3))
    df = DataFrame(a, columns=["x", "y", "z"])
    df_original = df.copy()
    tuples = [(i, j) for i in range(5) for j in range(2)]
    index = MultiIndex.from_tuples(tuples)
    df.index = index

    # setting via chained assignment
    # but actually works, since everything is a view

    with tm.raises_chained_assignment_error():
        df.loc[0]["z"].iloc[0] = 1.0

    if using_copy_on_write:
        assert df.loc[(0, 0), "z"] == df_original.loc[0, "z"]
    else:
        result = df.loc[(0, 0), "z"]
        assert result == 1

    # correct setting
    df.loc[(0, 0), "z"] = 2
    result = df.loc[(0, 0), "z"]
    assert result == 2


def test_indexer_caching(monkeypatch):
    # GH5727
    # make sure that indexers are in the _internal_names_set
    size_cutoff = 20
    with monkeypatch.context():
        monkeypatch.setattr(libindex, "_SIZE_CUTOFF", size_cutoff)
        index = MultiIndex.from_arrays([np.arange(size_cutoff), np.arange(size_cutoff)])
        s = Series(np.zeros(size_cutoff), index=index)

        # setitem
        s[s == 0] = 1
    expected = Series(np.ones(size_cutoff), index=index)
    tm.assert_series_equal(s, expected)
