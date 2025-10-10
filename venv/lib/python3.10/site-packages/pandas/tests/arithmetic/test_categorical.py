import numpy as np

from pandas import (
    Categorical,
    Series,
)
import pandas._testing as tm


class TestCategoricalComparisons:
    def test_categorical_nan_equality(self):
        cat = Series(Categorical(["a", "b", "c", np.nan]))
        expected = Series([True, True, True, False])
        result = cat == cat
        tm.assert_series_equal(result, expected)

    def test_categorical_tuple_equality(self):
        # GH 18050
        ser = Series([(0, 0), (0, 1), (0, 0), (1, 0), (1, 1)])
        expected = Series([True, False, True, False, False])
        result = ser == (0, 0)
        tm.assert_series_equal(result, expected)

        result = ser.astype("category") == (0, 0)
        tm.assert_series_equal(result, expected)
