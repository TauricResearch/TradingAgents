import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm


class TestCombine:
    @pytest.mark.parametrize(
        "data",
        [
            pd.date_range("2000", periods=4),
            pd.date_range("2000", periods=4, tz="US/Central"),
            pd.period_range("2000", periods=4),
            pd.timedelta_range(0, periods=4),
        ],
    )
    def test_combine_datetlike_udf(self, data):
        # GH#23079
        df = pd.DataFrame({"A": data})
        other = df.copy()
        df.iloc[1, 0] = None

        def combiner(a, b):
            return b

        result = df.combine(other, combiner)
        tm.assert_frame_equal(result, other)

    def test_combine_generic(self, float_frame):
        df1 = float_frame
        df2 = float_frame.loc[float_frame.index[:-5], ["A", "B", "C"]]

        combined = df1.combine(df2, np.add)
        combined2 = df2.combine(df1, np.add)
        assert combined["D"].isna().all()
        assert combined2["D"].isna().all()

        chunk = combined.loc[combined.index[:-5], ["A", "B", "C"]]
        chunk2 = combined2.loc[combined2.index[:-5], ["A", "B", "C"]]

        exp = (
            float_frame.loc[float_frame.index[:-5], ["A", "B", "C"]].reindex_like(chunk)
            * 2
        )
        tm.assert_frame_equal(chunk, exp)
        tm.assert_frame_equal(chunk2, exp)
