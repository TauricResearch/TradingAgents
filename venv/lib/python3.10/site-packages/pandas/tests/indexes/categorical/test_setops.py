import numpy as np
import pytest

from pandas import (
    CategoricalIndex,
    Index,
)
import pandas._testing as tm


@pytest.mark.parametrize("na_value", [None, np.nan])
def test_difference_with_na(na_value):
    # GH 57318
    ci = CategoricalIndex(["a", "b", "c", None])
    other = Index(["c", na_value])
    result = ci.difference(other)
    expected = CategoricalIndex(["a", "b"], categories=["a", "b", "c"])
    tm.assert_index_equal(result, expected)
