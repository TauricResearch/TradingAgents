"""Integration tests for news contracts using previous-run artifacts.

The fixture in ``fixtures/scanner_artifacts`` is a compact slice of a real
2026-04-10 MRVL run: smart-money scanner context, article evidence rows, and
the analyst structured payload captured in the run checkpoint. The LLM is
mocked, but ingestion, fact-checking, rendering, and context formatting use the
real production code paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable

from tradingagents.agents.analysts.news_analyst import create_news_analyst
from tradingagents.agents.managers.news_fact_checker import create_news_fact_checker
from tradingagents.agents.utils.summary_context import (
    build_debate_evidence_brief,
    build_research_packet,
)
from tradingagents.memory.news_evidence import NewsEvidenceStore

pytestmark = pytest.mark.integration


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "scanner_artifacts" / "mrvl_2026_04_10_news_contract.json"
)


class StaticLLM(Runnable):
    """Minimal Runnable that returns one deterministic AIMessage."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.call_count = 0

    def invoke(self, input, config=None, **kwargs):  # noqa: ANN001, ANN201
        self.call_count += 1
        return AIMessage(content=self.content)


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def test_news_contract_pipeline_replays_mrvl_previous_run_artifacts(
    tmp_path,
    monkeypatch,
):
    artifact = _load_fixture()
    store = NewsEvidenceStore(db_path=tmp_path / "news_evidence.sqlite3")
    llm = StaticLLM(json.dumps(artifact["news_analyst_output"]))

    monkeypatch.setattr(
        "tradingagents.agents.analysts.news_analyst.prefetch_tools_parallel",
        lambda _: artifact["prefetched_news_feeds"],
    )

    state = {
        "run_id": artifact["run_id"],
        "company_of_interest": artifact["ticker"],
        "trade_date": artifact["trade_date"],
        "messages": [HumanMessage(content=f"Analyze {artifact['ticker']}.")],
        "scanner_context_packet": artifact["scanner_context_packet"],
    }

    analyst_result = create_news_analyst(llm, evidence_store=store)(state)
    assert llm.call_count == 1
    assert analyst_result["news_report_structured"]["ticker"] == artifact["ticker"]

    fact_checker_result = create_news_fact_checker(evidence_store=store)(
        {**state, **analyst_result}
    )
    contract = fact_checker_result["news_report_structured"]
    expected = artifact["expected_contract"]

    assert contract["status"] == expected["status"]
    assert contract["contract_version"] == "news_report_v1"
    assert contract["ticker"] == artifact["ticker"]
    assert contract["as_of_date"] == artifact["trade_date"]
    assert contract["key_metrics"]["claim_count"] == expected["claim_count"]
    assert contract["key_metrics"]["summary_rows"] == expected["summary_rows"]
    assert contract["key_metrics"]["evidence_ids"] == expected["evidence_ids"]
    assert contract["key_metrics"]["removed_claims"] == 0
    assert all("scan_date" not in claim for claim in contract["claims"])
    assert "Evidence ID: art_7715d24cfa223b67" in fact_checker_result["news_report"]
    assert "stock reached a new 52-week high" in fact_checker_result["news_report"]

    final_state = {**state, **fact_checker_result}
    research_packet = build_research_packet(final_state)
    assert "## News Structured Contract" in research_packet
    assert "- status: completed" in research_packet
    assert "- claim_count: 5" in research_packet
    assert "## News Report" in research_packet
    assert "Marvell Technology shares received an upgrade" in research_packet

    debate_brief = build_debate_evidence_brief(final_state)
    assert "## News" in debate_brief
    assert "- News status: completed" in debate_brief
    assert "- News claims: 5" in debate_brief
