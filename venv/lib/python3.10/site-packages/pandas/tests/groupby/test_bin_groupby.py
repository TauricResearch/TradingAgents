import numpy as np
import pytest

from pandas._libs import lib
import pandas.util._test_decorators as td

import pandas as pd
import pandas._testing as tm


def assert_block_lengths(x):
    assert len(x) == len(x._mgr.blocks[0].mgr_locs)
    return 0


def cumsum_max(x):
    x.cumsum().max()
    return 0


@pytest.mark.parametrize(
    "func",
    [
        cumsum_max,
        pytest.param(assert_block_lengths, marks=td.skip_array_manager_invalid_test),
    ],
)
def test_mgr_locs_updated(func):
    # https://github.com/pandas-dev/pandas/issues/31802
    # Some operations may require creating new blocks, which requires
    # valid mgr_locs
    df = pd.DataFrame({"A": ["a", "a", "a"], "B": ["a", "b", "b"], "C": [1, 1, 1]})
    result = df.groupby(["A", "B"]).agg(func)
    expected = pd.DataFrame(
        {"C": [0, 0]},
        index=pd.MultiIndex.from_product([["a"], ["a", "b"]], names=["A", "B"]),
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "binner,closed,expected",
    [
        (
            np.array([0, 3, 6, 9], dtype=np.int64),
            "left",
            np.array([2, 5, 6], dtype=np.int64),
        ),
        (
            np.array([0, 3, 6, 9], dtype=np.int64),
            "right",
            np.array([3, 6, 6], dtype=np.int64),
        ),
        (np.array([0, 3, 6], dtype=np.int64), "left", np.array([2, 5], dtype=np.int64)),
        (
            np.array([0, 3, 6], dtype=np.int64),
            "right",
            np.array([3, 6], dtype=np.int64),
        ),
    ],
)
def test_generate_bins(binner, closed, expected):
    values = np.array([1, 2, 3, 4, 5, 6], dtype=np.int64)
    result = lib.generate_bins_dt64(values, binner, closed=closed)
    tm.assert_numpy_array_equal(result, expected)
