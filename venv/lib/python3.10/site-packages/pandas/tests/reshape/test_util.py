import numpy as np
import pytest

from pandas import (
    Index,
    date_range,
)
import pandas._testing as tm
from pandas.core.reshape.util import cartesian_product


class TestCartesianProduct:
    def test_simple(self):
        x, y = list("ABC"), [1, 22]
        result1, result2 = cartesian_product([x, y])
        expected1 = np.array(["A", "A", "B", "B", "C", "C"])
        expected2 = np.array([1, 22, 1, 22, 1, 22])
        tm.assert_numpy_array_equal(result1, expected1)
        tm.assert_numpy_array_equal(result2, expected2)

    def test_datetimeindex(self):
        # regression test for GitHub issue #6439
        # make sure that the ordering on datetimeindex is consistent
        x = date_range("2000-01-01", periods=2)
        result1, result2 = (Index(y).day for y in cartesian_product([x, x]))
        expected1 = Index([1, 1, 2, 2], dtype=np.int32)
        expected2 = Index([1, 2, 1, 2], dtype=np.int32)
        tm.assert_index_equal(result1, expected1)
        tm.assert_index_equal(result2, expected2)

    def test_tzaware_retained(self):
        x = date_range("2000-01-01", periods=2, tz="US/Pacific")
        y = np.array([3, 4])
        result1, result2 = cartesian_product([x, y])

        expected = x.repeat(2)
        tm.assert_index_equal(result1, expected)

    def test_tzaware_retained_categorical(self):
        x = date_range("2000-01-01", periods=2, tz="US/Pacific").astype("category")
        y = np.array([3, 4])
        result1, result2 = cartesian_product([x, y])

        expected = x.repeat(2)
        tm.assert_index_equal(result1, expected)

    @pytest.mark.parametrize("x, y", [[[], []], [[0, 1], []], [[], ["a", "b", "c"]]])
    def test_empty(self, x, y):
        # product of empty factors
        expected1 = np.array([], dtype=np.asarray(x).dtype)
        expected2 = np.array([], dtype=np.asarray(y).dtype)
        result1, result2 = cartesian_product([x, y])
        tm.assert_numpy_array_equal(result1, expected1)
        tm.assert_numpy_array_equal(result2, expected2)

    def test_empty_input(self):
        # empty product (empty input):
        result = cartesian_product([])
        expected = []
        assert result == expected

    @pytest.mark.parametrize(
        "X", [1, [1], [1, 2], [[1], 2], "a", ["a"], ["a", "b"], [["a"], "b"]]
    )
    def test_invalid_input(self, X):
        msg = "Input must be a list-like of list-likes"

        with pytest.raises(TypeError, match=msg):
            cartesian_product(X=X)

    def test_exceed_product_space(self):
        # GH31355: raise useful error when produce space is too large
        msg = "Product space too large to allocate arrays!"

        with pytest.raises(ValueError, match=msg):
            dims = [np.arange(0, 22, dtype=np.int16) for i in range(12)] + [
                (np.arange(15128, dtype=np.int16)),
            ]
            cartesian_product(X=dims)
