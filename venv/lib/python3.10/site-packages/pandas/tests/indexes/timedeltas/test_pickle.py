from pandas import timedelta_range
import pandas._testing as tm


class TestPickle:
    def test_pickle_after_set_freq(self):
        tdi = timedelta_range("1 day", periods=4, freq="s")
        tdi = tdi._with_freq(None)

        res = tm.round_trip_pickle(tdi)
        tm.assert_index_equal(res, tdi)
