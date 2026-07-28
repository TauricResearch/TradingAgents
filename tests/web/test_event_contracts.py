from datetime import datetime, timezone

import pytest

from tradingagents.analysts import ANALYST_CONFIG
from tradingagents.execution.models import (
    AnalysisCancelled,
    AnalysisRequest,
    AnalysisResult,
    CancellationToken,
)
from tradingagents.observability.events import (
    ArtifactRef,
    InvalidEvent,
    ObservationCommitV1,
    PersistedEvent,
    RunEventDraft,
)
from tradingagents.observability.roles import (
    ROLE_REGISTRY,
    ROLES_BY_ACTOR_ID,
    ROLES_BY_NODE_ID,
    role_instance_id,
)

pytestmark = pytest.mark.unit
HASH = "a" * 64


def test_role_registry_contains_exactly_thirteen_unique_roles_and_icons():
    assert len(ROLE_REGISTRY) == 13
    assert len(ROLES_BY_ACTOR_ID) == 13
    assert len(ROLES_BY_NODE_ID) == 13
    assert len({role.icon_id for role in ROLE_REGISTRY}) == 13
    assert set(ROLES_BY_ACTOR_ID) == {
        "analyst.market",
        "analyst.sentiment",
        "analyst.news",
        "analyst.fundamentals",
        "evidence.steward",
        "researcher.bull",
        "researcher.bear",
        "manager.research",
        "trader",
        "risk.aggressive",
        "risk.neutral",
        "risk.conservative",
        "manager.portfolio",
    }
    assert role_instance_id("run_1", "researcher.bull") == "run_1:researcher.bull"


def test_selectable_observability_roles_are_derived_from_analyst_config():
    selectable = tuple(role for role in ROLE_REGISTRY if role.analyst_key is not None)

    assert tuple(role.analyst_key for role in selectable) == tuple(
        definition.key for definition in ANALYST_CONFIG
    )
    assert tuple(role.node_id for role in selectable) == tuple(
        definition.node_id for definition in ANALYST_CONFIG
    )


def test_artifact_and_observation_commit_are_immutable_validated_contracts():
    artifact = ArtifactRef("data:a", "data", "application/json", HASH, 12, "data/a.json")
    commit = ObservationCommitV1(
        serializer_version=1,
        projection_version=1,
        agent_state_schema_sha256=HASH,
        task_kind="tool",
        graph_task_id="task-1",
        graph_step=2,
        node_id="tools_market",
        turn_id="turn-1",
        business_delta_sha256=HASH,
        tool_call_ids=("call-1", "call-2"),
    )

    assert artifact.byte_size == 12
    assert commit.as_dict()["tool_call_ids"] == ("call-1", "call-2")
    with pytest.raises(InvalidEvent, match="node_id"):
        ObservationCommitV1(1, 1, HASH, "role", "task", 1, HASH)


def test_persisted_event_is_derived_from_draft_with_required_envelope():
    draft = RunEventDraft(
        run_id="run_1",
        type="run.started",
        payload={"run_status": "running"},
    )

    event = PersistedEvent.from_draft(
        draft,
        3,
        datetime(2026, 7, 18, 12, 30, tzinfo=timezone.utc),
    )

    assert event.event_id == "run_1:3"
    assert event.sequence == 3
    assert event.timestamp == "2026-07-18T12:30:00.000Z"
    assert event.as_dict()["schema_version"] == 1


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        ("run.completed", {"run_status": "completed"}),
        ("graph.task_started", {"graph_task_id": "task", "graph_step": 1}),
        ("role.status_changed", {"role_instance_id": "role"}),
        ("turn.started", {"turn_id": "turn"}),
        ("model.started", {"turn_id": "turn"}),
        ("input.prompt_snapshot", {"turn_id": "turn"}),
        ("tool.requested", {"turn_id": "turn"}),
        ("data.progress", {"turn_id": "turn"}),
        ("data.cache_hit", {"turn_id": "turn"}),
        ("report.updated", {"turn_id": "turn"}),
        ("artifact.written", {"artifact_id": "artifact"}),
        ("stats.updated", {}),
    ],
)
def test_event_families_reject_missing_relationship_identifiers(event_type, payload):
    with pytest.raises(InvalidEvent, match="requires|missing"):
        RunEventDraft("run_1", event_type, payload)


def test_unknown_future_event_remains_replayable():
    event = PersistedEvent.from_draft(
        RunEventDraft("run_1", "future.observation", {"opaque": True}),
        1,
    )

    assert event.type == "future.observation"
    assert event.payload == {"opaque": True}


def test_requested_tool_cannot_claim_an_execution_identifier():
    payload = {
        "turn_id": "turn",
        "graph_task_id": "task",
        "attempt_id": "attempt",
        "tool_call_id": "call",
        "tool_name": "get_stock_data",
        "arguments": {},
        "tool_execution_id": "execution",
    }
    with pytest.raises(InvalidEvent, match="cannot contain"):
        RunEventDraft("run_1", "tool.requested", payload)


def test_analysis_request_result_and_cancellation_are_distinct_contracts():
    request = AnalysisRequest("AAPL", "2026-07-17", selected_analysts=("market",))
    result = AnalysisResult({"final_trade_decision": "Hold"}, "HOLD")
    token = CancellationToken()

    assert request.asset_type == "stock"
    assert result.final_signal == "HOLD"
    token.cancel()
    with pytest.raises(AnalysisCancelled) as exc_info:
        token.raise_if_cancelled({"market_report": "partial"})
    assert exc_info.value.partial_state == {"market_report": "partial"}
