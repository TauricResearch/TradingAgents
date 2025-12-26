"""Tests for Memory Integration module.

Issue #21: [MEM-20] Memory integration - retrieval in agent prompts
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from tradingagents.memory.integration import (
    AgentMemoryIntegration,
    MemoryContext,
    ContextType,
    create_memory_enhanced_prompt,
)
from tradingagents.memory.trade_history import (
    TradeRecord,
    TradeOutcome,
    TradeDirection,
    SignalStrength,
    AgentReasoning,
)
from tradingagents.memory.risk_profiles import (
    RiskCategory,
    MarketRegime,
    RiskTolerance,
    RiskProfile,
)


# =============================================================================
# MemoryContext Tests
# =============================================================================


class TestMemoryContext:
    """Tests for MemoryContext dataclass."""

    def test_empty_context(self):
        """Test empty context detection."""
        context = MemoryContext()
        assert context.is_empty()

    def test_non_empty_context(self):
        """Test non-empty context detection."""
        context = MemoryContext(trade_history="Some trade history")
        assert not context.is_empty()

    def test_to_prompt_string_empty(self):
        """Test prompt string for empty context."""
        context = MemoryContext()
        result = context.to_prompt_string()
        assert "No relevant memory context" in result

    def test_to_prompt_string_with_history(self):
        """Test prompt string with trade history."""
        context = MemoryContext(trade_history="AAPL: +5% last week")
        result = context.to_prompt_string()

        assert "Recent Trade History" in result
        assert "AAPL: +5% last week" in result

    def test_to_prompt_string_with_all_sections(self):
        """Test prompt string with all sections."""
        context = MemoryContext(
            trade_history="Trade history content",
            risk_context="Risk context content",
            similar_situations="Similar situations content",
            lessons_learned="Lessons learned content",
        )
        result = context.to_prompt_string()

        assert "Recent Trade History" in result
        assert "Risk Profile Context" in result
        assert "Similar Past Situations" in result
        assert "Lessons Learned" in result

    def test_to_prompt_string_filter_by_type(self):
        """Test filtering context by type."""
        context = MemoryContext(
            trade_history="Trade history content",
            risk_context="Risk context content",
            lessons_learned="Lessons learned content",
        )

        # Only trade history
        result = context.to_prompt_string([ContextType.TRADE_HISTORY])
        assert "Recent Trade History" in result
        assert "Risk Profile Context" not in result
        assert "Lessons Learned" not in result

    def test_to_prompt_string_multiple_types(self):
        """Test filtering with multiple types."""
        context = MemoryContext(
            trade_history="Trade history content",
            risk_context="Risk context content",
            lessons_learned="Lessons learned content",
        )

        result = context.to_prompt_string([
            ContextType.TRADE_HISTORY,
            ContextType.RISK_PROFILE,
        ])

        assert "Recent Trade History" in result
        assert "Risk Profile Context" in result
        assert "Lessons Learned" not in result


# =============================================================================
# AgentMemoryIntegration Tests
# =============================================================================


class TestAgentMemoryIntegration:
    """Tests for AgentMemoryIntegration class."""

    def test_create_integration(self):
        """Test creating integration instance."""
        integration = AgentMemoryIntegration()
        assert integration.trade_memory is not None
        assert integration.risk_memory is not None
        assert integration.situation_memory is not None

    def test_get_analyst_context_empty(self):
        """Test getting analyst context with no history."""
        integration = AgentMemoryIntegration()

        context = integration.get_analyst_context(
            symbol="AAPL",
            current_situation="Tech sector showing strength",
            analyst_type="momentum",
        )

        # Should return context (may be empty)
        assert isinstance(context, MemoryContext)

    def test_get_analyst_context_with_trades(self):
        """Test getting analyst context with trade history."""
        integration = AgentMemoryIntegration()

        # Add some trades
        trade = TradeRecord.create(
            symbol="AAPL",
            direction=TradeDirection.LONG,
            entry_price=150.0,
            quantity=100,
        )
        trade.close(exit_price=160.0)
        integration.trade_memory.record_trade(trade)

        context = integration.get_analyst_context(
            symbol="AAPL",
            current_situation="Tech rally",
            analyst_type="momentum",
        )

        assert len(context.raw_trades) > 0
        assert "AAPL" in context.trade_history

    def test_get_trader_context_empty(self):
        """Test getting trader context with no history."""
        integration = AgentMemoryIntegration()

        context = integration.get_trader_context(
            symbol="TSLA",
            current_situation="EV sector momentum",
            proposed_action="buy",
        )

        assert isinstance(context, MemoryContext)

    def test_get_trader_context_with_regime(self):
        """Test getting trader context with market regime."""
        integration = AgentMemoryIntegration()

        # Set up a profile
        profile = RiskProfile(user_id="default", base_tolerance=RiskTolerance.MODERATE)
        integration.risk_memory.set_profile(profile)

        context = integration.get_trader_context(
            symbol="AAPL",
            current_situation="Bull market",
            proposed_action="buy",
            market_regime=MarketRegime.BULL,
        )

        assert "Recommended risk level" in context.risk_context
        assert "moderate" in context.risk_context.lower()

    def test_get_risk_manager_context(self):
        """Test getting risk manager context."""
        integration = AgentMemoryIntegration()

        # Add some trades with outcomes
        for i in range(5):
            trade = TradeRecord.create(
                symbol="MSFT",
                direction=TradeDirection.LONG,
                entry_price=300.0 + i,
                quantity=100,
            )
            # Some winners, some losers
            if i % 2 == 0:
                trade.close(exit_price=310.0 + i)
            else:
                trade.close(exit_price=290.0 + i)
            integration.trade_memory.record_trade(trade)

        context = integration.get_risk_manager_context(
            symbol="MSFT",
            proposed_trade="Buy 100 shares at $305",
            position_size=30500,
            market_regime=MarketRegime.BULL,
        )

        assert "Trading history for MSFT" in context.trade_history
        assert "Win rate" in context.trade_history

    def test_record_trade_outcome(self):
        """Test recording a trade outcome."""
        integration = AgentMemoryIntegration()

        trade = TradeRecord.create(
            symbol="GOOGL",
            direction=TradeDirection.LONG,
            entry_price=140.0,
            quantity=50,
        )
        trade.close(exit_price=150.0)

        integration.record_trade_outcome(
            trade=trade,
            situation_context="Tech sector showing AI momentum",
            lesson_learned="AI momentum trades tend to work well",
        )

        # Trade should be in memory
        trades = integration.trade_memory.get_trades_by_symbol("GOOGL")
        assert len(trades) == 1
        assert trades[0].symbol == "GOOGL"

        # Situation should be recorded
        assert integration.situation_memory.count() == 1

    def test_record_risk_decision(self):
        """Test recording a risk decision."""
        integration = AgentMemoryIntegration()

        decision_id = integration.record_risk_decision(
            category=RiskCategory.POSITION_SIZE,
            risk_level=0.6,
            market_regime=MarketRegime.BULL,
            context="Strong momentum, increasing position",
        )

        assert decision_id is not None

        # Decision should be recorded
        decision = integration.risk_memory.get_decision(decision_id)
        assert decision is not None
        assert decision.risk_level == 0.6

    def test_evaluate_risk_decision(self):
        """Test evaluating a risk decision."""
        integration = AgentMemoryIntegration()

        decision_id = integration.record_risk_decision(
            category=RiskCategory.LEVERAGE,
            risk_level=0.7,
            market_regime=MarketRegime.LOW_VOLATILITY,
            context="Low vol, using leverage",
        )

        integration.evaluate_risk_decision(
            decision_id=decision_id,
            outcome="Profitable trade with leverage",
            outcome_score=0.6,
            was_appropriate=True,
        )

        decision = integration.risk_memory.get_decision(decision_id)
        assert decision.was_appropriate is True
        assert decision.outcome_score == 0.6

    def test_to_dict_and_from_dict(self):
        """Test serialization roundtrip."""
        integration = AgentMemoryIntegration()

        # Add some data
        trade = TradeRecord.create(
            symbol="NVDA",
            direction=TradeDirection.LONG,
            entry_price=500.0,
            quantity=20,
        )
        trade.close(exit_price=550.0)
        integration.trade_memory.record_trade(trade)

        profile = RiskProfile(user_id="test", base_tolerance=RiskTolerance.AGGRESSIVE)
        integration.risk_memory.set_profile(profile)

        # Serialize and restore
        data = integration.to_dict()
        restored = AgentMemoryIntegration.from_dict(data)

        # Verify data preserved
        trades = restored.trade_memory.get_trades_by_symbol("NVDA")
        assert len(trades) == 1

        profile = restored.risk_memory.get_profile("test")
        assert profile is not None
        assert profile.base_tolerance == RiskTolerance.AGGRESSIVE


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestCreateMemoryEnhancedPrompt:
    """Tests for create_memory_enhanced_prompt function."""

    def test_empty_context_returns_base(self):
        """Test that empty context returns base prompt unchanged."""
        base_prompt = "Analyze the stock"
        context = MemoryContext()

        result = create_memory_enhanced_prompt(base_prompt, context)

        assert result == base_prompt

    def test_adds_memory_section(self):
        """Test that memory section is added."""
        base_prompt = "Analyze the stock"
        context = MemoryContext(trade_history="Previous trade: +5%")

        result = create_memory_enhanced_prompt(base_prompt, context)

        assert "Analyze the stock" in result
        assert "Memory Context" in result
        assert "Previous trade: +5%" in result

    def test_respects_context_types(self):
        """Test filtering by context types."""
        base_prompt = "Analyze"
        context = MemoryContext(
            trade_history="Trade history",
            risk_context="Risk context",
        )

        result = create_memory_enhanced_prompt(
            base_prompt,
            context,
            [ContextType.TRADE_HISTORY],
        )

        assert "Trade history" in result
        assert "Risk context" not in result


# =============================================================================
# Integration Tests
# =============================================================================


class TestAgentMemoryIntegrationWorkflow:
    """Integration tests for complete memory workflow."""

    def test_full_trading_workflow(self):
        """Test a complete trading workflow with memory."""
        integration = AgentMemoryIntegration()

        # 1. Set up user profile
        profile = RiskProfile(
            user_id="trader1",
            base_tolerance=RiskTolerance.MODERATE,
        )
        integration.risk_memory.set_profile(profile)

        # 2. Record some historical trades
        historical_trades = [
            ("AAPL", TradeDirection.LONG, 150.0, 160.0),
            ("AAPL", TradeDirection.LONG, 155.0, 165.0),
            ("AAPL", TradeDirection.LONG, 160.0, 155.0),  # Loss
        ]

        for symbol, direction, entry, exit in historical_trades:
            trade = TradeRecord.create(
                symbol=symbol,
                direction=direction,
                entry_price=entry,
                quantity=100,
            )
            trade.close(exit_price=exit)
            integration.record_trade_outcome(
                trade=trade,
                situation_context=f"Trade in {symbol}",
            )

        # 3. Get analyst context for new analysis
        analyst_context = integration.get_analyst_context(
            symbol="AAPL",
            current_situation="Apple showing momentum",
            analyst_type="momentum",
        )

        assert len(analyst_context.raw_trades) == 3
        assert "AAPL" in analyst_context.trade_history

        # 4. Get trader context for decision
        trader_context = integration.get_trader_context(
            symbol="AAPL",
            current_situation="Strong momentum signal",
            proposed_action="buy",
            market_regime=MarketRegime.BULL,
            user_id="trader1",
        )

        assert "Recommended risk level" in trader_context.risk_context

        # 5. Get risk manager context
        risk_context = integration.get_risk_manager_context(
            symbol="AAPL",
            proposed_trade="Buy 100 shares",
            position_size=16000,
            market_regime=MarketRegime.BULL,
            user_id="trader1",
        )

        assert "Win rate" in risk_context.trade_history
        assert "moderate" in risk_context.risk_context.lower()

    def test_memory_influences_recommendations(self):
        """Test that memory influences risk recommendations."""
        integration = AgentMemoryIntegration()

        # Set up profile
        profile = RiskProfile(user_id="default", base_tolerance=RiskTolerance.MODERATE)
        integration.risk_memory.set_profile(profile)

        # Record successful high-risk decisions
        for i in range(5):
            decision_id = integration.record_risk_decision(
                category=RiskCategory.POSITION_SIZE,
                risk_level=0.7,
                market_regime=MarketRegime.BULL,
                context=f"Successful trade {i}",
            )
            integration.evaluate_risk_decision(
                decision_id=decision_id,
                outcome="Profitable",
                outcome_score=0.6,
                was_appropriate=True,
            )

        # Get recommendation - should be influenced by history
        risk_level, explanation = integration.risk_memory.recommend_risk_level(
            category=RiskCategory.POSITION_SIZE,
            market_regime=MarketRegime.BULL,
            context="Similar successful situation",
        )

        # With successful high-risk history, recommendation should be elevated
        # Base moderate (0.375) + bull adjustment (0.1) = 0.475
        # But with history of successful 0.7 decisions, should be higher
        assert risk_level > 0.5

    def test_lessons_extracted_from_trades(self):
        """Test that lessons are extracted from trade patterns."""
        integration = AgentMemoryIntegration()

        # Record winning trades with short hold times
        for i in range(3):
            trade = TradeRecord.create(
                symbol="TSLA",
                direction=TradeDirection.LONG,
                entry_price=200.0,
                quantity=50,
            )
            # Quick win - close the trade
            trade.close(exit_price=220.0)
            integration.trade_memory.record_trade(trade)

        # Record losing trades with long hold times
        for i in range(3):
            trade = TradeRecord.create(
                symbol="TSLA",
                direction=TradeDirection.LONG,
                entry_price=200.0,
                quantity=50,
            )
            # Slow loss
            trade.close(exit_price=180.0)
            integration.trade_memory.record_trade(trade)

        context = integration.get_analyst_context(
            symbol="TSLA",
            current_situation="EV sector",
            analyst_type="general",
        )

        # Lessons should exist (may be strategy continuation or specific lesson)
        assert context.lessons_learned != ""


class TestContextTypeFiltering:
    """Tests for context type filtering."""

    def test_all_types(self):
        """Test ALL context type includes everything."""
        context = MemoryContext(
            trade_history="History",
            risk_context="Risk",
            similar_situations="Similar",
            lessons_learned="Lessons",
        )

        result = context.to_prompt_string([ContextType.ALL])

        assert "History" in result
        assert "Risk" in result
        assert "Similar" in result
        assert "Lessons" in result

    def test_single_type(self):
        """Test filtering to single type."""
        context = MemoryContext(
            trade_history="History",
            risk_context="Risk",
        )

        result = context.to_prompt_string([ContextType.RISK_PROFILE])

        assert "History" not in result
        assert "Risk" in result

    def test_empty_sections_not_included(self):
        """Test that empty sections aren't shown."""
        context = MemoryContext(
            trade_history="History",
            risk_context="",  # Empty
        )

        result = context.to_prompt_string([ContextType.ALL])

        assert "Recent Trade History" in result
        assert "Risk Profile Context" not in result
