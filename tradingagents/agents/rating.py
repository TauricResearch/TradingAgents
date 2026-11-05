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

# The decision's own rating line, in the shape the Portfolio Manager is asked to
# open with ("- **Rating**: X", "**Final Rating**: X", "## Our rating - X"): an
# optional list marker, emphasis and heading marks, and only words naming the
# decision itself before "rating". "Consensus rating: Buy" or "Trader's rating:
# Buy" is someone else's rating.
_OWN_QUALIFIER = r"(?:(?:final|our|overall|my|recommended|updated|revised|new|current)\s+)*"
_RATING_LINE_RE = re.compile(
    r"\s*(?P<item>(?:[-+*\u2022]|\d+[.)])\s+)?[\s*_#]*" + _OWN_QUALIFIER
    + r"rating[^\w:\-\u2010-\u2015]*[:\-\u2010-\u2015][\s*]*(?P<value>\w+)",
    re.IGNORECASE,
)

# A line presenting the scale rather than a decision ("Rating Scale: Buy, ...").
_RATING_SCALE_RE = re.compile(r"rating\\s*(scale|options|legend)", re.IGNORECASE)

# Localized rating aliases: Chinese brokerage research conventions are
# standardized and map one-to-one onto the 5-tier scale, so a fully-localized
# decision still parses instead of silently falling to REVIEW when the model
# ignores the keep-anchors-in-English instruction despite it.
_LOCALIZED_RATING_ALIASES = {
    "买入": "Buy",
    "增持": "Overweight",
    "持有": "Hold",
    "减持": "Underweight",
    "卖出": "Sell",
}

# A localized anchor line ("**评级**：买入", "最终评级：增持") gets the same
# explicit-label precedence as "Rating: Buy": an optional qualifier before
# "评级", a fullwidth-or-ASCII colon, then the tier word itself. NFKC folding
# happens upstream in extract_rating, so the fullwidth colon arrives as ASCII.
_LOCALIZED_RATING_LABEL_RE = re.compile(
    r"(?:(?:最终|我们的|整体|推荐|更新|新的|当前)\s*)*评级[\s*]*[:\-][\s*]*(买入|增持|持有|减持|卖出)"
)


def _resolve_rating_word(word: str) -> str | None:
    """An English tier word to its canonical form, else ``None``.

    ``_RATING_LABEL_RE`` captures a single ``\\w+`` token, which a localized
    value never is, so alias resolution is a separate lookup rather than a
    wider regex.
    """
    lowered = word.strip().lower()
    if lowered in _RATING_SET:
        return lowered.capitalize()
    return _LOCALIZED_RATING_ALIASES.get(word.strip())

def extract_rating(text: str) -> str | None:
    """Extract a 5-tier rating from its label, or ``None`` if there is none.

    Reads an explicit "Rating: X" label (tolerant of markdown bold) in the
    NFKC-normalized text, so fullwidth punctuation like ``Rating：Overweight``
    matches as ASCII does: the decision's opening rating line, else its own
    rating lines or, failing those, every label, when they agree.
    """
    if not text:
        return None
    norm = unicodedata.normalize("NFKC", text)

    # The decision is asked to open with its rating, so a first line (after any
    # headings) in that shape is the call. A list item there may also be a quote
    # heading a list of other parties' ratings, so it counts with the decision's
    # other rating lines, which leave out list items; failing those, every label
    # counts. Either way they must agree: ratings that differ, with nothing
    # marking which one is the call, are no call (#1170). Lines presenting the
    # scale itself are a legend the model echoed, not a call.
    lines = [line for line in norm.splitlines() if line.strip() and not _RATING_SCALE_RE.search(line)]
    first = next((line for line in lines if not line.lstrip().startswith("#")
                  or _RATING_LINE_RE.match(line)), "")
    m = _RATING_LINE_RE.match(first)
    opening_resolved = _resolve_rating_word(m.group("value")) if m else None
    opening = m if m and opening_resolved else None
    if opening and not opening.group("item"):
        return opening_resolved

    own = [opening_resolved] if opening else []
    labels = []
    for line in lines:
        m = _RATING_LINE_RE.match(line)
        if m and not m.group("item"):
            resolved = _resolve_rating_word(m.group("value"))
            if resolved:
                own.append(resolved)
        labels += [r for r in map(_resolve_rating_word, _RATING_LABEL_RE.findall(line)) if r]
    # A localized anchor line gets the same explicit-label precedence as the
    # English one: the decision's opening line, else its own rating lines,
    # when they agree.
    localized = [_LOCALIZED_RATING_ALIASES[lm.group(1)]
                 for lm in (_LOCALIZED_RATING_LABEL_RE.search(line) for line in lines)
                 if lm]
    if localized:
        return localized[0] if len(set(localized)) == 1 else None
    # Without a label there is no call to read: a rating word in the prose may be
    # one the text argues against ("not a Sell"), and reading it reports a
    # direction nobody decided.
    found = own or labels
    return found[0] if found and len(set(found)) == 1 else None


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
