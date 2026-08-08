"""Book registry: the parallel arms of the forward test.

Ten alpha routes were tested and failed in Aug 2026, so instead of guessing
which core is best, every candidate runs as its own $10k book over the same
window. That turns "which should we pick?" into a controlled experiment where
the answer is read off the scoreboard rather than argued.

Arms
----
strategic   LLM signals (analyst -> debate -> trader -> risk -> PM) + index core
tactical    rule-based trend entries + index core
core_spy    100% SPY, no timing. The control every other arm must beat.
core_trend  SPY held only above its 200-day average. Crash insurance: measured
            at half the drawdown of SPY for the same return, but it costs
            3-5pp/yr outside a crash.
core_2x     SSO (2x SPY). The only lever that materially raises monthly income
            (~+$289/mo vs +$162 on $10k) and it lost 78% in 2008.
core_jepi   JEPI covered-call income. Lowest return (~+$133/mo), smallest
            drawdown (-14%).

Because every arm starts on the same date with the same capital and is priced
by the same broker, differences between them are attributable to the policy
rather than to luck about entry timing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BookSpec:
    label: str
    #: ``Position.account_type`` for this book's rows. 'paper' is the legacy
    #: value for the strategic book, kept so pre-books data keeps working.
    position_type: str
    #: ETF that idle cash rests in. Empty means "follow the CORE_ETF setting",
    #: so the strategic book stays user-configurable while every other arm is
    #: pinned — a passive control whose holding could change is not a control.
    core_etf: str
    #: Hold the core only while it trades above its long-term average.
    trend_filter: bool
    #: False for arms that only trade their core (no signals, no rules).
    active: bool
    description: str


BOOKS: dict[str, BookSpec] = {
    "strategic": BookSpec(
        "strategic", "paper", "", False, True,
        "LLM signals over an index core",
    ),
    # VOO, not SPY. The rule trades individual names and parks the rest in the
    # index; if both used SPY the sweep would refuse to add core (a conviction
    # position already owns the symbol) and the book would sit ~48% in idle
    # cash — exactly the drag the core exists to remove. VOO tracks the same
    # S&P 500 index, so the exposure is identical and the collision is gone.
    "tactical": BookSpec(
        "tactical", "tactical", "VOO", False, True,
        "rule-based trend entries over an index core",
    ),
    "core_spy": BookSpec(
        "core_spy", "core_spy", "SPY", False, False,
        "100% SPY — the control every active arm must beat",
    ),
    "core_trend": BookSpec(
        "core_trend", "core_trend", "SPY", True, False,
        "SPY above its 200-day average, else cash — crash insurance",
    ),
    "core_2x": BookSpec(
        "core_2x", "core_2x", "SSO", False, False,
        "2x SPY — double the income and double the losses",
    ),
    "core_jepi": BookSpec(
        "core_jepi", "core_jepi", "JEPI", False, False,
        "covered-call income — lowest return, smallest drawdown",
    ),
}

#: Legacy mapping kept for existing call sites.
BOOK_POSITION_TYPE: dict[str, str] = {k: v.position_type for k, v in BOOKS.items()}


def spec(book: str) -> BookSpec:
    """Look up a book, falling back to strategic-like defaults for unknowns."""
    return BOOKS.get(book, BOOKS["strategic"])
