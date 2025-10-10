# Arithmetic tests for TimedeltaIndex are generally about the result's `freq` attribute.
# Other cases can be shared in tests.arithmetic.test_timedelta64
import numpy as np

from pandas import (
    NaT,
    Timedelta,
    timedelta_range,
)
import pandas._testing as tm


class TestTimedeltaIndexArithmetic:
    def test_arithmetic_zero_freq(self):
        # GH#51575 don't get a .freq with freq.n = 0
        tdi = timedelta_range(0, periods=100, freq="ns")
        result = tdi / 2
        assert result.freq is None
        expected = tdi[:50].repeat(2)
        tm.assert_index_equal(result, expected)

        result2 = tdi // 2
        assert result2.freq is None
        expected2 = expected
        tm.assert_index_equal(result2, expected2)

        result3 = tdi * 0
        assert result3.freq is None
        expected3 = tdi[:1].repeat(100)
        tm.assert_index_equal(result3, expected3)

    def test_tdi_division(self, index_or_series):
        # doc example

        scalar = Timedelta(days=31)
        td = index_or_series(
            [scalar, scalar, scalar + Timedelta(minutes=5, seconds=3), NaT],
            dtype="m8[ns]",
        )

        result = td / np.timedelta64(1, "D")
        expected = index_or_series(
            [31, 31, (31 * 86400 + 5 * 60 + 3) / 86400.0, np.nan]
        )
        tm.assert_equal(result, expected)

        result = td / np.timedelta64(1, "s")
        expected = index_or_series(
            [31 * 86400, 31 * 86400, 31 * 86400 + 5 * 60 + 3, np.nan]
        )
        tm.assert_equal(result, expected)
