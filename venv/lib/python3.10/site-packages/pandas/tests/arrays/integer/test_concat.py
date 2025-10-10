import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm


@pytest.mark.parametrize(
    "to_concat_dtypes, result_dtype",
    [
        (["Int64", "Int64"], "Int64"),
        (["UInt64", "UInt64"], "UInt64"),
        (["Int8", "Int8"], "Int8"),
        (["Int8", "Int16"], "Int16"),
        (["UInt8", "Int8"], "Int16"),
        (["Int32", "UInt32"], "Int64"),
        (["Int64", "UInt64"], "Float64"),
        (["Int64", "boolean"], "object"),
        (["UInt8", "boolean"], "object"),
    ],
)
def test_concat_series(to_concat_dtypes, result_dtype):
    # we expect the same dtypes as we would get with non-masked inputs,
    #  just masked where available.

    result = pd.concat([pd.Series([0, 1, pd.NA], dtype=t) for t in to_concat_dtypes])
    expected = pd.concat([pd.Series([0, 1, pd.NA], dtype=object)] * 2).astype(
        result_dtype
    )
    tm.assert_series_equal(result, expected)

    # order doesn't matter for result
    result = pd.concat(
        [pd.Series([0, 1, pd.NA], dtype=t) for t in to_concat_dtypes[::-1]]
    )
    expected = pd.concat([pd.Series([0, 1, pd.NA], dtype=object)] * 2).astype(
        result_dtype
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "to_concat_dtypes, result_dtype",
    [
        (["Int64", "int64"], "Int64"),
        (["UInt64", "uint64"], "UInt64"),
        (["Int8", "int8"], "Int8"),
        (["Int8", "int16"], "Int16"),
        (["UInt8", "int8"], "Int16"),
        (["Int32", "uint32"], "Int64"),
        (["Int64", "uint64"], "Float64"),
        (["Int64", "bool"], "object"),
        (["UInt8", "bool"], "object"),
    ],
)
def test_concat_series_with_numpy(to_concat_dtypes, result_dtype):
    # we expect the same dtypes as we would get with non-masked inputs,
    #  just masked where available.

    s1 = pd.Series([0, 1, pd.NA], dtype=to_concat_dtypes[0])
    s2 = pd.Series(np.array([0, 1], dtype=to_concat_dtypes[1]))
    result = pd.concat([s1, s2], ignore_index=True)
    expected = pd.Series([0, 1, pd.NA, 0, 1], dtype=object).astype(result_dtype)
    tm.assert_series_equal(result, expected)

    # order doesn't matter for result
    result = pd.concat([s2, s1], ignore_index=True)
    expected = pd.Series([0, 1, 0, 1, pd.NA], dtype=object).astype(result_dtype)
    tm.assert_series_equal(result, expected)
