import os

import pytest

from pandas import (
    array,
    compat,
)
import pandas._testing as tm


def test_numpy_err_state_is_default():
    expected = {"over": "warn", "divide": "warn", "invalid": "warn", "under": "ignore"}
    import numpy as np

    # The error state should be unchanged after that import.
    assert np.geterr() == expected


def test_convert_rows_list_to_csv_str():
    rows_list = ["aaa", "bbb", "ccc"]
    ret = tm.convert_rows_list_to_csv_str(rows_list)

    if compat.is_platform_windows():
        expected = "aaa\r\nbbb\r\nccc\r\n"
    else:
        expected = "aaa\nbbb\nccc\n"

    assert ret == expected


@pytest.mark.parametrize("strict_data_files", [True, False])
def test_datapath_missing(datapath):
    with pytest.raises(ValueError, match="Could not find file"):
        datapath("not_a_file")


def test_datapath(datapath):
    args = ("io", "data", "csv", "iris.csv")

    result = datapath(*args)
    expected = os.path.join(os.path.dirname(os.path.dirname(__file__)), *args)

    assert result == expected


def test_external_error_raised():
    with tm.external_error_raised(TypeError):
        raise TypeError("Should not check this error message, so it will pass")


def test_is_sorted():
    arr = array([1, 2, 3], dtype="Int64")
    tm.assert_is_sorted(arr)

    arr = array([4, 2, 3], dtype="Int64")
    with pytest.raises(AssertionError, match="ExtensionArray are different"):
        tm.assert_is_sorted(arr)
