import numpy as np
import pytest

from pandas import DataFrame
import pandas._testing as tm


class TestDataFrameReindexLike:
    def test_reindex_like(self, float_frame):
        other = float_frame.reindex(index=float_frame.index[:10], columns=["C", "B"])

        tm.assert_frame_equal(other, float_frame.reindex_like(other))

    @pytest.mark.parametrize(
        "method,expected_values",
        [
            ("nearest", [0, 1, 1, 2]),
            ("pad", [np.nan, 0, 1, 1]),
            ("backfill", [0, 1, 2, 2]),
        ],
    )
    def test_reindex_like_methods(self, method, expected_values):
        df = DataFrame({"x": list(range(5))})

        result = df.reindex_like(df, method=method, tolerance=0)
        tm.assert_frame_equal(df, result)
        result = df.reindex_like(df, method=method, tolerance=[0, 0, 0, 0])
        tm.assert_frame_equal(df, result)

    def test_reindex_like_subclass(self):
        # https://github.com/pandas-dev/pandas/issues/31925
        class MyDataFrame(DataFrame):
            pass

        expected = DataFrame()
        df = MyDataFrame()
        result = df.reindex_like(expected)

        tm.assert_frame_equal(result, expected)
