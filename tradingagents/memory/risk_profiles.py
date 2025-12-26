"""Risk Profiles Memory for tracking user risk preferences over time.

This module provides memory for tracking and learning from risk preferences:
- Risk tolerance levels across different market conditions
- Risk preference evolution over time
- Market regime-specific risk adjustments
- Historical risk decisions and outcomes

Issue #20: [MEM-19] Risk profiles memory - user preferences over time
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
import statistics
import uuid

from .layered_memory import (
    LayeredMemory,
    MemoryEntry,
    MemoryConfig,
    ScoringWeights,
    ImportanceLevel,
)


class RiskTolerance(Enum):
    """User risk tolerance levels."""
    CONSERVATIVE = "conservative"      # Low risk, capital preservation
    MODERATE = "moderate"              # Balanced risk/reward
    AGGRESSIVE = "aggressive"          # High risk, growth focused
    VERY_AGGRESSIVE = "very_aggressive"  # Maximum risk tolerance

    @classmethod
    def from_score(cls, score: float) -> "RiskTolerance":
        """Convert a risk score (0-1) to RiskTolerance.

        Args:
            score: Risk score between 0 (conservative) and 1 (very aggressive)

        Returns:
            Corresponding RiskTolerance
        """
        if score < 0.25:
            return cls.CONSERVATIVE
        elif score < 0.50:
            return cls.MODERATE
        elif score < 0.75:
            return cls.AGGRESSIVE
        else:
            return cls.VERY_AGGRESSIVE

    def to_score(self) -> float:
        """Convert RiskTolerance to a numeric score.

        Returns:
            Score between 0 and 1
        """
        mapping = {
            RiskTolerance.CONSERVATIVE: 0.125,
            RiskTolerance.MODERATE: 0.375,
            RiskTolerance.AGGRESSIVE: 0.625,
            RiskTolerance.VERY_AGGRESSIVE: 0.875,
        }
        return mapping[self]


class MarketRegime(Enum):
    """Market regime classifications."""
    BULL = "bull"           # Strong uptrend
    BEAR = "bear"           # Strong downtrend
    SIDEWAYS = "sideways"   # Range-bound
    HIGH_VOLATILITY = "high_volatility"  # VIX > 25
    LOW_VOLATILITY = "low_volatility"    # VIX < 15
    CRISIS = "crisis"       # Market stress/crash


class RiskCategory(Enum):
    """Categories of risk decisions."""
    POSITION_SIZE = "position_size"      # How much to invest
    LEVERAGE = "leverage"                # Use of leverage
    DIVERSIFICATION = "diversification"  # Portfolio spread
    HEDGING = "hedging"                  # Protective positions
    STOP_LOSS = "stop_loss"              # Exit thresholds
    SECTOR_EXPOSURE = "sector_exposure"  # Sector concentration
    ASSET_CLASS = "asset_class"          # Asset allocation


@dataclass
class RiskDecision:
    """A recorded risk decision with context and outcome.

    Attributes:
        id: Unique decision ID
        timestamp: When decision was made
        category: Type of risk decision
        risk_level: Risk level chosen (0-1 scale)
        market_regime: Market conditions at decision time
        context: Situation description
        vix_level: VIX at decision time
        outcome: Outcome description (added later)
        outcome_score: Quantified outcome (-1 to 1)
        was_appropriate: Whether decision was appropriate in hindsight
        notes: Additional notes
    """
    id: str
    timestamp: datetime
    category: RiskCategory
    risk_level: float  # 0 (min risk) to 1 (max risk)
    market_regime: MarketRegime
    context: str
    vix_level: Optional[float] = None
    outcome: Optional[str] = None
    outcome_score: Optional[float] = None  # -1 (bad) to 1 (good)
    was_appropriate: Optional[bool] = None
    notes: Optional[str] = None

    @classmethod
    def create(
        cls,
        category: RiskCategory,
        risk_level: float,
        market_regime: MarketRegime,
        context: str,
        vix_level: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> "RiskDecision":
        """Create a new risk decision record.

        Args:
            category: Type of risk decision
            risk_level: Risk level chosen (0-1)
            market_regime: Current market regime
            context: Situation description
            vix_level: Current VIX level
            notes: Additional notes

        Returns:
            New RiskDecision instance
        """
        if not 0.0 <= risk_level <= 1.0:
            raise ValueError(f"Risk level must be between 0 and 1, got {risk_level}")

        return cls(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            category=category,
            risk_level=risk_level,
            market_regime=market_regime,
            context=context,
            vix_level=vix_level,
            notes=notes,
        )

    def evaluate(
        self,
        outcome: str,
        outcome_score: float,
        was_appropriate: bool,
    ) -> "RiskDecision":
        """Evaluate the decision after the outcome is known.

        Args:
            outcome: Description of what happened
            outcome_score: Quantified outcome (-1 to 1)
            was_appropriate: Whether the risk level was appropriate

        Returns:
            Self with updated evaluation
        """
        self.outcome = outcome
        self.outcome_score = max(-1.0, min(1.0, outcome_score))
        self.was_appropriate = was_appropriate
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "category": self.category.value,
            "risk_level": self.risk_level,
            "market_regime": self.market_regime.value,
            "context": self.context,
            "vix_level": self.vix_level,
            "outcome": self.outcome,
            "outcome_score": self.outcome_score,
            "was_appropriate": self.was_appropriate,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskDecision":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            category=RiskCategory(data["category"]),
            risk_level=data["risk_level"],
            market_regime=MarketRegime(data["market_regime"]),
            context=data["context"],
            vix_level=data.get("vix_level"),
            outcome=data.get("outcome"),
            outcome_score=data.get("outcome_score"),
            was_appropriate=data.get("was_appropriate"),
            notes=data.get("notes"),
        )


@dataclass
class RiskProfile:
    """User's risk profile with preferences and history.

    Attributes:
        user_id: User identifier
        base_tolerance: Baseline risk tolerance
        regime_adjustments: Adjustments by market regime
        category_preferences: Preferences by risk category
        max_drawdown_tolerance: Maximum acceptable drawdown
        volatility_preference: Preferred portfolio volatility
        created_at: Profile creation time
        updated_at: Last update time
    """
    user_id: str
    base_tolerance: RiskTolerance = RiskTolerance.MODERATE
    regime_adjustments: Dict[str, float] = field(default_factory=dict)
    category_preferences: Dict[str, float] = field(default_factory=dict)
    max_drawdown_tolerance: float = 0.20  # 20% max drawdown
    volatility_preference: float = 0.15   # 15% annual volatility
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Initialize default regime adjustments if empty."""
        if not self.regime_adjustments:
            self.regime_adjustments = {
                MarketRegime.BULL.value: 0.1,       # Slightly more risk
                MarketRegime.BEAR.value: -0.2,     # Reduce risk
                MarketRegime.SIDEWAYS.value: 0.0,  # No change
                MarketRegime.HIGH_VOLATILITY.value: -0.3,  # Reduce significantly
                MarketRegime.LOW_VOLATILITY.value: 0.1,    # Slightly more risk
                MarketRegime.CRISIS.value: -0.5,   # Maximum reduction
            }

    def get_adjusted_risk_score(self, market_regime: MarketRegime) -> float:
        """Get risk score adjusted for current market regime.

        Args:
            market_regime: Current market regime

        Returns:
            Adjusted risk score (0-1)
        """
        base_score = self.base_tolerance.to_score()
        adjustment = self.regime_adjustments.get(market_regime.value, 0.0)
        adjusted = base_score + adjustment
        return max(0.0, min(1.0, adjusted))

    def get_adjusted_tolerance(self, market_regime: MarketRegime) -> RiskTolerance:
        """Get risk tolerance adjusted for market regime.

        Args:
            market_regime: Current market regime

        Returns:
            Adjusted RiskTolerance
        """
        score = self.get_adjusted_risk_score(market_regime)
        return RiskTolerance.from_score(score)

    def update_regime_adjustment(
        self,
        regime: MarketRegime,
        adjustment: float,
    ) -> None:
        """Update the adjustment for a specific regime.

        Args:
            regime: Market regime to update
            adjustment: New adjustment value (-1 to 1)
        """
        self.regime_adjustments[regime.value] = max(-1.0, min(1.0, adjustment))
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "user_id": self.user_id,
            "base_tolerance": self.base_tolerance.value,
            "regime_adjustments": self.regime_adjustments,
            "category_preferences": self.category_preferences,
            "max_drawdown_tolerance": self.max_drawdown_tolerance,
            "volatility_preference": self.volatility_preference,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskProfile":
        """Create from dictionary."""
        return cls(
            user_id=data["user_id"],
            base_tolerance=RiskTolerance(data["base_tolerance"]),
            regime_adjustments=data.get("regime_adjustments", {}),
            category_preferences=data.get("category_preferences", {}),
            max_drawdown_tolerance=data.get("max_drawdown_tolerance", 0.20),
            volatility_preference=data.get("volatility_preference", 0.15),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


class RiskProfileMemory:
    """Memory system for tracking risk profiles and decisions.

    This class provides storage and retrieval for risk profiles and
    historical risk decisions, enabling learning from past decisions.

    Example:
        >>> memory = RiskProfileMemory()
        >>>
        >>> # Create a risk profile
        >>> profile = RiskProfile(user_id="user1", base_tolerance=RiskTolerance.MODERATE)
        >>> memory.set_profile(profile)
        >>>
        >>> # Record a risk decision
        >>> decision = RiskDecision.create(
        ...     category=RiskCategory.POSITION_SIZE,
        ...     risk_level=0.6,
        ...     market_regime=MarketRegime.BULL,
        ...     context="Strong momentum in tech sector",
        ... )
        >>> memory.record_decision(decision)
        >>>
        >>> # Get recommended risk level for similar situation
        >>> recommended = memory.recommend_risk_level(
        ...     category=RiskCategory.POSITION_SIZE,
        ...     market_regime=MarketRegime.BULL,
        ...     context="Tech sector showing strength",
        ... )
    """

    def __init__(
        self,
        config: Optional[MemoryConfig] = None,
        embedding_function=None,
    ):
        """Initialize risk profile memory.

        Args:
            config: Memory configuration
            embedding_function: Optional embedding function
        """
        if config is None:
            config = MemoryConfig(
                weights=ScoringWeights(
                    recency=0.35,      # Recent decisions more relevant
                    relevancy=0.40,    # Similar situations important
                    importance=0.25,   # Outcome importance
                ),
            )

        self._layered_memory = LayeredMemory(
            config=config,
            embedding_function=embedding_function,
        )
        self._profiles: Dict[str, RiskProfile] = {}
        self._decisions: Dict[str, RiskDecision] = {}
        self._default_user_id = "default"

    def set_profile(self, profile: RiskProfile) -> None:
        """Set or update a user's risk profile.

        Args:
            profile: Risk profile to store
        """
        self._profiles[profile.user_id] = profile

    def get_profile(self, user_id: Optional[str] = None) -> Optional[RiskProfile]:
        """Get a user's risk profile.

        Args:
            user_id: User ID (default: "default")

        Returns:
            RiskProfile or None
        """
        user_id = user_id or self._default_user_id
        return self._profiles.get(user_id)

    def get_or_create_profile(
        self,
        user_id: Optional[str] = None,
        base_tolerance: RiskTolerance = RiskTolerance.MODERATE,
    ) -> RiskProfile:
        """Get existing profile or create a new one.

        Args:
            user_id: User ID
            base_tolerance: Default tolerance if creating new

        Returns:
            RiskProfile
        """
        user_id = user_id or self._default_user_id
        profile = self._profiles.get(user_id)

        if profile is None:
            profile = RiskProfile(user_id=user_id, base_tolerance=base_tolerance)
            self._profiles[user_id] = profile

        return profile

    def record_decision(
        self,
        decision: RiskDecision,
        user_id: Optional[str] = None,
    ) -> str:
        """Record a risk decision.

        Args:
            decision: The risk decision to record
            user_id: User ID (default: "default")

        Returns:
            Decision ID
        """
        user_id = user_id or self._default_user_id
        self._decisions[decision.id] = decision

        # Calculate importance based on outcome if available
        importance = 0.5
        if decision.outcome_score is not None:
            importance = 0.5 + (abs(decision.outcome_score) * 0.5)

        # Create memory entry
        content = (
            f"Risk decision: {decision.category.value} with risk level "
            f"{decision.risk_level:.2f} in {decision.market_regime.value} market. "
            f"Context: {decision.context}"
        )

        entry = MemoryEntry.create(
            content=content,
            metadata={
                "decision_id": decision.id,
                "user_id": user_id,
                "category": decision.category.value,
                "risk_level": decision.risk_level,
                "market_regime": decision.market_regime.value,
                "vix_level": decision.vix_level,
                "outcome": decision.outcome,
                "outcome_score": decision.outcome_score,
                "was_appropriate": decision.was_appropriate,
            },
            importance=importance,
            tags=[
                user_id,
                decision.category.value,
                decision.market_regime.value,
            ],
            timestamp=decision.timestamp,
        )
        entry.id = decision.id

        self._layered_memory.add(entry)
        return decision.id

    def evaluate_decision(
        self,
        decision_id: str,
        outcome: str,
        outcome_score: float,
        was_appropriate: bool,
    ) -> Optional[RiskDecision]:
        """Evaluate a past decision with hindsight.

        Args:
            decision_id: ID of the decision
            outcome: What happened
            outcome_score: Quantified outcome (-1 to 1)
            was_appropriate: Whether decision was appropriate

        Returns:
            Updated decision or None
        """
        decision = self._decisions.get(decision_id)
        if decision is None:
            return None

        decision.evaluate(outcome, outcome_score, was_appropriate)

        # Update memory importance
        importance = 0.5 + (abs(outcome_score) * 0.5)
        self._layered_memory.update_importance(decision_id, importance)

        return decision

    def get_decision(self, decision_id: str) -> Optional[RiskDecision]:
        """Get a decision by ID.

        Args:
            decision_id: Decision ID

        Returns:
            RiskDecision or None
        """
        return self._decisions.get(decision_id)

    def find_similar_decisions(
        self,
        context: str,
        category: Optional[RiskCategory] = None,
        market_regime: Optional[MarketRegime] = None,
        top_k: int = 5,
    ) -> List[RiskDecision]:
        """Find similar past decisions.

        Args:
            context: Current situation context
            category: Optional filter by category
            market_regime: Optional filter by regime
            top_k: Maximum results

        Returns:
            List of similar decisions
        """
        tags = []
        if category:
            tags.append(category.value)
        if market_regime:
            tags.append(market_regime.value)

        results = self._layered_memory.retrieve(
            query=context,
            top_k=top_k * 2,
            tags=tags if tags else None,
        )

        decisions = []
        for scored in results:
            decision_id = scored.entry.metadata.get("decision_id")
            if decision_id and decision_id in self._decisions:
                decisions.append(self._decisions[decision_id])
                if len(decisions) >= top_k:
                    break

        return decisions

    def recommend_risk_level(
        self,
        category: RiskCategory,
        market_regime: MarketRegime,
        context: str,
        user_id: Optional[str] = None,
        use_history: bool = True,
    ) -> Tuple[float, str]:
        """Recommend a risk level based on profile and history.

        Args:
            category: Risk category
            market_regime: Current market regime
            context: Current situation
            user_id: User ID
            use_history: Whether to consider past decisions

        Returns:
            Tuple of (risk_level, explanation)
        """
        user_id = user_id or self._default_user_id
        profile = self.get_or_create_profile(user_id)

        # Start with profile-based recommendation
        base_risk = profile.get_adjusted_risk_score(market_regime)
        explanation_parts = [
            f"Base risk from profile: {base_risk:.2f} "
            f"({profile.base_tolerance.value} adjusted for {market_regime.value})"
        ]

        if not use_history:
            return base_risk, " | ".join(explanation_parts)

        # Find similar past decisions
        similar = self.find_similar_decisions(
            context=context,
            category=category,
            market_regime=market_regime,
            top_k=5,
        )

        if not similar:
            explanation_parts.append("No similar past decisions found")
            return base_risk, " | ".join(explanation_parts)

        # Analyze outcomes of similar decisions
        successful_decisions = [
            d for d in similar
            if d.was_appropriate is True
        ]
        unsuccessful_decisions = [
            d for d in similar
            if d.was_appropriate is False
        ]

        # Calculate weighted average of successful decisions
        if successful_decisions:
            successful_avg = statistics.mean([d.risk_level for d in successful_decisions])
            explanation_parts.append(
                f"Avg risk level from {len(successful_decisions)} successful similar decisions: "
                f"{successful_avg:.2f}"
            )

            # Blend with base risk (weight toward successful history)
            adjusted_risk = (base_risk * 0.4) + (successful_avg * 0.6)
        else:
            adjusted_risk = base_risk

        # Warn about unsuccessful patterns
        if unsuccessful_decisions:
            unsuccessful_avg = statistics.mean([d.risk_level for d in unsuccessful_decisions])
            if abs(adjusted_risk - unsuccessful_avg) < 0.1:
                explanation_parts.append(
                    f"WARNING: Similar risk level ({unsuccessful_avg:.2f}) was unsuccessful before"
                )
                # Adjust away from unsuccessful pattern
                if unsuccessful_avg > base_risk:
                    adjusted_risk = max(0.0, adjusted_risk - 0.1)
                else:
                    adjusted_risk = min(1.0, adjusted_risk + 0.1)

        return adjusted_risk, " | ".join(explanation_parts)

    def get_regime_statistics(
        self,
        user_id: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Get statistics of risk decisions by market regime.

        Args:
            user_id: Optional filter by user

        Returns:
            Dictionary of statistics by regime
        """
        stats: Dict[str, Dict[str, Any]] = {}

        for regime in MarketRegime:
            regime_decisions = [
                d for d in self._decisions.values()
                if d.market_regime == regime
            ]

            if not regime_decisions:
                stats[regime.value] = {
                    "count": 0,
                    "avg_risk_level": None,
                    "success_rate": None,
                }
                continue

            evaluated = [d for d in regime_decisions if d.was_appropriate is not None]
            successful = [d for d in evaluated if d.was_appropriate is True]

            stats[regime.value] = {
                "count": len(regime_decisions),
                "avg_risk_level": statistics.mean([d.risk_level for d in regime_decisions]),
                "success_rate": len(successful) / len(evaluated) if evaluated else None,
            }

        return stats

    def get_category_statistics(
        self,
        user_id: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Get statistics of risk decisions by category.

        Args:
            user_id: Optional filter by user

        Returns:
            Dictionary of statistics by category
        """
        stats: Dict[str, Dict[str, Any]] = {}

        for category in RiskCategory:
            category_decisions = [
                d for d in self._decisions.values()
                if d.category == category
            ]

            if not category_decisions:
                stats[category.value] = {
                    "count": 0,
                    "avg_risk_level": None,
                    "success_rate": None,
                }
                continue

            evaluated = [d for d in category_decisions if d.was_appropriate is not None]
            successful = [d for d in evaluated if d.was_appropriate is True]

            stats[category.value] = {
                "count": len(category_decisions),
                "avg_risk_level": statistics.mean([d.risk_level for d in category_decisions]),
                "success_rate": len(successful) / len(evaluated) if evaluated else None,
            }

        return stats

    def learn_regime_adjustments(
        self,
        user_id: Optional[str] = None,
        min_decisions: int = 5,
    ) -> Dict[str, float]:
        """Learn regime adjustments from historical decisions.

        Analyzes past decisions to suggest optimal regime adjustments.

        Args:
            user_id: User ID
            min_decisions: Minimum decisions per regime to learn from

        Returns:
            Suggested regime adjustments
        """
        user_id = user_id or self._default_user_id
        profile = self.get_or_create_profile(user_id)
        suggestions: Dict[str, float] = {}

        for regime in MarketRegime:
            regime_decisions = [
                d for d in self._decisions.values()
                if d.market_regime == regime
                and d.was_appropriate is not None
            ]

            if len(regime_decisions) < min_decisions:
                continue

            # Find the risk level with best outcomes
            successful = [d for d in regime_decisions if d.was_appropriate]
            unsuccessful = [d for d in regime_decisions if not d.was_appropriate]

            if not successful:
                # All decisions were unsuccessful - suggest lower risk
                avg_failed_risk = statistics.mean([d.risk_level for d in unsuccessful])
                suggested_adjustment = -0.2  # Lower risk
            elif not unsuccessful:
                # All decisions were successful - keep similar
                avg_success_risk = statistics.mean([d.risk_level for d in successful])
                base_score = profile.base_tolerance.to_score()
                suggested_adjustment = avg_success_risk - base_score
            else:
                # Mixed results - prefer successful pattern
                avg_success_risk = statistics.mean([d.risk_level for d in successful])
                base_score = profile.base_tolerance.to_score()
                suggested_adjustment = avg_success_risk - base_score

            suggestions[regime.value] = max(-0.5, min(0.5, suggested_adjustment))

        return suggestions

    def count(self) -> int:
        """Return total number of decisions."""
        return len(self._decisions)

    def clear(self) -> int:
        """Clear all decisions (preserves profiles).

        Returns:
            Number of decisions cleared
        """
        count = len(self._decisions)
        self._decisions.clear()
        self._layered_memory.clear()
        return count

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "profiles": {
                uid: p.to_dict()
                for uid, p in self._profiles.items()
            },
            "decisions": [d.to_dict() for d in self._decisions.values()],
            "memory": self._layered_memory.to_dict(),
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        embedding_function=None,
    ) -> "RiskProfileMemory":
        """Create from dictionary."""
        instance = cls(embedding_function=embedding_function)

        # Restore profiles
        for uid, profile_data in data.get("profiles", {}).items():
            profile = RiskProfile.from_dict(profile_data)
            instance._profiles[uid] = profile

        # Restore decisions
        for decision_data in data.get("decisions", []):
            decision = RiskDecision.from_dict(decision_data)
            instance._decisions[decision.id] = decision

        # Restore layered memory
        if "memory" in data:
            instance._layered_memory = LayeredMemory.from_dict(
                data["memory"],
                embedding_function=embedding_function,
            )

        return instance
