"""Pure trading rules for the paper broker — no I/O, unit-testable.

Sizing follows the rating's conviction: Buy is a full position (10% of
equity), Overweight a half position (5%). Sell exits fully, Underweight
trims half. Hold does nothing. These are deliberately mechanical — the paper
portfolio measures the *signals*, so execution must be rule-based, not
discretionary.
"""

import re

from app.domain import Market

# Position sizing by conviction AND category: core names (giants, index ETFs)
# are stable enough to hold big; satellites (screener finds) stay small
# because their volatility is the risk, whatever the rating says.
BUY_ALLOCATION = {
    "core":      {"Buy": 0.10, "Overweight": 0.05},
    "satellite": {"Buy": 0.05, "Overweight": 0.025},
}
SELL_FRACTION = {"Sell": 1.0, "Underweight": 0.5}    # fraction of the position

# Minimum order value; avoids dust positions when cash runs low.
MIN_ORDER_USD = 50.0

_LEVEL_RE = {
    "stop_loss": re.compile(r"\*\*Stop[- ]?Loss\*\*:?\s*\$?([\d,]+(?:\.\d+)?)", re.IGNORECASE),
    "price_target": re.compile(r"\*\*(?:Price )?Target\*\*:?\s*\$?([\d,]+(?:\.\d+)?)", re.IGNORECASE),
}

_REVIEW_RE = re.compile(r"\*\*Next Review\*\*:?\s*(\d+)\s*day", re.IGNORECASE)

# Bounds for the model-chosen re-analysis date; used as the fallback too.
REVIEW_MIN_DAYS = 3
REVIEW_MAX_DAYS = 21
REVIEW_DEFAULT_DAYS = 7


def parse_review_days(decision_text: str | None) -> int:
    """The analysis's own 'revisit me in N days', clamped; default when absent."""
    if decision_text:
        match = _REVIEW_RE.search(decision_text)
        if match:
            return max(REVIEW_MIN_DAYS, min(REVIEW_MAX_DAYS, int(match.group(1))))
    return REVIEW_DEFAULT_DAYS


def parse_level(decision_text: str | None, kind: str) -> float | None:
    """Extract a stop-loss or price-target level from the decision markdown.

    The Trader/Portfolio Manager render these as ``**Stop Loss**: 186.0`` /
    ``**Price Target**: 240`` when the model provides them; absent lines
    return None (the monitor then simply has no tripwire for the position).
    """
    if not decision_text:
        return None
    match = _LEVEL_RE[kind].search(decision_text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def currency_for_market(market: Market) -> str:
    return "INR" if market is Market.INDIA else "USD"


def buy_quantity(
    rating: str,
    equity_usd: float,
    cash_usd: float,
    price: float,
    usd_rate: float,
    category: str = "satellite",
) -> float:
    """Quantity to buy for a rating and category, capped by available cash.

    ``usd_rate`` is quote-currency units per USD (1.0 for USD, ~83 for INR).
    Fractional quantities are fine in a paper book. Returns 0 when the order
    would be below MIN_ORDER_USD. Unknown categories size like satellites —
    the cautious default.
    """
    pct = BUY_ALLOCATION.get(category, BUY_ALLOCATION["satellite"]).get(rating, 0.0)
    if pct <= 0 or price <= 0 or usd_rate <= 0:
        return 0.0
    alloc_usd = min(equity_usd * pct, cash_usd)
    if alloc_usd < MIN_ORDER_USD:
        return 0.0
    return (alloc_usd * usd_rate) / price


def sell_quantity(rating: str, held_quantity: float) -> float:
    return held_quantity * SELL_FRACTION.get(rating, 0.0)


# --- Transaction costs -------------------------------------------------------
# The paper broker charged NOTHING while the backtest charged 5bps/side, so
# every reported paper return was gross and the two were not comparable. That
# gap stops being cosmetic once the tactical rule can trade screener picks:
# a $200M nanocap does not cost what SPY costs, and a rule that round-trips
# ~30 times per name pays that spread on every leg.
#
# Figures are commission-free-broker reality: effective half-spread plus
# slippage, not headline commission. Deliberately conservative — under-charging
# flatters exactly the small, illiquid names the screener surfaces.
COST_BPS_LIQUID_ETF = 2      # SPY / VOO / QQQ — penny-wide, huge volume
COST_BPS_US_LARGE = 5        # mega-cap equities; matches the backtest gate
COST_BPS_US_SMALL = 25       # screener picks: wider spreads, thinner books
COST_BPS_INDIA = 35          # NSE: spread + STT + stamp duty + exchange fees
COST_BPS_CRYPTO = 10         # major pairs on a retail venue

_LIQUID_ETFS = frozenset({"SPY", "VOO", "QQQ", "IWM", "SSO", "JEPI", "GLD", "SLV", "AGG"})


def cost_bps(symbol: str, market: str, category: str = "satellite") -> float:
    """Round-trip-per-side cost in basis points for a paper fill.

    Keyed on what actually drives cost — venue and liquidity — rather than on
    the book placing the trade, so the same name costs the same everywhere.
    """
    sym = (symbol or "").upper()
    mkt = (market or "").lower()
    if sym in _LIQUID_ETFS:
        return COST_BPS_LIQUID_ETF
    if mkt == "crypto":
        return COST_BPS_CRYPTO
    if mkt == "india":
        return COST_BPS_INDIA
    # Screener picks are small caps by construction; core names are large caps.
    return COST_BPS_US_LARGE if category == "core" else COST_BPS_US_SMALL


def apply_cost(notional_usd: float, symbol: str, market: str, category: str = "satellite") -> float:
    """Cost in USD charged on one side of a fill."""
    return abs(notional_usd) * cost_bps(symbol, market, category) / 10_000
