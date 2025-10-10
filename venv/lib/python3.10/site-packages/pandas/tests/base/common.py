from typing import Any

from pandas import Index


def allow_na_ops(obj: Any) -> bool:
    """Whether to skip test cases including NaN"""
    is_bool_index = isinstance(obj, Index) and obj.inferred_type == "boolean"
    return not is_bool_index and obj._can_hold_na
