"""Relative valuation: peer-median multiples, implied prices, and bank/insurer ratios.

Pure functions over numbers. A multiple that is missing or not positive is left out
of a median (a negative P/E or EV/EBITDA is not a price anyone pays), never replaced.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

MULTIPLES = ("pe", "ev_ebitda", "ps", "pb")
LABELS = {"pe": "P/E", "ev_ebitda": "EV/EBITDA", "ps": "P/S", "pb": "P/B"}
MIN_PEERS = 3


def peer_median(values: list[float | None]) -> tuple[float | None, int]:
    """(median of the positive values, how many there were)."""
    usable = [v for v in values if v is not None and v > 0]
    return (statistics.median(usable) if usable else None), len(usable)


@dataclass(frozen=True)
class Implied:
    multiple: str
    own: float | None          # the company's own multiple at the price used
    peer_median: float | None
    peers_used: int
    implied_price: float | None
    reason: str = ""           # why there is no implied price


def implied_prices(price: float, target: dict, peers: list[dict], include_enterprise: bool) -> list[Implied]:
    """Each multiple's peer median and the price it implies for the company.

    Per-share price (main currency unit) is compared with per-share metrics:
      P/E       implied = median * EPS
      P/B       implied = median * book value per share
      P/S       implied = median * revenue / shares
      EV/EBITDA implied = (median * EBITDA - debt + cash) / shares
    The last two use figures in the reporting currency, so ``include_enterprise``
    must be False when that differs from the quote currency (no FX is applied).
    """
    eps, bvps = target.get("eps"), target.get("book_value_per_share")
    shares, revenue = target.get("shares"), target.get("revenue")
    ebitda = target.get("ebitda")
    debt, cash = target.get("total_debt") or 0.0, target.get("total_cash") or 0.0

    own = {
        "pe": price / eps if eps and eps > 0 else None,
        "pb": price / bvps if bvps and bvps > 0 else None,
        "ps": price * shares / revenue if include_enterprise and shares and revenue and revenue > 0 else None,
        "ev_ebitda": (price * shares + debt - cash) / ebitda
        if include_enterprise and shares and ebitda and ebitda > 0 else None,
    }
    out = []
    for key in MULTIPLES:
        median, n = peer_median([p.get(key) for p in peers])
        reason, implied = "", None
        if median is None:
            reason = "no peer has a positive multiple"
        elif key == "pe":
            implied, reason = (median * eps, "") if eps and eps > 0 else (None, "company EPS is not positive")
        elif key == "pb":
            implied, reason = (median * bvps, "") if bvps and bvps > 0 else (None, "company book value is not positive")
        elif not include_enterprise:
            reason = "company figures are in a different currency from the price (no FX applied)"
        elif key == "ps":
            implied, reason = ((median * revenue / shares, "") if shares and revenue and revenue > 0
                               else (None, "company revenue or share count is unavailable"))
        else:
            implied, reason = (((median * ebitda - debt + cash) / shares, "")
                               if shares and ebitda and ebitda > 0
                               else (None, "company EBITDA is not positive or share count is unavailable"))
        out.append(Implied(key, own[key], median, n, implied, reason))
    return out


@dataclass(frozen=True)
class BankRatios:
    book_value_per_share: float | None
    eps: float | None
    pb: float | None
    pe: float | None
    roe: float | None


def bank_ratios(price: float, equity: float | None, net_income: float | None, shares: float | None) -> BankRatios:
    """P/B, P/E and ROE from filed equity, net income and shares (a bank's own return on its book)."""
    bvps = equity / shares if equity is not None and shares else None
    eps = net_income / shares if net_income is not None and shares else None
    return BankRatios(
        book_value_per_share=bvps,
        eps=eps,
        pb=price / bvps if bvps and bvps > 0 else None,
        pe=price / eps if eps and eps > 0 else None,
        roe=net_income / equity if net_income is not None and equity and equity > 0 else None,
    )


def justified_pb(roe: float, cost_of_equity: float, growth: float) -> float | None:
    """Justified P/B = (ROE - g) / (Ke - g), the Gordon model on book value; None if Ke <= g."""
    if cost_of_equity - growth <= 0.005:
        return None
    return (roe - growth) / (cost_of_equity - growth)
