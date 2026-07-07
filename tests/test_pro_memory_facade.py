"""ProMemory facade: trade lifecycle, analogs, lessons, win statistics."""

import pytest

from tests.test_pro_agents_base import make_snapshot
from tests.test_pro_pipeline_units import make_evidence
from tradingagents.contracts import (
    AgentVote,
    AssetClass,
    Direction,
    MarketRegime,
    PositionSize,
    TakeProfitLevel,
    TradeAction,
    TradeRecommendation,
    VoteBreakdown,
)
from tradingagents.pro.memory import (
    MIN_TRADES_FOR_STATS,
    MemoryKind,
    ProMemory,
    describe_snapshot,
)


def make_recommendation(action=TradeAction.BUY, symbol="XAUUSD") -> TradeRecommendation:
    directional = action in (TradeAction.BUY, TradeAction.SELL)
    direction = Direction.BULLISH if action is TradeAction.BUY else Direction.BEARISH
    return TradeRecommendation(
        symbol=symbol,
        asset=AssetClass.GOLD,
        action=action,
        confidence=70,
        entry_price=2400.0 if directional else None,
        stop_loss=(2380.0 if action is TradeAction.BUY else 2420.0) if directional else None,
        take_profits=(
            [TakeProfitLevel(
                price=2440.0 if action is TradeAction.BUY else 2360.0,
                size_fraction=1.0,
            )] if directional else []
        ),
        position_size=PositionSize(quantity=1.0 if directional else 0),
        market_regime=MarketRegime.TRENDING_UP,
        evidence=[make_evidence("trend", direction, 70)],
        vote_breakdown=VoteBreakdown(votes=[
            AgentVote(agent_id="trend", vote=action, confidence=70)
        ]),
    )


class TestTradeLifecycle:
    def test_record_and_close_derives_lesson(self, tmp_path):
        memory = ProMemory(store_path=tmp_path / "m.jsonl")
        trade = memory.record_trade(make_recommendation())
        added = memory.close_trade(trade.id, pnl=-2.5, lesson="stop too tight for regime")

        kinds = [r.kind for r in added]
        assert kinds == [MemoryKind.OUTCOME, MemoryKind.MISTAKE]
        assert added[0].ref_id == trade.id
        assert "stop too tight" in added[1].text

    def test_winning_close_derives_winning_pattern(self, tmp_path):
        memory = ProMemory(store_path=tmp_path / "m.jsonl")
        trade = memory.record_trade(make_recommendation())
        added = memory.close_trade(trade.id, pnl=3.0)
        assert added[1].kind is MemoryKind.WINNING_PATTERN

    def test_close_unknown_trade_rejected(self):
        with pytest.raises(KeyError):
            ProMemory().close_trade("nope", pnl=1.0)

    def test_persistence_reload(self, tmp_path):
        path = tmp_path / "m.jsonl"
        memory = ProMemory(store_path=path)
        trade = memory.record_trade(make_recommendation())
        memory.close_trade(trade.id, pnl=1.0)

        reloaded = ProMemory(store_path=path)
        analogs = reloaded.historical_analogs("XAUUSD trending_up BUY", symbol="XAUUSD")
        assert len(analogs) == 1
        assert analogs[0].memory_ref == trade.id


class TestAnalogs:
    def test_only_closed_trades_become_analogs(self):
        memory = ProMemory()
        closed = memory.record_trade(make_recommendation())
        memory.record_trade(make_recommendation())  # open — no outcome
        memory.close_trade(closed.id, pnl=2.0)

        analogs = memory.historical_analogs("BUY XAUUSD trending_up")
        assert [a.memory_ref for a in analogs] == [closed.id]
        assert 0.0 <= analogs[0].similarity <= 1.0
        assert "win" in analogs[0].outcome
        assert analogs[0].period_end >= analogs[0].period_start

    def test_describe_snapshot_is_deterministic_and_rich(self):
        snapshot = make_snapshot()
        text = describe_snapshot(snapshot, MarketRegime.RANGING)
        assert text == describe_snapshot(snapshot, MarketRegime.RANGING)
        assert "XAUUSD" in text and "regime ranging" in text
        assert "RSI_14" in text and "DXY" in text


class TestLessonsAndStats:
    def test_lessons_surface_mistakes_and_reflections(self):
        memory = ProMemory()
        trade = memory.record_trade(make_recommendation())
        memory.close_trade(trade.id, pnl=-1.0, lesson="faded strong trend")
        memory.record_reflection("XAUUSD", "thin macro evidence", "close below 2350")

        hits = memory.lessons("XAUUSD trend", symbol="XAUUSD")
        kinds = {h.record.kind for h in hits}
        assert MemoryKind.MISTAKE in kinds
        assert MemoryKind.REFLECTION in kinds

    def test_win_stats_require_minimum_sample(self):
        memory = ProMemory()
        for _ in range(MIN_TRADES_FOR_STATS - 1):
            t = memory.record_trade(make_recommendation())
            memory.close_trade(t.id, pnl=1.0)
        assert memory.win_stats("XAUUSD") is None

    def test_win_stats_known_values(self):
        memory = ProMemory()
        pnls = [2.0, 2.0, 2.0, -1.0, -1.0]  # 60% win, avg win 2, avg loss 1
        for pnl in pnls:
            t = memory.record_trade(make_recommendation())
            memory.close_trade(t.id, pnl=pnl)
        stats = memory.win_stats("XAUUSD")
        assert stats == (pytest.approx(0.6), pytest.approx(2.0), pytest.approx(1.0))

    def test_degenerate_all_wins_returns_none(self):
        memory = ProMemory()
        for _ in range(MIN_TRADES_FOR_STATS):
            t = memory.record_trade(make_recommendation())
            memory.close_trade(t.id, pnl=1.0)
        assert memory.win_stats("XAUUSD") is None

    def test_regime_memory_recorded(self):
        memory = ProMemory()
        memory.record_regime("XAUUSD", MarketRegime.HIGH_VOLATILITY,
                             {"realized_vol": 0.42})
        hits = memory.retrieve("XAUUSD high_volatility", kinds=(MemoryKind.REGIME,))
        assert hits and hits[0].record.payload["regime"] == "high_volatility"

    def test_relations_block_defaults_by_symbol(self):
        memory = ProMemory()
        assert "XAUUSD" in memory.relations_block("XAUUSD")
        assert "FUNDING_RATE" in memory.relations_block("BTC-USD")
