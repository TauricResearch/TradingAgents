"""Plan-number extraction (P0.5 wiring): entry/stop from the plan text.

The Execution Gate's risk checks need the plan's own numbers — entry,
stop, ATR, direction. The Trader's proposal states them in prose
("Entry 560.00, stop 552.07, ATR 8.0"); this module extracts them
deterministically so the exposure-capped sizing runs in the real flow
without explicit caller parameters.

Extraction is conservative: a number is accepted only from an explicit
labelled pattern (``entry``, ``stop``, ``atr``, ``long``/``short``), never
guessed from bare prices in the text. A plan whose numbers cannot be
extracted yields None fields — the caller's fail-closed rule then skips
the risk check rather than inventing values, exactly as the contract
requires.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Labelled money/number patterns. Structural, any ticker: the labels are
# the plan vocabulary, not per-ticker rules.
_ENTRY_RE = re.compile(
    r"\bentry(?:\s+price)?\s*[:=]?\s*\$?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)
_STOP_RE = re.compile(
    r"\bstop(?:\s*-?\s*loss)?\s*[:=]?\s*\$?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)
_ATR_RE = re.compile(
    r"\bATR(?:\s*\(\s*\d+\s*\))?\s*[:=]?\s*\$?\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE)
_DIRECTION_RE = re.compile(r"\b(long|short)\b", re.IGNORECASE)


@dataclass(frozen=True)
class PlanNumbers:
    """The plan's numbers as extracted from its text (None when absent)."""

    entry: float | None = None
    stop: float | None = None
    atr: float | None = None
    direction: str = "LONG"

    @property
    def has_plan(self) -> bool:
        """Whether at least an entry and a stop were extracted."""
        return self.entry is not None and self.stop is not None


def _number(raw: str) -> float | None:
    """Parse a plan number; a comma decimal separator is normalized."""
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def extract_plan_numbers(plan_text: str | None) -> PlanNumbers:
    """Extract entry/stop/ATR/direction from the plan's own text.

    Only explicit labelled patterns count: "entry 560", "stop: 552.07",
    "ATR 8", "long"/"short". Bare numbers in prose are never guessed — a
    wrong extraction would size a position the plan never proposed.
    """
    if not plan_text:
        return PlanNumbers()

    entry = None
    stop = None
    atr = None

    entry_match = _ENTRY_RE.search(plan_text)
    if entry_match:
        entry = _number(entry_match.group(1))
    stop_match = _STOP_RE.search(plan_text)
    if stop_match:
        stop = _number(stop_match.group(1))
    atr_match = _ATR_RE.search(plan_text)
    if atr_match:
        atr = _number(atr_match.group(1))

    direction = "LONG"
    direction_match = _DIRECTION_RE.search(plan_text)
    if direction_match:
        direction = direction_match.group(1).upper()

    return PlanNumbers(entry=entry, stop=stop, atr=atr, direction=direction)
