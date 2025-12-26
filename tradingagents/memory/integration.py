"""Memory integration for agent prompts.

This module provides integration between the memory system and agent prompts,
enabling agents to access relevant historical context for better decision-making.

Issue #21: [MEM-20] Memory integration - retrieval in agent prompts
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from enum import Enum

from .layered_memory import LayeredMemory, MemoryEntry, MemoryConfig, ScoringWeights
from .trade_history import TradeHistoryMemory, TradeRecord, TradeOutcome, TradeDirection
from .risk_profiles import (
    RiskProfileMemory,
    RiskProfile,
    RiskDecision,
    RiskTolerance,
    MarketRegime,
    RiskCategory,
)


class ContextType(Enum):
    """Types of memory context that can be retrieved."""
    TRADE_HISTORY = "trade_history"
    RISK_PROFILE = "risk_profile"
    SIMILAR_SITUATIONS = "similar_situations"
    LESSONS_LEARNED = "lessons_learned"
    ALL = "all"


@dataclass
class MemoryContext:
    """Memory context for agent prompts.

    Attributes:
        trade_history: Summary of relevant past trades
        risk_context: Risk profile recommendations
        similar_situations: Similar past situations and outcomes
        lessons_learned: Key lessons from past trades
        raw_trades: List of relevant TradeRecord objects
    """
    trade_history: str = ""
    risk_context: str = ""
    similar_situations: str = ""
    lessons_learned: str = ""
    raw_trades: List[TradeRecord] = field(default_factory=list)

    def to_prompt_string(self, include_types: Optional[List[ContextType]] = None) -> str:
        """Convert memory context to a string for agent prompts.

        Args:
            include_types: Types of context to include (default: all non-empty)

        Returns:
            Formatted string for agent prompts
        """
        if include_types is None:
            include_types = [ContextType.ALL]

        parts = []

        if ContextType.ALL in include_types or ContextType.TRADE_HISTORY in include_types:
            if self.trade_history:
                parts.append(f"## Recent Trade History\n{self.trade_history}")

        if ContextType.ALL in include_types or ContextType.RISK_PROFILE in include_types:
            if self.risk_context:
                parts.append(f"## Risk Profile Context\n{self.risk_context}")

        if ContextType.ALL in include_types or ContextType.SIMILAR_SITUATIONS in include_types:
            if self.similar_situations:
                parts.append(f"## Similar Past Situations\n{self.similar_situations}")

        if ContextType.ALL in include_types or ContextType.LESSONS_LEARNED in include_types:
            if self.lessons_learned:
                parts.append(f"## Lessons Learned\n{self.lessons_learned}")

        if not parts:
            return "No relevant memory context available."

        return "\n\n".join(parts)

    def is_empty(self) -> bool:
        """Check if context is empty."""
        return not any([
            self.trade_history,
            self.risk_context,
            self.similar_situations,
            self.lessons_learned,
        ])


class AgentMemoryIntegration:
    """Integration layer between memory systems and agent prompts.

    This class provides methods to retrieve relevant memory context
    for different agents in the trading system.

    Example:
        >>> integration = AgentMemoryIntegration()
        >>>
        >>> # Get context for an analyst
        >>> context = integration.get_analyst_context(
        ...     ticker="AAPL",
        ...     current_situation="Tech sector showing momentum",
        ...     analyst_type="momentum",
        ... )
        >>>
        >>> # Use in prompt
        >>> prompt = f"Analyze {ticker}. Memory context: {context.to_prompt_string()}"
    """

    def __init__(
        self,
        trade_memory: Optional[TradeHistoryMemory] = None,
        risk_memory: Optional[RiskProfileMemory] = None,
        situation_memory: Optional[LayeredMemory] = None,
        embedding_function: Optional[Callable] = None,
    ):
        """Initialize memory integration.

        Args:
            trade_memory: Trade history memory instance
            risk_memory: Risk profile memory instance
            situation_memory: General situation memory
            embedding_function: Optional embedding function for similarity
        """
        self._trade_memory = trade_memory or TradeHistoryMemory()
        self._risk_memory = risk_memory or RiskProfileMemory()
        self._situation_memory = situation_memory or LayeredMemory(
            config=MemoryConfig(
                weights=ScoringWeights(recency=0.3, relevancy=0.5, importance=0.2)
            ),
            embedding_function=embedding_function,
        )
        self._embedding_function = embedding_function

    @property
    def trade_memory(self) -> TradeHistoryMemory:
        """Access trade history memory."""
        return self._trade_memory

    @property
    def risk_memory(self) -> RiskProfileMemory:
        """Access risk profile memory."""
        return self._risk_memory

    @property
    def situation_memory(self) -> LayeredMemory:
        """Access situation memory."""
        return self._situation_memory

    def get_analyst_context(
        self,
        symbol: str,
        current_situation: str,
        analyst_type: str = "general",
        lookback_days: int = 90,
        max_trades: int = 5,
        user_id: Optional[str] = None,
    ) -> MemoryContext:
        """Get memory context for an analyst agent.

        Args:
            symbol: Stock symbol being analyzed
            current_situation: Current market situation description
            analyst_type: Type of analyst (momentum, macro, etc.)
            lookback_days: Days to look back for trades
            max_trades: Maximum trades to include
            user_id: User ID for risk profile

        Returns:
            MemoryContext with relevant information
        """
        context = MemoryContext()

        # Get relevant past trades for this symbol
        trades = self._trade_memory.get_trades_by_symbol(symbol)

        if trades:
            # Filter to lookback period
            cutoff = datetime.now() - timedelta(days=lookback_days)
            recent_trades = [t for t in trades if t.entry_time >= cutoff][:max_trades]

            if recent_trades:
                context.raw_trades = recent_trades
                context.trade_history = self._format_trade_history(recent_trades)
                context.lessons_learned = self._extract_lessons(recent_trades)

        # Get similar situations
        similar = self._situation_memory.retrieve(
            query=current_situation,
            top_k=3,
            tags=[analyst_type] if analyst_type != "general" else None,
        )

        if similar:
            context.similar_situations = self._format_similar_situations(similar)

        return context

    def get_trader_context(
        self,
        symbol: str,
        current_situation: str,
        proposed_action: str,
        market_regime: Optional[MarketRegime] = None,
        user_id: Optional[str] = None,
    ) -> MemoryContext:
        """Get memory context for the trader agent.

        Args:
            symbol: Stock symbol being traded
            current_situation: Current market situation
            proposed_action: Proposed trade action (buy/sell/hold)
            market_regime: Current market regime
            user_id: User ID for risk profile

        Returns:
            MemoryContext with relevant information
        """
        context = MemoryContext()

        # Get past trades for this symbol
        trades = self._trade_memory.get_trades_by_symbol(symbol)
        if trades:
            context.raw_trades = trades[:5]
            context.trade_history = self._format_trade_history(trades[:5])
            context.lessons_learned = self._extract_lessons(trades)

        # Get risk profile context
        if market_regime:
            risk_level, explanation = self._risk_memory.recommend_risk_level(
                category=RiskCategory.POSITION_SIZE,
                market_regime=market_regime,
                context=current_situation,
                user_id=user_id,
            )
            profile = self._risk_memory.get_or_create_profile(user_id)
            context.risk_context = (
                f"Recommended risk level: {risk_level:.2f}\n"
                f"Base tolerance: {profile.base_tolerance.value}\n"
                f"Reasoning: {explanation}"
            )

        # Get similar trading situations
        similar = self._situation_memory.retrieve(
            query=f"{current_situation} {proposed_action}",
            top_k=3,
        )

        if similar:
            context.similar_situations = self._format_similar_situations(similar)

        return context

    def get_risk_manager_context(
        self,
        symbol: str,
        proposed_trade: str,
        position_size: float,
        market_regime: Optional[MarketRegime] = None,
        user_id: Optional[str] = None,
    ) -> MemoryContext:
        """Get memory context for risk management agent.

        Args:
            symbol: Stock symbol
            proposed_trade: Proposed trade description
            position_size: Proposed position size
            market_regime: Current market regime
            user_id: User ID

        Returns:
            MemoryContext with risk-focused information
        """
        context = MemoryContext()

        # Get past trades with outcome statistics
        trades = self._trade_memory.get_trades_by_symbol(symbol)
        if trades:
            winning = [t for t in trades if t.outcome == TradeOutcome.PROFITABLE]
            losing = [t for t in trades if t.outcome == TradeOutcome.LOSS]

            win_rate = len(winning) / len(trades) if trades else 0
            avg_return = sum(
                t.returns or 0 for t in trades if t.returns
            ) / max(1, len([t for t in trades if t.returns]))

            context.trade_history = (
                f"Trading history for {symbol}:\n"
                f"- Total trades: {len(trades)}\n"
                f"- Win rate: {win_rate:.1%}\n"
                f"- Average return: {avg_return:.2%}\n"
                f"- Winners: {len(winning)}, Losers: {len(losing)}"
            )

            # Extract risk lessons
            context.lessons_learned = self._extract_risk_lessons(trades)

        # Get risk profile and recommendations
        if market_regime:
            profile = self._risk_memory.get_or_create_profile(user_id)
            adjusted_tolerance = profile.get_adjusted_tolerance(market_regime)

            risk_level, explanation = self._risk_memory.recommend_risk_level(
                category=RiskCategory.POSITION_SIZE,
                market_regime=market_regime,
                context=proposed_trade,
                user_id=user_id,
            )

            context.risk_context = (
                f"User risk profile:\n"
                f"- Base tolerance: {profile.base_tolerance.value}\n"
                f"- Adjusted for {market_regime.value}: {adjusted_tolerance.value}\n"
                f"- Max drawdown tolerance: {profile.max_drawdown_tolerance:.1%}\n"
                f"- Recommended risk level: {risk_level:.2f}\n"
                f"- Reasoning: {explanation}"
            )

        return context

    def record_trade_outcome(
        self,
        trade: TradeRecord,
        situation_context: str,
        lesson_learned: Optional[str] = None,
    ) -> None:
        """Record a trade outcome for future reference.

        Args:
            trade: The completed trade record
            situation_context: Description of the market situation
            lesson_learned: Optional lesson to remember
        """
        # Record in trade memory
        self._trade_memory.record_trade(trade)

        # Record situation for future similarity matching
        importance = 0.5
        if trade.returns:
            # Higher importance for significant outcomes
            importance = min(1.0, 0.5 + abs(trade.returns))

        entry_content = (
            f"Trade: {trade.direction.value} {trade.symbol} at {trade.entry_price}. "
            f"Outcome: {trade.outcome.value if trade.outcome else 'pending'}. "
            f"Context: {situation_context}"
        )

        if lesson_learned:
            entry_content += f"\nLesson: {lesson_learned}"

        entry = MemoryEntry.create(
            content=entry_content,
            metadata={
                "trade_id": trade.id,
                "symbol": trade.symbol,
                "direction": trade.direction.value,
                "outcome": trade.outcome.value if trade.outcome else None,
                "return": trade.returns,
            },
            importance=importance,
            tags=[trade.symbol, trade.direction.value],
        )

        self._situation_memory.add(entry)

    def record_risk_decision(
        self,
        category: RiskCategory,
        risk_level: float,
        market_regime: MarketRegime,
        context: str,
        user_id: Optional[str] = None,
    ) -> str:
        """Record a risk decision for learning.

        Args:
            category: Risk category
            risk_level: Risk level chosen
            market_regime: Current market regime
            context: Decision context
            user_id: User ID

        Returns:
            Decision ID
        """
        decision = RiskDecision.create(
            category=category,
            risk_level=risk_level,
            market_regime=market_regime,
            context=context,
        )

        return self._risk_memory.record_decision(decision, user_id)

    def evaluate_risk_decision(
        self,
        decision_id: str,
        outcome: str,
        outcome_score: float,
        was_appropriate: bool,
    ) -> None:
        """Evaluate a past risk decision.

        Args:
            decision_id: Decision ID to evaluate
            outcome: What happened
            outcome_score: Outcome score (-1 to 1)
            was_appropriate: Whether decision was appropriate
        """
        self._risk_memory.evaluate_decision(
            decision_id=decision_id,
            outcome=outcome,
            outcome_score=outcome_score,
            was_appropriate=was_appropriate,
        )

    def _format_trade_history(self, trades: List[TradeRecord]) -> str:
        """Format trade history for prompts."""
        if not trades:
            return "No recent trades."

        lines = []
        for trade in trades:
            outcome = trade.outcome.value if trade.outcome else "pending"
            ret = f"{trade.returns:+.2%}" if trade.returns else "N/A"
            lines.append(
                f"- {trade.entry_time.strftime('%Y-%m-%d')}: "
                f"{trade.direction.value.upper()} {trade.symbol} @ ${trade.entry_price:.2f} "
                f"-> {outcome} ({ret})"
            )

        return "\n".join(lines)

    def _format_similar_situations(self, scored_entries) -> str:
        """Format similar situations for prompts."""
        if not scored_entries:
            return "No similar past situations found."

        lines = []
        for scored in scored_entries[:3]:
            entry = scored.entry
            score = scored.combined_score
            lines.append(f"- (relevance: {score:.2f}) {entry.content[:200]}...")

        return "\n".join(lines)

    def _extract_lessons(self, trades: List[TradeRecord]) -> str:
        """Extract lessons learned from trades."""
        if not trades:
            return "No lessons to extract."

        lessons = []

        # Analyze winning vs losing trades
        winners = [t for t in trades if t.outcome == TradeOutcome.PROFITABLE]
        losers = [t for t in trades if t.outcome == TradeOutcome.LOSS]

        if winners and losers:
            win_avg_hold = sum(
                (t.exit_time - t.entry_time).days
                for t in winners if t.exit_time
            ) / max(1, len([t for t in winners if t.exit_time]))

            loss_avg_hold = sum(
                (t.exit_time - t.entry_time).days
                for t in losers if t.exit_time
            ) / max(1, len([t for t in losers if t.exit_time]))

            if win_avg_hold < loss_avg_hold:
                lessons.append("Winners tend to show profits quickly; consider cutting losers earlier.")
            elif loss_avg_hold < win_avg_hold:
                lessons.append("Holding winners longer has been profitable; avoid taking profits too early.")

        # Look for patterns in agent reasoning
        for trade in trades:
            if trade.reasoning and trade.outcome:
                if trade.outcome == TradeOutcome.PROFITABLE:
                    if trade.reasoning.research_conclusion:
                        lessons.append("Trades following analyst conclusions have been profitable.")
                        break
                elif trade.outcome == TradeOutcome.LOSS:
                    if trade.reasoning.risk_assessment:
                        lessons.append("Consider risk assessment more carefully on future trades.")
                        break

        if not lessons:
            return "Continue following current strategy."

        return "\n".join(f"- {lesson}" for lesson in lessons[:3])

    def _extract_risk_lessons(self, trades: List[TradeRecord]) -> str:
        """Extract risk-specific lessons from trades."""
        if not trades:
            return "No risk lessons available."

        lessons = []

        # Analyze large losses
        large_losses = [
            t for t in trades
            if t.returns and t.returns < -0.1
        ]

        if large_losses:
            lessons.append(
                f"Had {len(large_losses)} trades with >10% losses. "
                "Consider tighter stop-losses."
            )

        # Check for position sizing patterns
        trades_with_size = [t for t in trades if t.quantity]
        if trades_with_size:
            large_positions = [
                t for t in trades_with_size
                if t.quantity > 100 and t.outcome == TradeOutcome.LOSS
            ]
            if large_positions:
                lessons.append(
                    "Larger positions have shown higher loss frequency. "
                    "Consider scaling in gradually."
                )

        if not lessons:
            return "No specific risk warnings from recent history."

        return "\n".join(f"- {lesson}" for lesson in lessons)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "trade_memory": self._trade_memory.to_dict(),
            "risk_memory": self._risk_memory.to_dict(),
            "situation_memory": self._situation_memory.to_dict(),
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        embedding_function: Optional[Callable] = None,
    ) -> "AgentMemoryIntegration":
        """Create from dictionary."""
        instance = cls(embedding_function=embedding_function)

        if "trade_memory" in data:
            instance._trade_memory = TradeHistoryMemory.from_dict(
                data["trade_memory"],
                embedding_function=embedding_function,
            )

        if "risk_memory" in data:
            instance._risk_memory = RiskProfileMemory.from_dict(
                data["risk_memory"],
                embedding_function=embedding_function,
            )

        if "situation_memory" in data:
            instance._situation_memory = LayeredMemory.from_dict(
                data["situation_memory"],
                embedding_function=embedding_function,
            )

        return instance


def create_memory_enhanced_prompt(
    base_prompt: str,
    context: MemoryContext,
    context_types: Optional[List[ContextType]] = None,
) -> str:
    """Create a memory-enhanced prompt from a base prompt.

    Args:
        base_prompt: Original agent prompt
        context: Memory context to include
        context_types: Types of context to include

    Returns:
        Enhanced prompt with memory context
    """
    if context.is_empty():
        return base_prompt

    memory_section = context.to_prompt_string(context_types)

    return (
        f"{base_prompt}\n\n"
        f"---\n"
        f"# Memory Context (Use this to inform your analysis)\n\n"
        f"{memory_section}\n"
        f"---"
    )
