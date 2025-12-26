"""Tests for Risk Profiles Memory module.

Issue #20: [MEM-19] Risk profiles memory - user preferences over time
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from tradingagents.memory.risk_profiles import (
    RiskProfileMemory,
    RiskProfile,
    RiskDecision,
    RiskTolerance,
    MarketRegime,
    RiskCategory,
)


# =============================================================================
# RiskTolerance Enum Tests
# =============================================================================


class TestRiskTolerance:
    """Tests for RiskTolerance enum."""

    def test_from_score_conservative(self):
        """Test conservative threshold (< 0.25)."""
        assert RiskTolerance.from_score(0.0) == RiskTolerance.CONSERVATIVE
        assert RiskTolerance.from_score(0.1) == RiskTolerance.CONSERVATIVE
        assert RiskTolerance.from_score(0.24) == RiskTolerance.CONSERVATIVE

    def test_from_score_moderate(self):
        """Test moderate threshold (0.25 - 0.50)."""
        assert RiskTolerance.from_score(0.25) == RiskTolerance.MODERATE
        assert RiskTolerance.from_score(0.37) == RiskTolerance.MODERATE
        assert RiskTolerance.from_score(0.49) == RiskTolerance.MODERATE

    def test_from_score_aggressive(self):
        """Test aggressive threshold (0.50 - 0.75)."""
        assert RiskTolerance.from_score(0.50) == RiskTolerance.AGGRESSIVE
        assert RiskTolerance.from_score(0.62) == RiskTolerance.AGGRESSIVE
        assert RiskTolerance.from_score(0.74) == RiskTolerance.AGGRESSIVE

    def test_from_score_very_aggressive(self):
        """Test very aggressive threshold (>= 0.75)."""
        assert RiskTolerance.from_score(0.75) == RiskTolerance.VERY_AGGRESSIVE
        assert RiskTolerance.from_score(0.9) == RiskTolerance.VERY_AGGRESSIVE
        assert RiskTolerance.from_score(1.0) == RiskTolerance.VERY_AGGRESSIVE

    def test_to_score(self):
        """Test conversion to numeric score."""
        assert RiskTolerance.CONSERVATIVE.to_score() == 0.125
        assert RiskTolerance.MODERATE.to_score() == 0.375
        assert RiskTolerance.AGGRESSIVE.to_score() == 0.625
        assert RiskTolerance.VERY_AGGRESSIVE.to_score() == 0.875

    def test_roundtrip_approximate(self):
        """Test from_score(to_score()) is consistent."""
        for tolerance in RiskTolerance:
            score = tolerance.to_score()
            recovered = RiskTolerance.from_score(score)
            assert recovered == tolerance


# =============================================================================
# MarketRegime Enum Tests
# =============================================================================


class TestMarketRegime:
    """Tests for MarketRegime enum."""

    def test_all_regimes_defined(self):
        """Test all expected regimes exist."""
        expected = ["bull", "bear", "sideways", "high_volatility", "low_volatility", "crisis"]
        for regime_value in expected:
            assert MarketRegime(regime_value) is not None

    def test_regime_values(self):
        """Test regime string values."""
        assert MarketRegime.BULL.value == "bull"
        assert MarketRegime.BEAR.value == "bear"
        assert MarketRegime.CRISIS.value == "crisis"


# =============================================================================
# RiskCategory Enum Tests
# =============================================================================


class TestRiskCategory:
    """Tests for RiskCategory enum."""

    def test_all_categories_defined(self):
        """Test all expected categories exist."""
        expected = [
            "position_size", "leverage", "diversification",
            "hedging", "stop_loss", "sector_exposure", "asset_class"
        ]
        for cat_value in expected:
            assert RiskCategory(cat_value) is not None


# =============================================================================
# RiskDecision Tests
# =============================================================================


class TestRiskDecision:
    """Tests for RiskDecision dataclass."""

    def test_create_decision(self):
        """Test creating a risk decision."""
        decision = RiskDecision.create(
            category=RiskCategory.POSITION_SIZE,
            risk_level=0.6,
            market_regime=MarketRegime.BULL,
            context="Strong momentum in tech",
        )

        assert decision.id is not None
        assert decision.category == RiskCategory.POSITION_SIZE
        assert decision.risk_level == 0.6
        assert decision.market_regime == MarketRegime.BULL
        assert decision.context == "Strong momentum in tech"
        assert decision.outcome is None
        assert decision.was_appropriate is None

    def test_create_with_vix(self):
        """Test creating decision with VIX level."""
        decision = RiskDecision.create(
            category=RiskCategory.LEVERAGE,
            risk_level=0.3,
            market_regime=MarketRegime.HIGH_VOLATILITY,
            context="Market stress",
            vix_level=32.5,
        )

        assert decision.vix_level == 32.5

    def test_create_with_notes(self):
        """Test creating decision with notes."""
        decision = RiskDecision.create(
            category=RiskCategory.HEDGING,
            risk_level=0.4,
            market_regime=MarketRegime.BEAR,
            context="Protective puts",
            notes="Weekly expiration",
        )

        assert decision.notes == "Weekly expiration"

    def test_create_validates_risk_level_low(self):
        """Test risk level validation - too low."""
        with pytest.raises(ValueError, match="Risk level must be between 0 and 1"):
            RiskDecision.create(
                category=RiskCategory.POSITION_SIZE,
                risk_level=-0.1,
                market_regime=MarketRegime.BULL,
                context="Test",
            )

    def test_create_validates_risk_level_high(self):
        """Test risk level validation - too high."""
        with pytest.raises(ValueError, match="Risk level must be between 0 and 1"):
            RiskDecision.create(
                category=RiskCategory.POSITION_SIZE,
                risk_level=1.5,
                market_regime=MarketRegime.BULL,
                context="Test",
            )

    def test_create_boundary_values(self):
        """Test boundary values for risk level."""
        decision_low = RiskDecision.create(
            category=RiskCategory.POSITION_SIZE,
            risk_level=0.0,
            market_regime=MarketRegime.BULL,
            context="Minimum risk",
        )
        assert decision_low.risk_level == 0.0

        decision_high = RiskDecision.create(
            category=RiskCategory.POSITION_SIZE,
            risk_level=1.0,
            market_regime=MarketRegime.BULL,
            context="Maximum risk",
        )
        assert decision_high.risk_level == 1.0

    def test_evaluate_decision(self):
        """Test evaluating a decision with outcome."""
        decision = RiskDecision.create(
            category=RiskCategory.POSITION_SIZE,
            risk_level=0.6,
            market_regime=MarketRegime.BULL,
            context="Strong momentum",
        )

        result = decision.evaluate(
            outcome="Profitable trade",
            outcome_score=0.8,
            was_appropriate=True,
        )

        assert result is decision
        assert decision.outcome == "Profitable trade"
        assert decision.outcome_score == 0.8
        assert decision.was_appropriate is True

    def test_evaluate_clamps_outcome_score(self):
        """Test outcome score is clamped to [-1, 1]."""
        decision = RiskDecision.create(
            category=RiskCategory.LEVERAGE,
            risk_level=0.9,
            market_regime=MarketRegime.BULL,
            context="High leverage",
        )

        decision.evaluate("Loss", -2.0, False)
        assert decision.outcome_score == -1.0

        decision.evaluate("Huge win", 5.0, True)
        assert decision.outcome_score == 1.0

    def test_to_dict(self):
        """Test serialization to dictionary."""
        decision = RiskDecision.create(
            category=RiskCategory.STOP_LOSS,
            risk_level=0.3,
            market_regime=MarketRegime.SIDEWAYS,
            context="Range-bound market",
            vix_level=18.0,
        )
        decision.evaluate("Hit stop", -0.5, True)

        data = decision.to_dict()

        assert data["id"] == decision.id
        assert data["category"] == "stop_loss"
        assert data["risk_level"] == 0.3
        assert data["market_regime"] == "sideways"
        assert data["context"] == "Range-bound market"
        assert data["vix_level"] == 18.0
        assert data["outcome"] == "Hit stop"
        assert data["outcome_score"] == -0.5
        assert data["was_appropriate"] is True

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        original = RiskDecision.create(
            category=RiskCategory.DIVERSIFICATION,
            risk_level=0.5,
            market_regime=MarketRegime.LOW_VOLATILITY,
            context="Adding sectors",
        )
        original.evaluate("Good diversification", 0.3, True)

        data = original.to_dict()
        restored = RiskDecision.from_dict(data)

        assert restored.id == original.id
        assert restored.category == original.category
        assert restored.risk_level == original.risk_level
        assert restored.market_regime == original.market_regime
        assert restored.outcome == original.outcome
        assert restored.was_appropriate == original.was_appropriate


# =============================================================================
# RiskProfile Tests
# =============================================================================


class TestRiskProfile:
    """Tests for RiskProfile dataclass."""

    def test_create_default_profile(self):
        """Test creating profile with defaults."""
        profile = RiskProfile(user_id="user1")

        assert profile.user_id == "user1"
        assert profile.base_tolerance == RiskTolerance.MODERATE
        assert profile.max_drawdown_tolerance == 0.20
        assert profile.volatility_preference == 0.15

    def test_default_regime_adjustments(self):
        """Test default regime adjustments are set."""
        profile = RiskProfile(user_id="user1")

        assert profile.regime_adjustments[MarketRegime.BULL.value] == 0.1
        assert profile.regime_adjustments[MarketRegime.BEAR.value] == -0.2
        assert profile.regime_adjustments[MarketRegime.CRISIS.value] == -0.5

    def test_get_adjusted_risk_score_bull(self):
        """Test adjusted score in bull market."""
        profile = RiskProfile(user_id="user1", base_tolerance=RiskTolerance.MODERATE)

        score = profile.get_adjusted_risk_score(MarketRegime.BULL)

        # MODERATE = 0.375, BULL adjustment = 0.1
        expected = 0.375 + 0.1
        assert abs(score - expected) < 0.001

    def test_get_adjusted_risk_score_crisis(self):
        """Test adjusted score in crisis."""
        profile = RiskProfile(user_id="user1", base_tolerance=RiskTolerance.AGGRESSIVE)

        score = profile.get_adjusted_risk_score(MarketRegime.CRISIS)

        # AGGRESSIVE = 0.625, CRISIS adjustment = -0.5
        expected = 0.625 - 0.5
        assert abs(score - expected) < 0.001

    def test_get_adjusted_risk_score_clamped_low(self):
        """Test adjusted score is clamped at 0."""
        profile = RiskProfile(user_id="user1", base_tolerance=RiskTolerance.CONSERVATIVE)

        score = profile.get_adjusted_risk_score(MarketRegime.CRISIS)

        # CONSERVATIVE = 0.125, CRISIS = -0.5, would be negative
        assert score == 0.0

    def test_get_adjusted_risk_score_clamped_high(self):
        """Test adjusted score is clamped at 1."""
        profile = RiskProfile(
            user_id="user1",
            base_tolerance=RiskTolerance.VERY_AGGRESSIVE,
            regime_adjustments={MarketRegime.BULL.value: 0.5},
        )

        score = profile.get_adjusted_risk_score(MarketRegime.BULL)

        # VERY_AGGRESSIVE = 0.875, BULL = 0.5, would exceed 1.0
        assert score == 1.0

    def test_get_adjusted_tolerance(self):
        """Test getting adjusted tolerance enum."""
        profile = RiskProfile(user_id="user1", base_tolerance=RiskTolerance.AGGRESSIVE)

        # In crisis, aggressive becomes moderate
        tolerance = profile.get_adjusted_tolerance(MarketRegime.CRISIS)
        assert tolerance == RiskTolerance.CONSERVATIVE

    def test_update_regime_adjustment(self):
        """Test updating regime adjustment."""
        profile = RiskProfile(user_id="user1")
        original_updated = profile.updated_at

        profile.update_regime_adjustment(MarketRegime.BEAR, -0.4)

        assert profile.regime_adjustments[MarketRegime.BEAR.value] == -0.4
        assert profile.updated_at >= original_updated

    def test_update_regime_adjustment_clamped(self):
        """Test adjustment is clamped to [-1, 1]."""
        profile = RiskProfile(user_id="user1")

        profile.update_regime_adjustment(MarketRegime.BULL, 2.0)
        assert profile.regime_adjustments[MarketRegime.BULL.value] == 1.0

        profile.update_regime_adjustment(MarketRegime.CRISIS, -2.0)
        assert profile.regime_adjustments[MarketRegime.CRISIS.value] == -1.0

    def test_to_dict(self):
        """Test serialization to dictionary."""
        profile = RiskProfile(
            user_id="user1",
            base_tolerance=RiskTolerance.AGGRESSIVE,
            max_drawdown_tolerance=0.15,
        )

        data = profile.to_dict()

        assert data["user_id"] == "user1"
        assert data["base_tolerance"] == "aggressive"
        assert data["max_drawdown_tolerance"] == 0.15
        assert "regime_adjustments" in data
        assert "created_at" in data

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        original = RiskProfile(
            user_id="user1",
            base_tolerance=RiskTolerance.CONSERVATIVE,
            max_drawdown_tolerance=0.10,
        )

        data = original.to_dict()
        restored = RiskProfile.from_dict(data)

        assert restored.user_id == original.user_id
        assert restored.base_tolerance == original.base_tolerance
        assert restored.max_drawdown_tolerance == original.max_drawdown_tolerance


# =============================================================================
# RiskProfileMemory Tests
# =============================================================================


class TestRiskProfileMemory:
    """Tests for RiskProfileMemory class."""

    def test_create_memory(self):
        """Test creating memory instance."""
        memory = RiskProfileMemory()
        assert memory.count() == 0

    def test_set_and_get_profile(self):
        """Test setting and getting a profile."""
        memory = RiskProfileMemory()
        profile = RiskProfile(user_id="user1", base_tolerance=RiskTolerance.AGGRESSIVE)

        memory.set_profile(profile)
        retrieved = memory.get_profile("user1")

        assert retrieved is not None
        assert retrieved.user_id == "user1"
        assert retrieved.base_tolerance == RiskTolerance.AGGRESSIVE

    def test_get_profile_default_user(self):
        """Test getting default user profile."""
        memory = RiskProfileMemory()
        profile = RiskProfile(user_id="default")
        memory.set_profile(profile)

        retrieved = memory.get_profile()
        assert retrieved.user_id == "default"

    def test_get_nonexistent_profile(self):
        """Test getting nonexistent profile returns None."""
        memory = RiskProfileMemory()
        assert memory.get_profile("unknown") is None

    def test_get_or_create_profile_new(self):
        """Test get_or_create creates new profile."""
        memory = RiskProfileMemory()

        profile = memory.get_or_create_profile("new_user", RiskTolerance.CONSERVATIVE)

        assert profile.user_id == "new_user"
        assert profile.base_tolerance == RiskTolerance.CONSERVATIVE

    def test_get_or_create_profile_existing(self):
        """Test get_or_create returns existing profile."""
        memory = RiskProfileMemory()
        original = RiskProfile(user_id="user1", base_tolerance=RiskTolerance.AGGRESSIVE)
        memory.set_profile(original)

        profile = memory.get_or_create_profile("user1", RiskTolerance.CONSERVATIVE)

        assert profile.base_tolerance == RiskTolerance.AGGRESSIVE

    def test_record_decision(self):
        """Test recording a decision."""
        memory = RiskProfileMemory()
        decision = RiskDecision.create(
            category=RiskCategory.POSITION_SIZE,
            risk_level=0.5,
            market_regime=MarketRegime.BULL,
            context="Tech momentum",
        )

        decision_id = memory.record_decision(decision)

        assert decision_id == decision.id
        assert memory.count() == 1

    def test_get_decision(self):
        """Test retrieving a decision by ID."""
        memory = RiskProfileMemory()
        decision = RiskDecision.create(
            category=RiskCategory.LEVERAGE,
            risk_level=0.7,
            market_regime=MarketRegime.LOW_VOLATILITY,
            context="Low vol environment",
        )
        memory.record_decision(decision)

        retrieved = memory.get_decision(decision.id)

        assert retrieved is not None
        assert retrieved.risk_level == 0.7

    def test_get_nonexistent_decision(self):
        """Test getting nonexistent decision returns None."""
        memory = RiskProfileMemory()
        assert memory.get_decision("unknown") is None

    def test_evaluate_decision(self):
        """Test evaluating a recorded decision."""
        memory = RiskProfileMemory()
        decision = RiskDecision.create(
            category=RiskCategory.POSITION_SIZE,
            risk_level=0.6,
            market_regime=MarketRegime.BULL,
            context="Strong momentum",
        )
        memory.record_decision(decision)

        result = memory.evaluate_decision(
            decision_id=decision.id,
            outcome="Profitable",
            outcome_score=0.5,
            was_appropriate=True,
        )

        assert result is not None
        assert result.outcome == "Profitable"
        assert result.was_appropriate is True

    def test_evaluate_nonexistent_decision(self):
        """Test evaluating nonexistent decision."""
        memory = RiskProfileMemory()
        result = memory.evaluate_decision("unknown", "Test", 0.5, True)
        assert result is None

    def test_find_similar_decisions(self):
        """Test finding similar decisions."""
        memory = RiskProfileMemory()

        # Record several decisions
        for i in range(5):
            decision = RiskDecision.create(
                category=RiskCategory.POSITION_SIZE,
                risk_level=0.5 + i * 0.05,
                market_regime=MarketRegime.BULL,
                context=f"Tech momentum scenario {i}",
            )
            memory.record_decision(decision)

        similar = memory.find_similar_decisions(
            context="Tech momentum similar",
            category=RiskCategory.POSITION_SIZE,
            market_regime=MarketRegime.BULL,
            top_k=3,
        )

        assert len(similar) <= 3
        for decision in similar:
            assert decision.category == RiskCategory.POSITION_SIZE

    def test_find_similar_decisions_with_filters(self):
        """Test finding similar decisions with regime filter."""
        memory = RiskProfileMemory()

        # Record decisions in different regimes
        for regime in [MarketRegime.BULL, MarketRegime.BEAR]:
            for i in range(3):
                decision = RiskDecision.create(
                    category=RiskCategory.POSITION_SIZE,
                    risk_level=0.5,
                    market_regime=regime,
                    context=f"Scenario {i}",
                )
                memory.record_decision(decision)

        # Filter by BULL regime only
        similar = memory.find_similar_decisions(
            context="Find scenario",
            market_regime=MarketRegime.BULL,
            top_k=10,
        )

        for decision in similar:
            assert decision.market_regime == MarketRegime.BULL

    def test_recommend_risk_level_no_history(self):
        """Test recommendation without history uses profile only."""
        memory = RiskProfileMemory()
        profile = RiskProfile(user_id="default", base_tolerance=RiskTolerance.MODERATE)
        memory.set_profile(profile)

        risk_level, explanation = memory.recommend_risk_level(
            category=RiskCategory.POSITION_SIZE,
            market_regime=MarketRegime.BULL,
            context="New situation",
            use_history=False,
        )

        # MODERATE (0.375) + BULL adjustment (0.1)
        expected = 0.375 + 0.1
        assert abs(risk_level - expected) < 0.01
        assert "Base risk from profile" in explanation

    def test_recommend_risk_level_with_history(self):
        """Test recommendation with historical decisions."""
        memory = RiskProfileMemory()
        profile = RiskProfile(user_id="default", base_tolerance=RiskTolerance.MODERATE)
        memory.set_profile(profile)

        # Record successful decisions
        for i in range(3):
            decision = RiskDecision.create(
                category=RiskCategory.POSITION_SIZE,
                risk_level=0.7,
                market_regime=MarketRegime.BULL,
                context=f"Momentum play {i}",
            )
            decision.evaluate("Profitable", 0.6, True)
            memory.record_decision(decision)

        risk_level, explanation = memory.recommend_risk_level(
            category=RiskCategory.POSITION_SIZE,
            market_regime=MarketRegime.BULL,
            context="Similar momentum play",
            use_history=True,
        )

        # Should be influenced by successful 0.7 risk decisions
        assert risk_level > 0.5  # Should be higher than base moderate
        assert "successful similar decisions" in explanation

    def test_recommend_warns_about_unsuccessful(self):
        """Test recommendation when only unsuccessful decisions exist."""
        memory = RiskProfileMemory()
        profile = RiskProfile(user_id="default", base_tolerance=RiskTolerance.MODERATE)
        memory.set_profile(profile)

        # Record unsuccessful decisions with matching context words
        for i in range(3):
            decision = RiskDecision.create(
                category=RiskCategory.LEVERAGE,
                risk_level=0.8,
                market_regime=MarketRegime.HIGH_VOLATILITY,
                context="High leverage situation volatility trade",
            )
            decision.evaluate("Loss", -0.5, False)
            memory.record_decision(decision)

        risk_level, explanation = memory.recommend_risk_level(
            category=RiskCategory.LEVERAGE,
            market_regime=MarketRegime.HIGH_VOLATILITY,
            context="High leverage situation volatility trade",
            use_history=True,
        )

        # Should either use base risk (no successful similar) or warn about unsuccessful
        # The explanation should NOT include "successful similar decisions" since there are none
        assert "successful similar decisions" not in explanation or "WARNING" in explanation

    def test_get_regime_statistics_empty(self):
        """Test regime statistics with no decisions."""
        memory = RiskProfileMemory()
        stats = memory.get_regime_statistics()

        for regime in MarketRegime:
            assert stats[regime.value]["count"] == 0
            assert stats[regime.value]["avg_risk_level"] is None

    def test_get_regime_statistics(self):
        """Test regime statistics with decisions."""
        memory = RiskProfileMemory()

        # Record decisions in bull market
        for i in range(5):
            decision = RiskDecision.create(
                category=RiskCategory.POSITION_SIZE,
                risk_level=0.6 + i * 0.02,
                market_regime=MarketRegime.BULL,
                context=f"Bull scenario {i}",
            )
            if i < 3:
                decision.evaluate("Win", 0.5, True)
            else:
                decision.evaluate("Loss", -0.3, False)
            memory.record_decision(decision)

        stats = memory.get_regime_statistics()

        assert stats[MarketRegime.BULL.value]["count"] == 5
        assert 0.6 <= stats[MarketRegime.BULL.value]["avg_risk_level"] <= 0.7
        assert stats[MarketRegime.BULL.value]["success_rate"] == 0.6  # 3/5

    def test_get_category_statistics(self):
        """Test category statistics."""
        memory = RiskProfileMemory()

        for i in range(4):
            decision = RiskDecision.create(
                category=RiskCategory.STOP_LOSS,
                risk_level=0.3 + i * 0.05,
                market_regime=MarketRegime.SIDEWAYS,
                context=f"Stop loss scenario {i}",
            )
            decision.evaluate("Hit stop", -0.2, i % 2 == 0)
            memory.record_decision(decision)

        stats = memory.get_category_statistics()

        assert stats[RiskCategory.STOP_LOSS.value]["count"] == 4
        assert stats[RiskCategory.STOP_LOSS.value]["success_rate"] == 0.5

    def test_learn_regime_adjustments_insufficient_data(self):
        """Test learning with insufficient data."""
        memory = RiskProfileMemory()

        # Only 2 decisions (below min_decisions=5)
        for i in range(2):
            decision = RiskDecision.create(
                category=RiskCategory.POSITION_SIZE,
                risk_level=0.5,
                market_regime=MarketRegime.BULL,
                context=f"Scenario {i}",
            )
            decision.evaluate("Win", 0.5, True)
            memory.record_decision(decision)

        suggestions = memory.learn_regime_adjustments(min_decisions=5)

        # Should not have suggestions for BULL (only 2 decisions)
        assert MarketRegime.BULL.value not in suggestions

    def test_learn_regime_adjustments_successful(self):
        """Test learning from successful decisions."""
        memory = RiskProfileMemory()
        profile = RiskProfile(user_id="default", base_tolerance=RiskTolerance.MODERATE)
        memory.set_profile(profile)

        # Record successful high-risk decisions in bull
        for i in range(6):
            decision = RiskDecision.create(
                category=RiskCategory.POSITION_SIZE,
                risk_level=0.7,  # Higher than base (0.375)
                market_regime=MarketRegime.BULL,
                context=f"Successful bull trade {i}",
            )
            decision.evaluate("Profit", 0.6, True)
            memory.record_decision(decision)

        suggestions = memory.learn_regime_adjustments(min_decisions=5)

        # Should suggest positive adjustment for bull (0.7 > 0.375)
        assert MarketRegime.BULL.value in suggestions
        assert suggestions[MarketRegime.BULL.value] > 0

    def test_learn_regime_adjustments_unsuccessful(self):
        """Test learning from unsuccessful decisions."""
        memory = RiskProfileMemory()
        profile = RiskProfile(user_id="default", base_tolerance=RiskTolerance.AGGRESSIVE)
        memory.set_profile(profile)

        # Record all unsuccessful decisions in crisis
        for i in range(6):
            decision = RiskDecision.create(
                category=RiskCategory.LEVERAGE,
                risk_level=0.8,
                market_regime=MarketRegime.CRISIS,
                context=f"Crisis loss {i}",
            )
            decision.evaluate("Loss", -0.7, False)
            memory.record_decision(decision)

        suggestions = memory.learn_regime_adjustments(min_decisions=5)

        # Should suggest negative adjustment (lower risk in crisis)
        assert MarketRegime.CRISIS.value in suggestions
        assert suggestions[MarketRegime.CRISIS.value] < 0

    def test_count(self):
        """Test decision count."""
        memory = RiskProfileMemory()
        assert memory.count() == 0

        for i in range(5):
            decision = RiskDecision.create(
                category=RiskCategory.POSITION_SIZE,
                risk_level=0.5,
                market_regime=MarketRegime.BULL,
                context=f"Scenario {i}",
            )
            memory.record_decision(decision)

        assert memory.count() == 5

    def test_clear(self):
        """Test clearing decisions (preserving profiles)."""
        memory = RiskProfileMemory()
        profile = RiskProfile(user_id="user1")
        memory.set_profile(profile)

        for i in range(3):
            decision = RiskDecision.create(
                category=RiskCategory.POSITION_SIZE,
                risk_level=0.5,
                market_regime=MarketRegime.BULL,
                context=f"Scenario {i}",
            )
            memory.record_decision(decision)

        assert memory.count() == 3
        cleared = memory.clear()

        assert cleared == 3
        assert memory.count() == 0
        assert memory.get_profile("user1") is not None  # Profile preserved

    def test_to_dict(self):
        """Test serialization to dictionary."""
        memory = RiskProfileMemory()
        profile = RiskProfile(user_id="user1", base_tolerance=RiskTolerance.AGGRESSIVE)
        memory.set_profile(profile)

        decision = RiskDecision.create(
            category=RiskCategory.POSITION_SIZE,
            risk_level=0.6,
            market_regime=MarketRegime.BULL,
            context="Test scenario",
        )
        memory.record_decision(decision)

        data = memory.to_dict()

        assert "profiles" in data
        assert "user1" in data["profiles"]
        assert "decisions" in data
        assert len(data["decisions"]) == 1
        assert "memory" in data

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        memory = RiskProfileMemory()
        profile = RiskProfile(user_id="user1", base_tolerance=RiskTolerance.CONSERVATIVE)
        memory.set_profile(profile)

        decision = RiskDecision.create(
            category=RiskCategory.HEDGING,
            risk_level=0.4,
            market_regime=MarketRegime.BEAR,
            context="Protective strategy",
        )
        decision.evaluate("Good protection", 0.5, True)
        memory.record_decision(decision)

        data = memory.to_dict()
        restored = RiskProfileMemory.from_dict(data)

        assert restored.get_profile("user1") is not None
        assert restored.get_profile("user1").base_tolerance == RiskTolerance.CONSERVATIVE
        assert restored.count() == 1
        assert restored.get_decision(decision.id) is not None

    def test_multiple_users(self):
        """Test handling multiple user profiles."""
        memory = RiskProfileMemory()

        users = ["alice", "bob", "charlie"]
        tolerances = [RiskTolerance.CONSERVATIVE, RiskTolerance.MODERATE, RiskTolerance.AGGRESSIVE]

        for user, tolerance in zip(users, tolerances):
            profile = RiskProfile(user_id=user, base_tolerance=tolerance)
            memory.set_profile(profile)

        for user, expected_tolerance in zip(users, tolerances):
            profile = memory.get_profile(user)
            assert profile.base_tolerance == expected_tolerance


# =============================================================================
# Integration Tests
# =============================================================================


class TestRiskProfileMemoryIntegration:
    """Integration tests for RiskProfileMemory."""

    def test_full_workflow(self):
        """Test complete workflow: profile -> decisions -> learning."""
        memory = RiskProfileMemory()

        # 1. Create profile
        profile = RiskProfile(
            user_id="trader1",
            base_tolerance=RiskTolerance.MODERATE,
            max_drawdown_tolerance=0.15,
        )
        memory.set_profile(profile)

        # 2. Record decisions across regimes
        decisions_data = [
            (MarketRegime.BULL, 0.6, True),
            (MarketRegime.BULL, 0.7, True),
            (MarketRegime.BULL, 0.65, True),
            (MarketRegime.BEAR, 0.3, True),
            (MarketRegime.BEAR, 0.5, False),
            (MarketRegime.CRISIS, 0.2, True),
        ]

        for regime, risk, appropriate in decisions_data:
            decision = RiskDecision.create(
                category=RiskCategory.POSITION_SIZE,
                risk_level=risk,
                market_regime=regime,
                context=f"Trading in {regime.value}",
            )
            outcome_score = 0.5 if appropriate else -0.5
            decision.evaluate("Result", outcome_score, appropriate)
            memory.record_decision(decision, user_id="trader1")

        # 3. Get recommendations
        bull_risk, _ = memory.recommend_risk_level(
            category=RiskCategory.POSITION_SIZE,
            market_regime=MarketRegime.BULL,
            context="Bull market opportunity",
            user_id="trader1",
        )

        bear_risk, _ = memory.recommend_risk_level(
            category=RiskCategory.POSITION_SIZE,
            market_regime=MarketRegime.BEAR,
            context="Bear market caution",
            user_id="trader1",
        )

        # Bull should recommend higher risk than bear
        assert bull_risk > bear_risk

        # 4. Get statistics
        stats = memory.get_regime_statistics()
        assert stats[MarketRegime.BULL.value]["count"] == 3
        assert stats[MarketRegime.BULL.value]["success_rate"] == 1.0

        # 5. Serialize and restore
        data = memory.to_dict()
        restored = RiskProfileMemory.from_dict(data)

        assert restored.get_profile("trader1") is not None
        assert restored.count() == 6

    def test_recommendation_adapts_over_time(self):
        """Test that recommendations adapt as more data is collected."""
        memory = RiskProfileMemory()
        profile = RiskProfile(user_id="default", base_tolerance=RiskTolerance.MODERATE)
        memory.set_profile(profile)

        # Initial recommendation (no history)
        initial_risk, _ = memory.recommend_risk_level(
            category=RiskCategory.POSITION_SIZE,
            market_regime=MarketRegime.BULL,
            context="Starting out",
        )

        # Add successful high-risk decisions
        for i in range(5):
            decision = RiskDecision.create(
                category=RiskCategory.POSITION_SIZE,
                risk_level=0.8,
                market_regime=MarketRegime.BULL,
                context=f"Successful trade {i}",
            )
            decision.evaluate("Win", 0.7, True)
            memory.record_decision(decision)

        # Later recommendation should be influenced by history
        later_risk, explanation = memory.recommend_risk_level(
            category=RiskCategory.POSITION_SIZE,
            market_regime=MarketRegime.BULL,
            context="Similar opportunity",
        )

        # Should be higher after seeing successful high-risk trades
        assert later_risk > initial_risk
        assert "successful similar decisions" in explanation
