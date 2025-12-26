"""Economic Conditions Module for regime tagging and evaluation.

This module provides economic and market regime analysis including:
- Market regime detection (bull, bear, sideways)
- Scenario tagging by economic conditions
- Performance evaluation by regime
- Regime-specific recommendations

Issue #35: [SIM-34] Economic conditions - regime tagging, evaluation

Design Principles:
    - Compatible with ScenarioRunner and StrategyComparator
    - Statistical regime detection
    - Comprehensive performance breakdown by regime
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import statistics
import uuid


# ============================================================================
# Enums
# ============================================================================

class MarketRegime(str, Enum):
    """Market regime classifications based on price action."""
    BULL = "bull"              # Strong uptrend (>20% annualized)
    MODERATE_BULL = "moderate_bull"  # Modest uptrend (5-20% annualized)
    SIDEWAYS = "sideways"      # Range-bound (-5% to 5% annualized)
    MODERATE_BEAR = "moderate_bear"  # Modest downtrend (-20% to -5%)
    BEAR = "bear"              # Strong downtrend (<-20% annualized)


class VolatilityRegime(str, Enum):
    """Volatility regime classifications."""
    LOW = "low"                # VIX < 15 or vol < 10%
    NORMAL = "normal"          # VIX 15-20 or vol 10-20%
    ELEVATED = "elevated"      # VIX 20-30 or vol 20-30%
    HIGH = "high"              # VIX > 30 or vol > 30%


class TrendStrength(str, Enum):
    """Strength of the detected trend."""
    STRONG = "strong"          # Clear, persistent trend
    MODERATE = "moderate"      # Identifiable trend with noise
    WEAK = "weak"              # Marginal trend
    NONE = "none"              # No discernible trend


class RegimeConfidence(str, Enum):
    """Confidence level in regime classification."""
    HIGH = "high"              # Strong statistical support
    MEDIUM = "medium"          # Moderate support
    LOW = "low"                # Marginal classification


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class RegimeTag:
    """Tag for a scenario or time period with regime information.

    Attributes:
        tag_id: Unique identifier for this tag
        start_date: Start of the tagged period
        end_date: End of the tagged period
        market_regime: Bull/bear/sideways classification
        volatility_regime: Low/normal/elevated/high volatility
        trend_strength: Strength of the detected trend
        confidence: Confidence in the regime classification
        annualized_return: Return during this period (annualized)
        volatility: Volatility during this period (annualized)
        max_drawdown: Maximum drawdown during period
        metadata: Additional tag data
    """
    tag_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    market_regime: MarketRegime = MarketRegime.SIDEWAYS
    volatility_regime: VolatilityRegime = VolatilityRegime.NORMAL
    trend_strength: TrendStrength = TrendStrength.NONE
    confidence: RegimeConfidence = RegimeConfidence.MEDIUM
    annualized_return: Decimal = Decimal("0")
    volatility: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegimePerformance:
    """Performance summary for a specific regime.

    Attributes:
        regime: The regime this performance is for
        period_count: Number of periods in this regime
        total_days: Total trading days in this regime
        avg_return: Average return across periods
        total_return: Cumulative return
        volatility: Average volatility in this regime
        avg_drawdown: Average max drawdown
        worst_drawdown: Worst max drawdown seen
        win_rate: Percentage of winning periods
        sharpe_ratio: Sharpe ratio for this regime
        best_period_return: Best single period return
        worst_period_return: Worst single period return
        consistency_score: How consistent returns are (0-1)
    """
    regime: Union[MarketRegime, VolatilityRegime]
    period_count: int = 0
    total_days: int = 0
    avg_return: Decimal = Decimal("0")
    total_return: Decimal = Decimal("0")
    volatility: Decimal = Decimal("0")
    avg_drawdown: Decimal = Decimal("0")
    worst_drawdown: Decimal = Decimal("0")
    win_rate: Decimal = Decimal("0")
    sharpe_ratio: Optional[Decimal] = None
    best_period_return: Decimal = Decimal("0")
    worst_period_return: Decimal = Decimal("0")
    consistency_score: Decimal = Decimal("0")


@dataclass
class RegimeTransition:
    """Record of a transition between regimes.

    Attributes:
        transition_id: Unique identifier
        transition_date: When the transition occurred
        from_regime: Previous regime
        to_regime: New regime
        transition_return: Return during transition period
        transition_volatility: Volatility during transition
        days_in_prior_regime: How long in prior regime
    """
    transition_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    transition_date: Optional[date] = None
    from_regime: Optional[MarketRegime] = None
    to_regime: Optional[MarketRegime] = None
    transition_return: Decimal = Decimal("0")
    transition_volatility: Decimal = Decimal("0")
    days_in_prior_regime: int = 0


@dataclass
class RegimeRecommendation:
    """Strategy recommendation for a specific regime.

    Attributes:
        regime: The regime this recommendation is for
        allocation_adjustment: Suggested allocation change (-1 to 1)
        risk_adjustment: Suggested risk adjustment (-1 to 1)
        position_sizing: Recommended position size factor (0.5-1.5)
        strategy_notes: Specific strategy recommendations
        cautions: Warnings for this regime
        opportunities: Potential opportunities
    """
    regime: MarketRegime
    allocation_adjustment: Decimal = Decimal("0")
    risk_adjustment: Decimal = Decimal("0")
    position_sizing: Decimal = Decimal("1")
    strategy_notes: List[str] = field(default_factory=list)
    cautions: List[str] = field(default_factory=list)
    opportunities: List[str] = field(default_factory=list)


@dataclass
class RegimeEvaluationResult:
    """Complete result of regime-based evaluation.

    Attributes:
        evaluation_id: Unique identifier
        strategy_id: ID of evaluated strategy
        strategy_name: Name of the strategy
        start_date: Evaluation period start
        end_date: Evaluation period end
        current_regime: Currently detected regime
        current_volatility: Current volatility regime
        regime_tags: All regime tags detected
        performance_by_market_regime: Performance in each market regime
        performance_by_volatility: Performance in each volatility regime
        transitions: Regime transitions detected
        recommendations: Regime-specific recommendations
        overall_regime_score: How well strategy handles regimes (0-100)
        regime_adaptability: How adaptive strategy is to changes (0-100)
        metadata: Additional evaluation data
    """
    evaluation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    strategy_id: str = ""
    strategy_name: str = ""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    current_regime: MarketRegime = MarketRegime.SIDEWAYS
    current_volatility: VolatilityRegime = VolatilityRegime.NORMAL
    regime_tags: List[RegimeTag] = field(default_factory=list)
    performance_by_market_regime: Dict[MarketRegime, RegimePerformance] = field(
        default_factory=dict
    )
    performance_by_volatility: Dict[VolatilityRegime, RegimePerformance] = field(
        default_factory=dict
    )
    transitions: List[RegimeTransition] = field(default_factory=list)
    recommendations: Dict[MarketRegime, RegimeRecommendation] = field(
        default_factory=dict
    )
    overall_regime_score: Decimal = Decimal("0")
    regime_adaptability: Decimal = Decimal("0")
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# RegimeDetector Class
# ============================================================================

class RegimeDetector:
    """Detects market and volatility regimes from price/return data.

    Uses statistical analysis of returns to classify market conditions
    into bull, bear, or sideways regimes with volatility assessment.

    Attributes:
        bull_threshold: Annualized return above this = bull
        bear_threshold: Annualized return below this = bear
        vol_low_threshold: Vol below this = low volatility
        vol_high_threshold: Vol above this = high volatility
        min_periods: Minimum periods needed for regime detection
    """

    def __init__(
        self,
        bull_threshold: Decimal = Decimal("0.20"),
        bear_threshold: Decimal = Decimal("-0.20"),
        moderate_bull_threshold: Decimal = Decimal("0.05"),
        moderate_bear_threshold: Decimal = Decimal("-0.05"),
        vol_low_threshold: Decimal = Decimal("0.10"),
        vol_normal_threshold: Decimal = Decimal("0.20"),
        vol_high_threshold: Decimal = Decimal("0.30"),
        min_periods: int = 20,
    ):
        """Initialize regime detector with thresholds.

        Args:
            bull_threshold: Return above this = strong bull (default 20%)
            bear_threshold: Return below this = strong bear (default -20%)
            moderate_bull_threshold: Return above this = moderate bull (default 5%)
            moderate_bear_threshold: Return below this = moderate bear (default -5%)
            vol_low_threshold: Volatility below this = low (default 10%)
            vol_normal_threshold: Vol above this = elevated (default 20%)
            vol_high_threshold: Vol above this = high (default 30%)
            min_periods: Minimum periods for detection (default 20)
        """
        self.bull_threshold = bull_threshold
        self.bear_threshold = bear_threshold
        self.moderate_bull_threshold = moderate_bull_threshold
        self.moderate_bear_threshold = moderate_bear_threshold
        self.vol_low_threshold = vol_low_threshold
        self.vol_normal_threshold = vol_normal_threshold
        self.vol_high_threshold = vol_high_threshold
        self.min_periods = min_periods

    def detect_market_regime(
        self,
        returns: List[Decimal],
        periods_per_year: int = 252,
    ) -> Tuple[MarketRegime, RegimeConfidence]:
        """Detect market regime from return series.

        Args:
            returns: List of periodic returns (daily, weekly, etc.)
            periods_per_year: Number of periods in a year (252 for daily)

        Returns:
            Tuple of (MarketRegime, RegimeConfidence)
        """
        if len(returns) < self.min_periods:
            return MarketRegime.SIDEWAYS, RegimeConfidence.LOW

        # Calculate annualized return
        avg_return = sum(returns) / len(returns)
        annualized = avg_return * Decimal(str(periods_per_year))

        # Calculate confidence based on consistency
        positive_count = sum(1 for r in returns if r > 0)
        win_rate = Decimal(str(positive_count)) / Decimal(str(len(returns)))

        # Determine regime
        if annualized > self.bull_threshold:
            regime = MarketRegime.BULL
            confidence = self._calculate_confidence(win_rate, Decimal("0.55"))
        elif annualized > self.moderate_bull_threshold:
            regime = MarketRegime.MODERATE_BULL
            confidence = self._calculate_confidence(win_rate, Decimal("0.52"))
        elif annualized < self.bear_threshold:
            regime = MarketRegime.BEAR
            confidence = self._calculate_confidence(
                Decimal("1") - win_rate, Decimal("0.55")
            )
        elif annualized < self.moderate_bear_threshold:
            regime = MarketRegime.MODERATE_BEAR
            confidence = self._calculate_confidence(
                Decimal("1") - win_rate, Decimal("0.52")
            )
        else:
            regime = MarketRegime.SIDEWAYS
            # Sideways confidence based on how close to zero
            deviation = abs(annualized)
            if deviation < Decimal("0.02"):
                confidence = RegimeConfidence.HIGH
            elif deviation < Decimal("0.04"):
                confidence = RegimeConfidence.MEDIUM
            else:
                confidence = RegimeConfidence.LOW

        return regime, confidence

    def detect_volatility_regime(
        self,
        returns: List[Decimal],
        periods_per_year: int = 252,
    ) -> Tuple[VolatilityRegime, Decimal]:
        """Detect volatility regime from return series.

        Args:
            returns: List of periodic returns
            periods_per_year: Number of periods in a year

        Returns:
            Tuple of (VolatilityRegime, annualized_volatility)
        """
        if len(returns) < self.min_periods:
            return VolatilityRegime.NORMAL, Decimal("0.15")

        # Calculate standard deviation of returns
        float_returns = [float(r) for r in returns]
        if len(set(float_returns)) == 1:
            # All returns identical, zero volatility
            return VolatilityRegime.LOW, Decimal("0")

        period_vol = Decimal(str(statistics.stdev(float_returns)))
        annual_vol = period_vol * Decimal(str(periods_per_year)).sqrt()

        if annual_vol < self.vol_low_threshold:
            regime = VolatilityRegime.LOW
        elif annual_vol < self.vol_normal_threshold:
            regime = VolatilityRegime.NORMAL
        elif annual_vol < self.vol_high_threshold:
            regime = VolatilityRegime.ELEVATED
        else:
            regime = VolatilityRegime.HIGH

        return regime, annual_vol

    def detect_trend_strength(
        self,
        returns: List[Decimal],
    ) -> TrendStrength:
        """Detect strength of trend from returns.

        Uses autocorrelation and directional consistency.

        Args:
            returns: List of periodic returns

        Returns:
            TrendStrength classification
        """
        if len(returns) < self.min_periods:
            return TrendStrength.NONE

        # Calculate directional consistency
        positive_count = sum(1 for r in returns if r > 0)
        consistency = abs(
            Decimal(str(positive_count)) / Decimal(str(len(returns))) - Decimal("0.5")
        )

        # Strong trend: >65% consistent direction
        if consistency > Decimal("0.15"):
            return TrendStrength.STRONG
        elif consistency > Decimal("0.10"):
            return TrendStrength.MODERATE
        elif consistency > Decimal("0.05"):
            return TrendStrength.WEAK
        else:
            return TrendStrength.NONE

    def _calculate_confidence(
        self,
        rate: Decimal,
        threshold: Decimal,
    ) -> RegimeConfidence:
        """Calculate confidence from win/loss rate.

        Args:
            rate: Observed win rate
            threshold: Threshold for high confidence

        Returns:
            RegimeConfidence level
        """
        if rate > threshold + Decimal("0.10"):
            return RegimeConfidence.HIGH
        elif rate > threshold:
            return RegimeConfidence.MEDIUM
        else:
            return RegimeConfidence.LOW

    def tag_period(
        self,
        returns: List[Decimal],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        periods_per_year: int = 252,
    ) -> RegimeTag:
        """Create a regime tag for a time period.

        Args:
            returns: List of returns for the period
            start_date: Period start date
            end_date: Period end date
            periods_per_year: Trading periods per year

        Returns:
            RegimeTag with detected regimes
        """
        market_regime, confidence = self.detect_market_regime(
            returns, periods_per_year
        )
        volatility_regime, vol = self.detect_volatility_regime(
            returns, periods_per_year
        )
        trend = self.detect_trend_strength(returns)

        # Calculate metrics
        if returns:
            avg_return = sum(returns) / len(returns)
            annualized = avg_return * Decimal(str(periods_per_year))
            max_dd = self._calculate_max_drawdown(returns)
        else:
            annualized = Decimal("0")
            max_dd = Decimal("0")

        return RegimeTag(
            start_date=start_date,
            end_date=end_date,
            market_regime=market_regime,
            volatility_regime=volatility_regime,
            trend_strength=trend,
            confidence=confidence,
            annualized_return=annualized,
            volatility=vol,
            max_drawdown=max_dd,
        )

    def _calculate_max_drawdown(self, returns: List[Decimal]) -> Decimal:
        """Calculate maximum drawdown from returns.

        Args:
            returns: List of periodic returns

        Returns:
            Maximum drawdown as negative decimal
        """
        if not returns:
            return Decimal("0")

        cumulative = Decimal("1")
        peak = Decimal("1")
        max_dd = Decimal("0")

        for ret in returns:
            cumulative *= (Decimal("1") + ret)
            if cumulative > peak:
                peak = cumulative
            drawdown = (cumulative - peak) / peak
            if drawdown < max_dd:
                max_dd = drawdown

        return max_dd


# ============================================================================
# RegimeEvaluator Class
# ============================================================================

class RegimeEvaluator:
    """Evaluates strategy performance across different regimes.

    Provides comprehensive analysis of how strategies perform in
    different market and volatility conditions.

    Attributes:
        detector: RegimeDetector for regime classification
        lookback_periods: Periods to look back for regime detection
    """

    def __init__(
        self,
        detector: Optional[RegimeDetector] = None,
        lookback_periods: int = 60,
    ):
        """Initialize regime evaluator.

        Args:
            detector: RegimeDetector instance (creates default if None)
            lookback_periods: Periods for rolling regime detection
        """
        self.detector = detector or RegimeDetector()
        self.lookback_periods = lookback_periods

    def evaluate_strategy(
        self,
        strategy_id: str,
        strategy_name: str,
        returns: List[Decimal],
        dates: Optional[List[date]] = None,
        periods_per_year: int = 252,
        benchmark_returns: Optional[List[Decimal]] = None,
    ) -> RegimeEvaluationResult:
        """Evaluate a strategy across all detected regimes.

        Args:
            strategy_id: Unique strategy identifier
            strategy_name: Human-readable strategy name
            returns: List of strategy returns
            dates: Optional list of dates for each return
            periods_per_year: Periods per year (252 for daily)
            benchmark_returns: Optional benchmark returns for regime detection

        Returns:
            RegimeEvaluationResult with complete analysis
        """
        if not returns:
            return RegimeEvaluationResult(
                strategy_id=strategy_id,
                strategy_name=strategy_name,
            )

        # Use benchmark returns for regime detection if provided
        regime_returns = benchmark_returns if benchmark_returns else returns

        # Detect regime tags using rolling windows
        regime_tags = self._detect_rolling_regimes(
            regime_returns, dates, periods_per_year
        )

        # Calculate performance by market regime
        perf_by_market = self._calculate_performance_by_regime(
            returns, dates, regime_tags, "market", periods_per_year
        )

        # Calculate performance by volatility regime
        perf_by_vol = self._calculate_performance_by_regime(
            returns, dates, regime_tags, "volatility", periods_per_year
        )

        # Detect transitions
        transitions = self._detect_transitions(regime_tags)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            perf_by_market, perf_by_vol
        )

        # Get current regime (most recent)
        current_regime = MarketRegime.SIDEWAYS
        current_vol = VolatilityRegime.NORMAL
        if regime_tags:
            current_regime = regime_tags[-1].market_regime
            current_vol = regime_tags[-1].volatility_regime

        # Calculate overall scores
        regime_score = self._calculate_regime_score(perf_by_market)
        adaptability = self._calculate_adaptability(transitions, perf_by_market)

        # Determine date range
        start = dates[0] if dates else None
        end = dates[-1] if dates else None

        return RegimeEvaluationResult(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            start_date=start,
            end_date=end,
            current_regime=current_regime,
            current_volatility=current_vol,
            regime_tags=regime_tags,
            performance_by_market_regime=perf_by_market,
            performance_by_volatility=perf_by_vol,
            transitions=transitions,
            recommendations=recommendations,
            overall_regime_score=regime_score,
            regime_adaptability=adaptability,
        )

    def compare_strategies_by_regime(
        self,
        strategies: List[Tuple[str, str, List[Decimal]]],
        dates: Optional[List[date]] = None,
        periods_per_year: int = 252,
        benchmark_returns: Optional[List[Decimal]] = None,
    ) -> Dict[str, RegimeEvaluationResult]:
        """Compare multiple strategies by regime performance.

        Args:
            strategies: List of (id, name, returns) tuples
            dates: Optional shared date list
            periods_per_year: Periods per year
            benchmark_returns: Benchmark for regime detection

        Returns:
            Dict mapping strategy_id to RegimeEvaluationResult
        """
        results = {}
        for strategy_id, strategy_name, returns in strategies:
            results[strategy_id] = self.evaluate_strategy(
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                returns=returns,
                dates=dates,
                periods_per_year=periods_per_year,
                benchmark_returns=benchmark_returns,
            )
        return results

    def get_best_strategy_for_regime(
        self,
        evaluations: Dict[str, RegimeEvaluationResult],
        regime: MarketRegime,
    ) -> Optional[str]:
        """Find the best performing strategy for a specific regime.

        Args:
            evaluations: Dict of strategy evaluations
            regime: The regime to find best strategy for

        Returns:
            strategy_id of best strategy, or None
        """
        best_id = None
        best_sharpe = None

        for strategy_id, result in evaluations.items():
            if regime in result.performance_by_market_regime:
                perf = result.performance_by_market_regime[regime]
                if perf.sharpe_ratio is not None:
                    if best_sharpe is None or perf.sharpe_ratio > best_sharpe:
                        best_sharpe = perf.sharpe_ratio
                        best_id = strategy_id

        return best_id

    def _detect_rolling_regimes(
        self,
        returns: List[Decimal],
        dates: Optional[List[date]],
        periods_per_year: int,
    ) -> List[RegimeTag]:
        """Detect regimes using rolling windows.

        Args:
            returns: Return series
            dates: Optional date list
            periods_per_year: Periods per year

        Returns:
            List of RegimeTag for each window
        """
        tags = []
        window_size = self.lookback_periods

        if len(returns) < window_size:
            # Single tag for entire period
            tag = self.detector.tag_period(
                returns=returns,
                start_date=dates[0] if dates else None,
                end_date=dates[-1] if dates else None,
                periods_per_year=periods_per_year,
            )
            return [tag]

        # Rolling windows with step = half window
        step = max(1, window_size // 2)
        for i in range(0, len(returns) - window_size + 1, step):
            window_returns = returns[i:i + window_size]
            start = dates[i] if dates else None
            end = dates[i + window_size - 1] if dates else None

            tag = self.detector.tag_period(
                returns=window_returns,
                start_date=start,
                end_date=end,
                periods_per_year=periods_per_year,
            )
            tags.append(tag)

        return tags

    def _calculate_performance_by_regime(
        self,
        returns: List[Decimal],
        dates: Optional[List[date]],
        tags: List[RegimeTag],
        regime_type: str,  # "market" or "volatility"
        periods_per_year: int,
    ) -> Dict:
        """Calculate performance breakdown by regime.

        Args:
            returns: Strategy returns
            dates: Date list
            tags: Regime tags
            regime_type: "market" or "volatility"
            periods_per_year: Periods per year

        Returns:
            Dict mapping regime to RegimePerformance
        """
        if regime_type == "market":
            regimes = list(MarketRegime)
        else:
            regimes = list(VolatilityRegime)

        result = {}

        for regime in regimes:
            # Collect returns for this regime
            regime_returns = []
            regime_days = 0

            for i, tag in enumerate(tags):
                if regime_type == "market":
                    tag_regime = tag.market_regime
                else:
                    tag_regime = tag.volatility_regime

                if tag_regime == regime:
                    # Add returns from this tag's period
                    # Approximate: divide returns evenly across tags
                    start_idx = i * (self.lookback_periods // 2)
                    end_idx = min(
                        start_idx + self.lookback_periods,
                        len(returns)
                    )
                    regime_returns.extend(returns[start_idx:end_idx])
                    regime_days += end_idx - start_idx

            if not regime_returns:
                continue

            # Calculate metrics
            avg_ret = sum(regime_returns) / len(regime_returns)
            total_ret = self._calculate_cumulative_return(regime_returns)

            # Volatility
            if len(regime_returns) > 1:
                float_rets = [float(r) for r in regime_returns]
                period_vol = Decimal(str(statistics.stdev(float_rets)))
                vol = period_vol * Decimal(str(periods_per_year)).sqrt()
            else:
                vol = Decimal("0")

            # Win rate
            wins = sum(1 for r in regime_returns if r > 0)
            win_rate = Decimal(str(wins)) / Decimal(str(len(regime_returns)))

            # Max drawdown
            max_dd = self.detector._calculate_max_drawdown(regime_returns)

            # Sharpe ratio
            if vol > 0:
                annual_ret = avg_ret * Decimal(str(periods_per_year))
                sharpe = annual_ret / vol
            else:
                sharpe = None

            # Best/worst
            best = max(regime_returns)
            worst = min(regime_returns)

            # Consistency (inverse of return std)
            if len(regime_returns) > 1:
                ret_std = Decimal(str(statistics.stdev(float_rets)))
                consistency = max(Decimal("0"), Decimal("1") - ret_std * 10)
            else:
                consistency = Decimal("0.5")

            result[regime] = RegimePerformance(
                regime=regime,
                period_count=len([t for t in tags if (
                    t.market_regime if regime_type == "market"
                    else t.volatility_regime
                ) == regime]),
                total_days=regime_days,
                avg_return=avg_ret * Decimal(str(periods_per_year)),
                total_return=total_ret,
                volatility=vol,
                avg_drawdown=max_dd,
                worst_drawdown=max_dd,
                win_rate=win_rate,
                sharpe_ratio=sharpe,
                best_period_return=best,
                worst_period_return=worst,
                consistency_score=consistency,
            )

        return result

    def _calculate_cumulative_return(
        self,
        returns: List[Decimal],
    ) -> Decimal:
        """Calculate cumulative return from periodic returns.

        Args:
            returns: List of periodic returns

        Returns:
            Total cumulative return
        """
        cumulative = Decimal("1")
        for ret in returns:
            cumulative *= (Decimal("1") + ret)
        return cumulative - Decimal("1")

    def _detect_transitions(
        self,
        tags: List[RegimeTag],
    ) -> List[RegimeTransition]:
        """Detect regime transitions from tag sequence.

        Args:
            tags: List of regime tags

        Returns:
            List of RegimeTransition
        """
        transitions = []

        for i in range(1, len(tags)):
            prev_regime = tags[i - 1].market_regime
            curr_regime = tags[i].market_regime

            if prev_regime != curr_regime:
                transitions.append(RegimeTransition(
                    transition_date=tags[i].start_date,
                    from_regime=prev_regime,
                    to_regime=curr_regime,
                    transition_return=tags[i].annualized_return,
                    transition_volatility=tags[i].volatility,
                    days_in_prior_regime=self.lookback_periods,
                ))

        return transitions

    def _generate_recommendations(
        self,
        perf_by_market: Dict[MarketRegime, RegimePerformance],
        perf_by_vol: Dict[VolatilityRegime, RegimePerformance],
    ) -> Dict[MarketRegime, RegimeRecommendation]:
        """Generate regime-specific recommendations.

        Args:
            perf_by_market: Performance by market regime
            perf_by_vol: Performance by volatility regime

        Returns:
            Dict of recommendations per regime
        """
        recommendations = {}

        for regime in MarketRegime:
            rec = self._create_recommendation_for_regime(
                regime, perf_by_market.get(regime)
            )
            recommendations[regime] = rec

        return recommendations

    def _create_recommendation_for_regime(
        self,
        regime: MarketRegime,
        perf: Optional[RegimePerformance],
    ) -> RegimeRecommendation:
        """Create recommendation for a specific regime.

        Args:
            regime: The market regime
            perf: Performance in this regime

        Returns:
            RegimeRecommendation
        """
        rec = RegimeRecommendation(regime=regime)

        if regime == MarketRegime.BULL:
            rec.allocation_adjustment = Decimal("0.2")
            rec.position_sizing = Decimal("1.2")
            rec.strategy_notes = [
                "Increase equity exposure",
                "Consider momentum strategies",
                "Reduce cash holdings",
            ]
            rec.opportunities = [
                "Growth stocks outperform",
                "Risk-on positioning favored",
            ]

        elif regime == MarketRegime.MODERATE_BULL:
            rec.allocation_adjustment = Decimal("0.1")
            rec.position_sizing = Decimal("1.1")
            rec.strategy_notes = [
                "Maintain balanced exposure",
                "Focus on quality growth",
            ]

        elif regime == MarketRegime.SIDEWAYS:
            rec.allocation_adjustment = Decimal("0")
            rec.position_sizing = Decimal("1.0")
            rec.strategy_notes = [
                "Range-trading strategies may work",
                "Consider covered calls for income",
                "Reduce directional bets",
            ]
            rec.cautions = [
                "Low returns expected",
                "Transaction costs eat into profits",
            ]

        elif regime == MarketRegime.MODERATE_BEAR:
            rec.allocation_adjustment = Decimal("-0.1")
            rec.risk_adjustment = Decimal("-0.2")
            rec.position_sizing = Decimal("0.9")
            rec.strategy_notes = [
                "Increase defensive allocation",
                "Add quality names on dips",
            ]
            rec.cautions = [
                "Trend may accelerate lower",
            ]

        elif regime == MarketRegime.BEAR:
            rec.allocation_adjustment = Decimal("-0.3")
            rec.risk_adjustment = Decimal("-0.4")
            rec.position_sizing = Decimal("0.7")
            rec.strategy_notes = [
                "Maximize defensive allocation",
                "Consider hedging strategies",
                "Hold cash for opportunities",
            ]
            rec.cautions = [
                "Capital preservation is priority",
                "Avoid catching falling knives",
            ]
            rec.opportunities = [
                "Build watchlist for recovery",
                "Quality assets on sale",
            ]

        # Adjust based on actual performance
        if perf:
            if perf.sharpe_ratio and perf.sharpe_ratio < Decimal("0"):
                rec.cautions.append(
                    f"Strategy underperforms in {regime.value} markets"
                )
                rec.position_sizing = max(
                    Decimal("0.5"),
                    rec.position_sizing - Decimal("0.2")
                )

            if perf.win_rate < Decimal("0.4"):
                rec.cautions.append(
                    f"Low win rate ({float(perf.win_rate):.1%}) in this regime"
                )

            if perf.worst_drawdown < Decimal("-0.15"):
                rec.cautions.append(
                    f"Large drawdowns ({float(perf.worst_drawdown):.1%}) observed"
                )

        return rec

    def _calculate_regime_score(
        self,
        perf_by_market: Dict[MarketRegime, RegimePerformance],
    ) -> Decimal:
        """Calculate overall regime handling score.

        Considers performance across all regimes weighted by severity.

        Args:
            perf_by_market: Performance by market regime

        Returns:
            Score from 0 to 100
        """
        if not perf_by_market:
            return Decimal("50")

        # Weight regimes by difficulty
        weights = {
            MarketRegime.BULL: Decimal("1.0"),
            MarketRegime.MODERATE_BULL: Decimal("1.0"),
            MarketRegime.SIDEWAYS: Decimal("1.2"),
            MarketRegime.MODERATE_BEAR: Decimal("1.5"),
            MarketRegime.BEAR: Decimal("2.0"),
        }

        total_weight = Decimal("0")
        weighted_score = Decimal("0")

        for regime, perf in perf_by_market.items():
            weight = weights.get(regime, Decimal("1"))

            # Score based on Sharpe
            if perf.sharpe_ratio is not None:
                # Convert Sharpe to 0-100 score
                # Sharpe of 2 = 100, Sharpe of -1 = 0
                sharpe_score = min(
                    Decimal("100"),
                    max(
                        Decimal("0"),
                        (perf.sharpe_ratio + Decimal("1")) * Decimal("33.33")
                    )
                )
            else:
                sharpe_score = Decimal("50")

            weighted_score += weight * sharpe_score
            total_weight += weight

        if total_weight > 0:
            return weighted_score / total_weight
        return Decimal("50")

    def _calculate_adaptability(
        self,
        transitions: List[RegimeTransition],
        perf_by_market: Dict[MarketRegime, RegimePerformance],
    ) -> Decimal:
        """Calculate strategy adaptability score.

        Measures how well strategy handles regime changes.

        Args:
            transitions: List of regime transitions
            perf_by_market: Performance by regime

        Returns:
            Score from 0 to 100
        """
        if not transitions or not perf_by_market:
            return Decimal("50")

        # Check performance variance across regimes
        sharpes = [
            p.sharpe_ratio for p in perf_by_market.values()
            if p.sharpe_ratio is not None
        ]

        if len(sharpes) < 2:
            return Decimal("50")

        float_sharpes = [float(s) for s in sharpes]
        sharpe_std = Decimal(str(statistics.stdev(float_sharpes)))

        # Lower std = more adaptive
        # Std of 0 = 100, Std of 2 = 0
        adaptability = max(
            Decimal("0"),
            Decimal("100") - sharpe_std * Decimal("50")
        )

        return adaptability

    def generate_regime_report(
        self,
        result: RegimeEvaluationResult,
    ) -> str:
        """Generate a formatted regime evaluation report.

        Args:
            result: RegimeEvaluationResult to report on

        Returns:
            Formatted markdown report
        """
        lines = [
            "# Regime Evaluation Report",
            f"**Strategy**: {result.strategy_name}",
            f"**Period**: {result.start_date} to {result.end_date}",
            "",
            "## Current Conditions",
            f"- **Market Regime**: {result.current_regime.value}",
            f"- **Volatility**: {result.current_volatility.value}",
            f"- **Overall Score**: {float(result.overall_regime_score):.1f}/100",
            f"- **Adaptability**: {float(result.regime_adaptability):.1f}/100",
            "",
            "## Performance by Market Regime",
            "",
            "| Regime | Periods | Avg Return | Sharpe | Win Rate | Max DD |",
            "|--------|---------|------------|--------|----------|--------|",
        ]

        for regime in MarketRegime:
            if regime in result.performance_by_market_regime:
                perf = result.performance_by_market_regime[regime]
                sharpe = f"{float(perf.sharpe_ratio):.2f}" if perf.sharpe_ratio else "N/A"
                lines.append(
                    f"| {regime.value} | {perf.period_count} | "
                    f"{float(perf.avg_return):.1%} | {sharpe} | "
                    f"{float(perf.win_rate):.1%} | {float(perf.worst_drawdown):.1%} |"
                )

        lines.extend([
            "",
            "## Performance by Volatility",
            "",
            "| Vol Regime | Periods | Avg Return | Sharpe | Win Rate |",
            "|------------|---------|------------|--------|----------|",
        ])

        for regime in VolatilityRegime:
            if regime in result.performance_by_volatility:
                perf = result.performance_by_volatility[regime]
                sharpe = f"{float(perf.sharpe_ratio):.2f}" if perf.sharpe_ratio else "N/A"
                lines.append(
                    f"| {regime.value} | {perf.period_count} | "
                    f"{float(perf.avg_return):.1%} | {sharpe} | "
                    f"{float(perf.win_rate):.1%} |"
                )

        if result.transitions:
            lines.extend([
                "",
                "## Regime Transitions",
                f"Total transitions detected: {len(result.transitions)}",
                "",
            ])
            for t in result.transitions[:5]:
                lines.append(
                    f"- {t.transition_date}: "
                    f"{t.from_regime.value if t.from_regime else 'N/A'} → "
                    f"{t.to_regime.value if t.to_regime else 'N/A'}"
                )

        # Add recommendation for current regime
        if result.current_regime in result.recommendations:
            rec = result.recommendations[result.current_regime]
            lines.extend([
                "",
                f"## Recommendations for {result.current_regime.value.title()} Market",
                "",
                "### Strategy Notes",
            ])
            for note in rec.strategy_notes:
                lines.append(f"- {note}")

            if rec.cautions:
                lines.append("")
                lines.append("### Cautions")
                for caution in rec.cautions:
                    lines.append(f"- ⚠️ {caution}")

            if rec.opportunities:
                lines.append("")
                lines.append("### Opportunities")
                for opp in rec.opportunities:
                    lines.append(f"- ✓ {opp}")

        return "\n".join(lines)
