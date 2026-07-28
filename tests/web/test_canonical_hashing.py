from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Annotated

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from typing_extensions import TypedDict

from tradingagents.agents.utils.agent_states import AgentState, merge_observation_commits
from tradingagents.observability.canonical import (
    AGENT_STATE_SCHEMA_SHA256,
    APPLICATION_STATE_FIELDS,
    BusinessStateProjectionV1,
    UnsupportedCanonicalValue,
    business_delta_sha256,
    canonical_business_value,
    canonical_sha256,
    derive_application_state_schema,
    pending_writes_touch_business_state,
    project_business_delta,
)
from tradingagents.observability.events import ObservationCommitV1

HASH = "a" * 64


class Rating(Enum):
    HOLD = "hold"


@dataclass(frozen=True)
class Point:
    x: int
    y: int


def test_canonical_value_freezes_unordered_special_and_declared_values():
    value = {
        "map": {"z": 1, "a": 2},
        "set": {"beta", "alpha"},
        "bytes": b"\x00\xff",
        "date": date(2026, 7, 18),
        "datetime": datetime(2026, 7, 18, 12, 30, tzinfo=timezone.utc),
        "floats": [1.0, -0.0, float("nan"), float("inf"), float("-inf")],
        "enum": Rating.HOLD,
        "dataclass": Point(2, 3),
    }

    canonical = canonical_business_value(value)

    assert canonical.bytes == canonical_business_value(value).bytes
    assert canonical.sha256 == "2851823b82cd4bbe2be94acfb47d205877e2a0cc31df46c7d636fe19f861e8dc"


def test_langchain_messages_and_tool_calls_have_stable_hashes():
    messages = [
        HumanMessage(content="Analyze AAPL", id="human-1"),
        AIMessage(
            content="",
            id="ai-1",
            tool_calls=[{"name": "get_stock_data", "args": {"symbol": "AAPL"}, "id": "call-1"}],
        ),
        ToolMessage(content="close=210", tool_call_id="call-1", id="tool-1"),
    ]

    assert canonical_sha256(messages) == "82a80ca5bded148602b449fcdb0194ea4c4654cce4a3bd60f6029837f7cc0716"


def test_redaction_happens_before_hashing():
    first = canonical_business_value({"OPENAI_API_KEY": "first", "value": 1})
    second = canonical_business_value({"OPENAI_API_KEY": "second", "value": 1})

    assert first.sha256 == second.sha256
    assert first.redaction.redacted is True
    assert b"first" not in first.bytes
    assert b"second" not in second.bytes


def test_business_projection_selects_only_declared_agent_state_channels():
    base = {
        "company_of_interest": "AAPL",
        "messages": [HumanMessage(content="start")],
        "branch:to:Market Analyst": "internal-a",
        "__pregel_tasks": ["internal"],
        "_observation_commits": {"task": "token"},
    }
    changed_internal = {
        **base,
        "branch:to:Market Analyst": "internal-b",
        "__pregel_tasks": ["different"],
    }

    first = BusinessStateProjectionV1.from_channel_values(base)
    second = BusinessStateProjectionV1.from_channel_values(changed_internal)

    assert "messages" in APPLICATION_STATE_FIELDS
    assert APPLICATION_STATE_FIELDS == (
        "allowed_actions",
        "asset_type",
        "canonical_company_profile",
        "clamp_events",
        "company_of_interest",
        "context_compaction_facts",
        "evidence_ledger",
        "evidence_ledger_artifact_id",
        "evidence_report",
        "evidence_status",
        "feature_contributions",
        "final_trade_decision",
        "fundamentals_report",
        "instrument_context",
        "investment_debate_state",
        "investment_plan",
        "market_report",
        "messages",
        "methodology_reports",
        "news_report",
        "past_context",
        "portfolio_context",
        "risk_debate_state",
        "sender",
        "sentiment_report",
        "trade_date",
        "trader_investment_plan",
    )
    assert "_observation_commits" not in APPLICATION_STATE_FIELDS
    assert set(first.values) == {"company_of_interest", "messages"}
    assert first.sha256 == second.sha256
    assert len(AGENT_STATE_SCHEMA_SHA256) == 64


def test_agent_state_field_or_nested_type_change_changes_schema_hash():
    class ExtendedState(AgentState):
        audit_label: Annotated[str, "new application field"]

    class Nested(TypedDict):
        value: int

    class StateWithNested(AgentState):
        nested: Nested

    base = derive_application_state_schema(AgentState)
    extended = derive_application_state_schema(ExtendedState)
    nested = derive_application_state_schema(StateWithNested)

    assert extended.sha256 != base.sha256
    assert nested.sha256 != base.sha256
    assert "audit_label" in extended.application_fields


def test_business_delta_rejects_observer_keys_but_removes_reserved_commit_map():
    delta = {"market_report": "report", "_observation_commits": {"task": "token"}}

    assert project_business_delta(delta) == {"market_report": "report"}
    assert business_delta_sha256(delta) == canonical_sha256({"market_report": "report"})
    with pytest.raises(UnsupportedCanonicalValue, match="observer_only"):
        project_business_delta({"market_report": "report", "observer_only": True})


def test_pending_write_mutation_checks_ignore_framework_channels():
    internal = [("task", "branch:to:Market Analyst", "value")]
    application = [*internal, ("task", "market_report", "report")]

    assert pending_writes_touch_business_state(internal) is False
    assert pending_writes_touch_business_state(application) is True


def test_unsupported_values_and_non_string_mapping_keys_fail_before_hashing():
    with pytest.raises(UnsupportedCanonicalValue, match="unsupported canonical value"):
        canonical_sha256(object())
    with pytest.raises(UnsupportedCanonicalValue, match="mapping keys"):
        canonical_sha256({1: "not allowed"})


def test_parallel_observation_commit_reducer_preserves_tokens_and_rejects_conflicts():
    first = ObservationCommitV1(1, 1, HASH, "input", "task-1", 0, HASH)
    second = ObservationCommitV1(1, 1, HASH, "role", "task-2", 1, HASH, "Market Analyst")

    first_value = first.as_dict()
    second_value = second.as_dict()
    merged = merge_observation_commits({"task-1": first_value}, {"task-2": second_value})

    assert merged == {"task-1": first_value, "task-2": second_value}
    with pytest.raises(ValueError, match="conflicting observation commit"):
        merge_observation_commits(
            {"task-1": first_value},
            {
                "task-1": ObservationCommitV1(
                    1, 1, HASH, "input", "task-1", 1, HASH
                ).as_dict()
            },
        )


def test_rfc8785_unicode_order_and_integer_domain_are_explicit():
    canonical = canonical_business_value({"\ue000": 2, "😀": 1})

    assert canonical.bytes == '{"😀":1,"":2}'.encode()
    with pytest.raises(UnsupportedCanonicalValue, match="RFC 8785"):
        canonical_sha256(2**53)
