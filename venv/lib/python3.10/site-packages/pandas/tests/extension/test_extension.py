"""
Tests for behavior if an author does *not* implement EA methods.
"""
import numpy as np
import pytest

from pandas.core.arrays import ExtensionArray


class MyEA(ExtensionArray):
    def __init__(self, values) -> None:
        self._values = values


@pytest.fixture
def data():
    arr = np.arange(10)
    return MyEA(arr)


class TestExtensionArray:
    def test_errors(self, data, all_arithmetic_operators):
        # invalid ops
        op_name = all_arithmetic_operators
        with pytest.raises(AttributeError):
            getattr(data, op_name)
