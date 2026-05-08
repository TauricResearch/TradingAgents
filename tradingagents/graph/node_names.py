"""Canonical node name constants shared between graph setup and conditional routing.

Import these instead of typing the strings inline so that a rename in one
place propagates everywhere automatically, and route mismatches become
import errors rather than silent runtime failures.
"""

from __future__ import annotations


class NodeNames:
    """Static node name constants for the trading-agents graph."""

    # Analyst nodes (parallel fan-out)
    MARKET_ANALYST = "Market Analyst"
    SOCIAL_ANALYST = "Social Analyst"
    NEWS_ANALYST = "News Analyst"
    FUNDAMENTALS_ANALYST = "Fundamentals Analyst"

    # Research debate loop
    BULL_RESEARCHER = "Bull Researcher"
    BEAR_RESEARCHER = "Bear Researcher"
    RESEARCH_MANAGER = "Research Manager"

    # Trading
    TRADER = "Trader"

    # Risk debate loop
    AGGRESSIVE_ANALYST = "Aggressive Analyst"
    NEUTRAL_ANALYST = "Neutral Analyst"
    CONSERVATIVE_ANALYST = "Conservative Analyst"

    # Final decision
    PORTFOLIO_MANAGER = "Portfolio Manager"


# Analyst key → node name — used for fan-out wiring and validation.
# Keep in sync with the NodeNames analyst constants above.
ANALYST_NODE_NAMES: dict[str, str] = {
    "market": NodeNames.MARKET_ANALYST,
    "social": NodeNames.SOCIAL_ANALYST,
    "news": NodeNames.NEWS_ANALYST,
    "fundamentals": NodeNames.FUNDAMENTALS_ANALYST,
}
