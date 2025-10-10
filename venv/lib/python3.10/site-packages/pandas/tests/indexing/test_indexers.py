# Tests aimed at pandas.core.indexers
import numpy as np
import pytest

from pandas.core.indexers import (
    is_scalar_indexer,
    length_of_indexer,
    validate_indices,
)


def test_length_of_indexer():
    arr = np.zeros(4, dtype=bool)
    arr[0] = 1
    result = length_of_indexer(arr)
    assert result == 1


def test_is_scalar_indexer():
    indexer = (0, 1)
    assert is_scalar_indexer(indexer, 2)
    assert not is_scalar_indexer(indexer[0], 2)

    indexer = (np.array([2]), 1)
    assert not is_scalar_indexer(indexer, 2)

    indexer = (np.array([2]), np.array([3]))
    assert not is_scalar_indexer(indexer, 2)

    indexer = (np.array([2]), np.array([3, 4]))
    assert not is_scalar_indexer(indexer, 2)

    assert not is_scalar_indexer(slice(None), 1)

    indexer = 0
    assert is_scalar_indexer(indexer, 1)

    indexer = (0,)
    assert is_scalar_indexer(indexer, 1)


class TestValidateIndices:
    def test_validate_indices_ok(self):
        indices = np.asarray([0, 1])
        validate_indices(indices, 2)
        validate_indices(indices[:0], 0)
        validate_indices(np.array([-1, -1]), 0)

    def test_validate_indices_low(self):
        indices = np.asarray([0, -2])
        with pytest.raises(ValueError, match="'indices' contains"):
            validate_indices(indices, 2)

    def test_validate_indices_high(self):
        indices = np.asarray([0, 1, 2])
        with pytest.raises(IndexError, match="indices are out"):
            validate_indices(indices, 2)

    def test_validate_indices_empty(self):
        with pytest.raises(IndexError, match="indices are out"):
            validate_indices(np.array([0, 1]), 0)
