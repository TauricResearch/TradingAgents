import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.arrays import BooleanArray
from pandas.tests.arrays.masked_shared import ComparisonOps


@pytest.fixture
def data():
    """Fixture returning boolean array with valid and missing data"""
    return pd.array(
        [True, False] * 4 + [np.nan] + [True, False] * 44 + [np.nan] + [True, False],
        dtype="boolean",
    )


@pytest.fixture
def dtype():
    """Fixture returning BooleanDtype"""
    return pd.BooleanDtype()


class TestComparisonOps(ComparisonOps):
    def test_compare_scalar(self, data, comparison_op):
        self._compare_other(data, comparison_op, True)

    def test_compare_array(self, data, comparison_op):
        other = pd.array([True] * len(data), dtype="boolean")
        self._compare_other(data, comparison_op, other)
        other = np.array([True] * len(data))
        self._compare_other(data, comparison_op, other)
        other = pd.Series([True] * len(data))
        self._compare_other(data, comparison_op, other)

    @pytest.mark.parametrize("other", [True, False, pd.NA])
    def test_scalar(self, other, comparison_op, dtype):
        ComparisonOps.test_scalar(self, other, comparison_op, dtype)

    def test_array(self, comparison_op):
        op = comparison_op
        a = pd.array([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean")
        b = pd.array([True, False, None] * 3, dtype="boolean")

        result = op(a, b)

        values = op(a._data, b._data)
        mask = a._mask | b._mask
        expected = BooleanArray(values, mask)
        tm.assert_extension_array_equal(result, expected)

        # ensure we haven't mutated anything inplace
        result[0] = None
        tm.assert_extension_array_equal(
            a, pd.array([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean")
        )
        tm.assert_extension_array_equal(
            b, pd.array([True, False, None] * 3, dtype="boolean")
        )
