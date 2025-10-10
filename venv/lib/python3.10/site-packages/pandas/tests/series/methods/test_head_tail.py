import pandas._testing as tm


def test_head_tail(string_series):
    tm.assert_series_equal(string_series.head(), string_series[:5])
    tm.assert_series_equal(string_series.head(0), string_series[0:0])
    tm.assert_series_equal(string_series.tail(), string_series[-5:])
    tm.assert_series_equal(string_series.tail(0), string_series[0:0])
