"""Shared AnalysisRunner contracts for CLI, web, and programmatic callers."""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from tradingagents.execution.models import (
    AnalysisCancelled,
    AnalysisRequest,
    AnalysisResult,
    CancellationToken,
)
from tradingagents.execution.runner import AnalysisRunner

pytestmark = pytest.mark.unit


def _request(**overrides):
    values = {
        "ticker": "AAPL",
        "analysis_date": "2026-07-18",
        "asset_type": "stock",
        "selected_analysts": ("market",),
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "effective_config": {},
    }
    values.update(overrides)
    return AnalysisRequest(**values)


def _owner(*, checkpoint_enabled=False, debug=False):
    events = []
    owner = SimpleNamespace()
    owner.config = {
        "checkpoint_enabled": checkpoint_enabled,
        "data_cache_dir": "/tmp/tradingagents-runner-test",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
    }
    owner.selected_analysts = ("market",)
    owner.callbacks = []
    owner.debug = debug
    owner.curr_state = None
    owner.ticker = None
    owner._checkpointer_ctx = None
    owner.graph = MagicMock()
    owner.workflow = MagicMock()
    owner.propagator = MagicMock()
    owner.memory_log = MagicMock()
    owner.signal_processor = MagicMock()
    owner._resolve_pending_entries = MagicMock(side_effect=lambda ticker: events.append("pending"))
    owner.resolve_instrument_context = MagicMock(
        side_effect=lambda ticker, asset: events.append("identity") or "Apple identity"
    )
    owner._run_signature = MagicMock(return_value="shape")
    owner._log_state = MagicMock(side_effect=lambda date, state: events.append("state_log"))
    owner.memory_log.get_past_context.side_effect = (
        lambda ticker: events.append("past_context") or "prior lesson"
    )
    owner.memory_log.store_decision.side_effect = lambda **kwargs: events.append("decision")
    owner.signal_processor.process_signal.side_effect = (
        lambda signal: events.append("signal") or "BUY"
    )
    owner.propagator.create_initial_state.return_value = {"input": True}
    owner.propagator.get_graph_args.return_value = {"stream_mode": "values"}
    return owner, events


def test_runner_returns_success_object_and_preserves_completion_order():
    owner, events = _owner()
    final_state = {
        "company_of_interest": "AAPL",
        "final_trade_decision": "Rating: Buy",
    }
    owner.graph.invoke.side_effect = lambda *_args, **_kwargs: events.append("graph") or final_state

    result = AnalysisRunner(owner).run(_request())

    assert isinstance(result, AnalysisResult)
    assert result.final_state is final_state
    assert result.final_signal == "BUY"
    assert owner.curr_state is final_state
    assert events == [
        "pending",
        "past_context",
        "identity",
        "graph",
        "state_log",
        "decision",
        "signal",
    ]
    owner.propagator.create_initial_state.assert_called_once_with(
        "AAPL",
        "2026-07-18",
        asset_type="stock",
        past_context="prior lesson",
        instrument_context="Apple identity",
    )


def test_runner_preserves_original_failure_and_skips_completion_side_effects():
    owner, events = _owner()
    original = RuntimeError("provider exploded")
    owner.graph.invoke.side_effect = original

    with pytest.raises(RuntimeError, match="provider exploded") as exc_info:
        AnalysisRunner(owner).run(_request())

    assert exc_info.value is original
    assert owner.curr_state is None
    assert events == ["pending", "past_context", "identity"]
    owner._log_state.assert_not_called()
    owner.memory_log.store_decision.assert_not_called()
    owner.signal_processor.process_signal.assert_not_called()


def test_cancellation_is_checked_before_graph_and_after_stream_boundaries():
    owner, _events = _owner()
    token = CancellationToken()
    token.cancel()

    with pytest.raises(AnalysisCancelled) as before:
        AnalysisRunner(owner).run(_request(), cancellation_token=token)
    assert before.value.partial_state is None
    owner.graph.invoke.assert_not_called()
    owner.graph.stream.assert_not_called()

    owner, _events = _owner()
    token = CancellationToken()
    partial = {"company_of_interest": "AAPL", "market_report": "candidate"}

    def stream(*_args, **_kwargs):
        token.cancel()
        yield partial

    owner.graph.stream.side_effect = stream
    with pytest.raises(AnalysisCancelled) as after:
        AnalysisRunner(owner).run(_request(), cancellation_token=token)
    assert after.value.partial_state == partial
    owner._log_state.assert_not_called()
    owner.memory_log.store_decision.assert_not_called()


def test_observed_execution_forwards_context_and_callbacks_without_double_sources():
    owner, _events = _owner()
    observer = object()
    run_context = object()
    final_state = {"final_trade_decision": "Rating: Buy"}
    owner.graph.stream.return_value = [final_state]

    result = AnalysisRunner(owner).run(
        _request(),
        observation_context=run_context,
        callbacks=[observer],
    )

    assert result.final_state is final_state
    owner.propagator.create_initial_state.assert_called_once_with(
        "AAPL",
        "2026-07-18",
        asset_type="stock",
        past_context="prior lesson",
        instrument_context="Apple identity",
        observation_context=run_context,
    )
    owner.propagator.get_graph_args.assert_called_once_with(callbacks=[observer])
    owner.graph.stream.assert_called_once_with(
        {"input": True},
        stream_mode="values",
        context=run_context,
    )


@pytest.mark.parametrize("fails", [False, True])
def test_checkpoint_lifecycle_is_owned_by_runner_and_always_closed(fails):
    owner, _events = _owner(checkpoint_enabled=True)
    saver = object()
    compiled = MagicMock()
    restored = MagicMock()
    owner.workflow.compile.side_effect = [compiled, restored]
    context = MagicMock()
    context.__enter__.return_value = saver
    final_state = {"final_trade_decision": "Rating: Hold"}
    original = RuntimeError("graph failed")
    compiled.invoke.side_effect = original if fails else None
    if not fails:
        compiled.invoke.return_value = final_state

    with (
        patch("tradingagents.execution.runner.get_checkpointer", return_value=context),
        patch("tradingagents.execution.runner.checkpoint_step", return_value=3),
        patch("tradingagents.execution.runner.clear_checkpoint") as clear,
    ):
        if fails:
            with pytest.raises(RuntimeError, match="graph failed") as exc_info:
                AnalysisRunner(owner).run(_request())
            assert exc_info.value is original
            clear.assert_not_called()
        else:
            AnalysisRunner(owner).run(_request())
            clear.assert_called_once_with(
                "/tmp/tradingagents-runner-test",
                "AAPL",
                "2026-07-18",
                "shape",
            )

    assert context.__exit__.call_count == 1
    assert owner._checkpointer_ctx is None
    assert owner.graph is restored
    owner.workflow.compile.assert_has_calls([call(checkpointer=saver), call()])


@pytest.mark.parametrize("failure_stage", ["enter", "compile", "step"])
def test_partial_checkpoint_setup_never_leaks_context(failure_stage):
    owner, _events = _owner(checkpoint_enabled=True)
    original_graph = owner.graph
    context = MagicMock()
    saver = object()
    original = RuntimeError(f"{failure_stage} failed")
    if failure_stage == "enter":
        context.__enter__.side_effect = original
    else:
        context.__enter__.return_value = saver
    if failure_stage == "compile":
        owner.workflow.compile.side_effect = original
    elif failure_stage == "step":
        owner.workflow.compile.side_effect = [MagicMock(), original]

    with (
        patch("tradingagents.execution.runner.get_checkpointer", return_value=context),
        patch(
            "tradingagents.execution.runner.checkpoint_step",
            side_effect=original if failure_stage == "step" else None,
        ),
        pytest.raises(RuntimeError, match=f"{failure_stage} failed") as exc_info,
    ):
        AnalysisRunner(owner).run(_request())

    assert exc_info.value is original
    assert owner._checkpointer_ctx is None
    if failure_stage == "enter":
        context.__exit__.assert_not_called()
    else:
        context.__exit__.assert_called_once()
    if failure_stage in {"enter", "compile"}:
        assert owner.graph is original_graph


def test_cleanup_failure_never_masks_original_graph_failure():
    owner, _events = _owner(checkpoint_enabled=True)
    original = RuntimeError("provider exploded")
    cleanup = RuntimeError("close failed")
    compiled = MagicMock()
    restored = MagicMock()
    compiled.invoke.side_effect = original
    owner.workflow.compile.side_effect = [compiled, restored]
    context = MagicMock()
    context.__enter__.return_value = object()
    context.__exit__.side_effect = cleanup

    with (
        patch("tradingagents.execution.runner.get_checkpointer", return_value=context),
        patch("tradingagents.execution.runner.checkpoint_step", return_value=None),
        pytest.raises(RuntimeError, match="provider exploded") as exc_info,
    ):
        AnalysisRunner(owner).run(_request())

    assert exc_info.value is original
    assert owner._checkpointer_ctx is None
    assert owner.graph is restored
