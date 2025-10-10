from pandas import (
    Index,
    NaT,
    Timedelta,
    TimedeltaIndex,
)
import pandas._testing as tm


class TestFillNA:
    def test_fillna_timedelta(self):
        # GH#11343
        idx = TimedeltaIndex(["1 day", NaT, "3 day"])

        exp = TimedeltaIndex(["1 day", "2 day", "3 day"])
        tm.assert_index_equal(idx.fillna(Timedelta("2 day")), exp)

        exp = TimedeltaIndex(["1 day", "3 hour", "3 day"])
        idx.fillna(Timedelta("3 hour"))

        exp = Index([Timedelta("1 day"), "x", Timedelta("3 day")], dtype=object)
        tm.assert_index_equal(idx.fillna("x"), exp)
