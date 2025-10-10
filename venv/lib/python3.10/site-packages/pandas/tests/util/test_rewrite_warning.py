import warnings

import pytest

from pandas.util._exceptions import rewrite_warning

import pandas._testing as tm


@pytest.mark.parametrize(
    "target_category, target_message, hit",
    [
        (FutureWarning, "Target message", True),
        (FutureWarning, "Target", True),
        (FutureWarning, "get mess", True),
        (FutureWarning, "Missed message", False),
        (DeprecationWarning, "Target message", False),
    ],
)
@pytest.mark.parametrize(
    "new_category",
    [
        None,
        DeprecationWarning,
    ],
)
def test_rewrite_warning(target_category, target_message, hit, new_category):
    new_message = "Rewritten message"
    if hit:
        expected_category = new_category if new_category else target_category
        expected_message = new_message
    else:
        expected_category = FutureWarning
        expected_message = "Target message"
    with tm.assert_produces_warning(expected_category, match=expected_message):
        with rewrite_warning(
            target_message, target_category, new_message, new_category
        ):
            warnings.warn(message="Target message", category=FutureWarning)
