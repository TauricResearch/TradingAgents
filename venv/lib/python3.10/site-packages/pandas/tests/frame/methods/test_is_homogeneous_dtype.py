import numpy as np
import pytest

import pandas.util._test_decorators as td

from pandas import (
    Categorical,
    DataFrame,
)

# _is_homogeneous_type always returns True for ArrayManager
pytestmark = td.skip_array_manager_invalid_test


@pytest.mark.parametrize(
    "data, expected",
    [
        # empty
        (DataFrame(), True),
        # multi-same
        (DataFrame({"A": [1, 2], "B": [1, 2]}), True),
        # multi-object
        (
            DataFrame(
                {
                    "A": np.array([1, 2], dtype=object),
                    "B": np.array(["a", "b"], dtype=object),
                },
                dtype="object",
            ),
            True,
        ),
        # multi-extension
        (
            DataFrame({"A": Categorical(["a", "b"]), "B": Categorical(["a", "b"])}),
            True,
        ),
        # differ types
        (DataFrame({"A": [1, 2], "B": [1.0, 2.0]}), False),
        # differ sizes
        (
            DataFrame(
                {
                    "A": np.array([1, 2], dtype=np.int32),
                    "B": np.array([1, 2], dtype=np.int64),
                }
            ),
            False,
        ),
        # multi-extension differ
        (
            DataFrame({"A": Categorical(["a", "b"]), "B": Categorical(["b", "c"])}),
            False,
        ),
    ],
)
def test_is_homogeneous_type(data, expected):
    assert data._is_homogeneous_type is expected
