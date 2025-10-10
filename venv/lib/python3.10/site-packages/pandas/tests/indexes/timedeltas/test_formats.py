import pytest

import pandas as pd
from pandas import (
    Series,
    TimedeltaIndex,
)


class TestTimedeltaIndexRendering:
    def test_repr_round_days_non_nano(self):
        # GH#55405
        # we should get "1 days", not "1 days 00:00:00" with non-nano
        tdi = TimedeltaIndex(["1 days"], freq="D").as_unit("s")
        result = repr(tdi)
        expected = "TimedeltaIndex(['1 days'], dtype='timedelta64[s]', freq='D')"
        assert result == expected

        result2 = repr(Series(tdi))
        expected2 = "0   1 days\ndtype: timedelta64[s]"
        assert result2 == expected2

    @pytest.mark.parametrize("method", ["__repr__", "__str__"])
    def test_representation(self, method):
        idx1 = TimedeltaIndex([], freq="D")
        idx2 = TimedeltaIndex(["1 days"], freq="D")
        idx3 = TimedeltaIndex(["1 days", "2 days"], freq="D")
        idx4 = TimedeltaIndex(["1 days", "2 days", "3 days"], freq="D")
        idx5 = TimedeltaIndex(["1 days 00:00:01", "2 days", "3 days"])

        exp1 = "TimedeltaIndex([], dtype='timedelta64[ns]', freq='D')"

        exp2 = "TimedeltaIndex(['1 days'], dtype='timedelta64[ns]', freq='D')"

        exp3 = "TimedeltaIndex(['1 days', '2 days'], dtype='timedelta64[ns]', freq='D')"

        exp4 = (
            "TimedeltaIndex(['1 days', '2 days', '3 days'], "
            "dtype='timedelta64[ns]', freq='D')"
        )

        exp5 = (
            "TimedeltaIndex(['1 days 00:00:01', '2 days 00:00:00', "
            "'3 days 00:00:00'], dtype='timedelta64[ns]', freq=None)"
        )

        with pd.option_context("display.width", 300):
            for idx, expected in zip(
                [idx1, idx2, idx3, idx4, idx5], [exp1, exp2, exp3, exp4, exp5]
            ):
                result = getattr(idx, method)()
                assert result == expected

    # TODO: this is a Series.__repr__ test
    def test_representation_to_series(self):
        idx1 = TimedeltaIndex([], freq="D")
        idx2 = TimedeltaIndex(["1 days"], freq="D")
        idx3 = TimedeltaIndex(["1 days", "2 days"], freq="D")
        idx4 = TimedeltaIndex(["1 days", "2 days", "3 days"], freq="D")
        idx5 = TimedeltaIndex(["1 days 00:00:01", "2 days", "3 days"])

        exp1 = """Series([], dtype: timedelta64[ns])"""

        exp2 = "0   1 days\ndtype: timedelta64[ns]"

        exp3 = "0   1 days\n1   2 days\ndtype: timedelta64[ns]"

        exp4 = "0   1 days\n1   2 days\n2   3 days\ndtype: timedelta64[ns]"

        exp5 = (
            "0   1 days 00:00:01\n"
            "1   2 days 00:00:00\n"
            "2   3 days 00:00:00\n"
            "dtype: timedelta64[ns]"
        )

        with pd.option_context("display.width", 300):
            for idx, expected in zip(
                [idx1, idx2, idx3, idx4, idx5], [exp1, exp2, exp3, exp4, exp5]
            ):
                result = repr(Series(idx))
                assert result == expected

    def test_summary(self):
        # GH#9116
        idx1 = TimedeltaIndex([], freq="D")
        idx2 = TimedeltaIndex(["1 days"], freq="D")
        idx3 = TimedeltaIndex(["1 days", "2 days"], freq="D")
        idx4 = TimedeltaIndex(["1 days", "2 days", "3 days"], freq="D")
        idx5 = TimedeltaIndex(["1 days 00:00:01", "2 days", "3 days"])

        exp1 = "TimedeltaIndex: 0 entries\nFreq: D"

        exp2 = "TimedeltaIndex: 1 entries, 1 days to 1 days\nFreq: D"

        exp3 = "TimedeltaIndex: 2 entries, 1 days to 2 days\nFreq: D"

        exp4 = "TimedeltaIndex: 3 entries, 1 days to 3 days\nFreq: D"

        exp5 = "TimedeltaIndex: 3 entries, 1 days 00:00:01 to 3 days 00:00:00"

        for idx, expected in zip(
            [idx1, idx2, idx3, idx4, idx5], [exp1, exp2, exp3, exp4, exp5]
        ):
            result = idx._summary()
            assert result == expected
