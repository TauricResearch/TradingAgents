"""Unit tests for the institutional-report analytics: extended metrics,
enriched trade log, agent attribution, and regime breakdown. Deterministic
inputs only — no LLM, no network."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradingagents.pro.backtest.agent_attribution import agent_attribution
from tradingagents.pro.backtest.broker import ClosedTrade
from tradingagents.pro.backtest.regime_breakdown import regime_breakdown
from tradingagents.pro.backtest.report import (
    alpha_beta,
    buy_hold_curve,
    cagr,
    calendar_returns,
    calmar_ratio,
    drawdown_curve,
    extended_report,
    recovery_factor,
    risk_of_ruin,
    rolling_sharpe,
    trade_stats,
)
from tradingagents.pro.backtest.trade_log import EnrichedTrade, enrich_trades

BASE = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _trade(pnl: float, side: str = "BUY", entry: float = 100.0, rid: str = "r",
           hold_h: int = 24, exitp: float | None = None) -> ClosedTrade:
    exit_price = exitp if exitp is not None else entry + (pnl if side == "BUY" else -pnl)
    return ClosedTrade(
        "BTC-USD", side, 1.0, entry, exit_price, BASE, BASE + timedelta(hours=hold_h),
        pnl, "take_profit" if pnl > 0 else "stop", rid,
    )


class TestExtendedMetrics:
    def test_cagr_doubling_over_one_year(self):
        assert cagr([100.0, 200.0], years=1.0) == pytest.approx(1.0)

    def test_cagr_degenerate_is_zero(self):
        assert cagr([100.0], years=1.0) == 0.0
        assert cagr([100.0, 200.0], years=0.0) == 0.0
        assert cagr([-1.0, 200.0], years=1.0) == 0.0

    def test_calmar_and_recovery(self):
        assert calmar_ratio(0.2, 0.1) == pytest.approx(2.0)
        assert calmar_ratio(0.2, 0.0) == 0.0
        assert recovery_factor(500.0, 250.0) == pytest.approx(2.0)
        assert recovery_factor(500.0, 0.0) == 0.0

    def test_drawdown_curve_tracks_underwater(self):
        dd = drawdown_curve([100, 120, 90, 130])
        assert dd[0] == 0.0  # first point is a peak
        assert dd[1] == 0.0  # new high
        assert dd[2] == pytest.approx(0.25)  # 120 -> 90
        assert dd[3] == 0.0  # new high recovers

    def test_rolling_sharpe_window(self):
        rets = [0.01, -0.005, 0.02, 0.0, 0.015, -0.01]
        rs = rolling_sharpe(rets, window=3)
        assert len(rs) == len(rets) - 3 + 1
        assert rolling_sharpe(rets, window=99) == []

    def test_alpha_beta_perfect_correlation(self):
        bench = [0.01, 0.02, -0.01, 0.03]
        strat = [0.02, 0.04, -0.02, 0.06]  # exactly 2x → beta 2, alpha 0
        alpha, beta = alpha_beta(strat, bench, periods_per_year=1)
        assert beta == pytest.approx(2.0, abs=1e-6)
        assert alpha == pytest.approx(0.0, abs=1e-6)

    def test_buy_hold_curve_normalizes(self):
        curve = buy_hold_curve([100, 110, 120], initial_equity=1000)
        assert curve[0] == pytest.approx(1000)
        assert curve[-1] == pytest.approx(1200)

    def test_risk_of_ruin_bounds(self):
        never = risk_of_ruin([10.0, 10.0, 10.0, 10.0], 100_000, ruin_fraction=0.5)
        assert never == 0.0
        ruinous = risk_of_ruin([-60_000.0, 5.0], 100_000, ruin_fraction=0.5)
        assert 0.0 < ruinous <= 1.0

    def test_calendar_returns_monthly(self):
        ts = [datetime(2025, 1, 31, tzinfo=timezone.utc),
              datetime(2025, 2, 28, tzinfo=timezone.utc),
              datetime(2025, 3, 31, tzinfo=timezone.utc)]
        eq = [1000.0, 1100.0, 1045.0]
        monthly = calendar_returns(ts, eq, "ME")
        assert monthly[0] == ("2025-02", pytest.approx(0.1))
        assert monthly[1] == ("2025-03", pytest.approx(-0.05))

    def test_trade_stats_streaks(self):
        ts = trade_stats([_trade(10), _trade(20), _trade(-5), _trade(-3), _trade(8)])
        assert ts.max_consecutive_wins == 2
        assert ts.max_consecutive_losses == 2
        assert ts.avg_win == pytest.approx((10 + 20 + 8) / 3)
        assert ts.largest_loss == pytest.approx(-5)

    def test_extended_report_end_to_end(self):
        equity = [100_000, 101_000, 100_500, 102_000]
        ts = [BASE + timedelta(days=i) for i in range(4)]
        closes = [50_000, 50_500, 50_200, 51_000]
        trades = [_trade(1000), _trade(-500), _trade(1500)]
        rep = extended_report(equity, trades, ts, closes, 100_000, years=1.0)
        assert rep.max_consecutive_wins == 1
        assert rep.benchmark_total_return == pytest.approx((51_000 - 50_000) / 50_000)
        sd = rep.scalar_dict()
        assert "drawdown_curve" not in sd and "cagr" in sd


class TestEnrichedTradeLog:
    def test_enrich_without_state_still_produces_rows(self):
        trades = [_trade(1000, rid="x"), _trade(-500, side="SELL", rid="y")]
        rows = enrich_trades(trades, {}, 100_000)
        assert len(rows) == 2
        assert rows[0].outcome == "Win"
        assert rows[1].outcome == "Loss"
        # gross/net/commission are internally consistent
        for r in rows:
            assert r.commission == pytest.approx(r.gross_pnl - r.net_pnl)

    def test_pct_return_on_notional(self):
        rows = enrich_trades([_trade(1000, entry=100)], {}, 100_000)
        # net 1000 on notional 100*1 = 100 → 10.0
        assert rows[0].pct_return == pytest.approx(10.0)

    def test_csv_json_roundtrip(self, tmp_path):
        from tradingagents.pro.backtest.trade_log import write_csv, write_json

        rows = enrich_trades([_trade(1000)], {}, 100_000)
        write_csv(tmp_path / "t.csv", rows)
        write_json(tmp_path / "t.json", rows)
        assert (tmp_path / "t.csv").read_text().splitlines()[0].startswith("trade_id,")
        assert '"symbol": "BTC-USD"' in (tmp_path / "t.json").read_text()


def _enriched(direction: str, outcome: str, votes: list[dict], regime="trending_up",
              pnl: float = 100.0) -> EnrichedTrade:
    return EnrichedTrade(
        trade_id="t", recommendation_id="r", symbol="BTC-USD", direction=direction,
        opened_at=BASE.isoformat(), closed_at=BASE.isoformat(), holding_hours=24,
        entry_price=100, exit_price=110, stop_loss=95, take_profits=[120],
        position_size=1, exit_reason="take_profit",
        gross_pnl=pnl, net_pnl=pnl, commission=0, pct_return=0.1, risk_reward=2.0,
        confidence=70, market_regime=regime, strategy=regime, portfolio_pct_equity=5,
        outcome=outcome, chief_quant="pass", risk_engine="pass", vote_breakdown=votes,
    )


class TestAgentAttribution:
    def test_aligned_winner_scores_correct_and_positive_pnl(self):
        trades = [
            _enriched("BUY", "Win", [{"agent_id": "bull", "vote": "BUY", "confidence": 80},
                                     {"agent_id": "bear", "vote": "SELL", "confidence": 60}], pnl=100),
            _enriched("BUY", "Loss", [{"agent_id": "bull", "vote": "BUY", "confidence": 80},
                                      {"agent_id": "bear", "vote": "SELL", "confidence": 60}], pnl=-50),
        ]
        scores = {s.agent_id: s for s in agent_attribution(trades)}
        assert scores["bull"].correct == 1 and scores["bull"].incorrect == 1
        assert scores["bull"].attributed_pnl == pytest.approx(50)  # +100 -50
        assert scores["bear"].attributed_pnl == pytest.approx(-50)  # -100 +50
        assert scores["bear"].correct == 1  # opposed the loser → correct

    def test_hold_vote_is_neutral(self):
        trades = [_enriched("BUY", "Win", [{"agent_id": "n", "vote": "HOLD", "confidence": 50}])]
        s = agent_attribution(trades)[0]
        assert s.aligned == 0 and s.opposed == 0 and s.hit_rate == 0.0


class TestRegimeBreakdown:
    def test_groups_and_ranks_by_pnl(self):
        trades = [
            _enriched("BUY", "Win", [], regime="trending_up", pnl=100),
            _enriched("BUY", "Loss", [], regime="ranging", pnl=-40),
            _enriched("BUY", "Win", [], regime="trending_up", pnl=60),
        ]
        out = regime_breakdown(trades)
        assert out[0].regime == "trending_up"
        assert out[0].n_trades == 2 and out[0].total_net_pnl == pytest.approx(160)
        assert out[0].win_rate == pytest.approx(1.0)
        assert out[1].regime == "ranging" and out[1].total_net_pnl == pytest.approx(-40)
