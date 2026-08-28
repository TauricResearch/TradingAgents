# Modified for A-share position management; see repository NOTICE.
"""Shared 5-tier rating vocabulary and a deterministic heuristic parser.

The same five-tier scale (Buy, Overweight, Hold, Underweight, Sell) is used by:
- The Research Manager (investment plan recommendation)
- The Portfolio Manager (final position decision)
- The signal processor (rating extracted for downstream consumers)
- The memory log (rating tag stored alongside each decision entry)

Centralising it here avoids drift between those call sites.
"""

from __future__ import annotations

import re

# Canonical, ordered 5-tier scale (most bullish to most bearish).
RATINGS_5_TIER: tuple[str, ...] = (
    "Buy", "Overweight", "Hold", "Underweight", "Sell",
)
POSITION_ACTIONS_5_TIER: tuple[str, ...] = (
    "Add", "Slight Add", "Hold", "Reduce", "Exit",
)

_RATING_SET = {r.lower() for r in RATINGS_5_TIER}

# Matches "Rating: X" / "rating - X" / "Rating: **X**" — tolerates markdown
# bold wrappers and either a colon or hyphen separator.
_RATING_LABEL_RE = re.compile(r"rating.*?[:\-][\s*]*(\w+)", re.IGNORECASE)
_POSITION_LABEL_RE = re.compile(
    r"position\s+action.*?[:\-][\s*]*(add|slight\s+add|hold|reduce|exit)",
    re.IGNORECASE,
)


def parse_rating(text: str, default: str = "Hold") -> str:
    """Heuristically extract a 5-tier rating from prose text.

    Two-pass strategy:
    1. Look for an explicit "Rating: X" label (tolerant of markdown bold).
    2. Fall back to the first 5-tier rating word found anywhere in the text.

    Returns a Title-cased rating string, or ``default`` if no rating word appears.
    """
    for line in text.splitlines():
        m = _RATING_LABEL_RE.search(line)
        if m and m.group(1).lower() in _RATING_SET:
            return m.group(1).capitalize()

    for line in text.splitlines():
        for word in line.lower().split():
            clean = word.strip("*:.,")
            if clean in _RATING_SET:
                return clean.capitalize()

    return default


def parse_position_action(text: str, default: str = "Hold") -> str:
    """Extract an A-share position action, with legacy rating compatibility."""
    for line in text.splitlines():
        match = _POSITION_LABEL_RE.search(line)
        if match:
            return " ".join(part.capitalize() for part in match.group(1).split())

    lower = text.lower()
    for action in POSITION_ACTIONS_5_TIER:
        if action.lower() in lower:
            return action

    legacy = parse_rating(text, default="")
    return {
        "Buy": "Add",
        "Overweight": "Slight Add",
        "Hold": "Hold",
        "Underweight": "Reduce",
        "Sell": "Exit",
    }.get(legacy, default)
