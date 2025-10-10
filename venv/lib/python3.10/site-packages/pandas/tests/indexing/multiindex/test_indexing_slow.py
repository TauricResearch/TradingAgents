import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm


@pytest.fixture
def m():
    return 5


@pytest.fixture
def n():
    return 100


@pytest.fixture
def cols():
    return ["jim", "joe", "jolie", "joline", "jolia"]


@pytest.fixture
def vals(n):
    vals = [
        np.random.default_rng(2).integers(0, 10, n),
        np.random.default_rng(2).choice(list("abcdefghij"), n),
        np.random.default_rng(2).choice(
            pd.date_range("20141009", periods=10).tolist(), n
        ),
        np.random.default_rng(2).choice(list("ZYXWVUTSRQ"), n),
        np.random.default_rng(2).standard_normal(n),
    ]
    vals = list(map(tuple, zip(*vals)))
    return vals


@pytest.fixture
def keys(n, m, vals):
    # bunch of keys for testing
    keys = [
        np.random.default_rng(2).integers(0, 11, m),
        np.random.default_rng(2).choice(list("abcdefghijk"), m),
        np.random.default_rng(2).choice(
            pd.date_range("20141009", periods=11).tolist(), m
        ),
        np.random.default_rng(2).choice(list("ZYXWVUTSRQP"), m),
    ]
    keys = list(map(tuple, zip(*keys)))
    keys += [t[:-1] for t in vals[:: n // m]]
    return keys


# covers both unique index and non-unique index
@pytest.fixture
def df(vals, cols):
    return DataFrame(vals, columns=cols)


@pytest.fixture
def a(df):
    return pd.concat([df, df])


@pytest.fixture
def b(df, cols):
    return df.drop_duplicates(subset=cols[:-1])


@pytest.mark.filterwarnings("ignore::pandas.errors.PerformanceWarning")
@pytest.mark.parametrize("lexsort_depth", list(range(5)))
@pytest.mark.parametrize("frame_fixture", ["a", "b"])
def test_multiindex_get_loc(request, lexsort_depth, keys, frame_fixture, cols):
    # GH7724, GH2646

    frame = request.getfixturevalue(frame_fixture)
    if lexsort_depth == 0:
        df = frame.copy(deep=False)
    else:
        df = frame.sort_values(by=cols[:lexsort_depth])

    mi = df.set_index(cols[:-1])
    assert not mi.index._lexsort_depth < lexsort_depth
    for key in keys:
        mask = np.ones(len(df), dtype=bool)

        # test for all partials of this key
        for i, k in enumerate(key):
            mask &= df.iloc[:, i] == k

            if not mask.any():
                assert key[: i + 1] not in mi.index
                continue

            assert key[: i + 1] in mi.index
            right = df[mask].copy(deep=False)

            if i + 1 != len(key):  # partial key
                return_value = right.drop(cols[: i + 1], axis=1, inplace=True)
                assert return_value is None
                return_value = right.set_index(cols[i + 1 : -1], inplace=True)
                assert return_value is None
                tm.assert_frame_equal(mi.loc[key[: i + 1]], right)

            else:  # full key
                return_value = right.set_index(cols[:-1], inplace=True)
                assert return_value is None
                if len(right) == 1:  # single hit
                    right = Series(
                        right["jolia"].values, name=right.index[0], index=["jolia"]
                    )
                    tm.assert_series_equal(mi.loc[key[: i + 1]], right)
                else:  # multi hit
                    tm.assert_frame_equal(mi.loc[key[: i + 1]], right)
