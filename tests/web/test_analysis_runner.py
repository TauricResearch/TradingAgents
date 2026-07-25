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
from tradingagents.execution.runner import AnalysisRunner, CheckpointAuthorization
from tradingagents.portfolio import FeatureContribution, FeatureContributionArtifact
from tradingagents.web.fingerprint import FingerprintCheckpointGuard
from tradingagents.web.run_models import RunSnapshot, generate_run_id
from tradingagents.web.store import RunStore

pytestmark = pytest.mark.unit


def _durable_checkpoint_guard(tmp_path, owner, request, run_id):
    store = RunStore(tmp_path)
    store.create_run(
        RunSnapshot.create(
            run_id=run_id,
            ticker=request.ticker,
            analysis_date=request.analysis_date,
            selected_analysts=request.selected_analysts,
            llm_provider="openai",
            quick_think_llm="quick",
            deep_think_llm="deep",
        )
    )
    return FingerprintCheckpointGuard(
        store,
        run_id,
        request,
        owner.config,
    )


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


def test_runner_only_injects_feature_drivers_from_typed_numeric_artifact():
    owner, _events = _owner()
    owner.graph.invoke.return_value = {"final_trade_decision": "Rating: Hold"}
    artifact = FeatureContributionArtifact(
        artifact_id="calc:factor-model:2026-07-18",
        producer="factor-model-v2",
        methodology_ref="docs/factor-model-v2.md#normalization",
        as_of_date="2026-07-18",
        contributions=(
            FeatureContribution(
                "cash_flow",
                -2.0,
                0.7,
                "risk",
                "dataset:financials:2026-07-18",
            ),
        ),
    )

    AnalysisRunner(owner).run(_request(feature_contribution_artifact=artifact))

    owner.graph.invoke.assert_called_once_with(
        {
            "input": True,
            "feature_contributions": [
                {
                    "feature": "cash_flow",
                    "z_score": -2.0,
                    "importance": 0.7,
                    "direction": "risk",
                    "evidence_ref": "dataset:financials:2026-07-18",
                    "source_artifact_id": "calc:factor-model:2026-07-18",
                }
            ],
        },
        stream_mode="values",
    )


def test_runner_streams_raw_state_updates_to_consumer_without_a_second_execution():
    owner, _events = _owner()
    owner.propagator.get_graph_args.return_value = {"stream_mode": "updates"}
    chunks = [
        {"market_report": "market evidence"},
        {"final_trade_decision": "Rating: Hold"},
    ]
    owner.graph.stream.return_value = chunks
    received = []

    result = AnalysisRunner(owner).run(
        _request(),
        state_update_sink=received.append,
    )

    assert received == chunks
    assert result.final_state == {
        "market_report": "market evidence",
        "final_trade_decision": "Rating: Hold",
    }
    owner.graph.stream.assert_called_once()
    owner.graph.invoke.assert_not_called()


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


def test_web_checkpoint_namespace_is_used_for_probe_invoke_and_clear(tmp_path):
    owner, _events = _owner(checkpoint_enabled=True)
    compiled = MagicMock()
    compiled.invoke.return_value = {"final_trade_decision": "Rating: Hold"}
    owner.workflow.compile.side_effect = [compiled, MagicMock()]
    context = MagicMock()
    context.__enter__.return_value = object()
    run_id = generate_run_id()
    request = _request(effective_config=dict(owner.config))
    checkpoint_guard = _durable_checkpoint_guard(
        tmp_path,
        owner,
        request,
        run_id,
    )
    checkpoint_frontier = object()

    with (
        patch("tradingagents.execution.runner.get_checkpointer", return_value=context),
        patch(
            "tradingagents.execution.runner.checkpoint_access",
            return_value=checkpoint_frontier,
        ) as access,
        patch("tradingagents.execution.runner.checkpoint_step", return_value=None) as step,
        patch("tradingagents.execution.runner.thread_id", return_value="web-thread") as identity,
        patch("tradingagents.execution.runner.clear_checkpoint") as clear,
    ):
        AnalysisRunner(owner).run(
            request,
            checkpoint_run_id=run_id,
            checkpoint_guard=checkpoint_guard,
        )

    access.assert_called_once_with(
        "/tmp/tradingagents-runner-test",
        "AAPL",
        "2026-07-18",
        "shape",
        run_id=run_id,
    )
    step.assert_called_once_with(
        "/tmp/tradingagents-runner-test",
        "AAPL",
        "2026-07-18",
        "shape",
        run_id=run_id,
    )
    identity.assert_called_once_with(
        "AAPL",
        "2026-07-18",
        "shape",
        run_id=run_id,
    )
    clear.assert_called_once_with(
        "/tmp/tradingagents-runner-test",
        "AAPL",
        "2026-07-18",
        "shape",
        run_id=run_id,
    )
    assert compiled.invoke.call_args.kwargs["config"]["configurable"]["thread_id"] == "web-thread"


def test_web_checkpoint_rejects_missing_or_drifted_effective_config_before_work():
    owner, events = _owner(checkpoint_enabled=True)
    runner = AnalysisRunner(owner)

    with pytest.raises(ValueError, match="complete effective_config"):
        runner.run(
            _request(),
            checkpoint_run_id="run-123",
            checkpoint_guard=MagicMock(),
        )
    assert events == []

    changed = dict(owner.config)
    changed["quick_think_llm"] = "different-model"
    with pytest.raises(ValueError, match="does not match"):
        runner.run(
            _request(effective_config=changed),
            checkpoint_run_id="run-123",
            checkpoint_guard=MagicMock(),
        )
    assert events == []


def test_checkpoint_guard_is_required_before_any_web_checkpoint_work():
    owner, events = _owner(checkpoint_enabled=True)

    with pytest.raises(ValueError, match="checkpoint guard"):
        AnalysisRunner(owner).run(
            _request(effective_config=dict(owner.config)),
            checkpoint_run_id="run-123",
        )

    assert events == []


def test_observation_run_id_is_derived_and_mismatch_is_rejected(tmp_path):
    owner, _events = _owner(checkpoint_enabled=True)
    run_id = generate_run_id()
    observed = SimpleNamespace(observer=SimpleNamespace(run_id=run_id))
    compiled = MagicMock()
    compiled.stream.return_value = [{"final_trade_decision": "Rating: Hold"}]
    owner.workflow.compile.side_effect = [compiled, MagicMock()]
    context = MagicMock()
    context.__enter__.return_value = object()

    with (
        patch("tradingagents.execution.runner.get_checkpointer", return_value=context),
        patch("tradingagents.execution.runner.checkpoint_access", return_value=object()),
        patch("tradingagents.execution.runner.checkpoint_step", return_value=None),
        patch("tradingagents.execution.runner.thread_id", return_value="derived") as identity,
        patch("tradingagents.execution.runner.clear_checkpoint"),
    ):
        request = _request(effective_config=dict(owner.config))
        AnalysisRunner(owner).run(
            request,
            observation_context=observed,
            checkpoint_guard=_durable_checkpoint_guard(
                tmp_path,
                owner,
                request,
                run_id,
            ),
        )

    identity.assert_called_once_with(
        "AAPL",
        "2026-07-18",
        "shape",
        run_id=run_id,
    )

    owner, events = _owner(checkpoint_enabled=True)
    with pytest.raises(ValueError, match="do not match"):
        AnalysisRunner(owner).run(
            _request(effective_config=dict(owner.config)),
            observation_context=observed,
            checkpoint_run_id="other-run",
            checkpoint_guard=MagicMock(),
        )
    assert events == []


def test_web_checkpoint_allows_preset_analyst_order_when_graph_matches():
    owner, events = _owner(checkpoint_enabled=True)
    owner.selected_analysts = ("news", "market")

    AnalysisRunner(owner)._validate_request_shape(
        _request(
            selected_analysts=("news", "market"),
            effective_config=dict(owner.config),
        ),
        checkpoint_run_id="run-123",
    )
    assert events == []


def test_config_validation_compares_semantics_without_secret_values():
    owner, _events = _owner()
    owner.config["OPENAI_API_KEY"] = "current-secret"
    owner.graph.invoke.return_value = {"final_trade_decision": "Rating: Hold"}
    request_config = dict(owner.config)
    request_config["OPENAI_API_KEY"] = "rotated-secret"

    result = AnalysisRunner(owner).run(_request(effective_config=request_config))

    assert result.final_signal == "BUY"

    owner, _events = _owner()
    owner.config["OPENAI_API_KEY"] = "current-secret"
    owner.graph.invoke.return_value = {"final_trade_decision": "Rating: Hold"}
    safe_request_config = {
        key: value for key, value in owner.config.items() if key != "OPENAI_API_KEY"
    }

    result = AnalysisRunner(owner).run(
        _request(effective_config=safe_request_config)
    )

    assert result.final_signal == "BUY"


def test_rejected_checkpoint_guard_cannot_persist_synthetic_input_observation(tmp_path):
    owner, events = _owner(checkpoint_enabled=True)
    original = RuntimeError("checkpoint_incompatible")
    run_id = generate_run_id()
    request = _request(effective_config=dict(owner.config))
    guard = _durable_checkpoint_guard(tmp_path, owner, request, run_id)

    with (
        patch(
            "tradingagents.execution.runner.checkpoint_access",
            return_value=SimpleNamespace(latest=None),
        ),
        patch(
            "tradingagents.web.fingerprint.build_resume_fingerprint",
            side_effect=original,
        ),
        patch("tradingagents.execution.runner.get_checkpointer") as open_checkpoint,
        pytest.raises(RuntimeError, match="checkpoint_incompatible") as exc_info,
    ):
        AnalysisRunner(owner).run(
            request,
            observation_context=SimpleNamespace(
                observer=SimpleNamespace(run_id=run_id)
            ),
            checkpoint_guard=guard,
        )

    assert exc_info.value is original
    assert events == ["pending", "past_context", "identity"]
    owner.propagator.create_initial_state.assert_not_called()
    open_checkpoint.assert_not_called()


def test_noop_checkpoint_guard_cannot_authorize_graph_execution():
    owner, events = _owner(checkpoint_enabled=True)

    with (
        patch("tradingagents.execution.runner.get_checkpointer") as open_checkpoint,
        pytest.raises(ValueError, match="FingerprintCheckpointGuard"),
    ):
        AnalysisRunner(owner).run(
            _request(effective_config=dict(owner.config)),
            checkpoint_run_id="run-123",
            checkpoint_guard=lambda *_args: None,
        )

    assert events == []
    owner.propagator.create_initial_state.assert_not_called()
    open_checkpoint.assert_not_called()


def test_issued_token_from_non_durable_callback_is_rejected_before_graph_execution():
    owner, events = _owner(checkpoint_enabled=True)
    forged = CheckpointAuthorization._issue(
        run_id="run-123",
        fingerprint_sha256="a" * 64,
        mode="fresh",
    )

    with (
        patch("tradingagents.execution.runner.get_checkpointer") as open_checkpoint,
        pytest.raises(ValueError, match="FingerprintCheckpointGuard"),
    ):
        AnalysisRunner(owner).run(
            _request(effective_config=dict(owner.config)),
            checkpoint_run_id="run-123",
            checkpoint_guard=lambda *_args: forged,
        )

    assert events == []
    owner.propagator.create_initial_state.assert_not_called()
    open_checkpoint.assert_not_called()
