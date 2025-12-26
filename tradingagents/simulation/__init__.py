"""Simulation module for portfolio simulations and backtesting.

This module provides simulation capabilities including:
- Parallel scenario execution
- Parameter sweep analysis
- Strategy comparison
- Economic regime simulation

Issue #33: [SIM-32] Scenario runner - parallel portfolio simulations

Submodules:
    scenario_runner: Core scenario execution framework

Classes:
    Enums:
    - ExecutionMode: Parallel execution mode (sequential, threaded, process)
    - ScenarioStatus: Status of a scenario run

    Data Classes:
    - ScenarioConfig: Configuration for a simulation scenario
    - ScenarioResult: Result from a scenario simulation
    - RunnerProgress: Progress information for batch runs

    Main Classes:
    - ScenarioRunner: Runner for parallel portfolio simulations
    - ScenarioBatchBuilder: Builder for creating scenario batches

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

__all__ = [
    # Enums
    "ExecutionMode",
    "ScenarioStatus",
    # Data Classes
    "ScenarioConfig",
    "ScenarioResult",
    "RunnerProgress",
    # Main Classes
    "ScenarioRunner",
    "ScenarioBatchBuilder",
    # Protocols
    "ScenarioExecutor",
    # Types
    "ProgressCallback",
    # Utility Functions
    "aggregate_results",
]
