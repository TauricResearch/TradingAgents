"""Deterministic checks that a decision's price levels agree with its direction.

The Trader and the Portfolio Manager each give a direction and, optionally,
price levels. Nothing made the two agree: a Buy could carry a stop-loss above
its entry, or a Buy rating a target below the price the Trader would pay
(#1168). These checks compare the typed fields in code and return a sentence
per conflict, which the renderers print as a ``Level Check`` line so the
agents downstream and the reader see it. They never change the decision.

Only long calls are checked. A Sell may exit a holding rather than open a
short, and a stop below an exit price is a valid plan for that, so the side
of a Sell's stop says nothing on its own.
"""

from __future__ import annotations

import math
import re

from tradingagents.agents.schemas import (
    PortfolioDecision,
    PortfolioRating,
    TraderAction,
    TraderProposal,
)

_LONG_RATINGS = frozenset({PortfolioRating.BUY, PortfolioRating.OVERWEIGHT})

# The Trader's entry line as render_trader_proposal writes it, and as the
# free-text fallback is asked to write it: "**Entry Price**: 189.5".
_ENTRY_LINE_RE = re.compile(
    r"^[\s\-*]*entry price[\s*]*:[\s*]*\$?(?P<value>[0-9][0-9,]*(?:\.[0-9]+)?(?:e-?[0-9]+)?)[\s*]*$",
    re.IGNORECASE | re.MULTILINE,
)


def trader_level_warnings(proposal: TraderProposal) -> list[str]:
    """Conflicts between the Trader's action and its own entry and stop."""
    entry, stop = proposal.entry_price, proposal.stop_loss
    if proposal.action is not TraderAction.BUY or entry is None or stop is None:
        return []
    if stop >= entry:
        return [
            f"The stop-loss ({stop:g}) is not below the entry price ({entry:g}), "
            "so this Buy would be stopped out as it is entered."
        ]
    return []


def trader_entry_price(trader_plan: str) -> float | None:
    """The entry price from the Trader's labelled line, or None when it gave none."""
    match = _ENTRY_LINE_RE.search(trader_plan or "")
    if match is None:
        return None
    value = float(match.group("value").replace(",", ""))
    return value if math.isfinite(value) and value > 0 else None


def decision_level_warnings(decision: PortfolioDecision, entry_price: float | None) -> list[str]:
    """Conflicts between the Portfolio Manager's rating and its target, against the Trader's entry."""
    target = decision.price_target
    if decision.rating not in _LONG_RATINGS or target is None or entry_price is None:
        return []
    if target <= entry_price:
        return [
            f"A {decision.rating.value} rating has a price target ({target:g}) "
            f"that is not above the Trader's entry price ({entry_price:g})."
        ]
    return []
