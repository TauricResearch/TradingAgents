"""Shared rendering rules for the news vendors.

Every news vendor ends up emitting the same block per article — headline,
source, summary, link — but they disagree wildly on how much text an article
carries: a yfinance blurb is a sentence, while an Alpha Vantage summary can run
to the full body. Unbounded, that body is what let one news call fill 6-7k
tokens of an analyst's context (#291), so the trim lives here and both vendors
apply it rather than each growing its own rule.
"""

from .config import get_config

# Marker appended to a summary that was cut. ASCII on purpose: reports are
# written to disk and rendered in terminals whose encoding we do not control.
TRUNCATION_MARKER = "..."


def article_max_chars() -> int:
    """Per-article summary budget from the active config."""
    return get_config()["news_article_max_chars"]


def trim_summary(summary: str, max_chars: int | None = None) -> str:
    """Collapse whitespace in ``summary`` and cut it to ``max_chars``.

    The cut falls on a word boundary so a trimmed summary still reads as
    prose. ``max_chars`` of 0 (or less) disables the trim, which is how a user
    who would rather pay the tokens than lose the tail opts out.
    """
    collapsed = " ".join((summary or "").split())
    if max_chars is None:
        max_chars = article_max_chars()
    if max_chars <= 0 or len(collapsed) <= max_chars:
        return collapsed

    head = collapsed[:max_chars]
    # Prefer the last full word, but keep the hard cut when the budget is so
    # small that no boundary exists inside it.
    boundary = head.rfind(" ")
    if boundary > 0:
        head = head[:boundary]
    return f"{head.rstrip()}{TRUNCATION_MARKER}"
