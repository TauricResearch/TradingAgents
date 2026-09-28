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

# Matches "Rating: X" / "rating - X" / "Rating — **X**" — tolerates markdown
# bold wrappers and any dash or colon a model writes as the separator.
_RATING_LABEL_RE = re.compile(r"rating\b[^:\-\u2010-\u2015]*[:\-\u2010-\u2015][\s*]*(\w+)",
                              re.IGNORECASE)

# A line presenting the scale rather than a decision ("Rating Scale: Buy, ...").
_RATING_SCALE_RE = re.compile(r"rating\s*(scale|options|legend)", re.IGNORECASE)

# Standalone 5-tier word anywhere (word boundaries so "Buyer"/"Holding" don't match).
_RATING_WORD_RE = re.compile(
    r"\b(" + "|".join(RATINGS_5_TIER) + r")\b", re.IGNORECASE
)

# Localized rating aliases for common non-English reports. When the output
# language is not English, a freetext decision may still spell the anchor
# line in the target language even though parsers match English words.
# Chinese brokerage research conventions are unambiguous and standardized:
# 买入/增持/持有/减持/卖出 map one-to-one onto the 5-tier scale.
_LOCALIZED_RATING_ALIASES = {
    "买入": "Buy",
    "增持": "Overweight",
    "持有": "Hold",
    "减持": "Underweight",
    "卖出": "Sell",
}

# A localized anchor line ("**评级**：买入") gets the same explicit-label
# precedence as "**Rating**: Buy". Whitespace-tolerant of the bold markdown and
# either colon.
_LOCALIZED_RATING_LABEL_RE = re.compile(
    r"评级[\s*]*[：:][\s*]*(买入|增持|持有|减持|卖出)")


def _resolve_alias(value: str) -> str | None:
    """Resolve an English word or a localized alias to a canonical rating."""
    lowered = value.strip().lower()
    if lowered in _RATING_SET:
        return lowered.capitalize()
    for alias, canonical in _LOCALIZED_RATING_ALIASES.items():
        if value.strip() == alias:
            return canonical
    return None


def extract_rating(text: str) -> str | None:
    """Extract a 5-tier rating from prose, or ``None`` if none is present.

    Two-pass strategy on the NFKC-normalized text (so fullwidth punctuation like
    ``Rating：Overweight`` is matched the same as ASCII):
    1. An explicit "Rating: X" label (tolerant of markdown bold).
    2. The first standalone 5-tier rating word found anywhere.

    Localized aliases (e.g. ``**评级**：买入``) are accepted in both passes so a
    non-English freetext decision still parses instead of falling to REVIEW.
    """
    if not text:
        return None
    norm = unicodedata.normalize("NFKC", text)

    # The labelled rating, taking the last one written: a decision states its
    # rating after discussing the alternatives. Lines presenting the scale
    # itself are a legend the model echoed, not a call.
    labelled = None
    for line in norm.splitlines():
        if _RATING_SCALE_RE.search(line):
            continue
        m = _RATING_LABEL_RE.search(line)
        if m:
            resolved = _resolve_alias(m.group(1))
            if resolved:
                labelled = resolved
                continue
        # A localized anchor line gets the same explicit-label precedence as
        # the English one. Two tiers on one line is the legend the model
        # echoed, not a decision.
        lm = _LOCALIZED_RATING_LABEL_RE.search(line)
        if lm:
            if labelled is None:
                labelled = _LOCALIZED_RATING_ALIASES[lm.group(1)]
            elif labelled != _LOCALIZED_RATING_ALIASES[lm.group(1)]:
                labelled = None
    if labelled:
        return labelled

    # No label. A single rating word in the text is the call; several are an
    # argument, and picking one of them reports a direction nobody decided --
    # prose that rejects a Buy before concluding Underweight read as Buy.
    # Localized aliases are deliberately NOT matched in prose: Chinese has no
    # word boundaries, so "不要买入" ("don't buy") or "机构持有" ("institutions
    # hold") would read as positive calls — exactly the direction-flip this
    # parser exists to prevent. Prose without a label parses to REVIEW.
    named = {m.group(1).capitalize() for m in _RATING_WORD_RE.finditer(norm)}
    if len(named) == 1:
        return named.pop()
    return None


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
