import numpy as np
import pytest

from pandas.util._validators import validate_inclusive

import pandas as pd


@pytest.mark.parametrize(
    "invalid_inclusive",
    (
        "ccc",
        2,
        object(),
        None,
        np.nan,
        pd.NA,
        pd.DataFrame(),
    ),
)
def test_invalid_inclusive(invalid_inclusive):
    with pytest.raises(
        ValueError,
        match="Inclusive has to be either 'both', 'neither', 'left' or 'right'",
    ):
        validate_inclusive(invalid_inclusive)


@pytest.mark.parametrize(
    "valid_inclusive, expected_tuple",
    (
        ("left", (True, False)),
        ("right", (False, True)),
        ("both", (True, True)),
        ("neither", (False, False)),
    ),
)
def test_valid_inclusive(valid_inclusive, expected_tuple):
    resultant_tuple = validate_inclusive(valid_inclusive)
    assert expected_tuple == resultant_tuple
