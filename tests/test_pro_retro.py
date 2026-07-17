"""Retro-scorer honesty invariants (score-plan Phase 3): real decisions
scored against real subsequent bars — idempotent, provenance-tagged,
lesson-free, and invisible to the trade blotter."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from tests.pro_fakes import BASE_TS
from tests.test_pro_memory_facade import make_recommendation
from tradingagents.contracts import OHLCVBar, Timeframe
from tradingagents.pro.analytics.retro import backfill_outcomes, simulate_ticket
from tradingagents.pro.dashboard.service import (
    estimate_p_win,
    trade_journal,
)
from tradingagents.pro.memory import MemoryKind, ProMemory


def bar(i: int, low: float, high: float) -> OHLCVBar:
    mid = (low + high) / 2
    return OHLCVBar(
        timeframe=Timeframe.H1, start=BASE_TS + timedelta(hours=i),
        open=mid, high=high, low=low, close=mid, volume=1_000.0,
    )


def make_run(rec, run_id="run-1"):
    return SimpleNamespace(run_id=run_id, recommendation=rec,
                           started_at=BASE_TS, timeframe="1h")


class TestSimulateTicket:
    # make_recommendation: BUY, entry 2400, stop 2380, TP 2440

    def test_target_touch_resolves_as_win(self):
        rec = make_recommendation()
        bars = [bar(1, 2395, 2410), bar(2, 2405, 2445)]
        outcome = simulate_ticket(rec, bars)
        assert outcome is not None and outcome.exit_reason == "take_profit"
        assert outcome.pnl > 0

    def test_stop_wins_ties_within_one_bar(self):
        # a single bar spanning both stop and target counts as the stop —
        # conservative by construction
        rec = make_recommendation()
        bars = [bar(1, 2375, 2450)]
        outcome = simulate_ticket(rec, bars)
        assert outcome is not None and outcome.exit_reason == "stop"
        assert outcome.pnl < 0

    def test_unresolved_ticket_returns_none(self):
        rec = make_recommendation()
        bars = [bar(1, 2395, 2410), bar(2, 2390, 2415)]
        assert simulate_ticket(rec, bars) is None


class TestBackfill:
    def test_scores_once_writes_no_lessons_and_skips_journal(self):
        memory = ProMemory()
        rec = make_recommendation()
        runs = [make_run(rec)]
        bars = [bar(1, 2405, 2445)]

        first = backfill_outcomes(runs, memory, lambda run: bars)
        assert first["scored"] == 1
        # idempotent: a second pass scores nothing
        second = backfill_outcomes(runs, memory, lambda run: bars)
        assert second["scored"] == 0 and second["skipped_already_scored"] == 1

        # provenance + no-poisoning guarantees
        outcomes = memory.records(MemoryKind.OUTCOME)
        assert len(outcomes) == 1
        assert outcomes[0].payload["mode"] == "retro"
        assert memory.records(MemoryKind.MISTAKE) == []
        assert memory.records(MemoryKind.WINNING_PATTERN) == []
        # the blotter never shows graded predictions
        assert trade_journal(memory)["n_trades"] == 0

    def test_unresolved_runs_are_skipped_not_guessed(self):
        memory = ProMemory()
        runs = [make_run(make_recommendation())]
        result = backfill_outcomes(runs, memory, lambda run: [])
        assert result["scored"] == 0 and result["skipped_unresolved"] == 1
        assert memory.records(MemoryKind.OUTCOME) == []


class TestPWin:
    def test_below_sample_floor_returns_none(self):
        memory = ProMemory()
        trade = memory.record_trade(make_recommendation())
        memory.close_trade(trade.id, pnl=50.0)
        assert estimate_p_win(memory, 70) is None

    def test_overall_record_backs_the_estimate(self):
        memory = ProMemory()
        for pnl in (50.0, -20.0, 30.0, 40.0, -10.0, 25.0):
            trade = memory.record_trade(make_recommendation())
            memory.close_trade(trade.id, pnl=pnl, write_lesson=False)
        est = estimate_p_win(memory, None)
        assert est is not None
        assert est["n"] == 6
        assert est["p_win"] == pytest.approx(4 / 6)
        assert est["median_hold_s"] is None or est["median_hold_s"] >= 0
