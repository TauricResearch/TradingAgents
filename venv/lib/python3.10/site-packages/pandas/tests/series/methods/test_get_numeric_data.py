from pandas import (
    Index,
    Series,
    date_range,
)
import pandas._testing as tm


class TestGetNumericData:
    def test_get_numeric_data_preserve_dtype(
        self, using_copy_on_write, warn_copy_on_write
    ):
        # get the numeric data
        obj = Series([1, 2, 3])
        result = obj._get_numeric_data()
        tm.assert_series_equal(result, obj)

        # returned object is a shallow copy
        with tm.assert_cow_warning(warn_copy_on_write):
            result.iloc[0] = 0
        if using_copy_on_write:
            assert obj.iloc[0] == 1
        else:
            assert obj.iloc[0] == 0

        obj = Series([1, "2", 3.0])
        result = obj._get_numeric_data()
        expected = Series([], dtype=object, index=Index([], dtype=object))
        tm.assert_series_equal(result, expected)

        obj = Series([True, False, True])
        result = obj._get_numeric_data()
        tm.assert_series_equal(result, obj)

        obj = Series(date_range("20130101", periods=3))
        result = obj._get_numeric_data()
        expected = Series([], dtype="M8[ns]", index=Index([], dtype=object))
        tm.assert_series_equal(result, expected)
