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
    #: True for arms driven by a mechanical rule rather than by the LLM. These
    #: are the arms that carry a trailing stop; the strategic book's stops come
    #: from the model's own decision text instead.
    rule_driven: bool = False
    #: Rule name for a rule-driven arm. Empty means "follow TACTICAL_RULE", so
    #: the original tactical book stays user-configurable. Every ADDITIONAL rule
    #: arm pins its own, for the same reason the core arms pin their ETF: an arm
    #: whose rule can change under you is not a comparison.
    rule: str = ""


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
        rule_driven=True,
    ),
    # Second rule arm. Donchian beat trend_following on every measured axis over
    # 10y/22 names with real per-market costs — more money ($43.6k vs $41.4k on
    # $10k), more realised profit ($491 vs $410 per 2 months), 46% vs 32% wins,
    # and a shallower drawdown (-19% vs -26%). But its edge over a random-entry
    # twin was +0.03 Sharpe, i.e. inside noise, so timing skill is UNPROVEN.
    # Running it as its own arm is how that gets settled with data.
    #
    # IVV, not SPY or VOO: a third S&P 500 tracker, because two books sharing a
    # core symbol makes get_position (scalar_one_or_none) raise
    # MultipleResultsFound and permanently blocks that book's sweep.
    "tactical_donchian": BookSpec(
        "tactical_donchian", "tac_donchian", "IVV", False, True,
        "rule-based 55/20 breakout over an index core",
        rule_driven=True, rule="donchian_breakout",
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

#: Reverse lookup: Position.account_type -> book label. Lets the stop monitor and
#: the trailing-stop ratchet resolve which book a row belongs to instead of
#: hardcoding book names, so a new arm wires itself in by being added above.
POSITION_TYPE_BOOK: dict[str, str] = {v.position_type: k for k, v in BOOKS.items()}

#: Position types whose book trades automatically (stop/target exits allowed).
AUTO_POSITION_TYPES: frozenset[str] = frozenset(
    s.position_type for s in BOOKS.values() if s.active
)

#: Position types that carry a ratcheting trailing stop (rule-driven arms only).
RULE_POSITION_TYPES: frozenset[str] = frozenset(
    s.position_type for s in BOOKS.values() if s.rule_driven
)


def rule_for(book: str, configured: str = "") -> str:
    """The rule a book trades. Pinned in the spec, else the configured default."""
    return spec(book).rule or configured


def spec(book: str) -> BookSpec:
    """Look up a book, falling back to strategic-like defaults for unknowns."""
    return BOOKS.get(book, BOOKS["strategic"])
