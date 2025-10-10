import pytest

import pandas as pd
import pandas._testing as tm


@pytest.mark.parametrize(
    "to_concat_dtypes, result_dtype",
    [
        (["Float64", "Float64"], "Float64"),
        (["Float32", "Float64"], "Float64"),
        (["Float32", "Float32"], "Float32"),
    ],
)
def test_concat_series(to_concat_dtypes, result_dtype):
    result = pd.concat([pd.Series([1, 2, pd.NA], dtype=t) for t in to_concat_dtypes])
    expected = pd.concat([pd.Series([1, 2, pd.NA], dtype=object)] * 2).astype(
        result_dtype
    )
    tm.assert_series_equal(result, expected)
