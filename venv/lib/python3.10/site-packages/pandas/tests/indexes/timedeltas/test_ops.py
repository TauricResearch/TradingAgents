from pandas import (
    TimedeltaIndex,
    timedelta_range,
)
import pandas._testing as tm


class TestTimedeltaIndexOps:
    def test_infer_freq(self, freq_sample):
        # GH#11018
        idx = timedelta_range("1", freq=freq_sample, periods=10)
        result = TimedeltaIndex(idx.asi8, freq="infer")
        tm.assert_index_equal(idx, result)
        assert result.freq == freq_sample
