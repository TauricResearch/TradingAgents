"""Shared 5-tier rating vocabulary and a deterministic heuristic parser.

The same five-tier scale (Buy, Overweight, Hold, Underweight, Sell) is used by:
- The Research Manager (investment plan recommendation)
- The Portfolio Manager (final position decision; its free-text fallback is read here)
- The memory log (rating tag stored alongside each decision entry)

Centralising it here avoids drift between those call sites.

``extract_rating`` returns ``None`` when no rating can be found, and every
caller turns that into ``REVIEW`` rather than a tradeable position: a decision
nobody can read is not a Hold, and a Hold recorded in its place is quoted back to
the next run as a call that was never made (#1170).
"""

from __future__ import annotations

import re
import unicodedata

# Canonical, ordered 5-tier scale (most bullish to most bearish).
RATINGS_5_TIER: tuple[str, ...] = (
    "Buy", "Overweight", "Hold", "Underweight", "Sell",
)

# Signal emitted when the model's decision has no recognizable rating. It is not
# a tradeable position: it flags output that needs a human/re-run rather than
# silently degrading to Hold. Callers that map the signal onto the 5-tier enum
# (e.g. ``PortfolioRating(signal)``) should guard with ``is_review`` first.
RATING_REVIEW = "REVIEW"

_RATING_SET = {r.lower() for r in RATINGS_5_TIER}

# Matches "Rating: X" / "rating - X" / "Rating — **X**" — tolerates markdown
# bold wrappers and any dash or colon a model writes as the separator. "rating"
# must start a word, so "Operating margin: Sell-side" is not a label.
_RATING_LABEL_RE = re.compile(r"(?<![a-z])rating\b[^:\-\u2010-\u2015]*[:\-\u2010-\u2015][\s*]*(\w+)",
                              re.IGNORECASE)

# A decision line opens with its rating label, optionally under a heading or
# emphasis. A list marker is stripped only from the first substantive line.
_RATING_LINE_RE = re.compile(
    r"\s*(?:#+\s*)?[*_]*(?:(?:final|our)\s+)?"
    r"rating[^\w:\-\u2010-\u2015]*[:\-\u2010-\u2015][\s*]*(\w+)",
    re.IGNORECASE,
)

# A line presenting the scale rather than a decision ("Rating Scale: Buy, ...").
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d{1,2}[.)])\s+")
_RATING_SCALE_RE = re.compile(r"rating\s*(scale|options|legend)", re.IGNORECASE)

def extract_rating(text: str) -> str | None:
    """Extract a 5-tier rating when the decision is unambiguous."""
    if not text:
        return None
    norm = unicodedata.normalize("NFKC", text)

    own_lines = set()
    labels = set()
    first_substantive_line = True
    for line in norm.splitlines():
        first_line = first_substantive_line
        if line.strip():
            first_substantive_line = False
        if _RATING_SCALE_RE.search(line):
            continue

        decision_line = _LIST_ITEM_RE.sub("", line, count=1) if first_line else line
        match = _RATING_LINE_RE.match(decision_line)
        if match and match.group(1).lower() in _RATING_SET:
            own_lines.add(match.group(1).capitalize())

        for match in _RATING_LABEL_RE.finditer(line):
            if match.group(1).lower() in _RATING_SET:
                labels.add(match.group(1).capitalize())

    calls = own_lines or labels
    return calls.pop() if len(calls) == 1 else None


def parse_rating(text: str, default: str = RATING_REVIEW) -> str:
    """Extract a 5-tier rating, or ``REVIEW`` when the decision has none.

    For callers that need a string for every decision, such as the memory log's
    entry tag. The default is the review sentinel, never a tradeable rating.
    """
    rating = extract_rating(text)
    return rating if rating is not None else default


def run_rating(final_state: dict) -> str:
    """A finished run's rating: the Portfolio Manager's own, else read from its decision.

    The fallback serves a state without ``final_rating``, such as a run an older
    version completed and a checkpoint hands back unchanged.
    """
    return final_state.get("final_rating") or parse_rating(final_state.get("final_trade_decision", ""))


def is_review(signal: str) -> bool:
    """Whether a signal is the non-tradeable REVIEW sentinel (#1170)."""
    return signal == RATING_REVIEW
