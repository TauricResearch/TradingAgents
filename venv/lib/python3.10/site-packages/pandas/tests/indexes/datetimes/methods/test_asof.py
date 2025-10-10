from datetime import timedelta

from pandas import (
    Index,
    Timestamp,
    date_range,
    isna,
)


class TestAsOf:
    def test_asof_partial(self):
        index = date_range("2010-01-01", periods=2, freq="ME")
        expected = Timestamp("2010-02-28")
        result = index.asof("2010-02")
        assert result == expected
        assert not isinstance(result, Index)

    def test_asof(self):
        index = date_range("2020-01-01", periods=10)

        dt = index[0]
        assert index.asof(dt) == dt
        assert isna(index.asof(dt - timedelta(1)))

        dt = index[-1]
        assert index.asof(dt + timedelta(1)) == dt

        dt = index[0].to_pydatetime()
        assert isinstance(index.asof(dt), Timestamp)
