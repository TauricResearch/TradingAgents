"""Black-Scholes value and greeks for European options, and implied volatility.

Used by the portfolio review to put listed options on the same footing as
shares: a value for the book and a delta that turns each contract into the
underlying exposure it carries. Listed US equity options are American, and no
dividend yield is modeled, so figures for deep in-the-money or dividend-heavy
contracts are approximations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DAYS_PER_YEAR = 365.0


def _cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


@dataclass
class Greeks:
    price: float
    delta: float
    gamma: float
    theta_per_day: float
    vega_per_point: float


def black_scholes(option_type: str, spot: float, strike: float, years: float,
                  rate: float, volatility: float) -> Greeks:
    """Per-share value and greeks. An expired contract is worth its intrinsic value."""
    call = option_type == "call"
    if years <= 0 or volatility <= 0:
        intrinsic = max(spot - strike, 0.0) if call else max(strike - spot, 0.0)
        return Greeks(intrinsic, 0.0, 0.0, 0.0, 0.0)
    root = volatility * math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * volatility ** 2) * years) / root
    d2 = d1 - root
    discount = math.exp(-rate * years)
    if call:
        price = spot * _cdf(d1) - strike * discount * _cdf(d2)
        delta = _cdf(d1)
        carry = -rate * strike * discount * _cdf(d2)
    else:
        price = strike * discount * _cdf(-d2) - spot * _cdf(-d1)
        delta = _cdf(d1) - 1
        carry = rate * strike * discount * _cdf(-d2)
    theta = -spot * _pdf(d1) * volatility / (2 * math.sqrt(years)) + carry
    return Greeks(
        price=price,
        delta=delta,
        gamma=_pdf(d1) / (spot * root),
        theta_per_day=theta / DAYS_PER_YEAR,
        vega_per_point=spot * _pdf(d1) * math.sqrt(years) / 100,
    )


def implied_volatility(option_type: str, price: float, spot: float, strike: float,
                       years: float, rate: float) -> float | None:
    """The volatility that reproduces ``price``, or None when no volatility can.

    A price below the no-arbitrage floor (a stale or crossed mark) has no
    implied volatility; the caller falls back to a modeled one.
    """
    if years <= 0 or price <= 0:
        return None
    low, high = 1e-4, 5.0
    if not (black_scholes(option_type, spot, strike, years, rate, low).price
            <= price <= black_scholes(option_type, spot, strike, years, rate, high).price):
        return None
    for _ in range(100):
        mid = (low + high) / 2
        if black_scholes(option_type, spot, strike, years, rate, mid).price < price:
            low = mid
        else:
            high = mid
        if high - low < 1e-6:
            break
    return (low + high) / 2
