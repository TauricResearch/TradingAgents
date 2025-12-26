"""Tests for Strategy Comparator.

Issue #34: [SIM-33] Strategy comparator - performance comparison, stats

Tests cover:
- RankingCriteria and ComparisonStatus enums
- StrategyMetrics dataclass
- PairwiseComparison and ComparisonResult dataclasses
- StrategyComparator comparison logic
- Statistical significance testing
- Ranking and recommendations
- Edge cases
"""

import pytest
from datetime import date
from decimal import Decimal

from tradingagents.simulation.strategy_comparator import (
    RankingCriteria,
    ComparisonStatus,
    StrategyMetrics,
    PairwiseComparison,
    ComparisonResult,
    StrategyComparator,
)


# ==============================================================================
# RankingCriteria Enum Tests
# ==============================================================================


class TestRankingCriteria:
    """Tests for RankingCriteria enum."""

    def test_total_return_value(self):
        """Test TOTAL_RETURN criterion value."""
        assert RankingCriteria.TOTAL_RETURN.value == "total_return"

    def test_sharpe_ratio_value(self):
        """Test SHARPE_RATIO criterion value."""
        assert RankingCriteria.SHARPE_RATIO.value == "sharpe_ratio"

    def test_sortino_ratio_value(self):
        """Test SORTINO_RATIO criterion value."""
        assert RankingCriteria.SORTINO_RATIO.value == "sortino_ratio"

    def test_max_drawdown_value(self):
        """Test MAX_DRAWDOWN criterion value."""
        assert RankingCriteria.MAX_DRAWDOWN.value == "max_drawdown"

    def test_win_rate_value(self):
        """Test WIN_RATE criterion value."""
        assert RankingCriteria.WIN_RATE.value == "win_rate"

    def test_profit_factor_value(self):
        """Test PROFIT_FACTOR criterion value."""
        assert RankingCriteria.PROFIT_FACTOR.value == "profit_factor"

    def test_all_criteria_exist(self):
        """Test all expected criteria exist."""
        criteria = [c for c in RankingCriteria]
        assert len(criteria) == 8


# ==============================================================================
# ComparisonStatus Enum Tests
# ==============================================================================


class TestComparisonStatus:
    """Tests for ComparisonStatus enum."""

    def test_valid_value(self):
        """Test VALID status value."""
        assert ComparisonStatus.VALID.value == "valid"

    def test_insufficient_data_value(self):
        """Test INSUFFICIENT_DATA status value."""
        assert ComparisonStatus.INSUFFICIENT_DATA.value == "insufficient_data"

    def test_incomparable_value(self):
        """Test INCOMPARABLE status value."""
        assert ComparisonStatus.INCOMPARABLE.value == "incomparable"


# ==============================================================================
# StrategyMetrics Tests
# ==============================================================================


class TestStrategyMetrics:
    """Tests for StrategyMetrics dataclass."""

    def test_create_basic_metrics(self):
        """Test creating basic strategy metrics."""
        metrics = StrategyMetrics(
            strategy_id="strat1",
            strategy_name="Momentum",
            total_return=Decimal("0.25"),
            sharpe_ratio=Decimal("1.5"),
        )
        assert metrics.strategy_id == "strat1"
        assert metrics.strategy_name == "Momentum"
        assert metrics.total_return == Decimal("0.25")
        assert metrics.sharpe_ratio == Decimal("1.5")

    def test_risk_adjusted_return(self):
        """Test risk-adjusted return calculation."""
        metrics = StrategyMetrics(
            strategy_id="strat1",
            strategy_name="Test",
            total_return=Decimal("0.20"),
            volatility=Decimal("0.10"),
        )
        assert metrics.risk_adjusted_return == Decimal("2.0000")

    def test_risk_adjusted_return_zero_volatility(self):
        """Test risk-adjusted return with zero volatility."""
        metrics = StrategyMetrics(
            strategy_id="strat1",
            strategy_name="Test",
            total_return=Decimal("0.20"),
            volatility=Decimal("0"),
        )
        assert metrics.risk_adjusted_return == Decimal("0")

    def test_has_sufficient_data_trades(self):
        """Test sufficient data check with trades."""
        metrics = StrategyMetrics(
            strategy_id="strat1",
            strategy_name="Test",
            total_trades=15,
        )
        assert metrics.has_sufficient_data is True

    def test_has_sufficient_data_returns(self):
        """Test sufficient data check with return series."""
        metrics = StrategyMetrics(
            strategy_id="strat1",
            strategy_name="Test",
            total_trades=5,
            returns_series=[Decimal("0.01")] * 35,
        )
        assert metrics.has_sufficient_data is True

    def test_insufficient_data(self):
        """Test insufficient data detection."""
        metrics = StrategyMetrics(
            strategy_id="strat1",
            strategy_name="Test",
            total_trades=5,
            returns_series=[Decimal("0.01")] * 10,
        )
        assert metrics.has_sufficient_data is False


# ==============================================================================
# PairwiseComparison Tests
# ==============================================================================


class TestPairwiseComparison:
    """Tests for PairwiseComparison dataclass."""

    def test_create_comparison(self):
        """Test creating a pairwise comparison."""
        comparison = PairwiseComparison(
            strategy_a_id="strat1",
            strategy_b_id="strat2",
            winner="strat1",
            return_difference=Decimal("0.05"),
            sharpe_difference=Decimal("0.3"),
        )
        assert comparison.strategy_a_id == "strat1"
        assert comparison.strategy_b_id == "strat2"
        assert comparison.winner == "strat1"
        assert comparison.return_difference == Decimal("0.05")

    def test_no_winner(self):
        """Test comparison with no clear winner."""
        comparison = PairwiseComparison(
            strategy_a_id="strat1",
            strategy_b_id="strat2",
            winner=None,
            return_difference=Decimal("0.01"),
        )
        assert comparison.winner is None


# ==============================================================================
# ComparisonResult Tests
# ==============================================================================


class TestComparisonResult:
    """Tests for ComparisonResult dataclass."""

    def test_strategy_count(self):
        """Test strategy count property."""
        result = ComparisonResult(
            status=ComparisonStatus.VALID,
            strategies=[
                StrategyMetrics(strategy_id="s1", strategy_name="S1"),
                StrategyMetrics(strategy_id="s2", strategy_name="S2"),
            ],
        )
        assert result.strategy_count == 2

    def test_empty_result(self):
        """Test empty comparison result."""
        result = ComparisonResult(status=ComparisonStatus.INSUFFICIENT_DATA)
        assert result.strategy_count == 0
        assert result.best_overall is None


# ==============================================================================
# StrategyComparator Tests - Basic Operations
# ==============================================================================


class TestStrategyComparatorBasic:
    """Tests for StrategyComparator basic operations."""

    def test_add_strategy(self):
        """Test adding a strategy."""
        comparator = StrategyComparator()
        strategy = StrategyMetrics(
            strategy_id="strat1",
            strategy_name="Test",
            total_return=Decimal("0.20"),
        )
        comparator.add_strategy(strategy)
        assert comparator.get_strategy("strat1") is not None

    def test_remove_strategy(self):
        """Test removing a strategy."""
        comparator = StrategyComparator()
        strategy = StrategyMetrics(strategy_id="strat1", strategy_name="Test")
        comparator.add_strategy(strategy)
        assert comparator.remove_strategy("strat1") is True
        assert comparator.get_strategy("strat1") is None

    def test_remove_nonexistent_strategy(self):
        """Test removing a nonexistent strategy."""
        comparator = StrategyComparator()
        assert comparator.remove_strategy("nonexistent") is False

    def test_get_all_strategies(self):
        """Test getting all strategies."""
        comparator = StrategyComparator()
        comparator.add_strategy(StrategyMetrics(strategy_id="s1", strategy_name="S1"))
        comparator.add_strategy(StrategyMetrics(strategy_id="s2", strategy_name="S2"))
        strategies = comparator.get_all_strategies()
        assert len(strategies) == 2

    def test_clear(self):
        """Test clearing all strategies."""
        comparator = StrategyComparator()
        comparator.add_strategy(StrategyMetrics(strategy_id="s1", strategy_name="S1"))
        comparator.clear()
        assert len(comparator.get_all_strategies()) == 0


# ==============================================================================
# StrategyComparator Tests - Comparison
# ==============================================================================


class TestStrategyComparatorComparison:
    """Tests for StrategyComparator comparison logic."""

    def test_compare_empty(self):
        """Test comparing with no strategies."""
        comparator = StrategyComparator()
        result = comparator.compare()
        assert result.status == ComparisonStatus.INSUFFICIENT_DATA

    def test_compare_single_strategy(self):
        """Test comparing with single strategy."""
        comparator = StrategyComparator()
        comparator.add_strategy(StrategyMetrics(
            strategy_id="strat1",
            strategy_name="Test",
            total_return=Decimal("0.20"),
        ))
        result = comparator.compare()
        assert result.status == ComparisonStatus.INSUFFICIENT_DATA
        assert result.best_overall == "strat1"
        assert result.worst_overall == "strat1"

    def test_compare_two_strategies(self):
        """Test comparing two strategies."""
        comparator = StrategyComparator()
        comparator.add_strategy(StrategyMetrics(
            strategy_id="strat1",
            strategy_name="Momentum",
            total_return=Decimal("0.25"),
            sharpe_ratio=Decimal("1.5"),
            volatility=Decimal("0.15"),
            max_drawdown=Decimal("-0.12"),
        ))
        comparator.add_strategy(StrategyMetrics(
            strategy_id="strat2",
            strategy_name="Value",
            total_return=Decimal("0.18"),
            sharpe_ratio=Decimal("1.2"),
            volatility=Decimal("0.12"),
            max_drawdown=Decimal("-0.08"),
        ))
        result = comparator.compare()
        assert result.status == ComparisonStatus.VALID
        assert result.strategy_count == 2
        assert len(result.pairwise_comparisons) == 1

    def test_compare_by_sharpe(self):
        """Test comparison by Sharpe ratio."""
        comparator = StrategyComparator()
        comparator.add_strategy(StrategyMetrics(
            strategy_id="high_sharpe",
            strategy_name="High Sharpe",
            total_return=Decimal("0.15"),
            sharpe_ratio=Decimal("2.0"),
        ))
        comparator.add_strategy(StrategyMetrics(
            strategy_id="low_sharpe",
            strategy_name="Low Sharpe",
            total_return=Decimal("0.25"),
            sharpe_ratio=Decimal("1.0"),
        ))
        result = comparator.compare(primary_criteria=RankingCriteria.SHARPE_RATIO)
        assert result.best_overall == "high_sharpe"

    def test_compare_by_return(self):
        """Test comparison by total return."""
        comparator = StrategyComparator()
        comparator.add_strategy(StrategyMetrics(
            strategy_id="high_return",
            strategy_name="High Return",
            total_return=Decimal("0.30"),
            sharpe_ratio=Decimal("1.0"),
        ))
        comparator.add_strategy(StrategyMetrics(
            strategy_id="low_return",
            strategy_name="Low Return",
            total_return=Decimal("0.10"),
            sharpe_ratio=Decimal("2.0"),
        ))
        result = comparator.compare(primary_criteria=RankingCriteria.TOTAL_RETURN)
        assert result.best_overall == "high_return"

    def test_rankings_all_criteria(self):
        """Test rankings for all criteria."""
        comparator = StrategyComparator()
        comparator.add_strategy(StrategyMetrics(
            strategy_id="s1",
            strategy_name="Strategy 1",
            total_return=Decimal("0.20"),
            sharpe_ratio=Decimal("1.5"),
            sortino_ratio=Decimal("2.0"),
            max_drawdown=Decimal("-0.10"),
            win_rate=Decimal("0.55"),
            profit_factor=Decimal("1.5"),
            calmar_ratio=Decimal("2.0"),
            volatility=Decimal("0.10"),
        ))
        comparator.add_strategy(StrategyMetrics(
            strategy_id="s2",
            strategy_name="Strategy 2",
            total_return=Decimal("0.15"),
            sharpe_ratio=Decimal("1.8"),
            sortino_ratio=Decimal("2.5"),
            max_drawdown=Decimal("-0.08"),
            win_rate=Decimal("0.60"),
            profit_factor=Decimal("1.8"),
            calmar_ratio=Decimal("1.8"),
            volatility=Decimal("0.08"),
        ))
        result = comparator.compare()
        assert result.status == ComparisonStatus.VALID
        assert len(result.rankings) == 8  # All criteria


# ==============================================================================
# StrategyComparator Tests - Statistical Testing
# ==============================================================================


class TestStrategyComparatorStatistics:
    """Tests for statistical significance testing."""

    def test_pairwise_with_return_series(self):
        """Test pairwise comparison with return series."""
        comparator = StrategyComparator()
        # Strategy with higher mean returns
        high_returns = [Decimal("0.02")] * 50
        low_returns = [Decimal("0.01")] * 50

        comparator.add_strategy(StrategyMetrics(
            strategy_id="high",
            strategy_name="High Returns",
            total_return=Decimal("0.50"),
            returns_series=high_returns,
        ))
        comparator.add_strategy(StrategyMetrics(
            strategy_id="low",
            strategy_name="Low Returns",
            total_return=Decimal("0.25"),
            returns_series=low_returns,
        ))
        result = comparator.compare()
        assert len(result.pairwise_comparisons) == 1
        comparison = result.pairwise_comparisons[0]
        # With identical values, should be highly significant
        assert comparison.p_value is not None

    def test_pairwise_insufficient_data(self):
        """Test pairwise comparison with insufficient data."""
        comparator = StrategyComparator()
        comparator.add_strategy(StrategyMetrics(
            strategy_id="s1",
            strategy_name="S1",
            total_return=Decimal("0.20"),
            returns_series=[Decimal("0.01")] * 10,  # Not enough
        ))
        comparator.add_strategy(StrategyMetrics(
            strategy_id="s2",
            strategy_name="S2",
            total_return=Decimal("0.15"),
            returns_series=[Decimal("0.01")] * 10,
        ))
        result = comparator.compare()
        comparison = result.pairwise_comparisons[0]
        # With insufficient data, no statistical test performed
        assert comparison.p_value is None


# ==============================================================================
# StrategyComparator Tests - Summary Statistics
# ==============================================================================


class TestStrategyComparatorSummary:
    """Tests for summary statistics."""

    def test_summary_statistics(self):
        """Test summary statistics calculation."""
        comparator = StrategyComparator()
        comparator.add_strategy(StrategyMetrics(
            strategy_id="s1",
            strategy_name="S1",
            total_return=Decimal("0.20"),
            volatility=Decimal("0.15"),
            max_drawdown=Decimal("-0.12"),
            sharpe_ratio=Decimal("1.5"),
        ))
        comparator.add_strategy(StrategyMetrics(
            strategy_id="s2",
            strategy_name="S2",
            total_return=Decimal("0.10"),
            volatility=Decimal("0.10"),
            max_drawdown=Decimal("-0.08"),
            sharpe_ratio=Decimal("1.2"),
        ))
        comparator.add_strategy(StrategyMetrics(
            strategy_id="s3",
            strategy_name="S3",
            total_return=Decimal("0.30"),
            volatility=Decimal("0.20"),
            max_drawdown=Decimal("-0.15"),
            sharpe_ratio=Decimal("1.8"),
        ))

        result = comparator.compare()
        summary = result.summary_statistics

        assert summary["strategy_count"] == 3
        assert "return" in summary
        assert "volatility" in summary
        assert "max_drawdown" in summary
        assert "sharpe_ratio" in summary

        # Return stats
        assert summary["return"]["min"] == pytest.approx(0.10)
        assert summary["return"]["max"] == pytest.approx(0.30)


# ==============================================================================
# StrategyComparator Tests - Recommendations
# ==============================================================================


class TestStrategyComparatorRecommendations:
    """Tests for recommendation generation."""

    def test_high_volatility_warning(self):
        """Test high volatility warning."""
        comparator = StrategyComparator()
        comparator.add_strategy(StrategyMetrics(
            strategy_id="high_vol",
            strategy_name="High Vol Strategy",
            total_return=Decimal("0.40"),
            volatility=Decimal("0.35"),  # Very high
            sharpe_ratio=Decimal("1.2"),
        ))
        comparator.add_strategy(StrategyMetrics(
            strategy_id="low_vol",
            strategy_name="Low Vol Strategy",
            total_return=Decimal("0.15"),
            volatility=Decimal("0.08"),
            sharpe_ratio=Decimal("1.8"),
        ))
        result = comparator.compare()
        vol_warnings = [r for r in result.recommendations if "volatility" in r.lower()]
        assert len(vol_warnings) >= 1

    def test_drawdown_warning(self):
        """Test significant drawdown warning."""
        comparator = StrategyComparator()
        comparator.add_strategy(StrategyMetrics(
            strategy_id="big_dd",
            strategy_name="Big Drawdown",
            total_return=Decimal("0.30"),
            max_drawdown=Decimal("-0.35"),  # Very large
            sharpe_ratio=Decimal("1.0"),
        ))
        comparator.add_strategy(StrategyMetrics(
            strategy_id="small_dd",
            strategy_name="Small Drawdown",
            total_return=Decimal("0.15"),
            max_drawdown=Decimal("-0.08"),
            sharpe_ratio=Decimal("1.5"),
        ))
        result = comparator.compare()
        dd_warnings = [r for r in result.recommendations if "drawdown" in r.lower()]
        assert len(dd_warnings) >= 1

    def test_low_trades_warning(self):
        """Test limited trade history warning."""
        comparator = StrategyComparator()
        comparator.add_strategy(StrategyMetrics(
            strategy_id="few_trades",
            strategy_name="Few Trades",
            total_return=Decimal("0.50"),
            total_trades=15,  # Low
            sharpe_ratio=Decimal("2.0"),
        ))
        comparator.add_strategy(StrategyMetrics(
            strategy_id="many_trades",
            strategy_name="Many Trades",
            total_return=Decimal("0.20"),
            total_trades=500,
            sharpe_ratio=Decimal("1.5"),
        ))
        result = comparator.compare()
        trade_warnings = [r for r in result.recommendations if "trade" in r.lower()]
        assert len(trade_warnings) >= 1


# ==============================================================================
# StrategyComparator Tests - Compare Returns
# ==============================================================================


class TestStrategyComparatorReturns:
    """Tests for return comparison."""

    def test_compare_returns_basic(self):
        """Test basic return comparison."""
        comparator = StrategyComparator()
        comparator.add_strategy(StrategyMetrics(
            strategy_id="s1",
            strategy_name="Strategy 1",
            total_return=Decimal("0.25"),
            annualized_return=Decimal("0.20"),
            best_trade=Decimal("0.05"),
            worst_trade=Decimal("-0.03"),
            avg_trade_return=Decimal("0.01"),
        ))
        comparator.add_strategy(StrategyMetrics(
            strategy_id="s2",
            strategy_name="Strategy 2",
            total_return=Decimal("0.18"),
            annualized_return=Decimal("0.15"),
            best_trade=Decimal("0.03"),
            worst_trade=Decimal("-0.02"),
            avg_trade_return=Decimal("0.008"),
        ))

        comparison = comparator.compare_returns()
        assert "strategies" in comparison
        assert len(comparison["strategies"]) == 2
        assert "returns" in comparison

    def test_compare_returns_with_series(self):
        """Test return comparison with return series."""
        comparator = StrategyComparator()
        returns = [Decimal("0.01"), Decimal("0.02"), Decimal("-0.01"), Decimal("0.015")]
        returns_extended = returns * 10  # 40 values

        comparator.add_strategy(StrategyMetrics(
            strategy_id="s1",
            strategy_name="Strategy 1",
            total_return=Decimal("0.25"),
            returns_series=returns_extended,
        ))

        comparison = comparator.compare_returns()
        assert "series_stats" in comparison["returns"]["Strategy 1"]
        stats = comparison["returns"]["Strategy 1"]["series_stats"]
        assert stats["count"] == 40


# ==============================================================================
# StrategyComparator Tests - Ranking Table
# ==============================================================================


class TestStrategyComparatorRankingTable:
    """Tests for ranking table generation."""

    def test_get_ranking_table_empty(self):
        """Test ranking table with no strategies."""
        comparator = StrategyComparator()
        table = comparator.get_ranking_table()
        assert table == []

    def test_get_ranking_table(self):
        """Test ranking table generation."""
        comparator = StrategyComparator()
        comparator.add_strategy(StrategyMetrics(
            strategy_id="s1",
            strategy_name="Best",
            total_return=Decimal("0.30"),
            sharpe_ratio=Decimal("2.0"),
            max_drawdown=Decimal("-0.05"),
            win_rate=Decimal("0.65"),
        ))
        comparator.add_strategy(StrategyMetrics(
            strategy_id="s2",
            strategy_name="Worst",
            total_return=Decimal("0.10"),
            sharpe_ratio=Decimal("0.8"),
            max_drawdown=Decimal("-0.20"),
            win_rate=Decimal("0.45"),
        ))
        comparator.add_strategy(StrategyMetrics(
            strategy_id="s3",
            strategy_name="Middle",
            total_return=Decimal("0.20"),
            sharpe_ratio=Decimal("1.5"),
            max_drawdown=Decimal("-0.10"),
            win_rate=Decimal("0.55"),
        ))

        table = comparator.get_ranking_table()
        assert len(table) == 3

        # Table should be sorted by average rank
        assert "avg_rank" in table[0]
        assert "rankings" in table[0]

        # First should be the best overall
        assert table[0]["strategy_name"] == "Best"


# ==============================================================================
# Module Import Tests
# ==============================================================================


class TestModuleImports:
    """Tests for module imports."""

    def test_import_from_simulation_module(self):
        """Test importing from simulation module."""
        from tradingagents.simulation import (
            RankingCriteria,
            ComparisonStatus,
            StrategyMetrics,
            PairwiseComparison,
            ComparisonResult,
            StrategyComparator,
        )
        assert RankingCriteria is not None
        assert ComparisonStatus is not None
        assert StrategyMetrics is not None
        assert PairwiseComparison is not None
        assert ComparisonResult is not None
        assert StrategyComparator is not None


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestStrategyComparatorIntegration:
    """Integration tests for StrategyComparator."""

    def test_full_comparison_workflow(self):
        """Test complete comparison workflow."""
        comparator = StrategyComparator()

        # Add multiple strategies with various characteristics
        strategies = [
            StrategyMetrics(
                strategy_id="momentum",
                strategy_name="Momentum",
                total_return=Decimal("0.28"),
                annualized_return=Decimal("0.22"),
                volatility=Decimal("0.18"),
                sharpe_ratio=Decimal("1.55"),
                sortino_ratio=Decimal("2.10"),
                max_drawdown=Decimal("-0.14"),
                calmar_ratio=Decimal("1.57"),
                win_rate=Decimal("0.52"),
                profit_factor=Decimal("1.45"),
                total_trades=150,
                avg_trade_return=Decimal("0.0018"),
            ),
            StrategyMetrics(
                strategy_id="value",
                strategy_name="Value",
                total_return=Decimal("0.18"),
                annualized_return=Decimal("0.15"),
                volatility=Decimal("0.12"),
                sharpe_ratio=Decimal("1.25"),
                sortino_ratio=Decimal("1.60"),
                max_drawdown=Decimal("-0.10"),
                calmar_ratio=Decimal("1.50"),
                win_rate=Decimal("0.58"),
                profit_factor=Decimal("1.65"),
                total_trades=80,
                avg_trade_return=Decimal("0.0022"),
            ),
            StrategyMetrics(
                strategy_id="growth",
                strategy_name="Growth",
                total_return=Decimal("0.35"),
                annualized_return=Decimal("0.28"),
                volatility=Decimal("0.25"),
                sharpe_ratio=Decimal("1.40"),
                sortino_ratio=Decimal("1.80"),
                max_drawdown=Decimal("-0.22"),
                calmar_ratio=Decimal("1.27"),
                win_rate=Decimal("0.48"),
                profit_factor=Decimal("1.35"),
                total_trades=200,
                avg_trade_return=Decimal("0.0017"),
            ),
        ]

        for s in strategies:
            comparator.add_strategy(s)

        # Compare by Sharpe ratio
        result = comparator.compare(primary_criteria=RankingCriteria.SHARPE_RATIO)

        # Verify result
        assert result.status == ComparisonStatus.VALID
        assert result.strategy_count == 3
        assert result.best_overall == "momentum"  # Highest Sharpe

        # Verify rankings
        assert "momentum" in result.rankings[RankingCriteria.SHARPE_RATIO][:1]
        assert "growth" in result.rankings[RankingCriteria.TOTAL_RETURN][:1]

        # Verify pairwise comparisons
        assert len(result.pairwise_comparisons) == 3  # 3 choose 2

        # Verify summary statistics
        assert result.summary_statistics["strategy_count"] == 3

        # Get ranking table
        table = comparator.get_ranking_table()
        assert len(table) == 3
