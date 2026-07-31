import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd
import pytest

from tradingagents.observability.events import RunEventDraft
from tradingagents.web.run_models import RunSnapshot, generate_run_id
from tradingagents.web.store import (
    InvalidStorePath,
    RunAlreadyExists,
    RunNotFound,
    RunStore,
    RunStoreError,
)


def _snapshot(*, run_id=None, ticker="AAPL", captured=None, metadata=None):
    snapshot = RunSnapshot.create(
        run_id=run_id or generate_run_id(captured),
        ticker=ticker,
        analysis_date="2026-07-17",
        selected_analysts=("market", "fundamentals"),
        llm_provider="openai",
        quick_think_llm="gpt-quick",
        deep_think_llm="gpt-deep",
        configured_keys={"openai": True},
        metadata=metadata or {},
    )
    if captured is not None:
        timestamp = (
            captured.astimezone(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        snapshot = snapshot.evolve(created_at=timestamp, updated_at=timestamp)
    return snapshot


def test_create_read_and_restart_list_runs_without_database(tmp_path):
    store = RunStore(tmp_path)
    older = _snapshot(captured=datetime(2026, 7, 18, 10, tzinfo=timezone.utc))
    newer = _snapshot(captured=datetime(2026, 7, 18, 11, tzinfo=timezone.utc))
    store.create_run(older)
    store.create_run(newer)

    restarted = RunStore(tmp_path)
    summaries = restarted.list_runs()

    assert [summary.run_id for summary in summaries] == [newer.run_id, older.run_id]
    assert restarted.read_snapshot(older.run_id).ticker == "AAPL"
    with pytest.raises(RunAlreadyExists):
        restarted.create_run(older)


def test_run_directory_is_never_derived_from_ticker_or_traversal(tmp_path):
    store = RunStore(tmp_path)
    snapshot = _snapshot(ticker="../../escape")

    store.create_run(snapshot)

    assert (tmp_path / snapshot.run_id / "run.json").is_file()
    assert not (tmp_path.parent / "escape").exists()
    with pytest.raises(InvalidStorePath):
        store.read_snapshot("../escape")


def test_append_event_is_redacted_durable_and_strictly_sequenced(tmp_path):
    store = RunStore(tmp_path)
    snapshot = store.create_run(_snapshot())

    first = store.append_event(
        RunEventDraft(snapshot.run_id, "run.started", {"run_status": "running"})
    )
    second = store.append_event(
        RunEventDraft(
            snapshot.run_id,
            "future.payload",
            {"headers": {"Authorization": "fake-secret"}, "max_tokens": 100},
        )
    )

    assert (first.sequence, second.sequence) == (1, 2)
    assert second.payload["headers"]["Authorization"] == "[REDACTED]"
    assert second.payload["max_tokens"] == 100
    assert second.payload["redaction_manifest"] == ["headers.authorization"]
    persisted = (tmp_path / snapshot.run_id / "events.jsonl").read_text()
    assert "fake-secret" not in persisted
    assert persisted.count("\n") == 2
    assert store.read_snapshot(snapshot.run_id).latest_sequence == 2
    assert [event.sequence for event in store.read_events(snapshot.run_id)] == [1, 2]
    assert [event.sequence for event in store.read_events(snapshot.run_id, after=1)] == [2]


def test_concurrent_appends_allocate_one_contiguous_sequence(tmp_path):
    store = RunStore(tmp_path)
    snapshot = store.create_run(_snapshot())

    def append(index):
        return store.append_event(
            RunEventDraft(snapshot.run_id, "future.concurrent", {"index": index})
        ).sequence

    with ThreadPoolExecutor(max_workers=8) as pool:
        sequences = list(pool.map(append, range(24)))

    assert sorted(sequences) == list(range(1, 25))
    assert [event.sequence for event in store.read_events(snapshot.run_id)] == list(range(1, 25))


def test_snapshot_cannot_move_behind_durable_event_log(tmp_path):
    store = RunStore(tmp_path)
    snapshot = store.create_run(_snapshot())
    store.append_event(RunEventDraft(snapshot.run_id, "run.started", {"run_status": "running"}))

    with pytest.raises(RunStoreError, match="cannot decrease"):
        store.write_snapshot_atomic(snapshot)


def test_snapshot_metadata_is_redacted_without_mutating_semantic_fields(tmp_path):
    store = RunStore(tmp_path)
    snapshot = _snapshot(
        metadata={"headers.Cookie": "fake-cookie", "max_tokens": 200},
    )

    store.create_run(snapshot)
    raw = (tmp_path / snapshot.run_id / "run.json").read_text()
    loaded = store.read_snapshot(snapshot.run_id)

    assert "fake-cookie" not in raw
    assert loaded.metadata["headers.Cookie"] == "[REDACTED]"
    assert loaded.metadata["max_tokens"] == 200
    assert "metadata.headers.cookie" in loaded.redaction_manifest


def test_content_addressed_artifacts_deduplicate_and_remain_inside_run(tmp_path):
    store = RunStore(tmp_path)
    snapshot = store.create_run(_snapshot())
    value = {"balance_sheet": {"cash": 100}, "TAVILY_API_KEY": "fake-key"}

    first = store.store_artifact(snapshot.run_id, kind="data", value=value)
    second = store.store_artifact(snapshot.run_id, kind="data", value=value)

    assert first == second
    assert (
        store.read_artifact(snapshot.run_id, first.artifact_id)
        == (tmp_path / snapshot.run_id / first.locator).read_bytes()
    )
    assert b"fake-key" not in store.read_artifact(snapshot.run_id, first.artifact_id)
    assert len(list((tmp_path / snapshot.run_id / "data").iterdir())) == 1
    with pytest.raises(InvalidStorePath):
        store.read_artifact(snapshot.run_id, "../data:bad")
    with pytest.raises(RunNotFound):
        store.read_artifact(snapshot.run_id, f"data:{'a' * 64}")


def test_dataframe_artifact_is_redacted_content_addressed_and_readable(tmp_path):
    store = RunStore(tmp_path)
    snapshot = store.create_run(_snapshot())
    frame = pd.DataFrame(
        {"close": [1500.0, 1512.5], "api_key": ["secret-a", "secret-b"]},
        index=pd.Index(["2026-07-28", "2026-07-29"], name="trade_date"),
    )

    artifact = store.store_artifact(snapshot.run_id, kind="data", value=frame)
    content = store.read_artifact(snapshot.run_id, artifact.artifact_id)
    payload = json.loads(content)

    assert hashlib.sha256(content).hexdigest() == artifact.content_sha256
    assert artifact.artifact_id == f"data:{artifact.content_sha256}"
    assert artifact.locator == f"data/{artifact.content_sha256}.json"
    assert payload["$tradingagents:dataframe"]["index"] == [
        "2026-07-28",
        "2026-07-29",
    ]
    assert payload["$tradingagents:dataframe"]["data"] == [
        [1500.0, "[REDACTED]"],
        [1512.5, "[REDACTED]"],
    ]
    assert b"secret-a" not in content
    assert b"secret-b" not in content


def test_unknown_directories_and_files_do_not_become_history(tmp_path):
    (tmp_path / "not-a-run").mkdir()
    (tmp_path / "README.txt").write_text("ignore")
    store = RunStore(tmp_path)

    assert store.list_runs() == []
