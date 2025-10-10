import pytest

from pandas import (
    Categorical,
    CategoricalDtype,
    Index,
    IntervalIndex,
)
import pandas._testing as tm


class TestAstype:
    @pytest.mark.parametrize("ordered", [True, False])
    def test_astype_categorical_retains_ordered(self, ordered):
        index = IntervalIndex.from_breaks(range(5))
        arr = index._data

        dtype = CategoricalDtype(None, ordered=ordered)

        expected = Categorical(list(arr), ordered=ordered)
        result = arr.astype(dtype)
        assert result.ordered is ordered
        tm.assert_categorical_equal(result, expected)

        # test IntervalIndex.astype while we're at it.
        result = index.astype(dtype)
        expected = Index(expected)
        tm.assert_index_equal(result, expected)
