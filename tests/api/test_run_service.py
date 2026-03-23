import pytest
from collections import defaultdict
from unittest.mock import patch, MagicMock
from api.services.run_service import RunService
from api.store.runs_store import RunsStore
from api.models.run import RunConfig, RunStatus


@pytest.fixture
def store(tmp_path):
    return RunsStore(tmp_path / "test.sqlite")


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


def test_completed_run_replays_without_re_running_graph(service, store):
    # Pre-populate a completed run in the store
    run = store.create(RunConfig(ticker="NVDA", date="2026-03-23"))
    store.update_status(run.id, RunStatus.RUNNING)
    store.add_report(run.id, "market_analyst:0", "bullish")
    store.update_status(run.id, RunStatus.COMPLETE)
    store.update_decision(run.id, "BUY")

    with patch("api.services.run_service.TradingAgentsGraph") as MockGraph:
        events = list(service.stream_events(run.id))

    assert MockGraph.call_count == 0  # no agent execution on replay
    agent_completes = [e for e in events if e["event"] == "agent:complete"]
    assert len(agent_completes) == 1
    assert agent_completes[0]["data"]["report"] == "bullish"
    run_complete = next(e for e in events if e["event"] == "run:complete")
    assert run_complete["data"]["decision"] == "BUY"


def test_running_run_returns_in_progress_error(service, store):
    run = store.create(RunConfig(ticker="NVDA", date="2026-03-23"))
    store.update_status(run.id, RunStatus.RUNNING)

    with patch("api.services.run_service.TradingAgentsGraph") as MockGraph:
        events = list(service.stream_events(run.id))

    assert MockGraph.call_count == 0  # no agent execution
    assert len(events) == 1
    assert events[0]["event"] == "run:error"
    assert "already in progress" in events[0]["data"]["message"]


def test_error_run_retries_and_clears_reports(service, store):
    # Simulate a run that failed partway through with a stale report
    run = store.create(RunConfig(ticker="NVDA", date="2026-03-23"))
    store.update_status(run.id, RunStatus.RUNNING)
    store.add_report(run.id, "market_analyst:0", "stale data")
    store.set_error(run.id, "timeout")

    assert store.get(run.id).status == RunStatus.ERROR
    assert store.get(run.id).reports == {"market_analyst:0": "stale data"}

    with patch("api.services.run_service.TradingAgentsGraph") as MockGraph:
        MockGraph.return_value = _mock_graph([("news_analyst", "fresh")], decision="HOLD")
        events = list(service.stream_events(run.id))

    assert MockGraph.call_count == 1  # graph was executed on retry
    final_reports = store.get(run.id).reports
    assert "news_analyst:0" in final_reports
    assert "market_analyst:0" not in final_reports  # stale data cleared on retry


def test_live_run_agent_complete_includes_token_fields(service, store):
    """agent:complete events must include tokens_in and tokens_out."""
    config = RunConfig(ticker="NVDA", date="2026-03-23")
    run = store.create(config)
    with patch("api.services.run_service.TradingAgentsGraph") as MockGraph:
        MockGraph.return_value = _mock_graph([("market_analyst", "bullish")])
        events = list(service.stream_events(run.id))

    complete_events = [e for e in events if e["event"] == "agent:complete"]
    assert len(complete_events) == 1
    data = complete_events[0]["data"]
    assert "tokens_in" in data
    assert "tokens_out" in data
    assert isinstance(data["tokens_in"], int)
    assert isinstance(data["tokens_out"], int)


def test_retry_clears_stale_token_usage(service, store):
    """After an errored run is retried, stale token keys are absent."""
    run = store.create(RunConfig(ticker="NVDA", date="2026-03-23"))
    store.update_status(run.id, RunStatus.RUNNING)
    store.add_token_usage(run.id, "market_analyst:0", {"tokens_in": 500, "tokens_out": 200})
    store.set_error(run.id, "timeout")

    with patch("api.services.run_service.TradingAgentsGraph") as MockGraph:
        MockGraph.return_value = _mock_graph([("news_analyst", "fresh")])
        list(service.stream_events(run.id))

    final = store.get(run.id)
    assert "market_analyst:0" not in final.token_usage  # stale key gone
    assert "news_analyst:0" in final.token_usage         # new key present


def test_replay_attaches_token_data_to_agent_complete(service, store):
    """Replaying a completed run emits agent:complete with token data."""
    run = store.create(RunConfig(ticker="NVDA", date="2026-03-23"))
    store.update_status(run.id, RunStatus.RUNNING)
    store.add_report(run.id, "market_analyst:0", "bullish")
    store.add_token_usage(run.id, "market_analyst:0", {"tokens_in": 1200, "tokens_out": 400})
    store.update_status(run.id, RunStatus.COMPLETE)
    store.update_decision(run.id, "BUY")

    with patch("api.services.run_service.TradingAgentsGraph") as MockGraph:
        events = list(service.stream_events(run.id))

    assert MockGraph.call_count == 0
    complete_events = [e for e in events if e["event"] == "agent:complete"]
    assert len(complete_events) == 1
    assert complete_events[0]["data"]["tokens_in"] == 1200
    assert complete_events[0]["data"]["tokens_out"] == 400


def test_replay_defaults_to_zero_tokens_when_missing(service, store):
    """Replay of a run with no token_usage emits tokens_in=0, tokens_out=0."""
    run = store.create(RunConfig(ticker="NVDA", date="2026-03-23"))
    store.update_status(run.id, RunStatus.RUNNING)
    store.add_report(run.id, "market_analyst:0", "bearish")
    store.update_status(run.id, RunStatus.COMPLETE)
    store.update_decision(run.id, "SELL")
    # No add_token_usage call — simulates old run with no token data

    with patch("api.services.run_service.TradingAgentsGraph"):
        events = list(service.stream_events(run.id))

    complete = next(e for e in events if e["event"] == "agent:complete")
    assert complete["data"]["tokens_in"] == 0
    assert complete["data"]["tokens_out"] == 0
