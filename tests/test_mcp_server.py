"""MCP server: tool registration, validation, job lifecycle, and data routing."""

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("mcp")

from mcp.shared.memory import create_connected_server_and_client_session

from tradingagents.mcp import runners
from tradingagents.mcp.jobs import JobCancelled, JobManager
from tradingagents.mcp.server import TradingAgentsMCPServer, create_server


def _manager():
    return JobManager(max_workers=1, max_jobs=5)


def _server():
    return TradingAgentsMCPServer(manager=_manager())


class _FakeGraph:
    """The graph surface run_analysis_job uses, without an LLM or a network."""

    def __init__(self, analysts, config=None, debug=False):
        self.analysts = analysts
        self.config = config or {}
        self.propagator = SimpleNamespace(get_graph_args=lambda: {})
        self.recorded = False

    def create_run_state(self, *args, **kwargs):
        return {}

    def begin_checkpoint(self, *args, **kwargs):
        return None

    def checkpoint_input(self, state):
        return state

    def stream_run(self, state, **args):
        yield (
            [],
            {
                "market_report": "MARKET",
                "final_trade_decision": "Rating: Buy",
                "final_rating": "Buy",
            },
        )

    def record_decision(self, *args, **kwargs):
        self.recorded = True

    def clear_checkpoint_on_success(self, *args, **kwargs):
        pass

    def end_checkpoint(self):
        pass

    def save_reports(self, state, ticker, html=True):
        path = Path(self.config["results_dir"]) / "reports" / ticker / "complete_report.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# report", encoding="utf-8")
        return path

    def run_settings(self):
        return {"llm_provider": self.config.get("llm_provider")}


@pytest.mark.unit
def test_tools_are_registered():
    server = create_server(manager=_manager())

    async def run():
        async with create_connected_server_and_client_session(server) as session:
            result = await session.list_tools()
            return {tool.name for tool in result.tools}

    names = asyncio.run(run())
    assert len(names) == 17
    assert {
        "analyze_ticker",
        "run_backtest",
        "get_job_status",
        "get_job_result",
        "get_analysis_report",
        "list_jobs",
        "cancel_job",
        "get_server_info",
        "get_stock_data",
        "get_news",
    } <= names


@pytest.mark.unit
def test_server_info_reports_whether_full_analysis_can_run(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    info = _server().get_server_info()

    assert info["analysis_ready"] is False
    assert info["provider_status"]["deep"]["detail"] == "OPENAI_API_KEY is not set"

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    info = _server().get_server_info()

    assert info["analysis_ready"] is True
    assert info["provider_status"]["quick"]["detail"] == "OPENAI_API_KEY is set"


@pytest.mark.unit
def test_server_info_marks_ollama_as_ready_without_a_key(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "ollama")

    info = _server().get_server_info()

    assert info["analysis_ready"] is True
    assert info["provider_status"]["deep"]["detail"] == "local Ollama needs no API key"


@pytest.mark.unit
def test_analysis_job_completes_and_exposes_its_reports(monkeypatch):
    monkeypatch.setattr(runners, "TradingAgentsGraph", _FakeGraph)
    mcp = _server()

    started = mcp.analyze_ticker(
        "AAPL", trade_date="2020-01-02", analysts=["market"], wait_seconds=10
    )

    assert started["status"] == "succeeded"
    assert started["rating"] == "Buy"
    assert started["decision"] == "Rating: Buy"
    result = mcp.get_job_result(started["job_id"])
    assert result["rating"] == "Buy"
    assert result["sections_available"] == ["market", "decision"]
    assert result["report_path"].endswith("complete_report.md")
    report = mcp.get_analysis_report(started["job_id"], section="market")
    assert report["content"] == "MARKET"
    complete = mcp.get_analysis_report(started["job_id"], section="complete")
    assert complete["content"] == "# report"


@pytest.mark.unit
def test_analysis_rejects_unknown_analysts():
    with pytest.raises(ValueError, match="unknown analyst"):
        _server().analyze_ticker("AAPL", analysts=["bogus"])


@pytest.mark.unit
def test_analysis_rejects_fundamentals_for_crypto():
    with pytest.raises(ValueError, match="not available for crypto"):
        _server().analyze_ticker("BTC-USD", analysts=["fundamentals"])


@pytest.mark.unit
def test_analysis_rejects_a_future_date():
    with pytest.raises(ValueError, match="future"):
        _server().analyze_ticker("AAPL", trade_date="2999-01-01")


@pytest.mark.unit
def test_analysis_rejects_config_keys_that_could_escape_the_run(monkeypatch):
    monkeypatch.setattr(runners, "TradingAgentsGraph", _FakeGraph)
    with pytest.raises(ValueError, match="not allowed"):
        _server().analyze_ticker("AAPL", config={"results_dir": "/tmp/elsewhere"})


@pytest.mark.unit
def test_stock_data_normalizes_the_symbol_before_routing(monkeypatch):
    calls = []

    def fake_route(*args, **kwargs):
        calls.append(args)
        return "DATA"

    monkeypatch.setattr("tradingagents.mcp.server.route_to_vendor", fake_route)

    assert _server().get_stock_data("BTCUSD", "2020-01-01", "2020-01-31") == "DATA"
    assert calls == [("get_stock_data", "BTC-USD", "2020-01-01", "2020-01-31")]


@pytest.mark.unit
def test_job_manager_records_success_and_failure():
    manager = _manager()

    ok = manager.submit("test", lambda job: {"ok": True})
    assert manager.wait(ok.id, 5)
    assert ok.status == "succeeded"
    assert ok.result == {"ok": True}

    def boom(job):
        raise RuntimeError("vendor down")

    failed = manager.submit("test", boom)
    assert manager.wait(failed.id, 5)
    assert failed.status == "failed"
    assert "vendor down" in failed.error


@pytest.mark.unit
def test_job_manager_rejects_more_active_jobs_than_its_limit():
    manager = JobManager(max_workers=1, max_jobs=1)
    release = threading.Event()

    def blocker(job):
        release.wait(5)
        return {}

    manager.submit("block", blocker)
    with pytest.raises(RuntimeError, match="too many active jobs"):
        manager.submit("test", lambda job: {})
    release.set()


@pytest.mark.unit
def test_cancelling_a_queued_job_skips_it():
    manager = JobManager(max_workers=1, max_jobs=5)
    release = threading.Event()

    def blocker(job):
        release.wait(5)
        return {}

    def runner(job):
        if job.cancel_requested:
            raise JobCancelled()
        return {"ran": True}

    manager.submit("block", blocker)
    queued = manager.submit("test", runner)
    manager.cancel(queued.id)
    release.set()

    assert manager.wait(queued.id, 5)
    assert queued.status == "cancelled"


@pytest.mark.unit
def test_unknown_job_is_a_clear_error():
    with pytest.raises(ValueError, match="no job with id"):
        _server().get_job_status("missing")
