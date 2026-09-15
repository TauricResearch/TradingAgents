"""Tests for the backtest portfolio simulator.

Every price series here is hand-built, so each assertion pins an exact figure
rather than whatever the market happened to do.
"""

import pandas as pd
import pytest

from tradingagents.backtest.portfolio import (
    DEFAULT_WEIGHTS,
    PortfolioConfig,
    simulate,
    simulate_multi,
    target_weight,
)

# Mon 2026-01-05 .. Fri 2026-01-09
WEEK = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]


def frame(dates=WEEK, opens=None, closes=None):
    """Build a daily OHLC frame; defaults to a flat series at 100."""
    opens = [100.0] * len(dates) if opens is None else opens
    closes = opens if closes is None else closes
    return pd.DataFrame(
        {"Open": opens, "Close": closes},
        index=pd.DatetimeIndex(pd.to_datetime(dates)),
    )


def free_config(**kwargs):
    """A config with no trading frictions, for testing sizing in isolation."""
    kwargs.setdefault("commission_bps", 0.0)
    kwargs.setdefault("slippage_bps", 0.0)
    return PortfolioConfig(**kwargs)


# ---------------------------------------------------------------------------
# Execution timing — the anti-look-ahead rule
# ---------------------------------------------------------------------------

def test_fill_happens_at_the_next_bar_not_the_decision_bar():
    """A decision dated D is built from data through D, so D's close is off limits."""
    result = simulate([("2026-01-05", "Buy")], frame(), free_config())

    assert [t["fill_date"] for t in result.trades] == ["2026-01-06"]
    # Still fully in cash when the decision bar closes.
    assert result.equity.loc["2026-01-05"] == pytest.approx(100_000.0)
    assert result.weights.loc["2026-01-05"] == pytest.approx(0.0)
    assert result.weights.loc["2026-01-06"] == pytest.approx(1.0)


def test_decision_bar_close_spike_is_not_captured():
    """The sharpest form of the same rule: a jump on the decision bar is missed."""
    # Flat at 100, then the decision bar closes at 200 and stays there.
    prices = frame(opens=[100, 100, 200, 200, 200], closes=[100, 200, 200, 200, 200])
    result = simulate([("2026-01-06", "Buy")], prices, free_config())

    # Filled at 2026-01-07's open of 200 — after the move, not before it.
    assert result.trades[0]["fill_price"] == pytest.approx(200.0)
    assert result.equity.iloc[-1] == pytest.approx(100_000.0)


def test_decision_on_a_non_trading_day_fills_at_the_next_bar():
    """Sat 2026-01-10 has no bar; the next open is Mon 2026-01-12."""
    prices = frame(dates=WEEK + ["2026-01-12", "2026-01-13"], opens=[100.0] * 7)
    result = simulate([("2026-01-10", "Buy")], prices, free_config())

    assert [t["fill_date"] for t in result.trades] == ["2026-01-12"]


def test_decision_after_the_last_bar_never_fills():
    result = simulate([("2026-02-01", "Buy")], frame(), free_config())

    assert result.trades == []
    assert result.equity.iloc[-1] == pytest.approx(100_000.0)


def test_decisions_sharing_a_date_with_a_none_rating_do_not_raise():
    """Sorting whole tuples would compare None against a string."""
    result = simulate(
        [("2026-01-05", None), ("2026-01-05", "Buy")], frame(), free_config()
    )

    assert result.weights.iloc[-1] in (0.0, 1.0)


def test_latest_decision_wins_when_several_map_to_one_fill_bar():
    """Two dates across a weekend fill on the same open; the later one saw more."""
    prices = frame(dates=["2026-01-09", "2026-01-12"], opens=[100.0, 100.0])
    result = simulate(
        [("2026-01-10", "Sell"), ("2026-01-11", "Buy")], prices, free_config()
    )

    assert len(result.trades) == 1
    assert result.trades[0]["rating"] == "Buy"


# ---------------------------------------------------------------------------
# Sizing and P&L
# ---------------------------------------------------------------------------

def test_buy_on_a_flat_series_returns_capital_minus_costs():
    result = simulate([("2026-01-05", "Buy")], frame(), PortfolioConfig())

    # A flat price series generates no P&L, so the accounting identity is exact:
    # everything lost is cost. 1bp commission + 5bp slippage = 6bp of notional.
    assert result.equity.iloc[-1] == pytest.approx(100_000.0 - result.total_costs)
    assert result.total_costs == pytest.approx(result.traded_notional * 0.0006)


def test_full_weight_buy_does_not_overdraw_cash():
    """Sizing must leave room for the commission, not borrow to pay it."""
    result = simulate([("2026-01-05", "Buy")], frame(), PortfolioConfig())

    assert (result.cash >= 0).all()
    assert result.weights.iloc[-1] == pytest.approx(1.0)


def test_cash_stays_non_negative_across_repeated_rebalances():
    result = simulate(
        [("2026-01-05", "Buy"), ("2026-01-06", "Sell"), ("2026-01-07", "Buy")],
        frame(),
        PortfolioConfig(),
    )

    assert (result.cash >= 0).all()


def test_full_weight_captures_the_full_move():
    prices = frame(opens=[100, 100, 100, 100, 100], closes=[100, 100, 100, 100, 200])
    result = simulate([("2026-01-05", "Buy")], prices, free_config())

    assert result.equity.iloc[-1] == pytest.approx(200_000.0)


def test_half_weight_captures_half_the_move():
    prices = frame(opens=[100, 100, 100, 100, 100], closes=[100, 100, 100, 100, 200])
    result = simulate([("2026-01-05", "Overweight")], prices, free_config())

    # 50% invested doubles; 50% stays in cash.
    assert result.equity.iloc[-1] == pytest.approx(150_000.0)


def test_costs_accrue_on_each_rebalance():
    result = simulate(
        [("2026-01-05", "Buy"), ("2026-01-07", "Sell")], frame(), PortfolioConfig()
    )

    # Two round trips, each charged on its own traded notional.
    assert len(result.trades) == 2
    assert result.total_costs == pytest.approx(
        sum(t["notional"] for t in result.trades) * 0.0006
    )
    assert result.equity.iloc[-1] == pytest.approx(100_000.0 - result.total_costs)


def test_turnover_is_notional_over_average_equity():
    result = simulate([("2026-01-05", "Buy")], frame(), free_config())

    assert result.traded_notional == pytest.approx(100_000.0)
    assert result.turnover == pytest.approx(100_000.0 / float(result.equity.mean()))


# ---------------------------------------------------------------------------
# Rating semantics
# ---------------------------------------------------------------------------

def test_hold_carries_the_position_by_default():
    """The Research Manager defines Hold as maintaining the current position."""
    result = simulate(
        [("2026-01-05", "Buy"), ("2026-01-07", "Hold")], frame(), free_config()
    )

    assert len(result.trades) == 1
    assert result.weights.iloc[-1] == pytest.approx(1.0)


def test_hold_exits_under_the_flat_policy():
    result = simulate(
        [("2026-01-05", "Buy"), ("2026-01-07", "Hold")],
        frame(),
        free_config(hold_policy="flat"),
    )

    assert len(result.trades) == 2
    assert result.weights.iloc[-1] == pytest.approx(0.0)


def test_review_never_trades():
    """REVIEW is not a tradeable rating — it flags output needing a human (#1170)."""
    result = simulate(
        [("2026-01-05", "Buy"), ("2026-01-07", "REVIEW")], frame(), free_config()
    )

    assert len(result.trades) == 1
    assert result.weights.iloc[-1] == pytest.approx(1.0)


def test_unknown_rating_carries_rather_than_liquidating():
    result = simulate(
        [("2026-01-05", "Buy"), ("2026-01-07", "Strong Buy")], frame(), free_config()
    )

    assert len(result.trades) == 1
    assert result.weights.iloc[-1] == pytest.approx(1.0)


def test_bearish_ratings_clamp_to_flat_when_shorting_is_off():
    result = simulate([("2026-01-05", "Sell")], frame(), free_config())

    assert result.trades == []
    assert result.weights.iloc[-1] == pytest.approx(0.0)


def test_bearish_ratings_go_short_when_shorting_is_on():
    prices = frame(opens=[100, 100, 100, 100, 100], closes=[100, 100, 100, 100, 50])
    result = simulate(
        [("2026-01-05", "Sell")], prices, free_config(allow_short=True)
    )

    assert result.weights.iloc[-1] == pytest.approx(-1.0)
    # Short a full sleeve into a 50% drop: +50,000.
    assert result.equity.iloc[-1] == pytest.approx(150_000.0)


@pytest.mark.parametrize("rating,previous,expected", [
    ("Buy", 0.0, 1.0),
    ("Overweight", 0.0, 0.5),
    ("Hold", 0.7, 0.7),
    ("Underweight", 0.5, 0.0),   # clamped, long-only
    ("Sell", 0.5, 0.0),          # clamped, long-only
    ("REVIEW", 0.3, 0.3),
    (None, 0.3, 0.3),
])
def test_target_weight_mapping(rating, previous, expected):
    assert target_weight(rating, previous, PortfolioConfig()) == pytest.approx(expected)


def test_default_weights_cover_the_five_tier_scale():
    from tradingagents.agents.utils.rating import RATINGS_5_TIER

    assert set(DEFAULT_WEIGHTS) == set(RATINGS_5_TIER)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def test_missing_price_columns_raise():
    bad = pd.DataFrame({"Close": [1.0]}, index=pd.DatetimeIndex(["2026-01-05"]))
    with pytest.raises(ValueError, match="missing required column"):
        simulate([], bad)


def test_non_datetime_index_raises():
    bad = pd.DataFrame({"Open": [1.0], "Close": [1.0]}, index=["2026-01-05"])
    with pytest.raises(ValueError, match="DatetimeIndex"):
        simulate([], bad)


def test_empty_price_frame_yields_empty_result():
    empty = pd.DataFrame({"Open": [], "Close": []}, index=pd.DatetimeIndex([]))
    result = simulate([("2026-01-05", "Buy")], empty)

    assert len(result.equity) == 0
    assert result.trades == []


def test_bars_with_missing_prices_are_dropped():
    prices = frame(opens=[100.0, None, 100.0, 100.0, 100.0])
    result = simulate([("2026-01-05", "Buy")], prices, free_config())

    assert len(result.equity) == 4
    assert not result.equity.isna().any()


@pytest.mark.parametrize("kwargs", [
    {"hold_policy": "maybe"},
    {"initial_cash": 0},
    {"commission_bps": -1},
])
def test_invalid_config_raises(kwargs):
    with pytest.raises(ValueError):
        PortfolioConfig(**kwargs)


def test_timezone_aware_prices_are_normalized():
    """yfinance returns tz-aware bars; decision dates are plain yyyy-mm-dd."""
    prices = frame()
    prices.index = prices.index.tz_localize("America/New_York")
    result = simulate([("2026-01-05", "Buy")], prices, free_config())

    assert [t["fill_date"] for t in result.trades] == ["2026-01-06"]


# ---------------------------------------------------------------------------
# Multi-ticker sleeves
# ---------------------------------------------------------------------------

def test_sleeves_split_capital_evenly():
    prices = frame()
    combined, per_ticker = simulate_multi(
        {"NVDA": [("2026-01-05", "Buy")], "AAPL": [("2026-01-05", "Buy")]},
        {"NVDA": prices, "AAPL": prices},
        free_config(),
    )

    assert set(per_ticker) == {"AAPL", "NVDA"}
    assert per_ticker["NVDA"].equity.iloc[-1] == pytest.approx(50_000.0)
    assert combined.equity.iloc[-1] == pytest.approx(100_000.0)


def test_sleeve_gains_combine():
    flat = frame()
    doubler = frame(opens=[100, 100, 100, 100, 100], closes=[100, 100, 100, 100, 200])
    combined, _ = simulate_multi(
        {"NVDA": [("2026-01-05", "Buy")], "AAPL": [("2026-01-05", "Buy")]},
        {"NVDA": doubler, "AAPL": flat},
        free_config(),
    )

    # NVDA sleeve doubles to 100,000; AAPL sleeve stays at 50,000.
    assert combined.equity.iloc[-1] == pytest.approx(150_000.0)


def test_sleeve_with_a_shut_market_is_forward_filled():
    """One ticker missing a bar must not dent the combined curve."""
    full = frame()
    short = frame(dates=["2026-01-05", "2026-01-06", "2026-01-08", "2026-01-09"],
                  opens=[100.0] * 4)
    combined, _ = simulate_multi(
        {"NVDA": [("2026-01-05", "Buy")], "AAPL": [("2026-01-05", "Buy")]},
        {"NVDA": full, "AAPL": short},
        free_config(),
    )

    assert len(combined.equity) == 5
    assert combined.equity.loc["2026-01-07"] == pytest.approx(100_000.0)


def test_tickers_without_prices_are_skipped():
    combined, per_ticker = simulate_multi(
        {"NVDA": [("2026-01-05", "Buy")], "NOPRICE": [("2026-01-05", "Buy")]},
        {"NVDA": frame()},
        free_config(),
    )

    assert set(per_ticker) == {"NVDA"}
    assert combined.equity.iloc[-1] == pytest.approx(100_000.0)


def test_multi_with_no_usable_tickers_is_empty():
    combined, per_ticker = simulate_multi({"NVDA": []}, {}, free_config())

    assert per_ticker == {}
    assert len(combined.equity) == 0
