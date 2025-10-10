# ruff: noqa: TCH004
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # import modules that have public classes/functions:
    from pandas.tseries import (
        frequencies,
        offsets,
    )

    # and mark only those modules as public
    __all__ = ["frequencies", "offsets"]
