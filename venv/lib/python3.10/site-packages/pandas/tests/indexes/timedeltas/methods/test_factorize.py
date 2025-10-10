import numpy as np

from pandas import (
    TimedeltaIndex,
    factorize,
    timedelta_range,
)
import pandas._testing as tm


class TestTimedeltaIndexFactorize:
    def test_factorize(self):
        idx1 = TimedeltaIndex(["1 day", "1 day", "2 day", "2 day", "3 day", "3 day"])

        exp_arr = np.array([0, 0, 1, 1, 2, 2], dtype=np.intp)
        exp_idx = TimedeltaIndex(["1 day", "2 day", "3 day"])

        arr, idx = idx1.factorize()
        tm.assert_numpy_array_equal(arr, exp_arr)
        tm.assert_index_equal(idx, exp_idx)
        assert idx.freq == exp_idx.freq

        arr, idx = idx1.factorize(sort=True)
        tm.assert_numpy_array_equal(arr, exp_arr)
        tm.assert_index_equal(idx, exp_idx)
        assert idx.freq == exp_idx.freq

    def test_factorize_preserves_freq(self):
        # GH#38120 freq should be preserved
        idx3 = timedelta_range("1 day", periods=4, freq="s")
        exp_arr = np.array([0, 1, 2, 3], dtype=np.intp)
        arr, idx = idx3.factorize()
        tm.assert_numpy_array_equal(arr, exp_arr)
        tm.assert_index_equal(idx, idx3)
        assert idx.freq == idx3.freq

        arr, idx = factorize(idx3)
        tm.assert_numpy_array_equal(arr, exp_arr)
        tm.assert_index_equal(idx, idx3)
        assert idx.freq == idx3.freq
