"""Enum-related utilities, including backports for older Python versions."""

from __future__ import annotations

from enum import Enum


__all__ = ["StrEnum"]

# StrEnum is only available in Python 3.11+
try:
    from enum import StrEnum
except ImportError:

    class StrEnum(str, Enum):
        """
        Minimal backport of Python 3.11's StrEnum for older versions.

        An Enum where all members are also strings.
        """

        def __str__(self) -> str:
            return self.value
