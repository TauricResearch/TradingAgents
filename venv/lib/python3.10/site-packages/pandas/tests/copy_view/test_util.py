import numpy as np

from pandas import DataFrame
from pandas.tests.copy_view.util import get_array


def test_get_array_numpy():
    df = DataFrame({"a": [1, 2, 3]})
    assert np.shares_memory(get_array(df, "a"), get_array(df, "a"))


def test_get_array_masked():
    df = DataFrame({"a": [1, 2, 3]}, dtype="Int64")
    assert np.shares_memory(get_array(df, "a"), get_array(df, "a"))
