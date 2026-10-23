"""Offline point-in-time screening contracts, with no trading or web calls."""

from dataclasses import replace
from datetime import date, timedelta
from math import inf

import pytest

from tradingagents.paper.research_screener import (
    AsOfStock,
    DailyClose,
    ScreeningRules,
    shortlist,
)


ASOF = "2026-10-21"


def sample(ticker: str = "ALFA", gain: float = 0.45) -> AsOfStock:
    base = date.fromisoformat(ASOF) - timedelta(days=252)
    history = tuple(
        DailyClose((base + timedelta(days=i)).isoformat(),
                   30 * (1 + gain * i / 252), 50_000_000)
        for i in range(253)
    )
    return AsOfStock(ticker, ASOF, history, 15_000_000_000,
                     ASOF, "2026-12-01", ASOF)


def reasons(result):
    return {item.ticker: item.reason for item in result.exclusions}


def test_valid_stock_is_ranked_with_momentum_scores():
    result = shortlist([sample()], ASOF)
    assert [c.ticker for c in result.selected] == ["ALFA"]
    assert result.selected[0].momentum_12_1 > result.selected[0].momentum_6_1 > 0
    assert result.selected[0].score > 0


def test_stronger_stock_ranked_first_and_limit_applies():
    result = shortlist([sample("SLOW", .15), sample("FAST", .60)], ASOF,
                       ScreeningRules(max_shortlist=1))
    assert [c.ticker for c in result.selected] == ["FAST"]


def test_future_price_bar_is_rejected_even_if_stock_would_rank():
    a = sample()
    next_bar = DailyClose("2026-10-22", 1000, 50_000_000)
    bad = replace(a, history=a.history + (next_bar,))
    assert reasons(shortlist([bad], ASOF))[a.ticker] == "invalid_or_future_history"


def test_history_must_reach_exact_asof_not_yesterday():
    a = sample()
    bad = replace(a, history=a.history[:-1])
    assert reasons(shortlist([bad], ASOF))[a.ticker] == "insufficient_history"


def test_stale_market_cap_is_excluded():
    a = replace(sample(), market_cap_asof="2026-09-29")
    assert reasons(shortlist([a], ASOF))[a.ticker] == "stale_or_future_market_cap"


def test_future_market_cap_is_excluded():
    a = replace(sample(), market_cap_asof="2026-10-22")
    assert reasons(shortlist([a], ASOF))[a.ticker] == "stale_or_future_market_cap"


def test_earnings_week_blackout_and_unknown_earnings_excluded():
    a = sample()
    soon = replace(a, next_earnings_date="2026-10-26")
    unknown = replace(a, ticker="BETA", next_earnings_date=None)
    r = reasons(shortlist([soon, unknown], ASOF))
    assert r["ALFA"] == "earnings_blackout"
    assert r["BETA"] == "missing_or_future_earnings_calendar"


def test_future_discovered_earnings_date_excluded():
    a = replace(sample(), earnings_calendar_asof="2026-10-22")
    assert reasons(shortlist([a], ASOF))[a.ticker] == "missing_or_future_earnings_calendar"


def test_low_liquidity_rejected():
    a = sample()
    history = tuple(replace(bar, dollar_volume_usd=5_000_000) for bar in a.history)
    a = replace(a, history=history)
    assert reasons(shortlist([a], ASOF))[a.ticker] == "liquidity_below_floor"


def test_low_price_and_cap_rejected():
    a = replace(sample(), market_cap_usd=1_000_000_000)
    assert reasons(shortlist([a], ASOF))[a.ticker] == "market_cap_below_floor"
    b = sample("PENNY")
    b = replace(b, history=tuple(replace(x, adjusted_close_usd=x.adjusted_close_usd / 10)
                                 for x in b.history))
    assert reasons(shortlist([b], ASOF))[b.ticker] == "price_below_floor"


def test_falling_or_flat_stock_does_not_pass_positive_momentum():
    a = sample(gain=-.15)
    assert not shortlist([a], ASOF).selected


def test_duplicate_and_bad_price_do_not_pollute_results():
    a = sample()
    b = replace(sample("ERROR"), history=tuple(
        replace(x, adjusted_close_usd=inf) if i == 240 else x
        for i, x in enumerate(sample("ERROR").history)
    ))
    res = shortlist([a, a, b], ASOF)
    assert [c.ticker for c in res.selected] == ["ALFA"]
    assert set(reasons(res).values()) == {"duplicate_symbol", "invalid_prices_or_liquidity"}


def test_invalid_target_date_is_rejected():
    with pytest.raises(ValueError):
        shortlist([], "2026-10-32")
