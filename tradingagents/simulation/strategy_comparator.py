"""Strategy Comparator for performance comparison and statistical analysis.

This module provides strategy comparison capabilities including:
- Performance metrics comparison across strategies
- Statistical significance testing
- Ranking and scoring
- Visualization data preparation

Issue #34: [SIM-33] Strategy comparator - performance comparison, stats

Design Principles:
    - Comprehensive performance metrics
    - Statistical rigor (hypothesis testing)
    - Flexible ranking criteria
    - Clear comparison outputs
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import math
import statistics


class RankingCriteria(Enum):
    """Criteria for ranking strategies."""
    TOTAL_RETURN = "total_return"
    SHARPE_RATIO = "sharpe_ratio"
    SORTINO_RATIO = "sortino_ratio"
    MAX_DRAWDOWN = "max_drawdown"
    WIN_RATE = "win_rate"
    PROFIT_FACTOR = "profit_factor"
    CALMAR_RATIO = "calmar_ratio"
    RISK_ADJUSTED_RETURN = "risk_adjusted_return"


class ComparisonStatus(Enum):
    """Status of strategy comparison."""
    VALID = "valid"
    INSUFFICIENT_DATA = "insufficient_data"
    INCOMPARABLE = "incomparable"


@dataclass
class StrategyMetrics:
    """Performance metrics for a strategy.

    Attributes:
        strategy_id: Unique identifier
        strategy_name: Human-readable name
        start_date: First date of performance data
        end_date: Last date of performance data
        total_return: Total return as decimal (0.10 = 10%)
        annualized_return: Annualized return
        volatility: Annualized standard deviation of returns
        sharpe_ratio: Sharpe ratio (risk-free rate assumed 0)
        sortino_ratio: Sortino ratio (downside deviation)
        max_drawdown: Maximum drawdown (negative)
        calmar_ratio: Annualized return / max drawdown
        win_rate: Percentage of winning trades
        profit_factor: Gross profit / gross loss
        total_trades: Number of trades executed
        avg_trade_return: Average return per trade
        avg_win: Average winning trade
        avg_loss: Average losing trade
        best_trade: Best single trade return
        worst_trade: Worst single trade return
        returns_series: Time series of periodic returns
        equity_curve: Time series of equity values
        metadata: Additional strategy data
    """
    strategy_id: str
    strategy_name: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    total_return: Decimal = Decimal("0")
    annualized_return: Decimal = Decimal("0")
    volatility: Decimal = Decimal("0")
    sharpe_ratio: Optional[Decimal] = None
    sortino_ratio: Optional[Decimal] = None
    max_drawdown: Decimal = Decimal("0")
    calmar_ratio: Optional[Decimal] = None
    win_rate: Decimal = Decimal("0")
    profit_factor: Optional[Decimal] = None
    total_trades: int = 0
    avg_trade_return: Decimal = Decimal("0")
    avg_win: Decimal = Decimal("0")
    avg_loss: Decimal = Decimal("0")
    best_trade: Decimal = Decimal("0")
    worst_trade: Decimal = Decimal("0")
    returns_series: List[Decimal] = field(default_factory=list)
    equity_curve: List[Tuple[date, Decimal]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def risk_adjusted_return(self) -> Decimal:
        """Calculate risk-adjusted return (return / volatility)."""
        if self.volatility == 0:
            return Decimal("0")
        return (self.total_return / self.volatility).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

    @property
    def has_sufficient_data(self) -> bool:
        """Check if strategy has sufficient data for comparison."""
        return self.total_trades >= 10 or len(self.returns_series) >= 30


@dataclass
class PairwiseComparison:
    """Comparison between two strategies.

    Attributes:
        strategy_a_id: First strategy ID
        strategy_b_id: Second strategy ID
        winner: ID of the winning strategy (or None if tie)
        return_difference: Difference in total returns (A - B)
        sharpe_difference: Difference in Sharpe ratios
        volatility_difference: Difference in volatility
        statistically_significant: Whether difference is significant
        p_value: P-value from statistical test
        confidence_interval: 95% CI for return difference
        notes: Additional comparison notes
    """
    strategy_a_id: str
    strategy_b_id: str
    winner: Optional[str] = None
    return_difference: Decimal = Decimal("0")
    sharpe_difference: Optional[Decimal] = None
    volatility_difference: Decimal = Decimal("0")
    statistically_significant: bool = False
    p_value: Optional[float] = None
    confidence_interval: Optional[Tuple[float, float]] = None
    notes: str = ""


@dataclass
class ComparisonResult:
    """Complete result of strategy comparison.

    Attributes:
        status: Comparison status
        strategies: List of strategies compared
        rankings: Strategies ranked by criteria
        best_overall: Best overall strategy ID
        worst_overall: Worst overall strategy ID
        pairwise_comparisons: Pairwise comparison results
        summary_statistics: Summary statistics across all strategies
        recommendations: Analysis recommendations
        metadata: Additional result data
    """
    status: ComparisonStatus
    strategies: List[StrategyMetrics] = field(default_factory=list)
    rankings: Dict[RankingCriteria, List[str]] = field(default_factory=dict)
    best_overall: Optional[str] = None
    worst_overall: Optional[str] = None
    pairwise_comparisons: List[PairwiseComparison] = field(default_factory=list)
    summary_statistics: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def strategy_count(self) -> int:
        """Number of strategies compared."""
        return len(self.strategies)


class StrategyComparator:
    """Compares multiple trading strategies.

    Provides comprehensive comparison of strategy performance including
    statistical tests, rankings, and recommendations.

    Example:
        >>> comparator = StrategyComparator()
        >>> comparator.add_strategy(StrategyMetrics(
        ...     strategy_id="strat1",
        ...     strategy_name="Momentum",
        ...     total_return=Decimal("0.25"),
        ...     sharpe_ratio=Decimal("1.5"),
        ... ))
        >>> comparator.add_strategy(StrategyMetrics(
        ...     strategy_id="strat2",
        ...     strategy_name="Value",
        ...     total_return=Decimal("0.18"),
        ...     sharpe_ratio=Decimal("1.2"),
        ... ))
        >>> result = comparator.compare()
        >>> print(f"Best: {result.best_overall}")
    """

    def __init__(
        self,
        risk_free_rate: Decimal = Decimal("0"),
        min_data_points: int = 30,
        significance_level: float = 0.05,
    ):
        """Initialize the comparator.

        Args:
            risk_free_rate: Risk-free rate for Sharpe calculations
            min_data_points: Minimum data points for valid comparison
            significance_level: Significance level for statistical tests
        """
        self.risk_free_rate = risk_free_rate
        self.min_data_points = min_data_points
        self.significance_level = significance_level
        self._strategies: Dict[str, StrategyMetrics] = {}

    def add_strategy(self, strategy: StrategyMetrics) -> None:
        """Add a strategy for comparison.

        Args:
            strategy: Strategy metrics to add
        """
        self._strategies[strategy.strategy_id] = strategy

    def remove_strategy(self, strategy_id: str) -> bool:
        """Remove a strategy from comparison.

        Args:
            strategy_id: ID of strategy to remove

        Returns:
            True if removed, False if not found
        """
        if strategy_id in self._strategies:
            del self._strategies[strategy_id]
            return True
        return False

    def get_strategy(self, strategy_id: str) -> Optional[StrategyMetrics]:
        """Get a strategy by ID.

        Args:
            strategy_id: Strategy ID

        Returns:
            Strategy metrics or None if not found
        """
        return self._strategies.get(strategy_id)

    def get_all_strategies(self) -> List[StrategyMetrics]:
        """Get all strategies.

        Returns:
            List of all strategy metrics
        """
        return list(self._strategies.values())

    def clear(self) -> None:
        """Remove all strategies."""
        self._strategies.clear()

    def _rank_by_criteria(
        self, criteria: RankingCriteria
    ) -> List[str]:
        """Rank strategies by a specific criterion.

        Args:
            criteria: Ranking criterion

        Returns:
            List of strategy IDs in ranked order (best first)
        """
        strategies = list(self._strategies.values())

        if criteria == RankingCriteria.TOTAL_RETURN:
            key = lambda s: float(s.total_return)
            reverse = True
        elif criteria == RankingCriteria.SHARPE_RATIO:
            key = lambda s: float(s.sharpe_ratio or Decimal("-999"))
            reverse = True
        elif criteria == RankingCriteria.SORTINO_RATIO:
            key = lambda s: float(s.sortino_ratio or Decimal("-999"))
            reverse = True
        elif criteria == RankingCriteria.MAX_DRAWDOWN:
            # Less negative is better
            key = lambda s: float(s.max_drawdown)
            reverse = True
        elif criteria == RankingCriteria.WIN_RATE:
            key = lambda s: float(s.win_rate)
            reverse = True
        elif criteria == RankingCriteria.PROFIT_FACTOR:
            key = lambda s: float(s.profit_factor or Decimal("0"))
            reverse = True
        elif criteria == RankingCriteria.CALMAR_RATIO:
            key = lambda s: float(s.calmar_ratio or Decimal("-999"))
            reverse = True
        elif criteria == RankingCriteria.RISK_ADJUSTED_RETURN:
            key = lambda s: float(s.risk_adjusted_return)
            reverse = True
        else:
            key = lambda s: float(s.total_return)
            reverse = True

        sorted_strategies = sorted(strategies, key=key, reverse=reverse)
        return [s.strategy_id for s in sorted_strategies]

    def _calculate_pairwise_comparison(
        self,
        strategy_a: StrategyMetrics,
        strategy_b: StrategyMetrics,
    ) -> PairwiseComparison:
        """Calculate pairwise comparison between two strategies.

        Args:
            strategy_a: First strategy
            strategy_b: Second strategy

        Returns:
            Pairwise comparison result
        """
        return_diff = strategy_a.total_return - strategy_b.total_return

        sharpe_diff = None
        if strategy_a.sharpe_ratio is not None and strategy_b.sharpe_ratio is not None:
            sharpe_diff = strategy_a.sharpe_ratio - strategy_b.sharpe_ratio

        vol_diff = strategy_a.volatility - strategy_b.volatility

        # Determine winner based on Sharpe ratio (or return if no Sharpe)
        winner = None
        if sharpe_diff is not None:
            if sharpe_diff > Decimal("0.1"):  # Meaningful difference
                winner = strategy_a.strategy_id
            elif sharpe_diff < Decimal("-0.1"):
                winner = strategy_b.strategy_id
        elif return_diff > Decimal("0.05"):
            winner = strategy_a.strategy_id
        elif return_diff < Decimal("-0.05"):
            winner = strategy_b.strategy_id

        # Statistical significance test
        significant = False
        p_value = None
        ci = None

        # Perform t-test if we have return series
        if (len(strategy_a.returns_series) >= self.min_data_points and
            len(strategy_b.returns_series) >= self.min_data_points):
            try:
                t_stat, p_value, ci = self._welch_t_test(
                    [float(r) for r in strategy_a.returns_series],
                    [float(r) for r in strategy_b.returns_series],
                )
                significant = p_value < self.significance_level
            except Exception:
                pass

        notes = ""
        if significant:
            notes = f"Statistically significant difference (p={p_value:.4f})"
        elif p_value is not None:
            notes = f"Not statistically significant (p={p_value:.4f})"

        return PairwiseComparison(
            strategy_a_id=strategy_a.strategy_id,
            strategy_b_id=strategy_b.strategy_id,
            winner=winner,
            return_difference=return_diff.quantize(Decimal("0.0001")),
            sharpe_difference=sharpe_diff.quantize(Decimal("0.0001")) if sharpe_diff else None,
            volatility_difference=vol_diff.quantize(Decimal("0.0001")),
            statistically_significant=significant,
            p_value=p_value,
            confidence_interval=ci,
            notes=notes,
        )

    def _welch_t_test(
        self,
        sample_a: List[float],
        sample_b: List[float],
    ) -> Tuple[float, float, Tuple[float, float]]:
        """Perform Welch's t-test for unequal variances.

        Args:
            sample_a: First sample
            sample_b: Second sample

        Returns:
            Tuple of (t-statistic, p-value, 95% CI)
        """
        n_a = len(sample_a)
        n_b = len(sample_b)

        mean_a = statistics.mean(sample_a)
        mean_b = statistics.mean(sample_b)
        var_a = statistics.variance(sample_a) if n_a > 1 else 0
        var_b = statistics.variance(sample_b) if n_b > 1 else 0

        # Pooled standard error
        se = math.sqrt(var_a / n_a + var_b / n_b) if (var_a + var_b) > 0 else 0.0001

        # t-statistic
        t_stat = (mean_a - mean_b) / se

        # Degrees of freedom (Welch-Satterthwaite)
        if var_a > 0 or var_b > 0:
            num = (var_a / n_a + var_b / n_b) ** 2
            denom = (
                (var_a / n_a) ** 2 / (n_a - 1) +
                (var_b / n_b) ** 2 / (n_b - 1)
            )
            df = num / denom if denom > 0 else n_a + n_b - 2
        else:
            df = n_a + n_b - 2

        # Approximate p-value using normal distribution (good for large samples)
        # For more accuracy, would use t-distribution
        p_value = 2 * (1 - self._normal_cdf(abs(t_stat)))

        # 95% confidence interval
        z = 1.96  # For 95% CI
        ci_lower = (mean_a - mean_b) - z * se
        ci_upper = (mean_a - mean_b) + z * se

        return t_stat, p_value, (ci_lower, ci_upper)

    @staticmethod
    def _normal_cdf(x: float) -> float:
        """Approximate standard normal CDF.

        Args:
            x: Value

        Returns:
            Cumulative probability
        """
        return (1 + math.erf(x / math.sqrt(2))) / 2

    def _calculate_summary_statistics(
        self, strategies: List[StrategyMetrics]
    ) -> Dict[str, Any]:
        """Calculate summary statistics across all strategies.

        Args:
            strategies: List of strategies

        Returns:
            Dictionary of summary statistics
        """
        if not strategies:
            return {}

        returns = [float(s.total_return) for s in strategies]
        vols = [float(s.volatility) for s in strategies]
        sharpes = [
            float(s.sharpe_ratio) for s in strategies
            if s.sharpe_ratio is not None
        ]
        drawdowns = [float(s.max_drawdown) for s in strategies]

        summary = {
            "strategy_count": len(strategies),
            "return": {
                "mean": statistics.mean(returns),
                "median": statistics.median(returns),
                "min": min(returns),
                "max": max(returns),
                "stdev": statistics.stdev(returns) if len(returns) > 1 else 0,
            },
            "volatility": {
                "mean": statistics.mean(vols),
                "median": statistics.median(vols),
                "min": min(vols),
                "max": max(vols),
            },
            "max_drawdown": {
                "mean": statistics.mean(drawdowns),
                "worst": min(drawdowns),
                "best": max(drawdowns),
            },
        }

        if sharpes:
            summary["sharpe_ratio"] = {
                "mean": statistics.mean(sharpes),
                "median": statistics.median(sharpes),
                "min": min(sharpes),
                "max": max(sharpes),
            }

        return summary

    def _generate_recommendations(
        self,
        strategies: List[StrategyMetrics],
        rankings: Dict[RankingCriteria, List[str]],
    ) -> List[str]:
        """Generate analysis recommendations.

        Args:
            strategies: List of strategies
            rankings: Rankings by criteria

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if len(strategies) < 2:
            recommendations.append(
                "Add more strategies for meaningful comparison."
            )
            return recommendations

        # Consistency check
        best_return = rankings[RankingCriteria.TOTAL_RETURN][0]
        best_sharpe = rankings.get(RankingCriteria.SHARPE_RATIO, [None])[0]

        if best_return != best_sharpe and best_sharpe:
            recommendations.append(
                f"'{self._strategies[best_return].strategy_name}' has highest "
                f"return but '{self._strategies[best_sharpe].strategy_name}' "
                "has best risk-adjusted performance."
            )

        # Volatility warning
        for s in strategies:
            if float(s.volatility) > 0.30:  # 30% annual volatility
                recommendations.append(
                    f"'{s.strategy_name}' has high volatility "
                    f"({float(s.volatility)*100:.1f}%). Consider risk reduction."
                )

        # Drawdown warning
        for s in strategies:
            if float(s.max_drawdown) < -0.25:  # 25% drawdown
                recommendations.append(
                    f"'{s.strategy_name}' experienced significant drawdown "
                    f"({float(s.max_drawdown)*100:.1f}%). Review risk management."
                )

        # Insufficient trades warning
        for s in strategies:
            if s.total_trades < 30:
                recommendations.append(
                    f"'{s.strategy_name}' has limited trade history "
                    f"({s.total_trades} trades). Results may not be reliable."
                )

        return recommendations

    def compare(
        self,
        primary_criteria: RankingCriteria = RankingCriteria.SHARPE_RATIO,
    ) -> ComparisonResult:
        """Compare all added strategies.

        Args:
            primary_criteria: Primary criterion for determining best/worst

        Returns:
            Complete comparison result
        """
        strategies = list(self._strategies.values())

        if len(strategies) == 0:
            return ComparisonResult(
                status=ComparisonStatus.INSUFFICIENT_DATA,
                recommendations=["No strategies to compare."],
            )

        if len(strategies) == 1:
            return ComparisonResult(
                status=ComparisonStatus.INSUFFICIENT_DATA,
                strategies=strategies,
                best_overall=strategies[0].strategy_id,
                worst_overall=strategies[0].strategy_id,
                recommendations=["Only one strategy provided. Add more for comparison."],
            )

        # Calculate rankings for each criterion
        rankings = {}
        for criteria in RankingCriteria:
            rankings[criteria] = self._rank_by_criteria(criteria)

        # Determine best and worst overall
        primary_ranking = rankings[primary_criteria]
        best_overall = primary_ranking[0] if primary_ranking else None
        worst_overall = primary_ranking[-1] if primary_ranking else None

        # Calculate pairwise comparisons
        pairwise = []
        for i, s_a in enumerate(strategies):
            for s_b in strategies[i+1:]:
                comparison = self._calculate_pairwise_comparison(s_a, s_b)
                pairwise.append(comparison)

        # Calculate summary statistics
        summary = self._calculate_summary_statistics(strategies)

        # Generate recommendations
        recommendations = self._generate_recommendations(strategies, rankings)

        return ComparisonResult(
            status=ComparisonStatus.VALID,
            strategies=strategies,
            rankings=rankings,
            best_overall=best_overall,
            worst_overall=worst_overall,
            pairwise_comparisons=pairwise,
            summary_statistics=summary,
            recommendations=recommendations,
        )

    def compare_returns(
        self,
        strategy_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Compare return distributions.

        Args:
            strategy_ids: Specific strategies to compare (None = all)

        Returns:
            Return comparison data
        """
        if strategy_ids:
            strategies = [
                self._strategies[sid] for sid in strategy_ids
                if sid in self._strategies
            ]
        else:
            strategies = list(self._strategies.values())

        comparison = {
            "strategies": [s.strategy_name for s in strategies],
            "returns": {
                s.strategy_name: {
                    "total": str(s.total_return),
                    "annualized": str(s.annualized_return),
                    "best_trade": str(s.best_trade),
                    "worst_trade": str(s.worst_trade),
                    "avg_trade": str(s.avg_trade_return),
                }
                for s in strategies
            },
        }

        # Return series statistics if available
        for s in strategies:
            if s.returns_series:
                returns = [float(r) for r in s.returns_series]
                comparison["returns"][s.strategy_name]["series_stats"] = {
                    "count": len(returns),
                    "mean": statistics.mean(returns),
                    "median": statistics.median(returns),
                    "stdev": statistics.stdev(returns) if len(returns) > 1 else 0,
                    "skew": self._calculate_skew(returns),
                    "kurtosis": self._calculate_kurtosis(returns),
                }

        return comparison

    @staticmethod
    def _calculate_skew(data: List[float]) -> float:
        """Calculate skewness of a distribution.

        Args:
            data: List of values

        Returns:
            Skewness value
        """
        if len(data) < 3:
            return 0.0
        n = len(data)
        mean = statistics.mean(data)
        std = statistics.stdev(data)
        if std == 0:
            return 0.0
        return sum((x - mean) ** 3 for x in data) / ((n - 1) * std ** 3)

    @staticmethod
    def _calculate_kurtosis(data: List[float]) -> float:
        """Calculate excess kurtosis of a distribution.

        Args:
            data: List of values

        Returns:
            Excess kurtosis value
        """
        if len(data) < 4:
            return 0.0
        n = len(data)
        mean = statistics.mean(data)
        std = statistics.stdev(data)
        if std == 0:
            return 0.0
        return sum((x - mean) ** 4 for x in data) / ((n - 1) * std ** 4) - 3

    def get_ranking_table(self) -> List[Dict[str, Any]]:
        """Generate a ranking table for all strategies.

        Returns:
            List of strategy data with rankings
        """
        if not self._strategies:
            return []

        # Get all rankings
        rankings = {}
        for criteria in RankingCriteria:
            for rank, sid in enumerate(self._rank_by_criteria(criteria), 1):
                if sid not in rankings:
                    rankings[sid] = {}
                rankings[sid][criteria.value] = rank

        # Build table
        table = []
        for sid, strategy in self._strategies.items():
            row = {
                "strategy_id": sid,
                "strategy_name": strategy.strategy_name,
                "total_return": str(strategy.total_return),
                "sharpe_ratio": str(strategy.sharpe_ratio) if strategy.sharpe_ratio else "N/A",
                "max_drawdown": str(strategy.max_drawdown),
                "win_rate": str(strategy.win_rate),
                "rankings": rankings.get(sid, {}),
            }

            # Calculate average rank
            ranks = list(rankings.get(sid, {}).values())
            row["avg_rank"] = sum(ranks) / len(ranks) if ranks else 0

            table.append(row)

        # Sort by average rank
        table.sort(key=lambda x: x["avg_rank"])

        return table
