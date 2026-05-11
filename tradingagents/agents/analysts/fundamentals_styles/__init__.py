"""Pluggable fundamental-analysis styles.

Each style is a small, self-contained class exposing:
  * ``key`` — config / CLI identifier (e.g. ``"buffett_value"``)
  * ``label`` — human-readable picker label
  * ``description`` — one-line subtitle for the CLI picker
  * ``system_message()`` — the analytical prompt injected into the agent
  * ``extra_tools()`` — additional ``@tool``-decorated callables the LLM
    should be able to invoke for this style (most styles return ``[]``)

The agent reads ``config["fundamentals_style"]`` and looks up the matching
class in :data:`STYLES`. Falls back to :data:`DEFAULT_STYLE_KEY` when the
key is missing, blank, or unknown — never crashes the run because of a
config typo.

Add a new style by:
  1. Creating ``tradingagents/agents/analysts/fundamentals_styles/<name>.py``
     with a class implementing :class:`FundamentalStyle`.
  2. Registering it in :data:`STYLES` below.

Tests live in ``tests/test_fundamentals_styles.py`` and lock the
registry surface so style additions can't accidentally break others.
"""

from __future__ import annotations

from typing import Dict

from .base import FundamentalStyle
from .buffett_value import BuffettValueStyle
from .comprehensive import ComprehensiveStyle
from .growth import GrowthStyle


# Order here is the order shown in the CLI picker. Comprehensive first so
# users who don't care get the previous default behavior unchanged.
STYLES: Dict[str, FundamentalStyle] = {
    ComprehensiveStyle.key: ComprehensiveStyle(),
    BuffettValueStyle.key: BuffettValueStyle(),
    GrowthStyle.key: GrowthStyle(),
}

DEFAULT_STYLE_KEY = ComprehensiveStyle.key


def resolve_style(key: str | None) -> FundamentalStyle:
    """Look up a style by key, falling back to the default on miss.

    Accepts ``None`` and empty strings so callers can pass
    ``config.get("fundamentals_style")`` without pre-checking.
    """
    if not key:
        return STYLES[DEFAULT_STYLE_KEY]
    return STYLES.get(key.strip().lower(), STYLES[DEFAULT_STYLE_KEY])


__all__ = [
    "STYLES",
    "DEFAULT_STYLE_KEY",
    "FundamentalStyle",
    "resolve_style",
]
