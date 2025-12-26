"""Simulation module for portfolio simulations and backtesting.

This module provides simulation capabilities including:
- Parallel scenario execution
- Parameter sweep analysis
- Strategy comparison
- Economic regime simulation

Issue #33: [SIM-32] Scenario runner - parallel portfolio simulations
Issue #34: [SIM-33] Strategy comparator - performance comparison, stats
Issue #35: [SIM-34] Economic conditions - regime tagging, evaluation

Submodules:
    scenario_runner: Core scenario execution framework
    strategy_comparator: Strategy comparison and statistical analysis
    economic_conditions: Economic regime tagging and evaluation

Classes:
    Enums:
    - ExecutionMode: Parallel execution mode (sequential, threaded, process)
    - ScenarioStatus: Status of a scenario run
    - RankingCriteria: Criteria for ranking strategies
    - ComparisonStatus: Status of strategy comparison
    - MarketRegime: Bull/bear/sideways market classification
    - VolatilityRegime: Low/normal/elevated/high volatility
    - TrendStrength: Strength of detected trend
    - RegimeConfidence: Confidence in regime classification

    Data Classes:
    - ScenarioConfig: Configuration for a simulation scenario
    - ScenarioResult: Result from a scenario simulation
    - RunnerProgress: Progress information for batch runs
    - StrategyMetrics: Performance metrics for a strategy
    - PairwiseComparison: Comparison between two strategies
    - ComparisonResult: Complete result of strategy comparison
    - RegimeTag: Tag for a period with regime information
    - RegimePerformance: Performance summary for a regime
    - RegimeTransition: Record of regime transitions
    - RegimeRecommendation: Strategy recommendations per regime
    - RegimeEvaluationResult: Complete regime evaluation result

    Main Classes:
    - ScenarioRunner: Runner for parallel portfolio simulations
    - ScenarioBatchBuilder: Builder for creating scenario batches
    - StrategyComparator: Compares multiple trading strategies
    - RegimeDetector: Detects market and volatility regimes
    - RegimeEvaluator: Evaluates strategy performance by regime

    Protocols:
    - ScenarioExecutor: Protocol for scenario execution functions

    Utility Functions:
    - aggregate_results: Aggregate results from multiple scenarios

Example:
    >>> from tradingagents.simulation import (
    ...     ScenarioRunner,
    ...     ScenarioConfig,
    ...     ScenarioResult,
    ...     ScenarioStatus,
    ...     ExecutionMode,
    ... )
    >>> from datetime import datetime
    >>> from decimal import Decimal
    >>>
    >>> def simple_executor(config: ScenarioConfig) -> ScenarioResult:
    ...     return ScenarioResult(
    ...         scenario_id=config.scenario_id,
    ...         scenario_name=config.name,
    ...         status=ScenarioStatus.COMPLETED,
    ...         start_time=datetime.now(),
    ...         final_value=config.initial_capital * Decimal("1.1"),
    ...         total_return=Decimal("0.1"),
    ...     )
    >>>
    >>> runner = ScenarioRunner(executor=simple_executor)
    >>> scenarios = [ScenarioConfig(name="Test1"), ScenarioConfig(name="Test2")]
    >>> results = runner.run(scenarios)
"""

from .scenario_runner import (
    # Enums
    ExecutionMode,
    ScenarioStatus,
    # Data Classes
    ScenarioConfig,
    ScenarioResult,
    RunnerProgress,
    # Main Classes
    ScenarioRunner,
    ScenarioBatchBuilder,
    # Protocols
    ScenarioExecutor,
    # Types
    ProgressCallback,
    # Utility Functions
    aggregate_results,
)

from .strategy_comparator import (
    # Enums
    RankingCriteria,
    ComparisonStatus,
    # Data Classes
    StrategyMetrics,
    PairwiseComparison,
    ComparisonResult,
    # Main Class
    StrategyComparator,
)

from .economic_conditions import (
    # Enums
    MarketRegime,
    VolatilityRegime,
    TrendStrength,
    RegimeConfidence,
    # Data Classes
    RegimeTag,
    RegimePerformance,
    RegimeTransition,
    RegimeRecommendation,
    RegimeEvaluationResult,
    # Main Classes
    RegimeDetector,
    RegimeEvaluator,
)

__all__ = [
    # Scenario Runner Enums
    "ExecutionMode",
    "ScenarioStatus",
    # Scenario Runner Data Classes
    "ScenarioConfig",
    "ScenarioResult",
    "RunnerProgress",
    # Scenario Runner Main Classes
    "ScenarioRunner",
    "ScenarioBatchBuilder",
    # Scenario Runner Protocols
    "ScenarioExecutor",
    # Scenario Runner Types
    "ProgressCallback",
    # Scenario Runner Utility Functions
    "aggregate_results",
    # Strategy Comparator Enums
    "RankingCriteria",
    "ComparisonStatus",
    # Strategy Comparator Data Classes
    "StrategyMetrics",
    "PairwiseComparison",
    "ComparisonResult",
    # Strategy Comparator Main Class
    "StrategyComparator",
    # Economic Conditions Enums
    "MarketRegime",
    "VolatilityRegime",
    "TrendStrength",
    "RegimeConfidence",
    # Economic Conditions Data Classes
    "RegimeTag",
    "RegimePerformance",
    "RegimeTransition",
    "RegimeRecommendation",
    "RegimeEvaluationResult",
    # Economic Conditions Main Classes
    "RegimeDetector",
    "RegimeEvaluator",
]
