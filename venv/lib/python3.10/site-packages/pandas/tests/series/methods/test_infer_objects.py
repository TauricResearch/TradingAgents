import numpy as np

from pandas import (
    Series,
    interval_range,
)
import pandas._testing as tm


class TestInferObjects:
    def test_copy(self, index_or_series):
        # GH#50096
        # case where we don't need to do inference because it is already non-object
        obj = index_or_series(np.array([1, 2, 3], dtype="int64"))

        result = obj.infer_objects(copy=False)
        assert tm.shares_memory(result, obj)

        # case where we try to do inference but can't do better than object
        obj2 = index_or_series(np.array(["foo", 2], dtype=object))
        result2 = obj2.infer_objects(copy=False)
        assert tm.shares_memory(result2, obj2)

    def test_infer_objects_series(self, index_or_series):
        # GH#11221
        actual = index_or_series(np.array([1, 2, 3], dtype="O")).infer_objects()
        expected = index_or_series([1, 2, 3])
        tm.assert_equal(actual, expected)

        actual = index_or_series(np.array([1, 2, 3, None], dtype="O")).infer_objects()
        expected = index_or_series([1.0, 2.0, 3.0, np.nan])
        tm.assert_equal(actual, expected)

        # only soft conversions, unconvertible pass thru unchanged

        obj = index_or_series(np.array([1, 2, 3, None, "a"], dtype="O"))
        actual = obj.infer_objects()
        expected = index_or_series([1, 2, 3, None, "a"], dtype=object)

        assert actual.dtype == "object"
        tm.assert_equal(actual, expected)

    def test_infer_objects_interval(self, index_or_series):
        # GH#50090
        ii = interval_range(1, 10)
        obj = index_or_series(ii)

        result = obj.astype(object).infer_objects()
        tm.assert_equal(result, obj)

    def test_infer_objects_bytes(self):
        # GH#49650
        ser = Series([b"a"], dtype="bytes")
        expected = ser.copy()
        result = ser.infer_objects()
        tm.assert_series_equal(result, expected)
