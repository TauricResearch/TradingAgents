import numpy as np
import pytest

from pandas import (
    TimedeltaIndex,
    Timestamp,
)
import pandas._testing as tm


class TestSearchSorted:
    def test_searchsorted_different_argument_classes(self, listlike_box):
        idx = TimedeltaIndex(["1 day", "2 days", "3 days"])
        result = idx.searchsorted(listlike_box(idx))
        expected = np.arange(len(idx), dtype=result.dtype)
        tm.assert_numpy_array_equal(result, expected)

        result = idx._data.searchsorted(listlike_box(idx))
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize(
        "arg", [[1, 2], ["a", "b"], [Timestamp("2020-01-01", tz="Europe/London")] * 2]
    )
    def test_searchsorted_invalid_argument_dtype(self, arg):
        idx = TimedeltaIndex(["1 day", "2 days", "3 days"])
        msg = "value should be a 'Timedelta', 'NaT', or array of those. Got"
        with pytest.raises(TypeError, match=msg):
            idx.searchsorted(arg)
