import numpy as np
import pytest

from pandas import (
    NaT,
    PeriodIndex,
    period_range,
)
import pandas._testing as tm

from pandas.tseries import offsets


class TestPickle:
    @pytest.mark.parametrize("freq", ["D", "M", "Y"])
    def test_pickle_round_trip(self, freq):
        idx = PeriodIndex(["2016-05-16", "NaT", NaT, np.nan], freq=freq)
        result = tm.round_trip_pickle(idx)
        tm.assert_index_equal(result, idx)

    def test_pickle_freq(self):
        # GH#2891
        prng = period_range("1/1/2011", "1/1/2012", freq="M")
        new_prng = tm.round_trip_pickle(prng)
        assert new_prng.freq == offsets.MonthEnd()
        assert new_prng.freqstr == "M"
