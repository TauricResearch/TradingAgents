import numpy as np
import pytest

from pandas import DataFrame


@pytest.mark.parametrize(
    "data, index, expected",
    [
        ({"col1": [1], "col2": [3]}, None, 2),
        ({}, None, 0),
        ({"col1": [1, np.nan], "col2": [3, 4]}, None, 4),
        ({"col1": [1, 2], "col2": [3, 4]}, [["a", "b"], [1, 2]], 4),
        ({"col1": [1, 2, 3, 4], "col2": [3, 4, 5, 6]}, ["x", "y", "a", "b"], 8),
    ],
)
def test_size(data, index, expected):
    # GH#52897
    df = DataFrame(data, index=index)
    assert df.size == expected
    assert isinstance(df.size, int)
