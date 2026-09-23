"""Shared 5-tier rating vocabulary and a deterministic heuristic parser.

The same five-tier scale (Buy, Overweight, Hold, Underweight, Sell) is used by:
- The Research Manager (investment plan recommendation)
- The Portfolio Manager (final position decision)
- The signal processor (rating extracted for downstream consumers)
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

# The line a decision opens with ("**Rating**: Hold"), as rendered or as the
# Portfolio Manager prompt asks a free-text answer to start.
_RATING_HEADER_RE = re.compile(r"[\s#*_\-]*rating[\s*_]*[:\-\u2010-\u2015][\s*]*(\w+)",
                               re.IGNORECASE)

# Matches "Rating: X" / "rating - X" / "Rating — **X**" — tolerates markdown
# bold wrappers and any dash or colon a model writes as the separator.
# A letter before "rating" makes it part of another word ("Operating"). Unlike
# \b, the lookbehind still matches after CJK text, as in "最终Rating：Hold".
_RATING_LABEL_RE = re.compile(
    r"(?<![a-z])rating\b[^:\-\u2010-\u2015]*[:\-\u2010-\u2015][\s*]*(\w+)", re.IGNORECASE
)

# A line presenting the scale rather than a decision ("Rating Scale: Buy, ...").
_RATING_SCALE_RE = re.compile(r"rating\s*(scale|options|legend)", re.IGNORECASE)

# Standalone 5-tier word anywhere (word boundaries so "Buyer"/"Holding" don't match).
_RATING_WORD_RE = re.compile(
    r"\b(" + "|".join(RATINGS_5_TIER) + r")\b", re.IGNORECASE
)


def extract_rating(text: str) -> str | None:
    """Extract a 5-tier rating from prose, or ``None`` if none is present.

    Three passes on the NFKC-normalized text (so fullwidth punctuation like
    ``Rating：Overweight`` is matched the same as ASCII):
    1. The rating header, a "Rating: X" line that opens the decision.
    2. The last line with a "Rating: X" label (tolerant of markdown bold).
    3. The only standalone 5-tier rating word in the text.
    """
    if not text:
        return None
    norm = unicodedata.normalize("NFKC", text)
    lines = norm.splitlines()

    # The header is the call. Only the line that opens the decision, below any
    # blank or "#" title lines, can be the header, because a "Rating: X" line
    # further down may be a quote. A header naming several tiers echoes the scale.
    for line in lines:
        m = _RATING_HEADER_RE.match(line)
        tiers = {t.lower() for t in _RATING_WORD_RE.findall(line)}
        if m and tiers == {m.group(1).lower()}:
            return m.group(1).capitalize()
        if line.strip() and not line.lstrip().startswith("#"):
            break

    # The labelled rating, taking the last one written: a decision states its
    # rating after discussing the alternatives. Lines presenting the scale
    # itself are a legend the model echoed, not a call.
    labelled = None
    for line in lines:
        if _RATING_SCALE_RE.search(line):
            continue
        m = _RATING_LABEL_RE.search(line)
        if m and m.group(1).lower() in _RATING_SET:
            labelled = m.group(1).capitalize()
    if labelled:
        return labelled

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


def is_review(signal: str) -> bool:
    """Whether a signal is the non-tradeable REVIEW sentinel (#1170)."""
    return signal == RATING_REVIEW
