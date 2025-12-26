"""Tests for Issue #19: Trade History Memory.

This module tests the trade history memory for tracking:
- Trade outcomes (profit/loss)
- Agent reasoning
- Market context
- Pattern finding
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from tradingagents.memory.trade_history import (
    TradeHistoryMemory,
    TradeRecord,
    TradeOutcome,
    TradeDirection,
    SignalStrength,
    AgentReasoning,
    MarketContext,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def memory():
    """Create a TradeHistoryMemory instance."""
    return TradeHistoryMemory()


@pytest.fixture
def sample_reasoning():
    """Create sample agent reasoning."""
    return AgentReasoning(
        fundamentals="Strong earnings growth, P/E below industry average",
        technical="Breaking out above 50-day MA with volume",
        news="Positive analyst upgrades",
        sentiment="Bullish social media sentiment",
        bull_case="Undervalued with strong growth trajectory",
        bear_case="Macro headwinds could impact demand",
        research_conclusion="Buy on fundamental strength",
        final_signal="STRONG_BUY",
    )


@pytest.fixture
def sample_market_context():
    """Create sample market context."""
    return MarketContext(
        vix=18.5,
        spy_return_1d=0.005,
        sector_performance={"XLK": 0.01, "XLF": -0.005},
        economic_regime="EXPANSION",
        yield_curve_state="NORMAL",
        macro_indicators={"gdp_growth": 2.5, "unemployment": 4.0},
    )


@pytest.fixture
def sample_trade(sample_reasoning, sample_market_context):
    """Create a sample trade record."""
    return TradeRecord.create(
        symbol="AAPL",
        direction=TradeDirection.LONG,
        entry_price=150.0,
        quantity=100,
        signal_strength=SignalStrength.STRONG_BUY,
        confidence=0.85,
        reasoning=sample_reasoning,
        market_context=sample_market_context,
        tags=["tech", "earnings"],
    )


@pytest.fixture
def multiple_trades():
    """Create multiple trade records for testing."""
    now = datetime.now()
    trades = []

    # Profitable AAPL trade
    trade1 = TradeRecord(
        id="trade-1",
        symbol="AAPL",
        direction=TradeDirection.LONG,
        entry_price=150.0,
        entry_time=now - timedelta(days=10),
        quantity=100,
        reasoning=AgentReasoning(research_conclusion="Buy on earnings"),
        tags=["tech", "earnings"],
    )
    trade1.close(165.0)

    # Loss GOOGL trade
    trade2 = TradeRecord(
        id="trade-2",
        symbol="GOOGL",
        direction=TradeDirection.LONG,
        entry_price=140.0,
        entry_time=now - timedelta(days=5),
        quantity=50,
        reasoning=AgentReasoning(research_conclusion="Momentum buy"),
        tags=["tech"],
    )
    trade2.close(130.0)

    # Break-even MSFT trade
    trade3 = TradeRecord(
        id="trade-3",
        symbol="MSFT",
        direction=TradeDirection.LONG,
        entry_price=350.0,
        entry_time=now - timedelta(days=2),
        quantity=20,
        reasoning=AgentReasoning(research_conclusion="Range trade"),
        tags=["tech"],
    )
    trade3.close(351.0)

    # Open NVDA trade
    trade4 = TradeRecord(
        id="trade-4",
        symbol="NVDA",
        direction=TradeDirection.LONG,
        entry_price=500.0,
        entry_time=now - timedelta(hours=2),
        quantity=10,
        reasoning=AgentReasoning(research_conclusion="AI momentum"),
        tags=["tech", "ai"],
    )

    trades = [trade1, trade2, trade3, trade4]
    return trades


# =============================================================================
# TradeDirection Tests
# =============================================================================

class TestTradeDirection:
    """Tests for TradeDirection enum."""

    def test_long_value(self):
        """LONG should have correct value."""
        assert TradeDirection.LONG.value == "long"

    def test_short_value(self):
        """SHORT should have correct value."""
        assert TradeDirection.SHORT.value == "short"

    def test_hold_value(self):
        """HOLD should have correct value."""
        assert TradeDirection.HOLD.value == "hold"


# =============================================================================
# TradeOutcome Tests
# =============================================================================

class TestTradeOutcome:
    """Tests for TradeOutcome enum."""

    def test_profitable(self):
        """PROFITABLE should have correct value."""
        assert TradeOutcome.PROFITABLE.value == "profitable"

    def test_loss(self):
        """LOSS should have correct value."""
        assert TradeOutcome.LOSS.value == "loss"

    def test_break_even(self):
        """BREAK_EVEN should have correct value."""
        assert TradeOutcome.BREAK_EVEN.value == "break_even"


# =============================================================================
# SignalStrength Tests
# =============================================================================

class TestSignalStrength:
    """Tests for SignalStrength enum."""

    def test_signal_values(self):
        """All signal strengths should have correct values."""
        assert SignalStrength.STRONG_BUY.value == "strong_buy"
        assert SignalStrength.BUY.value == "buy"
        assert SignalStrength.NEUTRAL.value == "neutral"
        assert SignalStrength.SELL.value == "sell"
        assert SignalStrength.STRONG_SELL.value == "strong_sell"


# =============================================================================
# AgentReasoning Tests
# =============================================================================

class TestAgentReasoning:
    """Tests for AgentReasoning class."""

    def test_default_reasoning(self):
        """Default reasoning should have None values."""
        reasoning = AgentReasoning()
        assert reasoning.fundamentals is None
        assert reasoning.technical is None
        assert reasoning.research_conclusion is None

    def test_reasoning_with_values(self, sample_reasoning):
        """Reasoning should store values correctly."""
        assert sample_reasoning.fundamentals is not None
        assert sample_reasoning.research_conclusion == "Buy on fundamental strength"

    def test_to_dict(self, sample_reasoning):
        """To dict should serialize correctly."""
        data = sample_reasoning.to_dict()
        assert data["fundamentals"] == sample_reasoning.fundamentals
        assert data["research_conclusion"] == sample_reasoning.research_conclusion

    def test_from_dict(self, sample_reasoning):
        """From dict should deserialize correctly."""
        data = sample_reasoning.to_dict()
        restored = AgentReasoning.from_dict(data)
        assert restored.fundamentals == sample_reasoning.fundamentals
        assert restored.research_conclusion == sample_reasoning.research_conclusion

    def test_summary(self, sample_reasoning):
        """Summary should generate text."""
        summary = sample_reasoning.summary()
        assert "Fundamentals" in summary
        assert "Conclusion" in summary

    def test_empty_summary(self):
        """Empty reasoning should have fallback summary."""
        reasoning = AgentReasoning()
        summary = reasoning.summary()
        assert summary == "No reasoning recorded"


# =============================================================================
# MarketContext Tests
# =============================================================================

class TestMarketContext:
    """Tests for MarketContext class."""

    def test_default_context(self):
        """Default context should have None/empty values."""
        context = MarketContext()
        assert context.vix is None
        assert context.sector_performance == {}

    def test_context_with_values(self, sample_market_context):
        """Context should store values correctly."""
        assert sample_market_context.vix == 18.5
        assert sample_market_context.economic_regime == "EXPANSION"
        assert "XLK" in sample_market_context.sector_performance

    def test_to_dict(self, sample_market_context):
        """To dict should serialize correctly."""
        data = sample_market_context.to_dict()
        assert data["vix"] == 18.5
        assert data["economic_regime"] == "EXPANSION"

    def test_from_dict(self, sample_market_context):
        """From dict should deserialize correctly."""
        data = sample_market_context.to_dict()
        restored = MarketContext.from_dict(data)
        assert restored.vix == sample_market_context.vix
        assert restored.economic_regime == sample_market_context.economic_regime

    def test_summary(self, sample_market_context):
        """Summary should generate text."""
        summary = sample_market_context.summary()
        assert "VIX" in summary
        assert "Regime" in summary


# =============================================================================
# TradeRecord Tests
# =============================================================================

class TestTradeRecord:
    """Tests for TradeRecord class."""

    def test_create_trade(self):
        """Create should generate a valid trade record."""
        trade = TradeRecord.create(
            symbol="AAPL",
            direction=TradeDirection.LONG,
            entry_price=150.0,
        )
        assert trade.symbol == "AAPL"
        assert trade.direction == TradeDirection.LONG
        assert trade.entry_price == 150.0
        assert trade.id is not None
        assert trade.entry_time is not None
        assert trade.is_open()

    def test_create_with_all_args(self, sample_reasoning, sample_market_context):
        """Create with all arguments should work."""
        trade = TradeRecord.create(
            symbol="AAPL",
            direction=TradeDirection.LONG,
            entry_price=150.0,
            quantity=100,
            signal_strength=SignalStrength.STRONG_BUY,
            confidence=0.85,
            reasoning=sample_reasoning,
            market_context=sample_market_context,
            tags=["tech"],
        )
        assert trade.quantity == 100
        assert trade.signal_strength == SignalStrength.STRONG_BUY
        assert trade.confidence == 0.85
        assert trade.reasoning == sample_reasoning
        assert trade.market_context == sample_market_context

    def test_close_profitable(self, sample_trade):
        """Closing at higher price should be profitable."""
        sample_trade.close(165.0)

        assert sample_trade.exit_price == 165.0
        assert sample_trade.exit_time is not None
        assert sample_trade.returns is not None
        assert sample_trade.returns > 0
        assert sample_trade.outcome == TradeOutcome.PROFITABLE
        assert not sample_trade.is_open()

    def test_close_loss(self, sample_trade):
        """Closing at lower price should be a loss."""
        sample_trade.close(140.0)

        assert sample_trade.returns < 0
        assert sample_trade.outcome == TradeOutcome.LOSS

    def test_close_break_even(self, sample_trade):
        """Closing at same price should be break even."""
        sample_trade.close(150.2)  # Within 0.5% threshold

        assert abs(sample_trade.returns) < 0.005
        assert sample_trade.outcome == TradeOutcome.BREAK_EVEN

    def test_close_short_profitable(self):
        """Short trade profitable when price goes down."""
        trade = TradeRecord.create(
            symbol="AAPL",
            direction=TradeDirection.SHORT,
            entry_price=150.0,
        )
        trade.close(140.0)

        assert trade.returns > 0
        assert trade.outcome == TradeOutcome.PROFITABLE

    def test_close_short_loss(self):
        """Short trade loss when price goes up."""
        trade = TradeRecord.create(
            symbol="AAPL",
            direction=TradeDirection.SHORT,
            entry_price=150.0,
        )
        trade.close(160.0)

        assert trade.returns < 0
        assert trade.outcome == TradeOutcome.LOSS

    def test_pnl_calculation(self, sample_trade):
        """PnL should be calculated correctly."""
        sample_trade.close(165.0)

        expected_return = (165 - 150) / 150
        expected_pnl = expected_return * 150 * 100

        assert abs(sample_trade.pnl - expected_pnl) < 0.01

    def test_holding_period(self, sample_trade):
        """Holding period should be calculated correctly."""
        assert sample_trade.holding_period_days() is None  # Still open

        sample_trade.close(165.0)
        holding = sample_trade.holding_period_days()
        assert holding is not None
        assert holding >= 0

    def test_to_memory_content(self, sample_trade):
        """Memory content should include key info."""
        sample_trade.close(165.0)
        content = sample_trade.to_memory_content()

        assert "AAPL" in content
        assert "long" in content
        assert "profitable" in content

    def test_to_dict(self, sample_trade):
        """To dict should serialize correctly."""
        data = sample_trade.to_dict()

        assert data["symbol"] == "AAPL"
        assert data["direction"] == "long"
        assert data["entry_price"] == 150.0
        assert "reasoning" in data
        assert "market_context" in data

    def test_from_dict(self, sample_trade):
        """From dict should deserialize correctly."""
        sample_trade.close(165.0)
        data = sample_trade.to_dict()
        restored = TradeRecord.from_dict(data)

        assert restored.symbol == sample_trade.symbol
        assert restored.direction == sample_trade.direction
        assert restored.entry_price == sample_trade.entry_price
        assert restored.exit_price == sample_trade.exit_price
        assert restored.outcome == sample_trade.outcome


# =============================================================================
# TradeHistoryMemory Basic Tests
# =============================================================================

class TestTradeHistoryMemoryBasic:
    """Basic tests for TradeHistoryMemory."""

    def test_create_empty(self, memory):
        """Empty memory should have zero trades."""
        assert memory.count() == 0

    def test_record_trade(self, memory, sample_trade):
        """Recording a trade should increase count."""
        trade_id = memory.record_trade(sample_trade)
        assert trade_id == sample_trade.id
        assert memory.count() == 1

    def test_get_trade(self, memory, sample_trade):
        """Get should return recorded trade."""
        memory.record_trade(sample_trade)
        retrieved = memory.get_trade(sample_trade.id)
        assert retrieved is not None
        assert retrieved.symbol == sample_trade.symbol

    def test_get_nonexistent(self, memory):
        """Get nonexistent trade should return None."""
        result = memory.get_trade("nonexistent")
        assert result is None

    def test_close_trade(self, memory, sample_trade):
        """Closing a trade should update it."""
        memory.record_trade(sample_trade)
        closed = memory.close_trade(sample_trade.id, exit_price=165.0)

        assert closed is not None
        assert closed.exit_price == 165.0
        assert closed.outcome is not None

    def test_close_with_lessons(self, memory, sample_trade):
        """Closing with lessons should store them."""
        memory.record_trade(sample_trade)
        memory.close_trade(
            sample_trade.id,
            exit_price=165.0,
            lessons_learned="Wait for confirmation before entry",
        )

        trade = memory.get_trade(sample_trade.id)
        assert trade.lessons_learned == "Wait for confirmation before entry"

    def test_clear(self, memory, multiple_trades):
        """Clear should remove all trades."""
        for trade in multiple_trades:
            memory.record_trade(trade)

        count = memory.clear()
        assert count == len(multiple_trades)
        assert memory.count() == 0


# =============================================================================
# TradeHistoryMemory Query Tests
# =============================================================================

class TestTradeHistoryMemoryQueries:
    """Query tests for TradeHistoryMemory."""

    def test_get_open_trades(self, memory, multiple_trades):
        """Get open trades should filter correctly."""
        for trade in multiple_trades:
            memory.record_trade(trade)

        open_trades = memory.get_open_trades()
        assert len(open_trades) == 1  # Only NVDA is open
        assert open_trades[0].symbol == "NVDA"

    def test_get_closed_trades(self, memory, multiple_trades):
        """Get closed trades should filter correctly."""
        for trade in multiple_trades:
            memory.record_trade(trade)

        closed_trades = memory.get_closed_trades()
        assert len(closed_trades) == 3  # AAPL, GOOGL, MSFT

    def test_get_trades_by_symbol(self, memory, multiple_trades):
        """Get trades by symbol should filter correctly."""
        for trade in multiple_trades:
            memory.record_trade(trade)

        aapl_trades = memory.get_trades_by_symbol("AAPL")
        assert len(aapl_trades) == 1
        assert aapl_trades[0].symbol == "AAPL"

    def test_find_similar_trades(self, memory, multiple_trades):
        """Find similar trades should return relevant trades."""
        for trade in multiple_trades:
            memory.record_trade(trade)

        similar = memory.find_similar_trades(
            query="tech stock momentum earnings",
            top_k=3,
        )
        assert len(similar) >= 1

    def test_find_profitable_patterns(self, memory, multiple_trades):
        """Find profitable patterns should return winners."""
        for trade in multiple_trades:
            memory.record_trade(trade)

        profitable = memory.find_profitable_patterns(
            query="tech stock buy",
            min_return=0.05,
            top_k=5,
        )
        # AAPL had 10% return
        assert len(profitable) >= 1
        for trade in profitable:
            assert trade.returns >= 0.05

    def test_find_losing_patterns(self, memory, multiple_trades):
        """Find losing patterns should return losers."""
        for trade in multiple_trades:
            memory.record_trade(trade)

        losers = memory.find_losing_patterns(
            query="tech stock momentum",
            max_return=-0.05,
            top_k=5,
        )
        # GOOGL had -7% return
        assert len(losers) >= 1
        for trade in losers:
            assert trade.returns <= -0.05


# =============================================================================
# TradeHistoryMemory Statistics Tests
# =============================================================================

class TestTradeHistoryMemoryStats:
    """Statistics tests for TradeHistoryMemory."""

    def test_empty_statistics(self, memory):
        """Empty memory should have zero stats."""
        stats = memory.get_statistics()
        assert stats["total_trades"] == 0
        assert stats["win_rate"] == 0.0

    def test_statistics_with_trades(self, memory, multiple_trades):
        """Statistics should reflect trade data."""
        for trade in multiple_trades:
            memory.record_trade(trade)

        stats = memory.get_statistics()

        assert stats["total_trades"] == 4
        assert stats["open_trades"] == 1
        assert stats["closed_trades"] == 3
        assert stats["win_rate"] > 0  # At least AAPL was profitable

    def test_symbol_statistics(self, memory, multiple_trades):
        """Symbol statistics should be calculated correctly."""
        for trade in multiple_trades:
            memory.record_trade(trade)

        stats = memory.get_symbol_statistics("AAPL")

        assert stats["symbol"] == "AAPL"
        assert stats["total_trades"] == 1
        assert stats["closed_trades"] == 1
        assert stats["win_rate"] == 1.0  # AAPL was profitable


# =============================================================================
# TradeHistoryMemory Serialization Tests
# =============================================================================

class TestTradeHistoryMemorySerialization:
    """Serialization tests for TradeHistoryMemory."""

    def test_to_dict(self, memory, multiple_trades):
        """To dict should serialize correctly."""
        for trade in multiple_trades:
            memory.record_trade(trade)

        data = memory.to_dict()

        assert "trades" in data
        assert "memory" in data
        assert len(data["trades"]) == len(multiple_trades)

    def test_from_dict(self, memory, multiple_trades):
        """From dict should deserialize correctly."""
        for trade in multiple_trades:
            memory.record_trade(trade)

        data = memory.to_dict()
        restored = TradeHistoryMemory.from_dict(data)

        assert restored.count() == len(multiple_trades)

    def test_roundtrip(self, memory, sample_trade):
        """Roundtrip serialization should preserve data."""
        memory.record_trade(sample_trade)
        memory.close_trade(sample_trade.id, exit_price=165.0)

        data = memory.to_dict()
        restored = TradeHistoryMemory.from_dict(data)

        original = memory.get_trade(sample_trade.id)
        restored_trade = restored.get_trade(sample_trade.id)

        assert restored_trade is not None
        assert restored_trade.symbol == original.symbol
        assert restored_trade.exit_price == original.exit_price
        assert restored_trade.outcome == original.outcome


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for trade history workflow."""

    def test_full_trade_lifecycle(self, memory):
        """Test complete trade lifecycle."""
        # 1. Create reasoning
        reasoning = AgentReasoning(
            fundamentals="Strong quarterly earnings",
            technical="Golden cross on daily chart",
            research_conclusion="Buy for momentum continuation",
        )

        # 2. Create market context
        context = MarketContext(
            vix=15.0,
            economic_regime="EXPANSION",
        )

        # 3. Open trade
        trade = TradeRecord.create(
            symbol="MSFT",
            direction=TradeDirection.LONG,
            entry_price=400.0,
            quantity=50,
            signal_strength=SignalStrength.BUY,
            confidence=0.75,
            reasoning=reasoning,
            market_context=context,
            tags=["tech", "earnings"],
        )
        memory.record_trade(trade)

        # 4. Verify open
        assert memory.count() == 1
        assert len(memory.get_open_trades()) == 1

        # 5. Close with profit
        memory.close_trade(
            trade.id,
            exit_price=440.0,
            lessons_learned="Good timing on earnings play",
        )

        # 6. Verify closed
        assert len(memory.get_closed_trades()) == 1
        closed = memory.get_trade(trade.id)
        assert closed.outcome == TradeOutcome.PROFITABLE
        assert closed.returns == pytest.approx(0.10, rel=0.01)

        # 7. Find similar trades
        similar = memory.find_similar_trades(
            query="tech earnings momentum",
            top_k=1,
        )
        assert len(similar) == 1
        assert similar[0].symbol == "MSFT"

        # 8. Check statistics
        stats = memory.get_statistics()
        assert stats["win_rate"] == 1.0
        assert stats["avg_return"] > 0

    def test_learning_from_history(self, memory):
        """Test learning patterns from trade history."""
        # Record several trades
        trades = [
            ("AAPL", "earnings beat", 150.0, 165.0),  # +10%
            ("GOOGL", "earnings beat", 140.0, 147.0),  # +5%
            ("MSFT", "earnings miss", 350.0, 315.0),  # -10%
            ("NVDA", "earnings beat", 500.0, 550.0),  # +10%
        ]

        for symbol, pattern, entry, exit_price in trades:
            trade = TradeRecord.create(
                symbol=symbol,
                direction=TradeDirection.LONG,
                entry_price=entry,
                reasoning=AgentReasoning(research_conclusion=f"Trade on {pattern}"),
                tags=["earnings"],
            )
            memory.record_trade(trade)
            memory.close_trade(trade.id, exit_price=exit_price)

        # Query for earnings beat patterns
        profitable = memory.find_profitable_patterns(
            query="earnings beat momentum",
            min_return=0.05,
        )

        # Should find the profitable earnings beat trades
        assert len(profitable) >= 2

        # Query for losses to avoid
        losers = memory.find_losing_patterns(
            query="earnings trade",
            max_return=-0.05,
        )

        # Should find the earnings miss trade
        assert len(losers) >= 1
