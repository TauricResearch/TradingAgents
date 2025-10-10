import numpy as np

from pandas import (
    DataFrame,
    Index,
    Series,
)
import pandas._testing as tm


def test_corrwith_with_1_axis():
    # GH 47723
    df = DataFrame({"a": [1, 1, 2], "b": [3, 7, 4]})
    gb = df.groupby("a")

    msg = "DataFrameGroupBy.corrwith with axis=1 is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = gb.corrwith(df, axis=1)
    index = Index(
        data=[(1, 0), (1, 1), (1, 2), (2, 2), (2, 0), (2, 1)],
        name=("a", None),
    )
    expected = Series([np.nan] * 6, index=index)
    tm.assert_series_equal(result, expected)
