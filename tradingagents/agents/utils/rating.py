"""Shared 5-tier rating vocabulary and a deterministic heuristic parser.

The same five-tier scale (Buy, Overweight, Hold, Underweight, Sell) is used by:
- The Research Manager (investment plan recommendation)
- The Portfolio Manager (final position decision)
- The signal processor (rating extracted for downstream consumers)
- The memory log (rating tag stored alongside each decision entry)

Centralising it here avoids drift between those call sites.

:func:`extract_rating` returns ``None`` when no rating can be recognised, so a
caller can tell a genuine ``Hold`` apart from a parse failure. :func:`parse_rating`
keeps the older "return a default" contract for callers that deliberately want
one. The 5-tier *rating* is intentionally kept separate from the 3-tier *trade
action* (Buy / Sell / Hold): a rating word is never mapped onto a trade action here.
"""

from __future__ import annotations

import re

# Canonical, ordered 5-tier scale (most bullish to most bearish).
RATINGS_5_TIER: tuple[str, ...] = (
    "Buy", "Overweight", "Hold", "Underweight", "Sell",
)

# Sentinel for "no parseable rating". It is deliberately NOT a member of the
# 5-tier scale: a genuine neutral call is "Hold", whereas this marks "the text
# carried no recognisable rating" so downstream consumers can surface it for
# review instead of mistaking a parse failure for a real Hold.
RATING_REVIEW = "REVIEW"

_RATING_SET = {r.lower() for r in RATINGS_5_TIER}

# Fullwidth / CJK punctuation that commonly wraps a rating in localized output,
# normalised to its ASCII equivalent so the label match and the tokeniser see the
# rating cleanly (e.g. "Rating：Overweight", "Sell（bearish）"). Only punctuation is
# mapped; letters and content are untouched.
_PUNCT_NORMALIZE = str.maketrans({
    "：": ":", "－": "-", "‐": "-",
    "（": "(", "）": ")", "［": "[", "］": "]",
    "，": ",", "、": ",", "．": ".", "｜": "|",
})

# Matches "Rating: X" / "rating - X" / "Rating: **X**" — tolerates markdown
# bold wrappers and either a colon or hyphen separator.
_RATING_LABEL_RE = re.compile(r"rating.*?[:\-][\s*]*(\w+)", re.IGNORECASE)


def _normalize(text: str) -> str:
    return text.translate(_PUNCT_NORMALIZE)


def extract_rating(text: str) -> str | None:
    """Heuristically extract a 5-tier rating, or ``None`` if none is recognised.

    After normalising harmless fullwidth/CJK punctuation, a two-pass strategy:

    1. An explicit ``Rating: X`` label (tolerant of markdown bold) takes priority.
    2. Otherwise, the first 5-tier rating *word* found anywhere in the text.

    Returns a Title-cased rating string, or ``None`` when the text contains no
    recognisable rating — never a silent default. Matching is on whole alphabetic
    tokens, so "buyer", "holding" or "seller" do not spuriously match.
    """
    if not text:
        return None
    norm = _normalize(text)

    # Pass 1: an explicit label anywhere wins over a bare rating word in prose.
    for line in norm.splitlines():
        m = _RATING_LABEL_RE.search(line)
        if m and m.group(1).lower() in _RATING_SET:
            return m.group(1).capitalize()

    # Pass 2: first standalone rating word. re.findall on [A-Za-z]+ splits on any
    # non-letter — whitespace, ASCII or normalised fullwidth punctuation, or CJK —
    # so a rating glued to a localized label ("评级:Overweight") is still found,
    # while longer words ("buyer", "holding") are not partially matched.
    for line in norm.splitlines():
        for token in re.findall(r"[A-Za-z]+", line):
            if token.lower() in _RATING_SET:
                return token.capitalize()

    return None


def parse_rating(text: str, default: str = "Hold") -> str:
    """Extract a 5-tier rating, falling back to ``default`` when none is found.

    Backwards-compatible convenience wrapper over :func:`extract_rating`, for
    callers that deliberately want a default. Prefer :func:`extract_rating` when a
    parse failure must be distinguished from a genuine rating.
    """
    rating = extract_rating(text)
    return rating if rating is not None else default
