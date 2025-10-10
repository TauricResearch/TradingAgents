import numpy as np

import pandas as pd
from pandas import (
    Categorical,
    Series,
)
import pandas._testing as tm


class TestSeriesCount:
    def test_count(self, datetime_series):
        assert datetime_series.count() == len(datetime_series)

        datetime_series[::2] = np.nan

        assert datetime_series.count() == np.isfinite(datetime_series).sum()

    def test_count_inf_as_na(self):
        # GH#29478
        ser = Series([pd.Timestamp("1990/1/1")])
        msg = "use_inf_as_na option is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            with pd.option_context("use_inf_as_na", True):
                assert ser.count() == 1

    def test_count_categorical(self):
        ser = Series(
            Categorical(
                [np.nan, 1, 2, np.nan], categories=[5, 4, 3, 2, 1], ordered=True
            )
        )
        result = ser.count()
        assert result == 2
