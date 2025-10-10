import numpy as np

from pandas import (
    DataFrame,
    Index,
    Timedelta,
    timedelta_range,
)
import pandas._testing as tm


class TestJoin:
    def test_append_join_nondatetimeindex(self):
        rng = timedelta_range("1 days", periods=10)
        idx = Index(["a", "b", "c", "d"])

        result = rng.append(idx)
        assert isinstance(result[0], Timedelta)

        # it works
        rng.join(idx, how="outer")

    def test_join_self(self, join_type):
        index = timedelta_range("1 day", periods=10)
        joined = index.join(index, how=join_type)
        tm.assert_index_equal(index, joined)

    def test_does_not_convert_mixed_integer(self):
        df = DataFrame(np.ones((5, 5)), columns=timedelta_range("1 day", periods=5))

        cols = df.columns.join(df.index, how="outer")
        joined = cols.join(df.columns)
        assert cols.dtype == np.dtype("O")
        assert cols.dtype == joined.dtype
        tm.assert_index_equal(cols, joined)

    def test_join_preserves_freq(self):
        # GH#32157
        tdi = timedelta_range("1 day", periods=10)
        result = tdi[:5].join(tdi[5:], how="outer")
        assert result.freq == tdi.freq
        tm.assert_index_equal(result, tdi)

        result = tdi[:5].join(tdi[6:], how="outer")
        assert result.freq is None
        expected = tdi.delete(5)
        tm.assert_index_equal(result, expected)
