"""Durable provenance tests for routed and direct provider calls."""

import json
import time
from types import SimpleNamespace

from tradingagents.dataflows import consistency, evidence, interface
from tradingagents.dataflows.config import set_config
from tradingagents.observability.observer import DurableRunObserver
from tradingagents.observability.provenance import (
    capture_direct_call,
    capture_vendor_raw,
)
from tradingagents.web.run_models import RunSnapshot
from tradingagents.web.store import RunStore


def _observer(tmp_path, *, actor_id="analyst.fundamentals"):
    store = RunStore(tmp_path)
    snapshot = RunSnapshot.create(ticker="AAPL", analysis_date="2026-07-18")
    store.create_run(snapshot)
    observer = DurableRunObserver(store, snapshot.run_id)
    turn = observer.start_turn(
        actor_id=actor_id,
        graph_task_id="task-data",
        graph_step=1,
        turn_index=1,
    )
    return store, snapshot, observer, turn


def _artifact_json(store, run_id, artifact_id):
    return json.loads(store.read_artifact(run_id, artifact_id))


def _events_of_type(store, run_id, event_type):
    return [event for event in store.read_events(run_id) if event.type == event_type]


def test_observed_vendor_success_joins_raw_output_and_normalized_artifacts(
    monkeypatch,
    tmp_path,
):
    raw_payload = {"transport": "provider-json", "total_assets": 1234}
    vendor_output = {"adapter": "vendor-output", "total_assets": 1234}

    def balance_sheet_adapter(*_args, **_kwargs):
        capture_vendor_raw(raw_payload, metadata={"transport": "https-json"})
        return vendor_output

    monkeypatch.setattr(interface, "get_vendor", lambda _category, method=None: "yfinance")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_balance_sheet",
        {"yfinance": balance_sheet_adapter},
    )
    store, snapshot, observer, turn = _observer(tmp_path)

    with observer.invocation_scope(turn, graph_task_id="task-data", graph_step=1):
        result = interface.route_to_vendor("get_balance_sheet", "AAPL", "quarterly")

    assert result == vendor_output
    progress = _events_of_type(store, snapshot.run_id, "data.progress")
    completed = _events_of_type(store, snapshot.run_id, "data.completed")
    assert len(progress) == 1
    assert len(completed) == 1
    assert progress[0].payload["vendor_call_id"] == completed[0].payload["vendor_call_id"]

    payload = completed[0].payload
    assert payload["raw_capture_status"] == "captured"
    assert payload["raw_metadata"] == [{"transport": "https-json"}]
    assert len(payload["raw_artifact_ids"]) == 1
    assert _artifact_json(
        store,
        snapshot.run_id,
        payload["raw_artifact_ids"][0],
    ) == raw_payload
    assert _artifact_json(
        store,
        snapshot.run_id,
        payload["vendor_output_artifact_id"],
    ) == vendor_output
    assert _artifact_json(
        store,
        snapshot.run_id,
        payload["normalized_artifact_id"],
    ) == vendor_output


def test_adapter_without_raw_hook_is_marked_unavailable(monkeypatch, tmp_path):
    vendor_output = {"revenue": 99, "currency": "USD"}

    monkeypatch.setattr(interface, "get_vendor", lambda _category, method=None: "yfinance")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_income_statement",
        {"yfinance": lambda *_args, **_kwargs: vendor_output},
    )
    store, snapshot, observer, turn = _observer(tmp_path)

    with observer.invocation_scope(turn, graph_task_id="task-data", graph_step=1):
        interface.route_to_vendor("get_income_statement", "AAPL", "annual")

    completed = _events_of_type(store, snapshot.run_id, "data.completed")
    assert len(completed) == 1
    assert completed[0].payload["raw_capture_status"] == "unavailable"
    assert completed[0].payload["raw_artifact_ids"] == []


def test_failed_vendor_then_fallback_preserves_attempt_lineage_without_secret(
    monkeypatch,
    tmp_path,
):
    secret = "credential-value-that-must-not-persist"

    def failing_vendor(*_args, **_kwargs):
        raise ValueError(f"provider rejected credential {secret}")

    def succeeding_vendor(*_args, **_kwargs):
        capture_vendor_raw({"provider": "fallback", "pe_ratio": 21.5})
        return {"pe_ratio": 21.5, "currency": "USD"}

    monkeypatch.setenv("TAVILY_API_KEY", secret)
    monkeypatch.setattr(
        interface,
        "get_vendor",
        lambda _category, method=None: "alpha_vantage,yfinance",
    )
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_fundamentals",
        {
            "alpha_vantage": failing_vendor,
            "yfinance": succeeding_vendor,
        },
    )
    store, snapshot, observer, turn = _observer(tmp_path)

    with observer.invocation_scope(turn, graph_task_id="task-data", graph_step=1):
        result = interface.route_to_vendor("get_fundamentals", "AAPL")

    assert result["pe_ratio"] == 21.5
    failures = _events_of_type(store, snapshot.run_id, "data.failed")
    completed = _events_of_type(store, snapshot.run_id, "data.completed")
    assert len(failures) == 1
    assert len(completed) == 1
    failed_call_id = failures[0].payload["vendor_call_id"]
    completed_call_id = completed[0].payload["vendor_call_id"]
    assert completed[0].payload["origin_vendor_call_ids"] == [
        failed_call_id,
        completed_call_id,
    ]

    failure_artifact = store.read_artifact(
        snapshot.run_id,
        failures[0].payload["error_artifact_id"],
    )
    assert secret.encode() not in failure_artifact
    assert _artifact_json(
        store,
        snapshot.run_id,
        failures[0].payload["error_artifact_id"],
    )["error_type"] == "ValueError"


def test_direct_call_records_invocation_path_and_artifacts(tmp_path):
    raw_payload = {"messages": [{"body": "bullish"}], "source": "stocktwits"}
    normalized = {"bullish": 1, "bearish": 0}

    def direct_adapter(symbol):
        assert symbol == "AAPL"
        capture_vendor_raw(raw_payload, metadata={"endpoint": "symbol-stream"})
        return normalized

    store, snapshot, observer, turn = _observer(tmp_path, actor_id="analyst.sentiment")

    with observer.invocation_scope(turn, graph_task_id="task-data", graph_step=1):
        result = capture_direct_call(
            invocation_path="sentiment.stocktwits",
            method="get_stocktwits_sentiment",
            vendor="stocktwits",
            function=direct_adapter,
            args=("AAPL",),
        )

    assert result == normalized
    completed = _events_of_type(store, snapshot.run_id, "data.completed")
    assert len(completed) == 1
    payload = completed[0].payload
    assert payload["invocation_path"] == "direct:sentiment.stocktwits"
    assert payload["raw_capture_status"] == "captured"
    assert _artifact_json(
        store,
        snapshot.run_id,
        payload["raw_artifact_ids"][0],
    ) == raw_payload
    assert _artifact_json(
        store,
        snapshot.run_id,
        payload["vendor_output_artifact_id"],
    ) == normalized
    assert _artifact_json(
        store,
        snapshot.run_id,
        payload["normalized_artifact_id"],
    ) == normalized


def test_evidence_tavily_enrichment_uses_direct_provenance(monkeypatch, tmp_path):
    response_payload = {
        "results": [
            {
                "title": "AAPL reports earnings",
                "url": "https://example.com/earnings",
                "content": "Revenue increased.",
            }
        ]
    }
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-secret")
    monkeypatch.setattr(
        evidence,
        "_build_enrichment_queries",
        lambda _profile: [{"query": "AAPL earnings"}],
    )
    monkeypatch.setattr(
        evidence.requests,
        "post",
        lambda *_args, **_kwargs: SimpleNamespace(
            status_code=200,
            json=lambda: response_payload,
        ),
    )
    monkeypatch.setattr(evidence, "_save_enrichment_raw_response", lambda *_args: None)
    store, snapshot, observer, turn = _observer(tmp_path, actor_id="evidence.steward")

    with observer.invocation_scope(turn, graph_task_id="task-data", graph_step=1):
        items = evidence._run_tavily_enrichment(
            {"ticker": "AAPL", "name": "Apple"},
            "2026-07-18",
            1,
            time.monotonic() + 10,
        )

    assert items[0]["title"] == "AAPL reports earnings"
    completed = _events_of_type(store, snapshot.run_id, "data.completed")
    assert len(completed) == 1
    payload = completed[0].payload
    assert payload["invocation_path"] == "direct:evidence.enrichment.fallback.1"
    assert payload["raw_capture_status"] == "captured"
    assert _artifact_json(
        store,
        snapshot.run_id,
        payload["raw_artifact_ids"][0],
    ) == response_payload
    assert _artifact_json(
        store,
        snapshot.run_id,
        payload["normalized_artifact_id"],
    )[0]["title"] == "AAPL reports earnings"


def test_dynamic_evidence_llm_receives_active_observer_callback(monkeypatch, tmp_path):
    captured = {}
    llm = object()

    def fake_factory(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(get_llm=lambda: llm)

    set_config(
        {
            "llm_provider": "openai",
            "quick_think_llm": "test-model",
            "backend_url": "http://localhost:1234/v1",
        }
    )
    monkeypatch.setattr("tradingagents.llm_clients.create_llm_client", fake_factory)
    _store, _snapshot, observer, turn = _observer(tmp_path, actor_id="evidence.steward")

    with observer.invocation_scope(turn, graph_task_id="task-data", graph_step=1):
        created = consistency.create_llm_from_config()

    assert created is llm
    assert captured["callbacks"] == [observer]
