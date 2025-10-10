import pytest

from pandas import (
    NaT,
    date_range,
    to_datetime,
)
import pandas._testing as tm


class TestPickle:
    def test_pickle(self):
        # GH#4606
        idx = to_datetime(["2013-01-01", NaT, "2014-01-06"])
        idx_p = tm.round_trip_pickle(idx)
        assert idx_p[0] == idx[0]
        assert idx_p[1] is NaT
        assert idx_p[2] == idx[2]

    def test_pickle_dont_infer_freq(self):
        # GH#11002
        # don't infer freq
        idx = date_range("1750-1-1", "2050-1-1", freq="7D")
        idx_p = tm.round_trip_pickle(idx)
        tm.assert_index_equal(idx, idx_p)

    def test_pickle_after_set_freq(self):
        dti = date_range("20130101", periods=3, tz="US/Eastern", name="foo")
        dti = dti._with_freq(None)

        res = tm.round_trip_pickle(dti)
        tm.assert_index_equal(res, dti)

    def test_roundtrip_pickle_with_tz(self):
        # GH#8367
        # round-trip of timezone
        index = date_range("20130101", periods=3, tz="US/Eastern", name="foo")
        unpickled = tm.round_trip_pickle(index)
        tm.assert_index_equal(index, unpickled)

    @pytest.mark.parametrize("freq", ["B", "C"])
    def test_pickle_unpickle(self, freq):
        rng = date_range("2009-01-01", "2010-01-01", freq=freq)
        unpickled = tm.round_trip_pickle(rng)
        assert unpickled.freq == freq
