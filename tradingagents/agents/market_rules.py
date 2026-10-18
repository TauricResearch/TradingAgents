"""Trading rules of the ticker's home exchange, for the agents' prompts.

The prompts otherwise assume a US-style market: exit any time, no daily price
limit, any share count, short selling allowed. Vietnam differs on each point, so
a plan written that way (a next-morning stop-loss, a short sale, an entry above
the day's ceiling price) is not one a Vietnamese account can carry out. Rules
are keyed by Yahoo's listing suffix; a market without a row adds nothing.
"""

from tradingagents.dataflows.symbols import normalize_symbol

_VIETNAM = (
    "Vietnam market rules (the plan must be executable by a Vietnamese account): "
    "prices are in VND. Settlement is T+2: shares bought on trading day T can be sold "
    "from the afternoon session of T+2 at the earliest, so no plan may exit the same day "
    "or the next. A stock may move at most 7% either way from its reference price (the "
    "previous close) in a session on HOSE, the exchange behind Yahoo's `.VN` listings "
    "(10% on HNX, 15% on UPCoM, wider on a first trading day); keep entries, stop-losses "
    "and next-session targets inside that band. A stop-loss is not guaranteed: on a "
    "limit-down day, sell orders at the floor price can stay unfilled for several "
    "sessions. Orders are in board lots of 100 shares, priced in ticks of 10, 50 or 100 "
    "VND (below 10,000; 10,000 to 49,950; 50,000 and above). Stocks cannot be sold "
    "short, so Sell or Underweight means reduce, exit or stay out, never open a short. "
    "On an ex-rights date (cash or stock dividend, bonus shares, rights issue) the "
    "reference price is cut, so that day's drop is an adjustment, not a selloff. Foreign "
    "ownership limits (30% at banks, commonly 49% elsewhere), foreign investors' net "
    "buying or selling, and index reviews (VN30 twice a year, FTSE, MSCI and ETF "
    "rebalances) drive flows. US data tools (FRED macro indicators, prediction markets) "
    "describe the US economy, not Vietnam's."
)

# Yahoo listing suffix -> the rules a plan for that market has to respect.
_RULES_BY_SUFFIX = {
    ".VN": _VIETNAM,
}


def market_rules(ticker: str) -> str:
    """Return the trading rules of ``ticker``'s home exchange, or "" when none are known."""
    symbol = normalize_symbol(ticker)
    for suffix, rules in _RULES_BY_SUFFIX.items():
        if symbol.endswith(suffix):
            return rules
    return ""
