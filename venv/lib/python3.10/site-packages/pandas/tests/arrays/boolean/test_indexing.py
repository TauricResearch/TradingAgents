import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm


@pytest.mark.parametrize("na", [None, np.nan, pd.NA])
def test_setitem_missing_values(na):
    arr = pd.array([True, False, None], dtype="boolean")
    expected = pd.array([True, None, None], dtype="boolean")
    arr[1] = na
    tm.assert_extension_array_equal(arr, expected)
