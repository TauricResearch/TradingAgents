from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm


class TestDataFrameCount:
    def test_count(self):
        # corner case
        frame = DataFrame()
        ct1 = frame.count(1)
        assert isinstance(ct1, Series)

        ct2 = frame.count(0)
        assert isinstance(ct2, Series)

        # GH#423
        df = DataFrame(index=range(10))
        result = df.count(1)
        expected = Series(0, index=df.index)
        tm.assert_series_equal(result, expected)

        df = DataFrame(columns=range(10))
        result = df.count(0)
        expected = Series(0, index=df.columns)
        tm.assert_series_equal(result, expected)

        df = DataFrame()
        result = df.count()
        expected = Series(dtype="int64")
        tm.assert_series_equal(result, expected)

    def test_count_objects(self, float_string_frame):
        dm = DataFrame(float_string_frame._series)
        df = DataFrame(float_string_frame._series)

        tm.assert_series_equal(dm.count(), df.count())
        tm.assert_series_equal(dm.count(1), df.count(1))
