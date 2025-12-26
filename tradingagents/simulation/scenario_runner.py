"""Scenario Runner for parallel portfolio simulations.

This module provides scenario-based simulation capabilities including:
- Parallel execution of multiple portfolio scenarios
- Configurable simulation parameters
- Progress tracking and callbacks
- Result aggregation and comparison

Issue #33: [SIM-32] Scenario runner - parallel portfolio simulations

Design Principles:
    - Thread-safe parallel execution
    - Configurable concurrency limits
    - Memory-efficient result handling
    - Progress reporting callbacks
"""

from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, Union
import copy
import threading
import time
import uuid


class ExecutionMode(Enum):
    """Mode of parallel execution."""
    SEQUENTIAL = "sequential"    # Run scenarios one at a time
    THREADED = "threaded"        # Use thread pool (for I/O bound)
    PROCESS = "process"          # Use process pool (for CPU bound)


class ScenarioStatus(Enum):
    """Status of a scenario run."""
    PENDING = "pending"          # Not yet started
    RUNNING = "running"          # Currently executing
    COMPLETED = "completed"      # Finished successfully
    FAILED = "failed"            # Finished with error
    CANCELLED = "cancelled"      # Cancelled before completion


@dataclass
class ScenarioConfig:
    """Configuration for a simulation scenario.

    Attributes:
        scenario_id: Unique identifier for the scenario
        name: Human-readable name
        start_date: Simulation start date
        end_date: Simulation end date
        initial_capital: Starting capital
        symbols: List of symbols to include
        strategy_params: Strategy-specific parameters
        risk_params: Risk management parameters
        metadata: Additional scenario data
    """
    scenario_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    initial_capital: Decimal = Decimal("100000")
    symbols: List[str] = field(default_factory=list)
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    risk_params: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Set default name if not provided."""
        if not self.name:
            self.name = f"Scenario-{self.scenario_id[:8]}"


@dataclass
class ScenarioResult:
    """Result from a scenario simulation.

    Attributes:
        scenario_id: ID of the scenario that was run
        scenario_name: Name of the scenario
        status: Final status of the run
        start_time: When simulation started
        end_time: When simulation ended
        duration_seconds: Total runtime in seconds
        final_value: Final portfolio value
        total_return: Total return as decimal (0.10 = 10%)
        trades_executed: Number of trades made
        max_drawdown: Maximum drawdown experienced
        sharpe_ratio: Sharpe ratio if calculable
        error_message: Error message if failed
        portfolio_history: Time series of portfolio values
        trade_history: List of trades executed
        metrics: Additional performance metrics
        metadata: Additional result data
    """
    scenario_id: str
    scenario_name: str
    status: ScenarioStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    final_value: Decimal = Decimal("0")
    total_return: Decimal = Decimal("0")
    trades_executed: int = 0
    max_drawdown: Decimal = Decimal("0")
    sharpe_ratio: Optional[Decimal] = None
    error_message: Optional[str] = None
    portfolio_history: List[Tuple[date, Decimal]] = field(default_factory=list)
    trade_history: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_successful(self) -> bool:
        """Check if scenario completed successfully."""
        return self.status == ScenarioStatus.COMPLETED

    @property
    def is_finished(self) -> bool:
        """Check if scenario has finished (success or failure)."""
        return self.status in (
            ScenarioStatus.COMPLETED,
            ScenarioStatus.FAILED,
            ScenarioStatus.CANCELLED,
        )


class ScenarioExecutor(Protocol):
    """Protocol for scenario execution functions.

    Implementations should take a ScenarioConfig and return a ScenarioResult.
    """

    def __call__(self, config: ScenarioConfig) -> ScenarioResult:
        """Execute a scenario and return results."""
        ...


@dataclass
class RunnerProgress:
    """Progress information for a scenario run batch.

    Attributes:
        total_scenarios: Total number of scenarios
        completed: Number of completed scenarios
        failed: Number of failed scenarios
        running: Number of currently running scenarios
        pending: Number of pending scenarios
        start_time: When the batch started
        estimated_remaining_seconds: Estimated time remaining
    """
    total_scenarios: int
    completed: int = 0
    failed: int = 0
    running: int = 0
    pending: int = 0
    start_time: Optional[datetime] = None
    estimated_remaining_seconds: Optional[float] = None

    @property
    def progress_percent(self) -> float:
        """Calculate completion percentage."""
        if self.total_scenarios == 0:
            return 100.0
        return (self.completed + self.failed) / self.total_scenarios * 100

    @property
    def is_complete(self) -> bool:
        """Check if all scenarios are finished."""
        return (self.completed + self.failed) >= self.total_scenarios


ProgressCallback = Callable[[RunnerProgress], None]


class ScenarioRunner:
    """Runner for parallel portfolio simulations.

    Executes multiple simulation scenarios in parallel using configurable
    execution modes (sequential, threaded, or process-based).

    Example:
        >>> def simulate(config: ScenarioConfig) -> ScenarioResult:
        ...     # Your simulation logic
        ...     return ScenarioResult(
        ...         scenario_id=config.scenario_id,
        ...         scenario_name=config.name,
        ...         status=ScenarioStatus.COMPLETED,
        ...         start_time=datetime.now(),
        ...     )
        ...
        >>> runner = ScenarioRunner(executor=simulate)
        >>> scenarios = [
        ...     ScenarioConfig(name="Bull Market", strategy_params={"leverage": 1.5}),
        ...     ScenarioConfig(name="Bear Market", strategy_params={"leverage": 0.5}),
        ... ]
        >>> results = runner.run(scenarios)
        >>> print(f"Completed: {len([r for r in results if r.is_successful])}")
    """

    def __init__(
        self,
        executor: ScenarioExecutor,
        mode: ExecutionMode = ExecutionMode.THREADED,
        max_workers: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ):
        """Initialize the scenario runner.

        Args:
            executor: Function that executes a single scenario
            mode: Execution mode (sequential, threaded, process)
            max_workers: Maximum number of parallel workers (None = auto)
            timeout_seconds: Timeout per scenario (None = no timeout)
        """
        self.executor = executor
        self.mode = mode
        self.max_workers = max_workers
        self.timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        self._cancelled = False
        self._progress = RunnerProgress(total_scenarios=0)
        self._progress_callbacks: List[ProgressCallback] = []

    def add_progress_callback(self, callback: ProgressCallback) -> None:
        """Add a callback for progress updates.

        Args:
            callback: Function to call with progress updates
        """
        with self._lock:
            self._progress_callbacks.append(callback)

    def remove_progress_callback(self, callback: ProgressCallback) -> None:
        """Remove a progress callback.

        Args:
            callback: Callback to remove
        """
        with self._lock:
            if callback in self._progress_callbacks:
                self._progress_callbacks.remove(callback)

    def _notify_progress(self) -> None:
        """Notify all registered progress callbacks."""
        with self._lock:
            callbacks = self._progress_callbacks.copy()
            progress = copy.copy(self._progress)

        for callback in callbacks:
            try:
                callback(progress)
            except Exception:
                pass  # Don't let callback errors affect execution

    def _update_progress(
        self,
        completed_delta: int = 0,
        failed_delta: int = 0,
        running_delta: int = 0,
        pending_delta: int = 0,
    ) -> None:
        """Update progress counters thread-safely."""
        with self._lock:
            self._progress.completed += completed_delta
            self._progress.failed += failed_delta
            self._progress.running += running_delta
            self._progress.pending += pending_delta

            # Estimate remaining time
            if self._progress.start_time and self._progress.completed > 0:
                elapsed = (datetime.now() - self._progress.start_time).total_seconds()
                avg_time = elapsed / self._progress.completed
                remaining = self._progress.pending + self._progress.running
                self._progress.estimated_remaining_seconds = avg_time * remaining

        self._notify_progress()

    def _execute_scenario(self, config: ScenarioConfig) -> ScenarioResult:
        """Execute a single scenario with error handling.

        Args:
            config: Scenario configuration

        Returns:
            ScenarioResult with outcome
        """
        start_time = datetime.now()

        # Check if cancelled
        if self._cancelled:
            return ScenarioResult(
                scenario_id=config.scenario_id,
                scenario_name=config.name,
                status=ScenarioStatus.CANCELLED,
                start_time=start_time,
                end_time=datetime.now(),
            )

        self._update_progress(running_delta=1, pending_delta=-1)

        try:
            result = self.executor(config)
            result.end_time = datetime.now()
            result.duration_seconds = (result.end_time - start_time).total_seconds()

            if result.status == ScenarioStatus.COMPLETED:
                self._update_progress(completed_delta=1, running_delta=-1)
            else:
                self._update_progress(failed_delta=1, running_delta=-1)

            return result

        except Exception as e:
            end_time = datetime.now()
            self._update_progress(failed_delta=1, running_delta=-1)
            return ScenarioResult(
                scenario_id=config.scenario_id,
                scenario_name=config.name,
                status=ScenarioStatus.FAILED,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=(end_time - start_time).total_seconds(),
                error_message=str(e),
            )

    def run(
        self,
        scenarios: List[ScenarioConfig],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[ScenarioResult]:
        """Run multiple scenarios.

        Args:
            scenarios: List of scenario configurations to run
            progress_callback: Optional callback for progress updates

        Returns:
            List of results in the same order as input scenarios
        """
        if not scenarios:
            return []

        # Reset state
        self._cancelled = False
        self._progress = RunnerProgress(
            total_scenarios=len(scenarios),
            pending=len(scenarios),
            start_time=datetime.now(),
        )

        if progress_callback:
            self.add_progress_callback(progress_callback)

        try:
            if self.mode == ExecutionMode.SEQUENTIAL:
                results = self._run_sequential(scenarios)
            elif self.mode == ExecutionMode.THREADED:
                results = self._run_parallel(scenarios, ThreadPoolExecutor)
            elif self.mode == ExecutionMode.PROCESS:
                results = self._run_parallel(scenarios, ProcessPoolExecutor)
            else:
                raise ValueError(f"Unknown execution mode: {self.mode}")

            return results

        finally:
            if progress_callback:
                self.remove_progress_callback(progress_callback)

    def _run_sequential(
        self, scenarios: List[ScenarioConfig]
    ) -> List[ScenarioResult]:
        """Run scenarios sequentially.

        Args:
            scenarios: List of scenarios to run

        Returns:
            List of results in order
        """
        results = []
        for config in scenarios:
            if self._cancelled:
                results.append(ScenarioResult(
                    scenario_id=config.scenario_id,
                    scenario_name=config.name,
                    status=ScenarioStatus.CANCELLED,
                    start_time=datetime.now(),
                ))
            else:
                results.append(self._execute_scenario(config))
        return results

    def _run_parallel(
        self,
        scenarios: List[ScenarioConfig],
        executor_class: type,
    ) -> List[ScenarioResult]:
        """Run scenarios in parallel using a pool executor.

        Args:
            scenarios: List of scenarios to run
            executor_class: ThreadPoolExecutor or ProcessPoolExecutor

        Returns:
            List of results in original order
        """
        # Map scenario IDs to their original indices
        id_to_index = {config.scenario_id: i for i, config in enumerate(scenarios)}
        results = [None] * len(scenarios)

        with executor_class(max_workers=self.max_workers) as pool:
            # Submit all scenarios
            future_to_id = {
                pool.submit(self._execute_scenario, config): config.scenario_id
                for config in scenarios
            }

            # Collect results as they complete
            for future in as_completed(future_to_id, timeout=self.timeout_seconds):
                scenario_id = future_to_id[future]
                index = id_to_index[scenario_id]

                try:
                    result = future.result()
                    results[index] = result
                except Exception as e:
                    # Create error result for this scenario
                    config = scenarios[index]
                    results[index] = ScenarioResult(
                        scenario_id=config.scenario_id,
                        scenario_name=config.name,
                        status=ScenarioStatus.FAILED,
                        start_time=datetime.now(),
                        error_message=str(e),
                    )

        return results

    def cancel(self) -> None:
        """Cancel all pending scenarios.

        Running scenarios will complete, but pending ones will be skipped.
        """
        with self._lock:
            self._cancelled = True

    def get_progress(self) -> RunnerProgress:
        """Get current progress information.

        Returns:
            Current progress state
        """
        with self._lock:
            return copy.copy(self._progress)


class ScenarioBatchBuilder:
    """Builder for creating batches of scenario configurations.

    Provides convenient methods for generating variations of scenarios
    for sensitivity analysis, parameter sweeps, etc.

    Example:
        >>> builder = ScenarioBatchBuilder()
        >>> scenarios = (
        ...     builder
        ...     .with_base_config(symbols=["AAPL", "GOOGL"])
        ...     .vary_parameter("leverage", [0.5, 1.0, 1.5, 2.0])
        ...     .vary_date_range(
        ...         date(2020, 1, 1),
        ...         date(2023, 12, 31),
        ...         window_months=12,
        ...     )
        ...     .build()
        ... )
    """

    def __init__(self):
        """Initialize the batch builder."""
        self._base_config: Dict[str, Any] = {}
        self._parameter_variations: Dict[str, List[Any]] = {}
        self._date_ranges: List[Tuple[date, date]] = []

    def with_base_config(self, **kwargs) -> "ScenarioBatchBuilder":
        """Set base configuration for all scenarios.

        Args:
            **kwargs: Configuration parameters

        Returns:
            Self for chaining
        """
        self._base_config.update(kwargs)
        return self

    def vary_parameter(
        self, name: str, values: List[Any]
    ) -> "ScenarioBatchBuilder":
        """Add a parameter to vary across scenarios.

        Args:
            name: Parameter name (in strategy_params or risk_params)
            values: List of values to use

        Returns:
            Self for chaining
        """
        self._parameter_variations[name] = values
        return self

    def vary_date_range(
        self,
        start: date,
        end: date,
        window_months: int = 12,
        step_months: int = 3,
    ) -> "ScenarioBatchBuilder":
        """Add rolling date windows.

        Args:
            start: Overall start date
            end: Overall end date
            window_months: Size of each window in months
            step_months: Step between windows in months

        Returns:
            Self for chaining
        """
        from datetime import timedelta
        from dateutil.relativedelta import relativedelta

        current_start = start
        while current_start < end:
            current_end = current_start + relativedelta(months=window_months)
            if current_end > end:
                current_end = end
            self._date_ranges.append((current_start, current_end))
            current_start += relativedelta(months=step_months)

        return self

    def with_date_ranges(
        self, ranges: List[Tuple[date, date]]
    ) -> "ScenarioBatchBuilder":
        """Set explicit date ranges.

        Args:
            ranges: List of (start_date, end_date) tuples

        Returns:
            Self for chaining
        """
        self._date_ranges.extend(ranges)
        return self

    def build(self) -> List[ScenarioConfig]:
        """Build all scenario configurations.

        Creates the Cartesian product of all variations.

        Returns:
            List of ScenarioConfig objects
        """
        import itertools

        scenarios = []

        # Get all parameter combinations
        param_names = list(self._parameter_variations.keys())
        param_values = [self._parameter_variations[name] for name in param_names]

        if param_values:
            param_combinations = list(itertools.product(*param_values))
        else:
            param_combinations = [()]

        # Get date ranges (use single None tuple if no ranges)
        date_ranges = self._date_ranges if self._date_ranges else [(None, None)]

        # Generate all combinations
        for param_combo in param_combinations:
            for start_date, end_date in date_ranges:
                # Build scenario config
                config_dict = copy.deepcopy(self._base_config)

                # Set dates
                if start_date is not None:
                    config_dict["start_date"] = start_date
                if end_date is not None:
                    config_dict["end_date"] = end_date

                # Set parameter variations
                strategy_params = config_dict.get("strategy_params", {})
                for name, value in zip(param_names, param_combo):
                    strategy_params[name] = value
                config_dict["strategy_params"] = strategy_params

                # Generate descriptive name
                name_parts = []
                for name, value in zip(param_names, param_combo):
                    name_parts.append(f"{name}={value}")
                if start_date:
                    name_parts.append(f"{start_date.year}")

                if name_parts:
                    config_dict["name"] = " | ".join(name_parts)

                scenarios.append(ScenarioConfig(**config_dict))

        return scenarios

    def clear(self) -> "ScenarioBatchBuilder":
        """Clear all configuration.

        Returns:
            Self for chaining
        """
        self._base_config = {}
        self._parameter_variations = {}
        self._date_ranges = []
        return self


def aggregate_results(results: List[ScenarioResult]) -> Dict[str, Any]:
    """Aggregate results from multiple scenarios.

    Args:
        results: List of scenario results

    Returns:
        Dictionary with aggregated statistics
    """
    if not results:
        return {
            "total_scenarios": 0,
            "successful": 0,
            "failed": 0,
        }

    successful = [r for r in results if r.is_successful]
    failed = [r for r in results if r.status == ScenarioStatus.FAILED]

    # Calculate aggregate metrics
    returns = [float(r.total_return) for r in successful if r.total_return]
    drawdowns = [float(r.max_drawdown) for r in successful if r.max_drawdown]
    durations = [r.duration_seconds for r in results if r.duration_seconds]

    aggregate = {
        "total_scenarios": len(results),
        "successful": len(successful),
        "failed": len(failed),
        "success_rate": len(successful) / len(results) if results else 0,
        "total_duration_seconds": sum(durations),
        "avg_duration_seconds": sum(durations) / len(durations) if durations else 0,
    }

    if returns:
        aggregate.update({
            "avg_return": sum(returns) / len(returns),
            "min_return": min(returns),
            "max_return": max(returns),
            "median_return": sorted(returns)[len(returns) // 2],
        })

    if drawdowns:
        aggregate.update({
            "avg_max_drawdown": sum(drawdowns) / len(drawdowns),
            "worst_drawdown": min(drawdowns),  # More negative is worse
        })

    # Best and worst scenarios
    if successful:
        best = max(successful, key=lambda r: float(r.total_return or 0))
        worst = min(successful, key=lambda r: float(r.total_return or 0))
        aggregate["best_scenario"] = {
            "name": best.scenario_name,
            "return": str(best.total_return),
        }
        aggregate["worst_scenario"] = {
            "name": worst.scenario_name,
            "return": str(worst.total_return),
        }

    return aggregate
