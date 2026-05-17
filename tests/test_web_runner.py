import pytest

from tradingagents.web.models import AnalysisRequest, AnalysisSnapshot, JobStatus
from tradingagents.web.runner import AnalysisAccumulator, AnalysisJobManager, validate_provider_credentials


class FakeMessage:
    id = "message-1"
    content = "Fetching market data"
    tool_calls = [{"name": "get_stock_data", "args": {"symbol": "NVDA"}}]


def _request() -> AnalysisRequest:
    return AnalysisRequest(
        ticker="NVDA",
        analysis_date="2026-04-30",
        output_language="English",
        analysts=["market", "news"],
        research_depth=1,
        llm_provider="openai",
        backend_url="https://api.openai.com/v1",
        quick_think_llm="gpt-5.4-mini",
        deep_think_llm="gpt-5.4",
    )


@pytest.mark.unit
def test_accumulator_tracks_messages_tool_calls_reports_and_statuses():
    accumulator = AnalysisAccumulator(["market", "news"])

    accumulator.update_from_chunk(
        {
            "messages": [FakeMessage()],
            "market_report": "Market report complete.",
        }
    )

    snapshot = accumulator.snapshot()
    assert snapshot.messages[-1].content == "Fetching market data"
    assert snapshot.tool_calls[-1].tool_name == "get_stock_data"
    assert snapshot.report_sections["market_report"] == "Market report complete."
    assert snapshot.agent_status["Market Analyst"] == "completed"
    assert snapshot.agent_status["News Analyst"] == "in_progress"

    accumulator.update_from_chunk(
        {
            "investment_debate_state": {
                "bull_history": "Bull case",
                "bear_history": "Bear case",
                "judge_decision": "Research manager decision",
            },
            "trader_investment_plan": "Trader plan",
            "risk_debate_state": {
                "aggressive_history": "Aggressive risk view",
                "conservative_history": "Conservative risk view",
                "neutral_history": "Neutral risk view",
                "judge_decision": "**Rating**: Buy",
            },
        }
    )

    final_state = {
        "final_trade_decision": "**Rating**: Buy",
        "risk_debate_state": {"judge_decision": "**Rating**: Buy"},
    }
    accumulator.finish(final_state, "Buy", "/tmp/report.md")
    snapshot = accumulator.snapshot({"llm_calls": 2})

    assert snapshot.decision == "Buy"
    assert snapshot.report_path == "/tmp/report.md"
    assert snapshot.stats["llm_calls"] == 2
    assert all(status == "completed" for status in snapshot.agent_status.values())


@pytest.mark.unit
def test_job_queue_runs_single_worker_to_completion():
    observed_statuses = []

    def runner(job):
        observed_statuses.append(job.status)
        job.update_snapshot(AnalysisSnapshot(decision="Hold"))

    manager = AnalysisJobManager(runner=runner)
    try:
        job = manager.enqueue(_request())
        status = manager.wait_for_terminal(job.job_id)
    finally:
        manager.shutdown()

    assert status == JobStatus.COMPLETED
    assert observed_statuses == [JobStatus.RUNNING]
    assert job.view()["snapshot"].decision == "Hold"


@pytest.mark.unit
def test_job_queue_can_cancel_queued_jobs():
    manager = AnalysisJobManager(start_worker=False)
    job = manager.enqueue(_request())

    assert manager.cancel(job.job_id) is True
    assert job.status == JobStatus.CANCELLED


@pytest.mark.unit
def test_job_queue_marks_runner_errors_failed():
    def runner(_job):
        raise RuntimeError("provider failed")

    manager = AnalysisJobManager(runner=runner)
    try:
        job = manager.enqueue(_request())
        status = manager.wait_for_terminal(job.job_id)
    finally:
        manager.shutdown()

    assert status == JobStatus.FAILED
    assert "provider failed" in (job.error or "")


@pytest.mark.unit
def test_validate_provider_credentials_reports_provider_specific_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    request = _request()
    request = AnalysisRequest(
        **{
            **request.to_cache_entry(),
            "llm_provider": "deepseek",
            "quick_think_llm": "deepseek-v4-flash",
            "deep_think_llm": "deepseek-v4-pro",
        }
    )

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        validate_provider_credentials(request)


@pytest.mark.unit
def test_validate_provider_credentials_skips_ollama(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    request = AnalysisRequest(
        **{
            **_request().to_cache_entry(),
            "llm_provider": "ollama",
            "backend_url": "http://localhost:11434/v1",
            "quick_think_llm": "qwen3:latest",
            "deep_think_llm": "qwen3:latest",
        }
    )

    validate_provider_credentials(request)
