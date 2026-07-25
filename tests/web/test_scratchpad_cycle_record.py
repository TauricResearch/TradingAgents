import json

import pytest
from pydantic import ValidationError

from tradingagents.observability.cycle_record import CycleRecord
from tradingagents.observability.observer import DurableRunObserver
from tradingagents.observability.scratchpad import ScratchpadEntry
from tradingagents.web.run_models import RunSnapshot
from tradingagents.web.store import InvalidStorePath, RunStore


def _observer(tmp_path):
    store = RunStore(tmp_path)
    snapshot = RunSnapshot.create(
        ticker="600519.SH",
        analysis_date="2026-07-23",
        llm_provider="openai",
        quick_think_llm="small-model",
        deep_think_llm="deep-model",
        runtime_semantics_hash="a" * 64,
        metadata={"effective_config_artifact_id": "data:" + "b" * 64},
    )
    store.create_run(snapshot)
    return store, snapshot, DurableRunObserver(store, snapshot.run_id)


def test_scratchpad_is_hash_and_reference_only(tmp_path):
    store, snapshot, observer = _observer(tmp_path)

    entry = observer.record_scratchpad(
        event_type="tool_limit",
        detail_code="maximum_tool_calls_reached",
        arguments={"api_key": "top-secret", "symbol": "600519.SH"},
        result={"private": "do not retain this raw result"},
        artifact_ids=("data:" + "c" * 64,),
        metadata={"limit": 8, "attempt": 9},
    )

    entries = store.read_scratchpad(snapshot.run_id)
    assert entries == [entry.model_dump(mode="json")]
    serialized = json.dumps(entries)
    assert "top-secret" not in serialized
    assert "do not retain this raw result" not in serialized
    assert entry.arguments_sha256 and entry.result_sha256
    event = next(event for event in store.read_events(snapshot.run_id) if event.type == "scratchpad.tool_limit")
    assert event.payload["scratchpad_entry_id"] == entry.entry_id
    assert event.payload["thinking_persisted"] is False
    assert entry.event_id == event.event_id
    assert entry.event_sequence == event.sequence


def test_thinking_event_has_an_explicit_no_private_reasoning_boundary(tmp_path):
    _store, snapshot, observer = _observer(tmp_path)

    entry = observer.record_scratchpad(
        event_type="thinking",
        detail_code="private_reasoning_not_persisted",
    )
    assert entry.run_id == snapshot.run_id
    assert entry.thinking_persisted is False

    with pytest.raises(ValidationError, match="private reasoning"):
        ScratchpadEntry.from_values(
            run_id=snapshot.run_id,
            event_type="thinking",
            detail_code="reasoning_omitted",
        )
    with pytest.raises(ValidationError, match="unsafe scratchpad fields"):
        ScratchpadEntry.from_values(
            run_id=snapshot.run_id,
            event_type="context_cleared",
            detail_code="history_cleared",
            metadata={"reasoning": 1},
        )


def test_store_rejects_unsafe_scratchpad_payload(tmp_path):
    store, snapshot, _observer_instance = _observer(tmp_path)

    with pytest.raises(InvalidStorePath, match="invalid or unsafe"):
        store.append_scratchpad(
            snapshot.run_id,
            {
                "run_id": snapshot.run_id,
                "thinking_persisted": True,
            },
        )
    with pytest.raises(InvalidStorePath, match="invalid or unsafe"):
        store.append_scratchpad(
            snapshot.run_id,
            {
                "run_id": snapshot.run_id,
                "thinking_persisted": False,
                "raw_result": "never accept this",
            },
        )


def test_cycle_record_captures_non_secret_spec_and_safe_replay_refs(tmp_path):
    store, snapshot, observer = _observer(tmp_path)
    scratchpad = observer.record_scratchpad(
        event_type="microcompact",
        detail_code="tool_messages_trimmed",
        result={"omitted_messages": 4},
    )

    record, artifact = observer.record_cycle(
        event_sequence_start=1,
        report_artifact_ids=("report-revision:" + "d" * 64,),
        public_context_fact_count=3,
    )

    assert record.run_id == snapshot.run_id
    assert record.query.ticker == "600519.SH"
    assert record.spec_snapshot.selected_analysts == snapshot.selected_analysts
    assert record.spec_snapshot.effective_config_artifact_id == "data:" + "b" * 64
    assert record.scratchpad_entry_ids == (scratchpad.entry_id,)
    assert artifact.kind == "cycle-record"
    stored = json.loads(store.read_artifact(snapshot.run_id, artifact.artifact_id))
    assert stored["cycle_id"] == record.cycle_id
    cycle_event = next(event for event in store.read_events(snapshot.run_id) if event.type == "cycle.recorded")
    assert cycle_event.payload["artifact_id"] == artifact.artifact_id
    assert cycle_event.payload["event_sequence_end"] == record.event_sequence_end


def test_cycle_record_rejects_negative_event_range(tmp_path):
    _store, snapshot, _observer_instance = _observer(tmp_path)
    with pytest.raises(ValidationError):
        CycleRecord.from_run_snapshot(snapshot, event_sequence_start=-1)
