"""Deterministic *research-only* stock shortlist, never an execution instruction.

Every input snapshot carries a point-in-time observation date. This validates
ordering and known-as-of cutoffs; it CANNOT certify a vendor's historical
membership, split adjustments, fundamental revisions or filing publication times.

It deliberately does not alter the existing live-forward paper CLI. A proposed
candidate must still pass an independent, evidence-grounded AI investment review,
portfolio risk limits and a separately approved integration test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite


@dataclass(frozen=True)
class ScreeningRules:
    """Research hypotheses, not fitted parameters or evidence of alpha."""

    min_price_usd: float = 10.0
    min_market_cap_usd: float = 2_000_000_000.0
    min_avg_daily_dollar_volume_usd: float = 20_000_000.0
    max_market_cap_age_days: int = 10
    earnings_blackout_calendar_days: int = 7
    max_shortlist: int = 12
    # Cross-sectional momentum: last 6/12 months omitting newest 21 sessions.
    weight_six_minus_one: float = 0.60
    weight_twelve_minus_one: float = 0.40


@dataclass(frozen=True)
class DailyClose:
    session: str
    adjusted_close_usd: float
    dollar_volume_usd: float


@dataclass(frozen=True)
class AsOfStock:
    ticker: str
    asof: str
    history: tuple[DailyClose, ...]
    market_cap_usd: float
    market_cap_asof: str
    next_earnings_date: str | None
    earnings_calendar_asof: str | None


@dataclass(frozen=True)
class Candidate:
    ticker: str
    score: float
    momentum_6_1: float
    momentum_12_1: float
    avg_dollar_volume_usd: float
    price_usd: float
    moving_average_200: float


@dataclass(frozen=True)
class Exclusion:
    ticker: str
    reason: str


@dataclass(frozen=True)
class ScreenResult:
    asof: str
    selected: tuple[Candidate, ...]
    exclusions: tuple[Exclusion, ...]


def _date(value: str) -> date | None:
    try:
        parsed = date.fromisoformat(value)
        return parsed if parsed.isoformat() == value else None
    except (TypeError, ValueError):
        return None


def _valid_positive(value: float) -> bool:
    return isinstance(value, (int, float)) and isfinite(value) and value > 0


def evaluate(snapshot: AsOfStock, asof: str, rules: ScreeningRules) -> tuple[Candidate | None, str | None]:
    """Fail closed on missing/stale/non-point-in-time required observations."""

    day = _date(asof)
    if day is None or snapshot.asof != asof:
        return None, "wrong_asof_date"
    if not snapshot.ticker or not all(c.isalnum() or c in '.-' for c in snapshot.ticker):
        return None, "invalid_symbol"
    history = snapshot.history
    if len(history) < 253:
        return None, "insufficient_history"
    sessions = [_date(bar.session) for bar in history]
    if any(x is None for x in sessions) or sessions != sorted(set(sessions)) or sessions[-1] != day:
        return None, "invalid_or_future_history"
    if any(not _valid_positive(bar.adjusted_close_usd)
           or not _valid_positive(bar.dollar_volume_usd) for bar in history):
        return None, "invalid_prices_or_liquidity"
    cap_asof = _date(snapshot.market_cap_asof)
    if (cap_asof is None or cap_asof > day
            or (day - cap_asof).days > rules.max_market_cap_age_days):
        return None, "stale_or_future_market_cap"
    if not _valid_positive(snapshot.market_cap_usd) or snapshot.market_cap_usd < rules.min_market_cap_usd:
        return None, "market_cap_below_floor"
    price = history[-1].adjusted_close_usd
    if price < rules.min_price_usd:
        return None, "price_below_floor"
    adv = sum(bar.dollar_volume_usd for bar in history[-20:]) / 20
    if adv < rules.min_avg_daily_dollar_volume_usd:
        return None, "liquidity_below_floor"
    calendar_asof = _date(snapshot.earnings_calendar_asof)
    earnings = _date(snapshot.next_earnings_date) if snapshot.next_earnings_date else None
    if (calendar_asof is None or earnings is None or calendar_asof > day or earnings < day):
        return None, "missing_or_future_earnings_calendar"
    if (earnings - day).days <= rules.earnings_blackout_calendar_days:
        return None, "earnings_blackout"
    ma_200 = sum(bar.adjusted_close_usd for bar in history[-200:]) / 200
    if not price > ma_200:
        return None, "below_200_session_average"
    # Reference close 21 sessions before the decision, and 126/252 sessions back.
    # The most recent month is omitted from both momentum signals.
    p_skip = history[-22].adjusted_close_usd
    p_6 = history[-127].adjusted_close_usd
    p_12 = history[-253].adjusted_close_usd
    mom6 = p_skip / p_6 - 1
    mom12 = p_skip / p_12 - 1
    if mom6 <= 0 or mom12 <= 0:
        return None, "nonpositive_intermediate_momentum"
    score = rules.weight_six_minus_one * mom6 + rules.weight_twelve_minus_one * mom12
    return Candidate(snapshot.ticker, score, mom6, mom12, adv, price, ma_200), None


def shortlist(snapshots: list[AsOfStock], asof: str,
              rules: ScreeningRules = ScreeningRules()) -> ScreenResult:
    """Produce a traceable, ranked shortlist without calling any model or broker.

    Input membership must itself be historical point-in-time data: feeding today's
    S&P 500 constituents into old dates creates survivorship bias.
    """

    if _date(asof) is None:
        raise ValueError("asof must be a canonical YYYY-MM-DD date")
    if rules.max_shortlist <= 0 or not (0 <= rules.weight_six_minus_one <= 1):
        raise ValueError("invalid screening rules")
    if abs(rules.weight_six_minus_one + rules.weight_twelve_minus_one - 1) > 1e-9:
        raise ValueError("momentum weights must sum to one")
    seen: set[str] = set()
    selected: list[Candidate] = []
    excluded: list[Exclusion] = []
    for item in snapshots:
        normalized = item.ticker.upper()
        if normalized in seen:
            excluded.append(Exclusion(item.ticker, "duplicate_symbol"))
            continue
        seen.add(normalized)
        candidate, reason = evaluate(item, asof, rules)
        if reason:
            excluded.append(Exclusion(item.ticker, reason))
        else:
            assert candidate is not None
            selected.append(candidate)
    ranked = sorted(selected, key=lambda candidate: (-candidate.score, candidate.ticker))
    return ScreenResult(asof, tuple(ranked[:rules.max_shortlist]), tuple(excluded))
