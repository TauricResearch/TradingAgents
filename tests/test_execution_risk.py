"""Unit tests for the RiskGuard (tradingagents/execution/risk.py).

Everything is offline: the audit log lives in ``tmp_path``, prices come from
an injected ``price_of`` mapping, and the UTC clock is frozen by monkeypatching
``risk._utc_now`` (the single seam for both day scoping and written halt
timestamps). No network, no filesystem outside tmp_path.

The FIFO interpretation (buys open lots per ticker, sells consume the oldest
across days, unknown-basis sells are skipped) is pinned by these tests on
purpose: it is the documented stand-in for order-level buy/sell matching that
the L1 audit cannot provide.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import tradingagents.execution.risk as risk
from tradingagents.execution.risk import RiskDecision, RiskGuard, RiskLimits
from tradingagents.portfolio import PortfolioContext, Position

pytestmark = pytest.mark.unit

FROZEN_NOW = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)
TOMORROW = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)


def freeze(monkeypatch, moment):
    monkeypatch.setattr(risk, "_utc_now", lambda: moment)


def write_events(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")


def read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def guard(limits=None, prices=None) -> RiskGuard:
    return RiskGuard(
        limits=limits,
        price_of=(lambda ticker: (prices or {}).get(ticker)),
    )


def plan(side="buy", cost=250.0, ticker="BTC-USD", market="spot", leverage=1.0, quantity=0.005):
    """A minimal planned-order stand-in (duck-typed like PlannedOrder)."""
    from types import SimpleNamespace

    return SimpleNamespace(
        side=side, cost=cost, ticker=ticker, market=market, leverage=leverage, quantity=quantity
    )


def ts(day=FROZEN_NOW, hour=10) -> str:
    return day.replace(hour=hour).isoformat()


def event(action, qty, price, ticker="BTC-USD", day=FROZEN_NOW, hour=10):
    return {"timestamp": ts(day, hour), "ticker": ticker, "action": action, "qty": qty, "price_est": price}


# --- halt sticky / reset / day rollover ------------------------------------


def test_halt_is_sticky_across_checks_and_reset_clears_it(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [{"event": "halt", "timestamp": ts(), "reason": "streak"}])
    g = guard()
    for _ in range(3):  # sticky: every later check today stays halted
        decision = g.check(plan(), PortfolioContext(cash=1_000.0), audit)
        assert decision.halted is True
        assert decision.allowed is False
    g.reset_halt(audit)
    decision = g.check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is False
    assert decision.allowed is True


def test_halt_expires_when_the_utc_day_rolls_over(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [{"event": "halt", "timestamp": ts(), "reason": "streak"}])
    g = guard()
    assert g.check(plan(), PortfolioContext(cash=1_000.0), audit).halted is True
    freeze(monkeypatch, TOMORROW)  # next UTC day: the halt self-expires
    assert g.check(plan(), PortfolioContext(cash=1_000.0), audit).halted is False


def test_reset_halt_stays_reset_for_the_forgiven_breach(tmp_path, monkeypatch):
    # The operator's reset must be an effective exit (FR-K3): the three
    # losses that caused the halt are already-forgiven history, so the next
    # checks must not re-fire the halt for the same breach (previously the
    # full-history streak walk re-appended the halt right after the reset).
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [
        event("buy", 1.0, 100.0, hour=8),
        event("sell", 1.0, 90.0, hour=9),
        event("buy", 1.0, 100.0, hour=9),
        event("sell", 1.0, 80.0, hour=10),
        event("buy", 1.0, 100.0, hour=10),
        event("sell", 1.0, 70.0, hour=11),
    ])
    g = guard()
    assert g.check(plan(), PortfolioContext(cash=1_000.0), audit).halted is True
    g.reset_halt(audit)  # frozen at 12:00, after every loss above
    second = g.check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert second.halted is False
    assert second.allowed is True
    third = g.check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert third.halted is False
    halts = [e for e in read_events(audit) if e.get("event") == "halt"]
    assert len(halts) == 1  # the forgiven breach never re-appends a halt


def test_new_losses_after_reset_halt_again(tmp_path, monkeypatch):
    # The reset is not a permanent kill-switch bypass: losses AFTER the
    # reset build a fresh streak and halt again once they reach the limit.
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [
        event("buy", 1.0, 100.0, hour=8),
        event("sell", 1.0, 90.0, hour=9),
        event("buy", 1.0, 100.0, hour=9),
        event("sell", 1.0, 80.0, hour=10),
        event("buy", 1.0, 100.0, hour=10),
        event("sell", 1.0, 70.0, hour=11),
    ])
    g = guard()
    assert g.check(plan(), PortfolioContext(cash=1_000.0), audit).halted is True
    g.reset_halt(audit)  # 12:00
    write_events(audit, [
        event("buy", 1.0, 100.0, hour=13),
        event("sell", 1.0, 90.0, hour=13),
        event("buy", 1.0, 100.0, hour=14),
        event("sell", 1.0, 80.0, hour=14),
        event("buy", 1.0, 100.0, hour=15),
        event("sell", 1.0, 70.0, hour=15),
    ])
    decision = g.check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is True
    halts = [e for e in read_events(audit) if e.get("event") == "halt"]
    assert len(halts) == 2


def test_daily_loss_breach_after_reset_can_halt_again(tmp_path, monkeypatch):
    # Same rule for the daily-loss cap: the forgiven pre-reset loss does not
    # re-fire, but a NEW post-reset loss beyond the cap does.
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    # pre-reset: bought and sold today, realized -60 on equity 1000 = 6%
    write_events(audit, [
        event("buy", 2.0, 100.0, hour=8),
        event("sell", 2.0, 70.0, hour=9),
    ])
    g = guard()
    assert g.check(plan(), PortfolioContext(cash=1_000.0), audit).halted is True
    g.reset_halt(audit)  # 12:00
    # post-reset: a fresh -60 round-trip (hours after the reset)
    write_events(audit, [
        event("buy", 2.0, 100.0, hour=13),
        event("sell", 2.0, 70.0, hour=14),
    ])
    decision = g.check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is True
    assert "daily loss" in decision.reason
    halts = [e for e in read_events(audit) if e.get("event") == "halt"]
    assert len(halts) == 2


def test_breach_halt_expires_the_next_utc_day(tmp_path, monkeypatch):
    # (c) a guard-appended breach halt self-expires when the UTC day rolls.
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [
        event("buy", 1.0, 100.0, hour=8),
        event("sell", 1.0, 90.0, hour=9),
        event("buy", 1.0, 100.0, hour=9),
        event("sell", 1.0, 80.0, hour=10),
        event("buy", 1.0, 100.0, hour=10),
        event("sell", 1.0, 70.0, hour=11),
    ])
    g = guard()
    assert g.check(plan(), PortfolioContext(cash=1_000.0), audit).halted is True
    freeze(monkeypatch, TOMORROW)
    decision = g.check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is False
    assert decision.allowed is True


def test_consecutive_loss_breach_appends_exactly_one_halt_and_halts(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    # three losing sells, each matched FIFO against an earlier buy
    write_events(audit, [
        event("buy", 1.0, 100.0, hour=8),
        event("sell", 1.0, 90.0, hour=9),
        event("buy", 1.0, 100.0, hour=9),
        event("sell", 1.0, 80.0, hour=10),
        event("buy", 1.0, 100.0, hour=10),
        event("sell", 1.0, 70.0, hour=11),
    ])
    g = guard()
    decision = g.check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is True
    assert decision.allowed is False
    assert "consecutive" in decision.reason
    halts = [e for e in read_events(audit) if e.get("event") == "halt"]
    assert len(halts) == 1  # one breach -> one halt line, not one per check


def test_profitable_sell_ends_the_loss_streak(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [
        event("buy", 1.0, 100.0, hour=8),
        event("sell", 1.0, 90.0, hour=9),   # loss
        event("buy", 1.0, 100.0, hour=9),
        event("sell", 1.0, 110.0, hour=10),  # win ends the walk
        event("buy", 1.0, 100.0, hour=10),
        event("sell", 1.0, 95.0, hour=11),   # loss, but streak is 1
    ])
    decision = guard().check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is False
    assert decision.allowed is True


def test_unknown_basis_sells_are_skipped_not_counted(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    # a sell with no open lot (position predates the log) must neither count
    # as a loss nor break the streak of the two classified losses
    write_events(audit, [
        event("sell", 0.4, 50_000.0, ticker="ETH-USD", hour=7),  # unknown basis
        event("buy", 1.0, 100.0, hour=8),
        event("sell", 1.0, 90.0, hour=9),   # loss 1
        event("buy", 1.0, 100.0, hour=9),
        event("sell", 1.0, 85.0, hour=10),  # loss 2
    ])
    decision = guard(RiskLimits(max_consecutive_loss_count=2)).check(
        plan(), PortfolioContext(cash=1_000.0), audit
    )
    assert decision.halted is True
    assert "2 consecutive" in decision.reason


def test_streak_counts_across_days(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    yesterday = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
    write_events(audit, [
        event("buy", 1.0, 100.0, day=yesterday, hour=8),
        event("sell", 1.0, 90.0, day=yesterday, hour=9),   # loss yesterday
        event("buy", 1.0, 100.0, hour=8),
        event("sell", 1.0, 85.0, hour=9),                  # loss today
        event("buy", 1.0, 100.0, hour=10),
        event("sell", 1.0, 80.0, hour=11),                 # loss today -> 3
    ])
    decision = guard().check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is True


# --- daily loss (FR-K4) ----------------------------------------------------


def test_daily_loss_beyond_the_cap_halts(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    # bought and sold today: realized -60 on equity 1000 = 6% > 5%
    write_events(audit, [
        event("buy", 2.0, 100.0, hour=8),
        event("sell", 2.0, 70.0, hour=9),
    ])
    decision = guard().check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is True
    assert "daily loss" in decision.reason


def test_daily_loss_at_or_under_the_cap_passes(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [
        event("buy", 2.0, 100.0, hour=8),
        event("sell", 2.0, 76.0, hour=9),  # -48 on 1000 = 4.8% <= 5%
    ])
    decision = guard().check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is False
    assert decision.allowed is True


def test_unrealized_pnl_on_lots_opened_today_is_marked_via_price_of(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [event("buy", 2.0, 100.0, hour=8)])  # still open
    # marked at 70: unrealized -60 on equity 1000 = 6% > 5% -> halt
    decision = guard(prices={"BTC-USD": 70.0}).check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is True
    assert "daily loss" in decision.reason


def test_lots_opened_before_today_are_not_marked_into_daily_pnl(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    yesterday = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
    write_events(audit, [event("buy", 2.0, 100.0, day=yesterday, hour=8)])
    # the open lot predates today: even a big mark-down today is not "today's loss"
    decision = guard(prices={"BTC-USD": 10.0}).check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is False
    assert decision.allowed is True


# --- short P&L (derivatives lines carry market="derivatives") -----------------


def test_covered_short_loss_reaches_the_daily_loss_cap(tmp_path, monkeypatch):
    # Short opened at 70 and covered at 100 loses (70-100)*2 = -60 = 6% of
    # equity: the FIFO matcher must register it via the audit line's
    # market="derivatives" (as bridge._audit writes) and halt the day.
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [
        {**event("sell", 2.0, 70.0, hour=8), "market": "derivatives"},  # opens the short
        {**event("buy", 2.0, 100.0, hour=9), "market": "derivatives"},  # covers it
    ])
    decision = guard().check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is True
    assert "daily loss" in decision.reason


def test_covered_short_loss_feeds_the_consecutive_loss_streak(tmp_path, monkeypatch):
    # Two losing longs then a LOSING short: the matcher must see the short's
    # cover as a third loss -- without short matching, sells never reach the
    # streak walk and the third loss is invisible.
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [
        event("buy", 1.0, 100.0, hour=7),
        event("sell", 1.0, 90.0, hour=8),    # long loss 1
        event("buy", 1.0, 100.0, hour=8),
        event("sell", 1.0, 85.0, hour=9),    # long loss 2
        {**event("sell", 1.0, 100.0, hour=9), "market": "derivatives"},  # open short
        {**event("buy", 1.0, 110.0, hour=10), "market": "derivatives"},  # cover: -10
    ])
    decision = guard().check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is True
    assert "consecutive" in decision.reason


def test_covered_short_win_ends_the_consecutive_loss_streak(tmp_path, monkeypatch):
    # A PROFITABLE short (+10: covered lower than opened) ends the walk: two
    # long losses + a winning short must not halt at a limit of 2.
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [
        event("buy", 1.0, 100.0, hour=7),
        event("sell", 1.0, 90.0, hour=8),    # long loss 1
        event("buy", 1.0, 100.0, hour=8),
        event("sell", 1.0, 85.0, hour=9),    # long loss 2
        {**event("sell", 1.0, 100.0, hour=9), "market": "derivatives"},  # open short
        {**event("buy", 1.0, 90.0, hour=10), "market": "derivatives"},   # cover: +10
    ])
    decision = guard(RiskLimits(max_consecutive_loss_count=2)).check(
        plan(), PortfolioContext(cash=1_000.0), audit
    )
    assert decision.halted is False
    assert decision.allowed is True


def test_open_short_is_marked_into_daily_pnl(tmp_path, monkeypatch):
    # Short opened today at 70, marked now at 100: unrealized (70-100)*2 = -60.
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [
        {**event("sell", 2.0, 70.0, hour=8), "market": "derivatives"},
    ])
    decision = guard(prices={"BTC-USD": 100.0}).check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is True
    assert "daily loss" in decision.reason


def test_legacy_lines_without_market_never_open_shorts(tmp_path, monkeypatch):
    # A sell with no market field (a pre-derivatives log line) stays an
    # unknown-basis close: it must not become a short lot a later buy closes.
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [
        event("sell", 2.0, 70.0, hour=8),
        event("buy", 2.0, 100.0, hour=9),
    ])
    decision = guard(prices={"BTC-USD": 100.0}).check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is False
    assert decision.allowed is True


# --- fail-open when equity is not computable --------------------------------


def test_equity_unknown_skips_pct_checks_but_halt_still_fires(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    g = guard()
    # no portfolio at all: percentage checks are skipped, decision is allowed
    skipped = g.check(plan(), None, audit)
    assert skipped.allowed is True
    assert skipped.halted is False
    assert "fail-open" in skipped.reason
    # ... but a consecutive-loss breach still halts without any denominator
    write_events(audit, [
        event("buy", 1.0, 100.0, hour=8),
        event("sell", 1.0, 90.0, hour=9),
        event("buy", 1.0, 100.0, hour=9),
        event("sell", 1.0, 80.0, hour=10),
        event("buy", 1.0, 100.0, hour=10),
        event("sell", 1.0, 70.0, hour=11),
    ])
    halted = g.check(plan(), None, audit)
    assert halted.halted is True


def test_unmarkable_price_only_makes_checks_stricter(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    book = PortfolioContext(cash=1_000.0, positions=[Position(ticker="BTC-USD", quantity=1.0)])
    # BTC cannot be marked: it counts 0 in equity (400 instead of 45400), so a
    # 250 buy is 62.5% of equity and breaches the 25% per-asset cap
    decision = guard().check(plan(cost=250.0), book, audit)
    assert decision.allowed is False
    assert "per-asset" in decision.reason


# --- per-asset and total exposure caps --------------------------------------


def test_buy_within_per_asset_and_exposure_caps_passes(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    book = PortfolioContext(cash=1_000.0)
    decision = guard(prices={"BTC-USD": 50_000.0}).check(plan(cost=250.0), book, audit)
    assert decision.allowed is True
    assert decision.halted is False


def test_buy_breaching_per_asset_cap_is_rejected(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    book = PortfolioContext(cash=1_000.0, positions=[Position(ticker="BTC-USD", quantity=0.01)])
    # existing 0.01 x 50000 = 500 (50%) + plan 250 (25%) = 75% > 25%
    decision = guard(prices={"BTC-USD": 50_000.0}).check(plan(cost=250.0), book, audit)
    assert decision.allowed is False
    assert decision.halted is False
    assert "per-asset" in decision.reason


def test_buy_breaching_total_exposure_cap_is_rejected(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    book = PortfolioContext(
        cash=1_000.0,
        positions=[Position(ticker="ETH-USD", quantity=10.0)],
    )
    # equity = 1000 + 10 x 75 = 1750; exposure = (750 + 700)/1750 = 82.9% > 80%
    decision = guard(prices={"ETH-USD": 75.0}).check(plan(cost=700.0), book, audit)
    assert decision.allowed is False
    assert "total exposure" in decision.reason


def test_sell_plans_bypass_position_and_exposure_caps(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    book = PortfolioContext(cash=1_000.0, positions=[Position(ticker="BTC-USD", quantity=1.0)])
    decision = guard(prices={"BTC-USD": 50_000.0}).check(
        plan(side="sell", cost=None, quantity=1.0), book, audit
    )
    assert decision.allowed is True


# --- derivatives-specific caps ----------------------------------------------


def test_derivatives_leverage_above_cap_is_rejected(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    decision = guard().check(
        plan(cost=100.0, market="derivatives", leverage=5.0),
        PortfolioContext(cash=1_000.0),
        audit,
    )
    assert decision.allowed is False
    assert "leverage" in decision.reason


def test_derivatives_notional_above_zero_default_cap_is_rejected(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    # default max_derivatives_exposure_pct is 0.0: any derivatives notional breaches
    decision = guard().check(
        plan(cost=100.0, market="derivatives", leverage=1.0),
        PortfolioContext(cash=1_000.0),
        audit,
    )
    assert decision.allowed is False
    assert "derivatives notional" in decision.reason


def test_derivatives_within_raised_caps_passes(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    limits = RiskLimits(max_derivatives_leverage=3.0, max_derivatives_exposure_pct=50.0)
    # per-asset now sees the NOTIONAL for derivatives (50 x 3 = 150 = 15% of
    # equity 1000, <= 25); total exposure 15% (<= 80), derivatives notional
    # 15% (<= 50)
    decision = guard(limits).check(
        plan(cost=50.0, market="derivatives", leverage=3.0),
        PortfolioContext(cash=1_000.0),
        audit,
    )
    assert decision.allowed is True


# --- derivatives caps on every side (shorts included) ------------------------


def test_default_guard_refuses_a_derivatives_short(tmp_path, monkeypatch):
    # The P0 probe: a 50x short sailed through the buy-only cap branch. A
    # sell on derivatives OPENS a short, so every cap must evaluate for it.
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    decision = guard().check(
        plan(side="sell", cost=10.0, market="derivatives", leverage=50.0),
        PortfolioContext(cash=1_000.0),
        audit,
    )
    assert decision.allowed is False
    assert decision.halted is False
    assert "leverage" in decision.reason
    assert "derivatives notional" in decision.reason


def test_derivatives_short_leverage_above_cap_is_rejected(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    limits = RiskLimits(max_derivatives_leverage=3.0, max_derivatives_exposure_pct=1000.0)
    decision = guard(limits).check(
        plan(side="sell", cost=100.0, market="derivatives", leverage=5.0),
        PortfolioContext(cash=1_000.0),
        audit,
    )
    assert decision.allowed is False
    assert "leverage" in decision.reason


def test_derivatives_short_notional_above_cap_is_rejected(tmp_path, monkeypatch):
    # The margin is 25% of equity, but a short's exposure is its notional:
    # 250 x 5 = 1250 = 125% of equity breaches the 100% cap (abs notional --
    # a short's sign must not hide it).
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    limits = RiskLimits(max_derivatives_leverage=5.0, max_derivatives_exposure_pct=100.0)
    decision = guard(limits).check(
        plan(side="sell", cost=250.0, market="derivatives", leverage=5.0),
        PortfolioContext(cash=1_000.0),
        audit,
    )
    assert decision.allowed is False
    assert "derivatives notional" in decision.reason


def test_derivatives_short_within_raised_caps_passes(tmp_path, monkeypatch):
    # Caps are not a blanket short ban: the mirror of the long case passes
    # (per-asset sees the notional: 50 x 3 = 150 = 15% <= 25).
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    limits = RiskLimits(max_derivatives_leverage=3.0, max_derivatives_exposure_pct=50.0)
    decision = guard(limits).check(
        plan(side="sell", cost=50.0, market="derivatives", leverage=3.0),
        PortfolioContext(cash=1_000.0),
        audit,
    )
    assert decision.allowed is True


def test_derivatives_per_asset_cap_uses_notional_not_margin(tmp_path, monkeypatch):
    # Margin 200 at 10x is only 20% of equity on a cost basis, but it moves
    # 2000 of the asset (200% of equity): the per-asset cap must read the
    # notional for derivatives and refuse (spot keeps the cost basis --
    # deliberate change from the earlier margin reading).
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    limits = RiskLimits(
        max_derivatives_leverage=10.0,
        max_derivatives_exposure_pct=1000.0,
        max_total_exposure_pct=1000.0,
    )
    decision = guard(limits).check(
        plan(cost=200.0, market="derivatives", leverage=10.0),
        PortfolioContext(cash=1_000.0),
        audit,
    )
    assert decision.allowed is False
    assert "per-asset" in decision.reason


def test_leverage_cap_enforced_even_without_portfolio(tmp_path, monkeypatch):
    # The leverage cap needs no equity denominator, so it runs BEFORE the
    # equity-None fail-open branch: a 100x plan is refused with no portfolio
    # at all (previously the fail-open skip silently disarmed it).
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    decision = guard().check(
        plan(cost=100.0, market="derivatives", leverage=100.0), None, audit
    )
    assert decision.allowed is False
    assert "leverage" in decision.reason
    # boundary: within the leverage cap the documented fail-open still holds
    within = guard().check(
        plan(cost=100.0, market="derivatives", leverage=1.0), None, audit
    )
    assert within.allowed is True
    assert "fail-open" in within.reason


# --- legacy (pre-phase) lines: plan vs fill on upgrade -------------------------


def test_legacy_confirmed_false_lines_are_plans_not_fills(tmp_path, monkeypatch):
    # The L1 writer logged PLANNED orders as action=side with confirmed=False
    # and no phase; counting them as fills fabricates P&L (and halts) from
    # orders that may never have been sent. This -60 round-trip must stay
    # invisible to the daily-loss check.
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [
        {**event("buy", 2.0, 100.0, hour=8), "confirmed": False},
        {**event("sell", 2.0, 70.0, hour=9), "confirmed": False},
    ])
    decision = guard().check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.allowed is True
    assert decision.halted is False


def test_legacy_confirmed_true_lines_still_count_as_fills(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [
        {**event("buy", 2.0, 100.0, hour=8), "confirmed": True},
        {**event("sell", 2.0, 70.0, hour=9), "confirmed": True},
    ])
    decision = guard().check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.halted is True
    assert "daily loss" in decision.reason


# --- decision model and malformed input -------------------------------------


def test_decision_defaults_shape():
    decision = RiskDecision(allowed=True, halted=False)
    assert decision.reason is None


def test_missing_audit_file_is_a_fresh_log(tmp_path):
    decision = guard().check(plan(), PortfolioContext(cash=1_000.0), tmp_path / "missing.jsonl")
    assert decision.allowed is True


def test_corrupt_lines_are_skipped(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    audit.write_text("not json\n{\"event\": \"halt\"}\n", encoding="utf-8")  # no timestamp either
    decision = guard().check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.allowed is True  # unparseable/unusable lines cannot fabricate a halt


def test_price_of_exceptions_are_treated_as_no_price(tmp_path, monkeypatch):
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    write_events(audit, [event("buy", 2.0, 100.0, hour=8)])  # open lot needs a mark

    def broken(ticker):
        raise RuntimeError("feed down")

    g = RiskGuard(price_of=broken)
    decision = g.check(plan(), PortfolioContext(cash=1_000.0), audit)
    # the open lot is excluded from daily P&L and from equity; the trade plan
    # itself still passes the (weaker) checks
    assert decision.allowed is True


# --- unreadable audit log: fail-closed at execute time only -------------------


def test_unreadable_log_fails_closed_at_execute_time(tmp_path, monkeypatch):
    # A log locked by a backup/AV scan (or permission loss) hides the halt
    # and loss-streak state exactly when a send is being decided: the
    # execute-time re-check must refuse, not pass.
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    audit.mkdir()  # exists but cannot be read as text (OSError)
    decision = guard().check(
        plan(), PortfolioContext(cash=1_000.0), audit, fail_closed=True
    )
    assert decision.allowed is False
    assert decision.halted is False
    assert "unreadable" in decision.reason


def test_unreadable_log_stays_fail_open_at_plan_time(tmp_path, monkeypatch):
    # Plan-time keeps the documented fail-open read: a blind plan must not
    # fabricate a halt either way.
    freeze(monkeypatch, FROZEN_NOW)
    audit = tmp_path / "audit.jsonl"
    audit.mkdir()
    decision = guard().check(plan(), PortfolioContext(cash=1_000.0), audit)
    assert decision.allowed is True


def test_missing_log_is_a_fresh_log_even_when_failing_closed(tmp_path):
    decision = guard().check(
        plan(), PortfolioContext(cash=1_000.0), tmp_path / "missing.jsonl", fail_closed=True
    )
    assert decision.allowed is True
