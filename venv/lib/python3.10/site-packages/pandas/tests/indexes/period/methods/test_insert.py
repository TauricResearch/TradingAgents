import numpy as np
import pytest

from pandas import (
    NaT,
    PeriodIndex,
    period_range,
)
import pandas._testing as tm


class TestInsert:
    @pytest.mark.parametrize("na", [np.nan, NaT, None])
    def test_insert(self, na):
        # GH#18295 (test missing)
        expected = PeriodIndex(["2017Q1", NaT, "2017Q2", "2017Q3", "2017Q4"], freq="Q")
        result = period_range("2017Q1", periods=4, freq="Q").insert(1, na)
        tm.assert_index_equal(result, expected)
