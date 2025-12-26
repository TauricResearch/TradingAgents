"""Trade History Memory for learning from past trade outcomes.

This module provides specialized memory for tracking and learning from trades:
- Trade outcomes (profit/loss, returns)
- Agent reasoning and signals
- Entry/exit conditions
- Market context at time of trade

Issue #19: [MEM-18] Trade history memory - outcomes, agent reasoning
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
import uuid

from .layered_memory import (
    LayeredMemory,
    MemoryEntry,
    MemoryConfig,
    ScoringWeights,
    ImportanceLevel,
)


class TradeOutcome(Enum):
    """Trade outcome categories."""
    PROFITABLE = "profitable"      # Positive return
    BREAK_EVEN = "break_even"      # ~0% return
    LOSS = "loss"                  # Negative return
    STOPPED_OUT = "stopped_out"    # Hit stop loss
    TARGET_HIT = "target_hit"      # Hit profit target


class TradeDirection(Enum):
    """Trade direction."""
    LONG = "long"
    SHORT = "short"
    HOLD = "hold"


class SignalStrength(Enum):
    """Signal strength levels."""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


@dataclass
class AgentReasoning:
    """Captures reasoning from each agent in the trading workflow.

    Attributes:
        fundamentals: Fundamentals analyst reasoning
        technical: Technical/market analyst reasoning
        news: News analyst reasoning
        sentiment: Social media sentiment reasoning
        momentum: Momentum analyst reasoning (if enabled)
        macro: Macro analyst reasoning (if enabled)
        correlation: Correlation analyst reasoning (if enabled)
        bull_case: Bull researcher arguments
        bear_case: Bear researcher arguments
        research_conclusion: Research manager decision
        risk_assessment: Risk manager assessment
        final_signal: Final trading signal
    """
    fundamentals: Optional[str] = None
    technical: Optional[str] = None
    news: Optional[str] = None
    sentiment: Optional[str] = None
    momentum: Optional[str] = None
    macro: Optional[str] = None
    correlation: Optional[str] = None
    bull_case: Optional[str] = None
    bear_case: Optional[str] = None
    research_conclusion: Optional[str] = None
    risk_assessment: Optional[str] = None
    final_signal: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        """Convert to dictionary."""
        return {
            "fundamentals": self.fundamentals,
            "technical": self.technical,
            "news": self.news,
            "sentiment": self.sentiment,
            "momentum": self.momentum,
            "macro": self.macro,
            "correlation": self.correlation,
            "bull_case": self.bull_case,
            "bear_case": self.bear_case,
            "research_conclusion": self.research_conclusion,
            "risk_assessment": self.risk_assessment,
            "final_signal": self.final_signal,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentReasoning":
        """Create from dictionary."""
        return cls(
            fundamentals=data.get("fundamentals"),
            technical=data.get("technical"),
            news=data.get("news"),
            sentiment=data.get("sentiment"),
            momentum=data.get("momentum"),
            macro=data.get("macro"),
            correlation=data.get("correlation"),
            bull_case=data.get("bull_case"),
            bear_case=data.get("bear_case"),
            research_conclusion=data.get("research_conclusion"),
            risk_assessment=data.get("risk_assessment"),
            final_signal=data.get("final_signal"),
        )

    def summary(self) -> str:
        """Generate a text summary of the reasoning."""
        parts = []

        if self.fundamentals:
            parts.append(f"Fundamentals: {self.fundamentals[:100]}...")
        if self.technical:
            parts.append(f"Technical: {self.technical[:100]}...")
        if self.bull_case:
            parts.append(f"Bull: {self.bull_case[:100]}...")
        if self.bear_case:
            parts.append(f"Bear: {self.bear_case[:100]}...")
        if self.research_conclusion:
            parts.append(f"Conclusion: {self.research_conclusion[:100]}...")

        return " | ".join(parts) if parts else "No reasoning recorded"


@dataclass
class MarketContext:
    """Market conditions at time of trade.

    Attributes:
        vix: VIX volatility index level
        spy_return_1d: SPY 1-day return
        sector_performance: Dict of sector returns
        economic_regime: Detected economic regime
        yield_curve_state: Yield curve status
        macro_indicators: Key macro indicators
    """
    vix: Optional[float] = None
    spy_return_1d: Optional[float] = None
    sector_performance: Dict[str, float] = field(default_factory=dict)
    economic_regime: Optional[str] = None
    yield_curve_state: Optional[str] = None
    macro_indicators: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "vix": self.vix,
            "spy_return_1d": self.spy_return_1d,
            "sector_performance": self.sector_performance,
            "economic_regime": self.economic_regime,
            "yield_curve_state": self.yield_curve_state,
            "macro_indicators": self.macro_indicators,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketContext":
        """Create from dictionary."""
        return cls(
            vix=data.get("vix"),
            spy_return_1d=data.get("spy_return_1d"),
            sector_performance=data.get("sector_performance", {}),
            economic_regime=data.get("economic_regime"),
            yield_curve_state=data.get("yield_curve_state"),
            macro_indicators=data.get("macro_indicators", {}),
        )

    def summary(self) -> str:
        """Generate a text summary of market context."""
        parts = []

        if self.vix is not None:
            parts.append(f"VIX: {self.vix:.1f}")
        if self.economic_regime:
            parts.append(f"Regime: {self.economic_regime}")
        if self.yield_curve_state:
            parts.append(f"Yield Curve: {self.yield_curve_state}")

        return " | ".join(parts) if parts else "No market context"


@dataclass
class TradeRecord:
    """Complete record of a trade including reasoning and outcome.

    Attributes:
        id: Unique trade ID
        symbol: Trading symbol
        direction: Trade direction (long/short/hold)
        entry_price: Entry price
        exit_price: Exit price (if closed)
        entry_time: Entry timestamp
        exit_time: Exit timestamp (if closed)
        quantity: Number of shares/contracts
        returns: Percentage return
        pnl: Dollar profit/loss
        outcome: Trade outcome category
        signal_strength: Original signal strength
        confidence: Confidence score (0-1)
        reasoning: Agent reasoning captured
        market_context: Market conditions at entry
        lessons_learned: Post-trade lessons (added later)
        tags: Trade tags for filtering
    """
    id: str
    symbol: str
    direction: TradeDirection
    entry_price: float
    entry_time: datetime
    quantity: float = 1.0
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    returns: Optional[float] = None
    pnl: Optional[float] = None
    outcome: Optional[TradeOutcome] = None
    signal_strength: SignalStrength = SignalStrength.NEUTRAL
    confidence: float = 0.5
    reasoning: AgentReasoning = field(default_factory=AgentReasoning)
    market_context: MarketContext = field(default_factory=MarketContext)
    lessons_learned: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        symbol: str,
        direction: TradeDirection,
        entry_price: float,
        quantity: float = 1.0,
        signal_strength: SignalStrength = SignalStrength.NEUTRAL,
        confidence: float = 0.5,
        reasoning: Optional[AgentReasoning] = None,
        market_context: Optional[MarketContext] = None,
        tags: Optional[List[str]] = None,
    ) -> "TradeRecord":
        """Create a new trade record."""
        return cls(
            id=str(uuid.uuid4()),
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            entry_time=datetime.now(),
            quantity=quantity,
            signal_strength=signal_strength,
            confidence=confidence,
            reasoning=reasoning or AgentReasoning(),
            market_context=market_context or MarketContext(),
            tags=tags or [],
        )

    def close(
        self,
        exit_price: float,
        exit_time: Optional[datetime] = None,
    ) -> "TradeRecord":
        """Close the trade and calculate returns.

        Args:
            exit_price: Exit price
            exit_time: Exit timestamp (default: now)

        Returns:
            Self with updated exit info
        """
        self.exit_price = exit_price
        self.exit_time = exit_time or datetime.now()

        # Calculate returns
        if self.direction == TradeDirection.LONG:
            self.returns = (exit_price - self.entry_price) / self.entry_price
        elif self.direction == TradeDirection.SHORT:
            self.returns = (self.entry_price - exit_price) / self.entry_price
        else:
            self.returns = 0.0

        # Calculate PnL
        self.pnl = self.returns * self.entry_price * self.quantity

        # Determine outcome
        if self.returns > 0.005:  # > 0.5%
            self.outcome = TradeOutcome.PROFITABLE
        elif self.returns < -0.005:  # < -0.5%
            self.outcome = TradeOutcome.LOSS
        else:
            self.outcome = TradeOutcome.BREAK_EVEN

        return self

    def is_open(self) -> bool:
        """Check if trade is still open."""
        return self.exit_time is None

    def holding_period_days(self) -> Optional[float]:
        """Calculate holding period in days."""
        if self.exit_time is None:
            return None
        delta = self.exit_time - self.entry_time
        return delta.total_seconds() / 86400

    def to_memory_content(self) -> str:
        """Generate memory content for this trade."""
        parts = [
            f"Trade {self.direction.value} {self.symbol} at ${self.entry_price:.2f}",
        ]

        if self.outcome:
            parts.append(f"Outcome: {self.outcome.value}")

        if self.returns is not None:
            parts.append(f"Return: {self.returns * 100:.2f}%")

        if self.reasoning.research_conclusion:
            parts.append(f"Reasoning: {self.reasoning.research_conclusion}")

        if self.market_context.economic_regime:
            parts.append(f"Regime: {self.market_context.economic_regime}")

        return " | ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "direction": self.direction.value,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "quantity": self.quantity,
            "returns": self.returns,
            "pnl": self.pnl,
            "outcome": self.outcome.value if self.outcome else None,
            "signal_strength": self.signal_strength.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning.to_dict(),
            "market_context": self.market_context.to_dict(),
            "lessons_learned": self.lessons_learned,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradeRecord":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            symbol=data["symbol"],
            direction=TradeDirection(data["direction"]),
            entry_price=data["entry_price"],
            exit_price=data.get("exit_price"),
            entry_time=datetime.fromisoformat(data["entry_time"]),
            exit_time=datetime.fromisoformat(data["exit_time"]) if data.get("exit_time") else None,
            quantity=data.get("quantity", 1.0),
            returns=data.get("returns"),
            pnl=data.get("pnl"),
            outcome=TradeOutcome(data["outcome"]) if data.get("outcome") else None,
            signal_strength=SignalStrength(data.get("signal_strength", "neutral")),
            confidence=data.get("confidence", 0.5),
            reasoning=AgentReasoning.from_dict(data.get("reasoning", {})),
            market_context=MarketContext.from_dict(data.get("market_context", {})),
            lessons_learned=data.get("lessons_learned"),
            tags=data.get("tags", []),
        )


class TradeHistoryMemory:
    """Memory system specialized for trade history and learning.

    This class combines trade record storage with the layered memory system
    for intelligent retrieval of past trades based on similarity.

    Example:
        >>> memory = TradeHistoryMemory()
        >>>
        >>> # Record a trade
        >>> trade = TradeRecord.create(
        ...     symbol="AAPL",
        ...     direction=TradeDirection.LONG,
        ...     entry_price=150.0,
        ...     reasoning=AgentReasoning(
        ...         fundamentals="Strong earnings",
        ...         research_conclusion="Buy on earnings momentum",
        ...     ),
        ... )
        >>> memory.record_trade(trade)
        >>>
        >>> # Close the trade
        >>> memory.close_trade(trade.id, exit_price=165.0)
        >>>
        >>> # Find similar past trades
        >>> similar = memory.find_similar_trades(
        ...     query="Apple earnings momentum",
        ...     top_k=5,
        ... )
    """

    def __init__(
        self,
        config: Optional[MemoryConfig] = None,
        embedding_function=None,
    ):
        """Initialize trade history memory.

        Args:
            config: Memory configuration
            embedding_function: Optional embedding function for similarity
        """
        # Default config with weights tuned for trade history
        if config is None:
            config = MemoryConfig(
                weights=ScoringWeights(
                    recency=0.25,      # Recent trades somewhat important
                    relevancy=0.45,    # Similarity most important
                    importance=0.30,   # Outcome importance matters
                ),
            )

        self._layered_memory = LayeredMemory(
            config=config,
            embedding_function=embedding_function,
        )
        self._trades: Dict[str, TradeRecord] = {}

    def record_trade(self, trade: TradeRecord) -> str:
        """Record a new trade.

        Args:
            trade: The trade record to store

        Returns:
            Trade ID
        """
        self._trades[trade.id] = trade

        # Create memory entry for the trade
        importance = self._calculate_trade_importance(trade)
        entry = MemoryEntry.create(
            content=trade.to_memory_content(),
            metadata={
                "trade_id": trade.id,
                "symbol": trade.symbol,
                "direction": trade.direction.value,
                "outcome": trade.outcome.value if trade.outcome else None,
                "returns": trade.returns,
                "reasoning_summary": trade.reasoning.summary(),
            },
            importance=importance,
            tags=trade.tags + [trade.symbol, trade.direction.value],
            timestamp=trade.entry_time,
        )
        entry.id = trade.id  # Use trade ID as memory ID

        self._layered_memory.add(entry)
        return trade.id

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        lessons_learned: Optional[str] = None,
    ) -> Optional[TradeRecord]:
        """Close an open trade and update memory.

        Args:
            trade_id: ID of the trade to close
            exit_price: Exit price
            lessons_learned: Optional lessons from the trade

        Returns:
            Updated trade record or None if not found
        """
        trade = self._trades.get(trade_id)
        if trade is None:
            return None

        # Close the trade
        trade.close(exit_price)

        if lessons_learned:
            trade.lessons_learned = lessons_learned

        # Update memory with outcome
        importance = self._calculate_trade_importance(trade)
        self._layered_memory.update_importance(trade_id, importance)

        # Update memory entry content
        entry = self._layered_memory.get(trade_id)
        if entry:
            entry.metadata["outcome"] = trade.outcome.value if trade.outcome else None
            entry.metadata["returns"] = trade.returns
            if lessons_learned:
                entry.metadata["lessons_learned"] = lessons_learned

        return trade

    def get_trade(self, trade_id: str) -> Optional[TradeRecord]:
        """Get a trade by ID.

        Args:
            trade_id: Trade ID

        Returns:
            Trade record or None
        """
        return self._trades.get(trade_id)

    def get_open_trades(self) -> List[TradeRecord]:
        """Get all open trades.

        Returns:
            List of open trade records
        """
        return [t for t in self._trades.values() if t.is_open()]

    def get_closed_trades(self) -> List[TradeRecord]:
        """Get all closed trades.

        Returns:
            List of closed trade records
        """
        return [t for t in self._trades.values() if not t.is_open()]

    def get_trades_by_symbol(self, symbol: str) -> List[TradeRecord]:
        """Get all trades for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            List of trade records for the symbol
        """
        return [t for t in self._trades.values() if t.symbol == symbol]

    def find_similar_trades(
        self,
        query: str,
        top_k: int = 5,
        symbol: Optional[str] = None,
        outcome: Optional[TradeOutcome] = None,
    ) -> List[TradeRecord]:
        """Find similar past trades.

        Args:
            query: Query describing the current situation
            top_k: Maximum number of results
            symbol: Optional filter by symbol
            outcome: Optional filter by outcome

        Returns:
            List of similar trade records
        """
        # Build tags filter
        tags = []
        if symbol:
            tags.append(symbol)

        # Retrieve from layered memory
        results = self._layered_memory.retrieve(
            query=query,
            top_k=top_k * 2,  # Get more to filter
            tags=tags if tags else None,
        )

        # Convert to trade records and filter
        trades = []
        for scored in results:
            trade_id = scored.entry.metadata.get("trade_id")
            if trade_id and trade_id in self._trades:
                trade = self._trades[trade_id]

                # Apply outcome filter
                if outcome and trade.outcome != outcome:
                    continue

                trades.append(trade)

                if len(trades) >= top_k:
                    break

        return trades

    def find_profitable_patterns(
        self,
        query: str,
        min_return: float = 0.0,
        top_k: int = 5,
    ) -> List[TradeRecord]:
        """Find profitable trades similar to the query.

        Args:
            query: Query describing the current situation
            min_return: Minimum return filter
            top_k: Maximum number of results

        Returns:
            List of profitable trade records
        """
        results = self._layered_memory.retrieve(query=query, top_k=top_k * 3)

        trades = []
        for scored in results:
            trade_id = scored.entry.metadata.get("trade_id")
            if trade_id and trade_id in self._trades:
                trade = self._trades[trade_id]

                if trade.returns is not None and trade.returns >= min_return:
                    trades.append(trade)

                    if len(trades) >= top_k:
                        break

        return trades

    def find_losing_patterns(
        self,
        query: str,
        max_return: float = 0.0,
        top_k: int = 5,
    ) -> List[TradeRecord]:
        """Find losing trades similar to the query (for learning what to avoid).

        Args:
            query: Query describing the current situation
            max_return: Maximum return filter
            top_k: Maximum number of results

        Returns:
            List of losing trade records
        """
        results = self._layered_memory.retrieve(query=query, top_k=top_k * 3)

        trades = []
        for scored in results:
            trade_id = scored.entry.metadata.get("trade_id")
            if trade_id and trade_id in self._trades:
                trade = self._trades[trade_id]

                if trade.returns is not None and trade.returns <= max_return:
                    trades.append(trade)

                    if len(trades) >= top_k:
                        break

        return trades

    def get_statistics(self) -> Dict[str, Any]:
        """Get trade history statistics.

        Returns:
            Dictionary with statistics
        """
        closed_trades = self.get_closed_trades()

        if not closed_trades:
            return {
                "total_trades": len(self._trades),
                "open_trades": len(self.get_open_trades()),
                "closed_trades": 0,
                "win_rate": 0.0,
                "avg_return": 0.0,
                "total_pnl": 0.0,
                "best_trade": None,
                "worst_trade": None,
            }

        returns = [t.returns for t in closed_trades if t.returns is not None]
        pnls = [t.pnl for t in closed_trades if t.pnl is not None]
        winners = [t for t in closed_trades if t.outcome == TradeOutcome.PROFITABLE]

        # Find best and worst
        best_trade = max(closed_trades, key=lambda t: t.returns or 0, default=None)
        worst_trade = min(closed_trades, key=lambda t: t.returns or 0, default=None)

        # Outcome distribution
        outcome_dist = {}
        for trade in closed_trades:
            if trade.outcome:
                outcome_dist[trade.outcome.value] = outcome_dist.get(trade.outcome.value, 0) + 1

        return {
            "total_trades": len(self._trades),
            "open_trades": len(self.get_open_trades()),
            "closed_trades": len(closed_trades),
            "win_rate": len(winners) / len(closed_trades) if closed_trades else 0.0,
            "avg_return": sum(returns) / len(returns) if returns else 0.0,
            "total_pnl": sum(pnls) if pnls else 0.0,
            "best_trade": best_trade.to_dict() if best_trade else None,
            "worst_trade": worst_trade.to_dict() if worst_trade else None,
            "outcome_distribution": outcome_dist,
        }

    def get_symbol_statistics(self, symbol: str) -> Dict[str, Any]:
        """Get statistics for a specific symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Dictionary with symbol-specific statistics
        """
        symbol_trades = self.get_trades_by_symbol(symbol)
        closed_trades = [t for t in symbol_trades if not t.is_open()]

        if not closed_trades:
            return {
                "symbol": symbol,
                "total_trades": len(symbol_trades),
                "open_trades": len([t for t in symbol_trades if t.is_open()]),
                "closed_trades": 0,
                "win_rate": 0.0,
                "avg_return": 0.0,
            }

        returns = [t.returns for t in closed_trades if t.returns is not None]
        winners = [t for t in closed_trades if t.outcome == TradeOutcome.PROFITABLE]

        return {
            "symbol": symbol,
            "total_trades": len(symbol_trades),
            "open_trades": len([t for t in symbol_trades if t.is_open()]),
            "closed_trades": len(closed_trades),
            "win_rate": len(winners) / len(closed_trades) if closed_trades else 0.0,
            "avg_return": sum(returns) / len(returns) if returns else 0.0,
        }

    def _calculate_trade_importance(self, trade: TradeRecord) -> float:
        """Calculate importance score for a trade.

        Args:
            trade: Trade record

        Returns:
            Importance score [0, 1]
        """
        # Base on returns if closed
        if trade.returns is not None:
            abs_return = abs(trade.returns)
            if abs_return >= 0.10:  # 10%+
                return ImportanceLevel.CRITICAL.value
            elif abs_return >= 0.05:  # 5%+
                return ImportanceLevel.HIGH.value
            elif abs_return >= 0.01:  # 1%+
                return ImportanceLevel.MEDIUM.value
            else:
                return ImportanceLevel.LOW.value

        # For open trades, base on confidence
        if trade.confidence >= 0.8:
            return ImportanceLevel.HIGH.value
        elif trade.confidence >= 0.5:
            return ImportanceLevel.MEDIUM.value
        else:
            return ImportanceLevel.LOW.value

    def count(self) -> int:
        """Return total number of trades."""
        return len(self._trades)

    def clear(self) -> int:
        """Clear all trades.

        Returns:
            Number of trades cleared
        """
        count = len(self._trades)
        self._trades.clear()
        self._layered_memory.clear()
        return count

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "trades": [t.to_dict() for t in self._trades.values()],
            "memory": self._layered_memory.to_dict(),
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        embedding_function=None,
    ) -> "TradeHistoryMemory":
        """Create from dictionary.

        Args:
            data: Dictionary representation
            embedding_function: Optional embedding function

        Returns:
            TradeHistoryMemory instance
        """
        instance = cls(embedding_function=embedding_function)

        # Restore trades
        for trade_data in data.get("trades", []):
            trade = TradeRecord.from_dict(trade_data)
            instance._trades[trade.id] = trade

        # Restore layered memory
        if "memory" in data:
            instance._layered_memory = LayeredMemory.from_dict(
                data["memory"],
                embedding_function=embedding_function,
            )

        return instance
