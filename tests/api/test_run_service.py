import pytest
from collections import defaultdict
from unittest.mock import patch, MagicMock
from api.services.run_service import RunService
from api.store.runs_store import RunsStore
from api.models.run import RunConfig, RunStatus


@pytest.fixture
def store():
    return RunsStore()


@pytest.fixture
def service(store):
    return RunService(store)


def _mock_graph(stream_yields, decision="BUY"):
    """Return a mock TradingAgentsGraph instance for stream_propagate tests."""
    mock = MagicMock()
    mock.stream_propagate.return_value = iter(stream_yields)
    mock._last_decision = decision
    return mock


def test_emits_agent_start_and_complete_per_step(service, store):
    config = RunConfig(ticker="NVDA", date="2026-03-23")
    run = store.create(config)
    yields = [
        ("market_analyst", "bullish"),
        ("news_analyst", "stable"),
    ]
    with patch("api.services.run_service.TradingAgentsGraph") as MockGraph:
        MockGraph.return_value = _mock_graph(yields)
        events = list(service.stream_events(run.id))

    starts    = [e for e in events if e["event"] == "agent:start"]
    completes = [e for e in events if e["event"] == "agent:complete"]
    assert len(starts) == 2
    assert len(completes) == 2
    assert starts[0]["data"]["step"] == "market_analyst"
    assert starts[0]["data"]["turn"] == 0
    assert completes[0]["data"]["report"] == "bullish"


def test_turn_increments_for_repeat_steps(service, store):
    config = RunConfig(ticker="NVDA", date="2026-03-23")
    run = store.create(config)
    yields = [
        ("bull_researcher", "bull round 1"),
        ("bear_researcher", "bear round 1"),
        ("bull_researcher", "bull round 2"),
    ]
    with patch("api.services.run_service.TradingAgentsGraph") as MockGraph:
        MockGraph.return_value = _mock_graph(yields)
        events = list(service.stream_events(run.id))

    bull_completes = [e for e in events
                      if e["event"] == "agent:complete" and e["data"]["step"] == "bull_researcher"]
    assert len(bull_completes) == 2
    assert bull_completes[0]["data"]["turn"] == 0
    assert bull_completes[1]["data"]["turn"] == 1


def test_run_complete_emitted_with_decision(service, store):
    config = RunConfig(ticker="NVDA", date="2026-03-23")
    run = store.create(config)
    with patch("api.services.run_service.TradingAgentsGraph") as MockGraph:
        MockGraph.return_value = _mock_graph([("trader", "buy signal")], decision="SELL")
        events = list(service.stream_events(run.id))

    complete = next(e for e in events if e["event"] == "run:complete")
    assert complete["data"]["decision"] == "SELL"


def test_store_status_set_to_complete(service, store):
    config = RunConfig(ticker="NVDA", date="2026-03-23")
    run = store.create(config)
    with patch("api.services.run_service.TradingAgentsGraph") as MockGraph:
        MockGraph.return_value = _mock_graph([])
        list(service.stream_events(run.id))

    assert store.get(run.id).status == RunStatus.COMPLETE


def test_error_during_stream_emits_run_error(service, store):
    config = RunConfig(ticker="NVDA", date="2026-03-23")
    run = store.create(config)

    def bad_stream(*args, **kwargs):
        yield ("market_analyst", "ok")
        raise RuntimeError("LLM network error")

    with patch("api.services.run_service.TradingAgentsGraph") as MockGraph:
        mock = MagicMock()
        mock.stream_propagate.side_effect = bad_stream
        MockGraph.return_value = mock
        events = list(service.stream_events(run.id))

    error_events = [e for e in events if e["event"] == "run:error"]
    assert len(error_events) == 1
    assert "LLM network error" in error_events[0]["data"]["message"]
    # Also verify the store recorded the error
    assert store.get(run.id).error is not None
    assert "LLM network error" in store.get(run.id).error


def test_selected_analysts_passed_to_graph(service, store):
    config = RunConfig(ticker="NVDA", date="2026-03-23",
                       enabled_analysts=["market", "news"])
    run = store.create(config)
    with patch("api.services.run_service.TradingAgentsGraph") as MockGraph:
        MockGraph.return_value = _mock_graph([])
        list(service.stream_events(run.id))

    call_kwargs = MockGraph.call_args.kwargs
    assert call_kwargs.get("selected_analysts") == ["market", "news"]
