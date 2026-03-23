import pytest
from api.models.run import RunConfig, RunSummary, RunStatus
from api.models.settings import Settings


def test_run_config_defaults():
    config = RunConfig(ticker="NVDA", date="2024-05-10")
    assert config.llm_provider == "openai"
    assert config.max_debate_rounds == 1


def test_run_summary_has_decision():
    summary = RunSummary(
        id="abc123", ticker="NVDA", date="2024-05-10",
        status=RunStatus.COMPLETE, decision="BUY", created_at="2026-03-23T09:00:00"
    )
    assert summary.decision == "BUY"


def test_settings_defaults():
    s = Settings()
    assert s.deep_think_llm == "gpt-5.2"
    assert s.max_debate_rounds == 1
