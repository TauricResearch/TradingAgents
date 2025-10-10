import numpy as np
import pytest

import pandas as pd
from pandas import (
    DatetimeIndex,
    Index,
)
import pandas._testing as tm

dtlike_dtypes = [
    np.dtype("timedelta64[ns]"),
    np.dtype("datetime64[ns]"),
    pd.DatetimeTZDtype("ns", "Asia/Tokyo"),
    pd.PeriodDtype("ns"),
]


@pytest.mark.parametrize("ldtype", dtlike_dtypes)
@pytest.mark.parametrize("rdtype", dtlike_dtypes)
def test_get_indexer_non_unique_wrong_dtype(ldtype, rdtype):
    vals = np.tile(3600 * 10**9 * np.arange(3, dtype=np.int64), 2)

    def construct(dtype):
        if dtype is dtlike_dtypes[-1]:
            # PeriodArray will try to cast ints to strings
            return DatetimeIndex(vals).astype(dtype)
        return Index(vals, dtype=dtype)

    left = construct(ldtype)
    right = construct(rdtype)

    result = left.get_indexer_non_unique(right)

    if ldtype is rdtype:
        ex1 = np.array([0, 3, 1, 4, 2, 5] * 2, dtype=np.intp)
        ex2 = np.array([], dtype=np.intp)
        tm.assert_numpy_array_equal(result[0], ex1)
        tm.assert_numpy_array_equal(result[1], ex2)

    else:
        no_matches = np.array([-1] * 6, dtype=np.intp)
        missing = np.arange(6, dtype=np.intp)
        tm.assert_numpy_array_equal(result[0], no_matches)
        tm.assert_numpy_array_equal(result[1], missing)
