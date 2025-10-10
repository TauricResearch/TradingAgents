import pytest

import pandas as pd


class TestResolution:
    @pytest.mark.parametrize(
        "freq,expected",
        [
            ("Y", "year"),
            ("Q", "quarter"),
            ("M", "month"),
            ("D", "day"),
            ("h", "hour"),
            ("min", "minute"),
            ("s", "second"),
            ("ms", "millisecond"),
            ("us", "microsecond"),
        ],
    )
    def test_resolution(self, freq, expected):
        idx = pd.period_range(start="2013-04-01", periods=30, freq=freq)
        assert idx.resolution == expected
