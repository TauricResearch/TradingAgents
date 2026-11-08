import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from tradingagents.usage import UsageCallback, UsageStore
from webapp.app import create_app


@pytest.fixture
def store(tmp_path, monkeypatch):
    from tradingagents.default_config import DEFAULT_CONFIG
    monkeypatch.setitem(DEFAULT_CONFIG, "usage_db_path", str(tmp_path / "usage.sqlite"))
    return UsageStore()


def record(store, cached=200, missing=False, failed=False):
    callback = UsageCallback({"run_id": "run1", "ticker": "NVDA", "source": "web"}, "test", "model", store)
    ident = uuid.uuid4()
    callback.on_chat_model_start({}, [], run_id=ident, metadata={"langgraph_node": "market"})
    callback.on_chat_model_start({}, [], run_id=ident)  # duplicate delivery
    if failed:
        callback.on_llm_error(RuntimeError("secret"), run_id=ident)
    else:
        message = AIMessage(content="secret", usage_metadata=None if missing else {
            "input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100,
            "input_token_details": {"cache_read": cached}})
        response = LLMResult(generations=[[ChatGeneration(message=message)]])
        callback.on_llm_end(response, run_id=ident)
        callback.on_llm_end(response, run_id=ident)
    return ident


def test_pricing_cache_idempotence_and_history(store):
    store.set_price("test", "model", 2, 10, 0.5)
    record(store)
    store.set_price("test", "model", 200, 1000, 50)
    report = UsageStore(store.path).report()
    assert report["totals"]["calls"] == 1
    assert report["totals"]["tokens_in"] == 1000
    assert report["totals"]["cost_usd"] == pytest.approx(0.0027)
    assert report["calls"][0]["agent"] == "market"
    assert "secret" not in str(report)


def test_unknown_usage_errors_and_unfinished_are_not_free(store):
    record(store, missing=True)
    record(store, failed=True)
    UsageCallback({}, "test", "model", store).on_chat_model_start({}, [], run_id=uuid.uuid4())
    report = store.report()
    assert report["totals"]["unknown_usage"] == 3
    assert report["totals"]["unpriced"] == 3
    assert report["totals"]["failed"] == 1
    assert report["totals"]["unfinished"] == 1
    assert all(row["cost_usd"] is None for row in report["calls"])


def test_parallel_calls(store):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: record(store), range(16)))
    assert store.report()["totals"]["calls"] == 16
    assert store.report()["totals"]["tokens_in"] == 16000


def test_usage_api_prices_filters_csv_and_validation(store):
    client = TestClient(create_app())
    assert client.get("/api/usage").json()["totals"]["calls"] == 0
    assert client.put("/api/usage/prices", json={"provider": "test", "model": "model", "input_rate": 2, "output_rate": 10, "cache_rate": 0.5}).status_code == 200
    record(store)
    assert client.get("/api/usage", params={"ticker": "nvda"}).json()["totals"]["calls"] == 1
    assert client.get("/api/usage", params={"ticker": "AAPL"}).json()["totals"]["calls"] == 0
    assert client.get("/api/usage", params={"start": "2999-01-01"}).json()["totals"]["calls"] == 0
    assert client.get("/api/usage", params={"start": "2026-10-02", "end": "2026-10-01"}).status_code == 422
    assert client.get("/api/usage", params={"start": "invalid"}).status_code == 422
    assert client.put("/api/usage/prices", json={"provider": "test", "model": "model", "input_rate": -1, "output_rate": 1}).status_code == 422
    assert "NVDA" in client.get("/api/usage.csv").text
    assert client.get("/api/usage/prices").json()["prices"][0]["input_rate"] == 2
    assert client.get("/api/usage", headers={"host": "evil.example"}).status_code == 403


def test_store_failure_does_not_fail_analysis(tmp_path):
    callback = UsageCallback({}, "test", "model", UsageStore(tmp_path))
    callback.on_chat_model_start({}, [], run_id=uuid.uuid4())


def test_cached_tokens_need_cache_price(store):
    store.set_price("test", "model", 2, 10)
    record(store)
    assert store.report()["calls"][0]["cost_usd"] is None


def test_callback_receives_real_langchain_events(store):
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    callback = UsageCallback({"run_id": "real-events", "ticker": "AAPL"}, "test", "model", store)
    message = AIMessage(content="ok", usage_metadata={
        "input_tokens": 7, "output_tokens": 3, "total_tokens": 10})
    model = FakeMessagesListChatModel(responses=[message], callbacks=[callback])
    model.invoke("hello", config={"metadata": {"langgraph_node": "News Analyst"}})
    report = store.report()
    assert report["totals"]["calls"] == 1
    assert report["totals"]["tokens_in"] == 7
    assert report["calls"][0]["agent"] == "News Analyst"
    assert report["calls"][0]["status"] == "completed"


def test_price_snapshot_is_taken_at_start(store):
    store.set_price("test", "model", 2, 10)
    callback = UsageCallback({}, "test", "model", store)
    ident = uuid.uuid4()
    callback.on_chat_model_start({}, [], run_id=ident)
    store.set_price("test", "model", 200, 1000)
    callback.on_llm_end(LLMResult(generations=[[ChatGeneration(message=AIMessage(
        content="ok", usage_metadata={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100}))]]), run_id=ident)
    assert store.report()["totals"]["cost_usd"] == pytest.approx(0.003)


def test_cache_creation_charge_is_not_silently_omitted(store):
    store.set_price("test", "model", 2, 10)
    callback = UsageCallback({}, "test", "model", store)
    ident = uuid.uuid4()
    callback.on_chat_model_start({}, [], run_id=ident)
    callback.on_llm_end(LLMResult(generations=[[ChatGeneration(message=AIMessage(
        content="ok", usage_metadata={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100,
                                      "input_token_details": {"cache_creation": 500}}))]]), run_id=ident)
    assert store.report()["calls"][0]["cost_usd"] is None
