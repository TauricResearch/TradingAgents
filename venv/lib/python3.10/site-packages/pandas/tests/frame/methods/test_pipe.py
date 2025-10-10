import pytest

from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm


class TestPipe:
    def test_pipe(self, frame_or_series):
        obj = DataFrame({"A": [1, 2, 3]})
        expected = DataFrame({"A": [1, 4, 9]})
        if frame_or_series is Series:
            obj = obj["A"]
            expected = expected["A"]

        f = lambda x, y: x**y
        result = obj.pipe(f, 2)
        tm.assert_equal(result, expected)

    def test_pipe_tuple(self, frame_or_series):
        obj = DataFrame({"A": [1, 2, 3]})
        obj = tm.get_obj(obj, frame_or_series)

        f = lambda x, y: y
        result = obj.pipe((f, "y"), 0)
        tm.assert_equal(result, obj)

    def test_pipe_tuple_error(self, frame_or_series):
        obj = DataFrame({"A": [1, 2, 3]})
        obj = tm.get_obj(obj, frame_or_series)

        f = lambda x, y: y

        msg = "y is both the pipe target and a keyword argument"

        with pytest.raises(ValueError, match=msg):
            obj.pipe((f, "y"), x=1, y=0)
