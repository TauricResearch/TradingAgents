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

# The same label opening its own line ("**Rating**: X", "## Final Rating - X",
# "Our rating: X"): the shape the Portfolio Manager is asked to write its
# decision in. Only emphasis and heading marks may precede it, so a list item,
# table row or blockquote quoting someone else's rating is not one.
_RATING_LINE_RE = re.compile(
    r"[\s*_#]*(?:\w+\s+)?rating[^\w:\-\u2010-\u2015]*[:\-\u2010-\u2015][\s*]*(\w+)",
    re.IGNORECASE,
)

# A line presenting the scale rather than a decision ("Rating Scale: Buy, ...").
_RATING_SCALE_RE = re.compile(r"rating\s*(scale|options|legend)", re.IGNORECASE)

# Standalone 5-tier word anywhere (word boundaries so "Buyer"/"Holding" don't match).
_RATING_WORD_RE = re.compile(
    r"\b(" + "|".join(RATINGS_5_TIER) + r")\b", re.IGNORECASE
)


def extract_rating(text: str) -> str | None:
    """Extract a 5-tier rating from prose, or ``None`` if none is present.

    Two-pass strategy on the NFKC-normalized text (so fullwidth punctuation like
    ``Rating：Overweight`` is matched the same as ASCII):
    1. An explicit "Rating: X" label (tolerant of markdown bold): the first one
       opening its own line, else the last one anywhere.
    2. A single 5-tier rating word, when the text names only one.
    """
    if not text:
        return None
    norm = unicodedata.normalize("NFKC", text)

    # A decision is asked to open with its rating on its own line, so the first
    # such line is the call; later ones may quote someone else's ("Consensus
    # rating: Buy"). Without one, the last label anywhere wins: prose states its
    # rating after discussing the alternatives. Lines presenting the scale itself
    # are a legend the model echoed, not a call.
    on_own_line = anywhere = None
    for line in norm.splitlines():
        if _RATING_SCALE_RE.search(line):
            continue
        m = _RATING_LINE_RE.match(line)
        if on_own_line is None and m and m.group(1).lower() in _RATING_SET:
            on_own_line = m.group(1).capitalize()
        m = _RATING_LABEL_RE.search(line)
        if m and m.group(1).lower() in _RATING_SET:
            anywhere = m.group(1).capitalize()
    if on_own_line or anywhere:
        return on_own_line or anywhere

    # No label. A single rating word in the text is the call; several are an
    # argument, and picking one of them reports a direction nobody decided --
    # prose that rejects a Buy before concluding Underweight read as Buy.
    named = {m.group(1).capitalize() for m in _RATING_WORD_RE.finditer(norm)}
    return named.pop() if len(named) == 1 else None


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
