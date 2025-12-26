"""Tests for Scenario Runner.

Issue #33: [SIM-32] Scenario runner - parallel portfolio simulations

Tests cover:
- ExecutionMode and ScenarioStatus enums
- ScenarioConfig and ScenarioResult dataclasses
- ScenarioRunner sequential execution
- ScenarioRunner parallel execution
- Progress tracking and callbacks
- ScenarioBatchBuilder variations
- Result aggregation
- Error handling
- Cancellation
"""

import pytest
import time
from datetime import datetime, date
from decimal import Decimal
from unittest.mock import Mock, patch
import threading

from tradingagents.simulation.scenario_runner import (
    ExecutionMode,
    ScenarioStatus,
    ScenarioConfig,
    ScenarioResult,
    RunnerProgress,
    ScenarioRunner,
    ScenarioBatchBuilder,
    aggregate_results,
)


# ==============================================================================
# ExecutionMode Enum Tests
# ==============================================================================


class TestExecutionMode:
    """Tests for ExecutionMode enum."""

    def test_sequential_value(self):
        """Test SEQUENTIAL mode value."""
        assert ExecutionMode.SEQUENTIAL.value == "sequential"

    def test_threaded_value(self):
        """Test THREADED mode value."""
        assert ExecutionMode.THREADED.value == "threaded"

    def test_process_value(self):
        """Test PROCESS mode value."""
        assert ExecutionMode.PROCESS.value == "process"

    def test_all_modes_exist(self):
        """Test all expected modes exist."""
        modes = [m for m in ExecutionMode]
        assert len(modes) == 3


# ==============================================================================
# ScenarioStatus Enum Tests
# ==============================================================================


class TestScenarioStatus:
    """Tests for ScenarioStatus enum."""

    def test_pending_value(self):
        """Test PENDING status value."""
        assert ScenarioStatus.PENDING.value == "pending"

    def test_running_value(self):
        """Test RUNNING status value."""
        assert ScenarioStatus.RUNNING.value == "running"

    def test_completed_value(self):
        """Test COMPLETED status value."""
        assert ScenarioStatus.COMPLETED.value == "completed"

    def test_failed_value(self):
        """Test FAILED status value."""
        assert ScenarioStatus.FAILED.value == "failed"

    def test_cancelled_value(self):
        """Test CANCELLED status value."""
        assert ScenarioStatus.CANCELLED.value == "cancelled"

    def test_all_statuses_exist(self):
        """Test all expected statuses exist."""
        statuses = [s for s in ScenarioStatus]
        assert len(statuses) == 5


# ==============================================================================
# ScenarioConfig Tests
# ==============================================================================


class TestScenarioConfig:
    """Tests for ScenarioConfig dataclass."""

    def test_default_config(self):
        """Test creating config with defaults."""
        config = ScenarioConfig()
        assert config.scenario_id is not None
        assert config.name.startswith("Scenario-")
        assert config.initial_capital == Decimal("100000")
        assert config.symbols == []
        assert config.strategy_params == {}
        assert config.risk_params == {}

    def test_custom_config(self):
        """Test creating config with custom values."""
        config = ScenarioConfig(
            name="Bull Market Test",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            initial_capital=Decimal("50000"),
            symbols=["AAPL", "GOOGL"],
            strategy_params={"leverage": 1.5},
            risk_params={"max_drawdown": 0.2},
        )
        assert config.name == "Bull Market Test"
        assert config.start_date == date(2023, 1, 1)
        assert config.end_date == date(2023, 12, 31)
        assert config.initial_capital == Decimal("50000")
        assert config.symbols == ["AAPL", "GOOGL"]
        assert config.strategy_params["leverage"] == 1.5
        assert config.risk_params["max_drawdown"] == 0.2

    def test_auto_generated_name(self):
        """Test auto-generated name from scenario_id."""
        config = ScenarioConfig()
        # Name should start with "Scenario-" and contain part of the ID
        assert config.name.startswith("Scenario-")
        assert len(config.name) > 8

    def test_explicit_scenario_id(self):
        """Test explicit scenario ID."""
        config = ScenarioConfig(scenario_id="test-123")
        assert config.scenario_id == "test-123"


# ==============================================================================
# ScenarioResult Tests
# ==============================================================================


class TestScenarioResult:
    """Tests for ScenarioResult dataclass."""

    def test_successful_result(self):
        """Test creating a successful result."""
        result = ScenarioResult(
            scenario_id="test-1",
            scenario_name="Test",
            status=ScenarioStatus.COMPLETED,
            start_time=datetime.now(),
            final_value=Decimal("110000"),
            total_return=Decimal("0.10"),
        )
        assert result.is_successful is True
        assert result.is_finished is True

    def test_failed_result(self):
        """Test creating a failed result."""
        result = ScenarioResult(
            scenario_id="test-1",
            scenario_name="Test",
            status=ScenarioStatus.FAILED,
            start_time=datetime.now(),
            error_message="Simulation error",
        )
        assert result.is_successful is False
        assert result.is_finished is True
        assert result.error_message == "Simulation error"

    def test_pending_result(self):
        """Test pending result properties."""
        result = ScenarioResult(
            scenario_id="test-1",
            scenario_name="Test",
            status=ScenarioStatus.PENDING,
            start_time=datetime.now(),
        )
        assert result.is_successful is False
        assert result.is_finished is False

    def test_running_result(self):
        """Test running result properties."""
        result = ScenarioResult(
            scenario_id="test-1",
            scenario_name="Test",
            status=ScenarioStatus.RUNNING,
            start_time=datetime.now(),
        )
        assert result.is_successful is False
        assert result.is_finished is False

    def test_cancelled_result(self):
        """Test cancelled result properties."""
        result = ScenarioResult(
            scenario_id="test-1",
            scenario_name="Test",
            status=ScenarioStatus.CANCELLED,
            start_time=datetime.now(),
        )
        assert result.is_successful is False
        assert result.is_finished is True


# ==============================================================================
# RunnerProgress Tests
# ==============================================================================


class TestRunnerProgress:
    """Tests for RunnerProgress dataclass."""

    def test_progress_percent(self):
        """Test progress percentage calculation."""
        progress = RunnerProgress(
            total_scenarios=10,
            completed=3,
            failed=2,
        )
        assert progress.progress_percent == 50.0

    def test_progress_percent_zero_total(self):
        """Test progress with zero total scenarios."""
        progress = RunnerProgress(total_scenarios=0)
        assert progress.progress_percent == 100.0

    def test_is_complete(self):
        """Test completion detection."""
        progress = RunnerProgress(
            total_scenarios=5,
            completed=3,
            failed=2,
        )
        assert progress.is_complete is True

    def test_not_complete(self):
        """Test incomplete detection."""
        progress = RunnerProgress(
            total_scenarios=5,
            completed=2,
            failed=1,
        )
        assert progress.is_complete is False


# ==============================================================================
# ScenarioRunner Tests - Sequential Execution
# ==============================================================================


class TestScenarioRunnerSequential:
    """Tests for ScenarioRunner sequential execution."""

    def test_run_empty_list(self):
        """Test running with empty scenario list."""
        def executor(config):
            return ScenarioResult(
                scenario_id=config.scenario_id,
                scenario_name=config.name,
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
            )

        runner = ScenarioRunner(executor=executor, mode=ExecutionMode.SEQUENTIAL)
        results = runner.run([])
        assert results == []

    def test_run_single_scenario(self):
        """Test running a single scenario."""
        def executor(config):
            return ScenarioResult(
                scenario_id=config.scenario_id,
                scenario_name=config.name,
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
                final_value=Decimal("110000"),
                total_return=Decimal("0.10"),
            )

        runner = ScenarioRunner(executor=executor, mode=ExecutionMode.SEQUENTIAL)
        scenarios = [ScenarioConfig(name="Test1")]
        results = runner.run(scenarios)

        assert len(results) == 1
        assert results[0].is_successful
        assert results[0].scenario_name == "Test1"

    def test_run_multiple_scenarios(self):
        """Test running multiple scenarios sequentially."""
        call_order = []

        def executor(config):
            call_order.append(config.name)
            return ScenarioResult(
                scenario_id=config.scenario_id,
                scenario_name=config.name,
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
            )

        runner = ScenarioRunner(executor=executor, mode=ExecutionMode.SEQUENTIAL)
        scenarios = [
            ScenarioConfig(name="Test1"),
            ScenarioConfig(name="Test2"),
            ScenarioConfig(name="Test3"),
        ]
        results = runner.run(scenarios)

        assert len(results) == 3
        assert call_order == ["Test1", "Test2", "Test3"]
        assert all(r.is_successful for r in results)

    def test_run_with_executor_exception(self):
        """Test handling executor exceptions."""
        def executor(config):
            if config.name == "FailMe":
                raise ValueError("Simulated error")
            return ScenarioResult(
                scenario_id=config.scenario_id,
                scenario_name=config.name,
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
            )

        runner = ScenarioRunner(executor=executor, mode=ExecutionMode.SEQUENTIAL)
        scenarios = [
            ScenarioConfig(name="Test1"),
            ScenarioConfig(name="FailMe"),
            ScenarioConfig(name="Test3"),
        ]
        results = runner.run(scenarios)

        assert len(results) == 3
        assert results[0].is_successful
        assert results[1].status == ScenarioStatus.FAILED
        assert "Simulated error" in results[1].error_message
        assert results[2].is_successful


# ==============================================================================
# ScenarioRunner Tests - Parallel Execution
# ==============================================================================


class TestScenarioRunnerParallel:
    """Tests for ScenarioRunner parallel execution."""

    def test_run_threaded(self):
        """Test running scenarios in parallel using threads."""
        def executor(config):
            time.sleep(0.01)  # Small delay to ensure parallelism
            return ScenarioResult(
                scenario_id=config.scenario_id,
                scenario_name=config.name,
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
            )

        runner = ScenarioRunner(
            executor=executor,
            mode=ExecutionMode.THREADED,
            max_workers=4,
        )
        scenarios = [ScenarioConfig(name=f"Test{i}") for i in range(8)]

        start = time.time()
        results = runner.run(scenarios)
        elapsed = time.time() - start

        assert len(results) == 8
        assert all(r.is_successful for r in results)
        # With 4 workers and 8 scenarios at 0.01s each,
        # parallel should be faster than sequential (0.08s)
        # Allow some overhead
        assert elapsed < 0.1

    def test_results_order_preserved(self):
        """Test that results match input order."""
        import random

        def executor(config):
            # Random delay to encourage out-of-order completion
            time.sleep(random.uniform(0.001, 0.01))
            return ScenarioResult(
                scenario_id=config.scenario_id,
                scenario_name=config.name,
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
                final_value=Decimal(config.metadata.get("index", 0)),
            )

        runner = ScenarioRunner(
            executor=executor,
            mode=ExecutionMode.THREADED,
            max_workers=4,
        )
        scenarios = [
            ScenarioConfig(name=f"Test{i}", metadata={"index": i})
            for i in range(10)
        ]
        results = runner.run(scenarios)

        assert len(results) == 10
        for i, result in enumerate(results):
            assert result.scenario_name == f"Test{i}"
            assert result.final_value == Decimal(i)


# ==============================================================================
# ScenarioRunner Tests - Progress Tracking
# ==============================================================================


class TestScenarioRunnerProgress:
    """Tests for ScenarioRunner progress tracking."""

    def test_progress_callback(self):
        """Test progress callback invocation."""
        progress_updates = []

        def on_progress(progress):
            progress_updates.append({
                "completed": progress.completed,
                "total": progress.total_scenarios,
            })

        def executor(config):
            return ScenarioResult(
                scenario_id=config.scenario_id,
                scenario_name=config.name,
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
            )

        runner = ScenarioRunner(executor=executor, mode=ExecutionMode.SEQUENTIAL)
        scenarios = [ScenarioConfig(name=f"Test{i}") for i in range(3)]
        runner.run(scenarios, progress_callback=on_progress)

        # Should have received progress updates
        assert len(progress_updates) > 0
        # Final update should show all completed
        final = progress_updates[-1]
        assert final["completed"] == 3

    def test_get_progress(self):
        """Test get_progress method."""
        def executor(config):
            time.sleep(0.01)
            return ScenarioResult(
                scenario_id=config.scenario_id,
                scenario_name=config.name,
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
            )

        runner = ScenarioRunner(
            executor=executor,
            mode=ExecutionMode.THREADED,
            max_workers=2,
        )

        scenarios = [ScenarioConfig(name=f"Test{i}") for i in range(4)]

        # Start in background
        results = []
        def run_in_thread():
            nonlocal results
            results = runner.run(scenarios)

        thread = threading.Thread(target=run_in_thread)
        thread.start()

        # Give it time to start
        time.sleep(0.005)
        progress = runner.get_progress()
        assert progress.total_scenarios == 4

        thread.join()
        assert len(results) == 4


# ==============================================================================
# ScenarioRunner Tests - Cancellation
# ==============================================================================


class TestScenarioRunnerCancellation:
    """Tests for ScenarioRunner cancellation."""

    def test_cancel_pending_scenarios(self):
        """Test cancelling pending scenarios."""
        executed = []

        def executor(config):
            executed.append(config.name)
            time.sleep(0.02)
            return ScenarioResult(
                scenario_id=config.scenario_id,
                scenario_name=config.name,
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
            )

        runner = ScenarioRunner(
            executor=executor,
            mode=ExecutionMode.SEQUENTIAL,
        )

        scenarios = [ScenarioConfig(name=f"Test{i}") for i in range(5)]

        # Cancel after short delay
        def cancel_after_delay():
            time.sleep(0.03)
            runner.cancel()

        cancel_thread = threading.Thread(target=cancel_after_delay)
        cancel_thread.start()

        results = runner.run(scenarios)
        cancel_thread.join()

        # Some should be completed, some cancelled
        completed = [r for r in results if r.status == ScenarioStatus.COMPLETED]
        cancelled = [r for r in results if r.status == ScenarioStatus.CANCELLED]

        assert len(completed) + len(cancelled) == 5
        # At least the first one should have completed
        assert len(completed) >= 1


# ==============================================================================
# ScenarioBatchBuilder Tests
# ==============================================================================


class TestScenarioBatchBuilder:
    """Tests for ScenarioBatchBuilder."""

    def test_empty_build(self):
        """Test building with no configuration."""
        builder = ScenarioBatchBuilder()
        scenarios = builder.build()
        assert len(scenarios) == 1  # One default scenario

    def test_base_config(self):
        """Test setting base configuration."""
        builder = ScenarioBatchBuilder()
        scenarios = (
            builder
            .with_base_config(
                initial_capital=Decimal("50000"),
                symbols=["AAPL", "GOOGL"],
            )
            .build()
        )
        assert len(scenarios) == 1
        assert scenarios[0].initial_capital == Decimal("50000")
        assert scenarios[0].symbols == ["AAPL", "GOOGL"]

    def test_parameter_variation(self):
        """Test varying a single parameter."""
        builder = ScenarioBatchBuilder()
        scenarios = (
            builder
            .vary_parameter("leverage", [0.5, 1.0, 1.5])
            .build()
        )
        assert len(scenarios) == 3
        leverages = [s.strategy_params["leverage"] for s in scenarios]
        assert leverages == [0.5, 1.0, 1.5]

    def test_multiple_parameter_variations(self):
        """Test varying multiple parameters (Cartesian product)."""
        builder = ScenarioBatchBuilder()
        scenarios = (
            builder
            .vary_parameter("leverage", [1.0, 2.0])
            .vary_parameter("stop_loss", [0.05, 0.10])
            .build()
        )
        assert len(scenarios) == 4  # 2 x 2

        combinations = [
            (s.strategy_params["leverage"], s.strategy_params["stop_loss"])
            for s in scenarios
        ]
        expected = [
            (1.0, 0.05),
            (1.0, 0.10),
            (2.0, 0.05),
            (2.0, 0.10),
        ]
        assert sorted(combinations) == sorted(expected)

    def test_explicit_date_ranges(self):
        """Test setting explicit date ranges."""
        builder = ScenarioBatchBuilder()
        scenarios = (
            builder
            .with_date_ranges([
                (date(2020, 1, 1), date(2020, 12, 31)),
                (date(2021, 1, 1), date(2021, 12, 31)),
            ])
            .build()
        )
        assert len(scenarios) == 2
        assert scenarios[0].start_date == date(2020, 1, 1)
        assert scenarios[1].start_date == date(2021, 1, 1)

    def test_clear_builder(self):
        """Test clearing builder configuration."""
        builder = ScenarioBatchBuilder()
        builder.with_base_config(initial_capital=Decimal("50000"))
        builder.vary_parameter("leverage", [1.0, 2.0])
        builder.clear()

        scenarios = builder.build()
        assert len(scenarios) == 1
        assert scenarios[0].initial_capital == Decimal("100000")  # Default

    def test_scenario_names_generated(self):
        """Test that scenario names are auto-generated."""
        builder = ScenarioBatchBuilder()
        scenarios = (
            builder
            .vary_parameter("leverage", [1.0, 2.0])
            .build()
        )
        assert "leverage=1.0" in scenarios[0].name
        assert "leverage=2.0" in scenarios[1].name


# ==============================================================================
# Result Aggregation Tests
# ==============================================================================


class TestResultAggregation:
    """Tests for result aggregation."""

    def test_aggregate_empty_results(self):
        """Test aggregating empty results list."""
        agg = aggregate_results([])
        assert agg["total_scenarios"] == 0
        assert agg["successful"] == 0
        assert agg["failed"] == 0

    def test_aggregate_successful_results(self):
        """Test aggregating successful results."""
        results = [
            ScenarioResult(
                scenario_id=f"test-{i}",
                scenario_name=f"Test{i}",
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
                total_return=Decimal(f"0.{i+1}"),
                max_drawdown=Decimal(f"-0.0{i+1}"),
                duration_seconds=1.0,
            )
            for i in range(3)
        ]

        agg = aggregate_results(results)
        assert agg["total_scenarios"] == 3
        assert agg["successful"] == 3
        assert agg["failed"] == 0
        assert agg["success_rate"] == 1.0
        assert "avg_return" in agg
        assert "min_return" in agg
        assert "max_return" in agg

    def test_aggregate_mixed_results(self):
        """Test aggregating mixed success/failure results."""
        results = [
            ScenarioResult(
                scenario_id="test-1",
                scenario_name="Success1",
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
                total_return=Decimal("0.10"),
            ),
            ScenarioResult(
                scenario_id="test-2",
                scenario_name="Failed1",
                status=ScenarioStatus.FAILED,
                start_time=datetime.now(),
                error_message="Error",
            ),
            ScenarioResult(
                scenario_id="test-3",
                scenario_name="Success2",
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
                total_return=Decimal("0.20"),
            ),
        ]

        agg = aggregate_results(results)
        assert agg["total_scenarios"] == 3
        assert agg["successful"] == 2
        assert agg["failed"] == 1
        assert agg["success_rate"] == pytest.approx(0.667, rel=0.01)

    def test_aggregate_best_worst_scenarios(self):
        """Test best/worst scenario identification."""
        results = [
            ScenarioResult(
                scenario_id="test-1",
                scenario_name="Low",
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
                total_return=Decimal("0.05"),
            ),
            ScenarioResult(
                scenario_id="test-2",
                scenario_name="High",
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
                total_return=Decimal("0.25"),
            ),
            ScenarioResult(
                scenario_id="test-3",
                scenario_name="Mid",
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
                total_return=Decimal("0.15"),
            ),
        ]

        agg = aggregate_results(results)
        assert agg["best_scenario"]["name"] == "High"
        assert agg["worst_scenario"]["name"] == "Low"


# ==============================================================================
# Module Import Tests
# ==============================================================================


class TestModuleImports:
    """Tests for module imports."""

    def test_import_from_simulation_module(self):
        """Test importing from simulation module."""
        from tradingagents.simulation import (
            ExecutionMode,
            ScenarioStatus,
            ScenarioConfig,
            ScenarioResult,
            RunnerProgress,
            ScenarioRunner,
            ScenarioBatchBuilder,
            aggregate_results,
        )
        assert ExecutionMode is not None
        assert ScenarioStatus is not None
        assert ScenarioConfig is not None
        assert ScenarioResult is not None
        assert RunnerProgress is not None
        assert ScenarioRunner is not None
        assert ScenarioBatchBuilder is not None
        assert aggregate_results is not None


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestScenarioRunnerIntegration:
    """Integration tests for ScenarioRunner."""

    def test_full_simulation_workflow(self):
        """Test complete simulation workflow."""
        # Create executor that simulates trading
        def trading_simulator(config: ScenarioConfig) -> ScenarioResult:
            # Simulate based on strategy params
            leverage = config.strategy_params.get("leverage", 1.0)
            base_return = 0.08  # 8% base return
            final_return = base_return * leverage

            final_value = config.initial_capital * Decimal(str(1 + final_return))

            return ScenarioResult(
                scenario_id=config.scenario_id,
                scenario_name=config.name,
                status=ScenarioStatus.COMPLETED,
                start_time=datetime.now(),
                end_time=datetime.now(),
                final_value=final_value.quantize(Decimal("0.01")),
                total_return=Decimal(str(final_return)).quantize(Decimal("0.0001")),
                max_drawdown=Decimal("-0.10"),
                trades_executed=25,
            )

        # Build scenarios with varying leverage
        scenarios = (
            ScenarioBatchBuilder()
            .with_base_config(initial_capital=Decimal("100000"))
            .vary_parameter("leverage", [0.5, 1.0, 1.5, 2.0])
            .build()
        )

        # Run simulations
        runner = ScenarioRunner(
            executor=trading_simulator,
            mode=ExecutionMode.THREADED,
            max_workers=4,
        )

        progress_updates = []
        results = runner.run(
            scenarios,
            progress_callback=lambda p: progress_updates.append(p.completed),
        )

        # Verify results
        assert len(results) == 4
        assert all(r.is_successful for r in results)

        # Aggregate and analyze
        agg = aggregate_results(results)
        assert agg["total_scenarios"] == 4
        assert agg["successful"] == 4
        assert agg["best_scenario"]["name"] == "leverage=2.0"
        assert agg["worst_scenario"]["name"] == "leverage=0.5"
