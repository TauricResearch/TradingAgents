"""Map the 5-tier portfolio rating to an order side.

Buy/Overweight -> BUY, Sell/Underweight -> SELL, Hold -> no order.
"""

_BUY = {"buy", "overweight"}
_SELL = {"sell", "underweight"}


def rating_to_side(rating: str):
    """Return 'BUY', 'SELL', or None (Hold / unrecognised)."""
    r = rating.strip().lower()
    if r in _BUY:
        return "BUY"
    if r in _SELL:
        return "SELL"
    return None
