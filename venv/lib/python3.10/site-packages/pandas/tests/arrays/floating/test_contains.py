import numpy as np

import pandas as pd


def test_contains_nan():
    # GH#52840
    arr = pd.array(range(5)) / 0

    assert np.isnan(arr._data[0])
    assert not arr.isna()[0]
    assert np.nan in arr
