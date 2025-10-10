import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays import FloatingArray
from pandas.tests.arrays.masked_shared import (
    ComparisonOps,
    NumericOps,
)


class TestComparisonOps(NumericOps, ComparisonOps):
    @pytest.mark.parametrize("other", [True, False, pd.NA, -1.0, 0.0, 1])
    def test_scalar(self, other, comparison_op, dtype):
        ComparisonOps.test_scalar(self, other, comparison_op, dtype)

    def test_compare_with_integerarray(self, comparison_op):
        op = comparison_op
        a = pd.array([0, 1, None] * 3, dtype="Int64")
        b = pd.array([0] * 3 + [1] * 3 + [None] * 3, dtype="Float64")
        other = b.astype("Int64")
        expected = op(a, other)
        result = op(a, b)
        tm.assert_extension_array_equal(result, expected)
        expected = op(other, a)
        result = op(b, a)
        tm.assert_extension_array_equal(result, expected)


def test_equals():
    # GH-30652
    # equals is generally tested in /tests/extension/base/methods, but this
    # specifically tests that two arrays of the same class but different dtype
    # do not evaluate equal
    a1 = pd.array([1, 2, None], dtype="Float64")
    a2 = pd.array([1, 2, None], dtype="Float32")
    assert a1.equals(a2) is False


def test_equals_nan_vs_na():
    # GH#44382

    mask = np.zeros(3, dtype=bool)
    data = np.array([1.0, np.nan, 3.0], dtype=np.float64)

    left = FloatingArray(data, mask)
    assert left.equals(left)
    tm.assert_extension_array_equal(left, left)

    assert left.equals(left.copy())
    assert left.equals(FloatingArray(data.copy(), mask.copy()))

    mask2 = np.array([False, True, False], dtype=bool)
    data2 = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    right = FloatingArray(data2, mask2)
    assert right.equals(right)
    tm.assert_extension_array_equal(right, right)

    assert not left.equals(right)

    # with mask[1] = True, the only difference is data[1], which should
    #  not matter for equals
    mask[1] = True
    assert left.equals(right)
