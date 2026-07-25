from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.schemas import (
    PortfolioRating,
    ResearchDelegationTask,
    ResearchPlan,
)
from tradingagents.research.delegation import (
    DelegatedResearchOutput,
    ResearchDelegationError,
    ResearchDelegationExecutor,
    ResearchDelegationRequest,
    build_default_report_lens_delegation,
)


def _output(arguments):
    return DelegatedResearchOutput(
        public_summary=f"Public finding for {arguments['ticker']}",
        citations=("https://example.test/source",),
    )


def test_executor_runs_only_allowlisted_read_only_tools_and_keeps_public_output():
    executor = ResearchDelegationExecutor({"company_filing_lookup": _output}, max_parallel=2)

    results = executor.execute(
        [
            ResearchDelegationRequest(
                request_id="valuation",
                subquestion="What did the latest filing say about valuation?",
                tool_name="company_filing_lookup",
                arguments={"ticker": "600519.SH"},
            ),
            ResearchDelegationRequest(
                request_id="industry",
                subquestion="What did the filing say about industry demand?",
                tool_name="company_filing_lookup",
                arguments={"ticker": "600519.SH"},
            ),
        ]
    )

    assert [result.status for result in results] == ["completed", "completed"]
    assert all(result.depth == 1 for result in results)
    assert all("Public finding" in result.public_summary for result in results)
    assert all(result.citations == ("https://example.test/source",) for result in results)


def test_executor_fans_out_independent_requests_in_parallel():
    barrier = threading.Barrier(2)

    def parallel_tool(arguments):
        try:
            barrier.wait(timeout=1)
            summary = f"Parallel public finding for {arguments['ticker']}"
        except threading.BrokenBarrierError:
            summary = "Tool was not run in parallel"
        return DelegatedResearchOutput(public_summary=summary)

    executor = ResearchDelegationExecutor({"filing": parallel_tool}, max_parallel=2)
    results = executor.execute(
        [
            ResearchDelegationRequest("one", "First independent question", "filing", {"ticker": "A"}),
            ResearchDelegationRequest("two", "Second independent question", "filing", {"ticker": "B"}),
        ]
    )

    assert all("Parallel public finding" in result.public_summary for result in results)


def test_executor_rejects_unknown_and_recursive_delegation_before_calling_a_tool():
    called = threading.Event()

    def tool(_arguments):
        called.set()
        return DelegatedResearchOutput(public_summary="Should not run")

    executor = ResearchDelegationExecutor({"filing": tool})
    with pytest.raises(ResearchDelegationError, match="allowlisted"):
        executor.execute(
            [
                ResearchDelegationRequest(
                    request_id="nested",
                    subquestion="Try to recurse",
                    tool_name="spawn_subagent",
                    arguments={},
                )
            ]
        )
    assert not called.is_set()

    with pytest.raises(ResearchDelegationError, match="one delegation layer"):
        ResearchDelegationRequest(
            request_id="too-deep",
            subquestion="Try depth two",
            tool_name="filing",
            arguments={},
            parent_depth=1,
        )


def test_executor_returns_safe_failure_without_persisting_tool_exception():
    def failing_tool(_arguments):
        raise RuntimeError("provider returned internal trace: do not persist")

    executor = ResearchDelegationExecutor({"filing": failing_tool})
    result = executor.execute(
        [
            ResearchDelegationRequest(
                request_id="failure",
                subquestion="Check filing",
                tool_name="filing",
                arguments={},
            )
        ]
    )[0]

    assert result.status == "failed"
    assert "internal trace" not in result.public_summary
    assert result.citations == ()


def test_research_manager_appends_parallel_public_findings_to_trader_pm_handoff():
    structured = MagicMock()
    structured.invoke.return_value = ResearchPlan(
        recommendation=PortfolioRating.HOLD,
        rationale="Core debate is balanced.",
        strategic_actions="Wait for the next filing.",
        delegation_tasks=[
            ResearchDelegationTask(
                request_id="valuation",
                subquestion="Check valuation disclosure.",
                tool_name="filing",
                arguments={"ticker": "600519.SH"},
            ),
            ResearchDelegationTask(
                request_id="demand",
                subquestion="Check demand disclosure.",
                tool_name="filing",
                arguments={"ticker": "600519.SH"},
            ),
        ],
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    executor = ResearchDelegationExecutor({"filing": _output}, max_parallel=2)
    manager = create_research_manager(llm, delegation_executor=executor)

    result = manager(
        {
            "company_of_interest": "600519.SH",
            "investment_debate_state": {
                "history": "Bull and bear evidence.",
                "bull_history": "bull",
                "bear_history": "bear",
                "current_response": "",
                "judge_decision": "",
                "count": 1,
            },
        }
    )

    handoff = result["investment_plan"]
    assert "**Independent Research Delegation**:" in handoff
    assert handoff.count("[completed]") == 2
    assert "Public finding for 600519.SH" in handoff
    assert "spawn_subagent" not in handoff
    assert "company_filing_lookup" not in structured.invoke.call_args.args[0]
    assert "filing" in structured.invoke.call_args.args[0]


def test_default_report_lenses_are_code_owned_bounded_and_use_only_published_reports():
    executor, requests = build_default_report_lens_delegation(
        {
            "market_report": "Trend is constructive, but volume confirmation is limited.",
            "fundamentals_report": "Cash flow is stable.",
            "news_report": "   ",
            "sentiment_report": "Retail sentiment is mixed.",
        }
    )

    assert executor is not None
    assert [request.request_id for request in requests] == [
        "published-market-report",
        "published-fundamentals-report",
        "published-sentiment-report",
    ]
    assert {request.tool_name for request in requests} == {"published_report_lens"}
    assert all(request.parent_depth == 0 for request in requests)

    rendered = executor.execute(requests)
    assert [result.status for result in rendered] == ["completed", "completed", "completed"]
    assert "Market Analyst: Trend is constructive" in rendered[0].public_summary
    assert "News Analyst" not in "\n".join(result.public_summary for result in rendered)


def test_default_lenses_reach_the_normal_manager_handoff_without_model_chosen_tools():
    structured = MagicMock()
    structured.invoke.return_value = ResearchPlan(
        recommendation=PortfolioRating.HOLD,
        rationale="The public reports conflict.",
        strategic_actions="Wait for a confirmation catalyst.",
        # A default graph must ignore model-requested tasks.  It uses its
        # code-owned report-lens list instead.
        delegation_tasks=[
            ResearchDelegationTask(
                request_id="not-used",
                subquestion="Do something outside the approved graph path.",
                tool_name="spawn_subagent",
                arguments={},
            )
        ],
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    manager = create_research_manager(llm, use_default_report_lenses=True)

    result = manager(
        {
            "company_of_interest": "600519.SH",
            "market_report": "Trend is constructive, but the breakout lacks volume confirmation.",
            "fundamentals_report": "Free cash flow supports the base case.",
            "investment_debate_state": {
                "history": "Bull and bear public evidence.",
                "bull_history": "bull",
                "bear_history": "bear",
                "current_response": "",
                "judge_decision": "",
                "count": 1,
            },
        }
    )

    handoff = result["investment_plan"]
    prompt = structured.invoke.call_args.args[0]
    assert "### Market Analyst published report" in prompt
    assert "### Fundamentals Analyst published report" in prompt
    assert "delegation_tasks" not in prompt
    assert handoff.count("[completed]") == 2
    assert "published Market Analyst report" in handoff
    assert "spawn_subagent" not in handoff


def test_graph_setup_enables_default_report_lenses(monkeypatch):
    import tradingagents.graph.setup as setup_module

    captured = {}

    def research_manager_factory(_llm, **kwargs):
        captured.update(kwargs)
        return lambda _state: {}

    class Conditional:
        def should_continue_news(self, _state):
            return "Msg Clear News"

        def should_continue_debate(self, _state):
            return "Research Manager"

        def should_continue_risk_analysis(self, _state):
            return "Portfolio Manager"

    monkeypatch.setattr(setup_module, "create_research_manager", research_manager_factory)
    setup_module.GraphSetup(
        quick_thinking_llm=None,
        deep_thinking_llm=None,
        tool_nodes={"news": lambda state: state},
        conditional_logic=Conditional(),
    ).setup_graph(["news"])

    assert captured == {"use_default_report_lenses": True}


def test_default_lenses_are_retained_when_a_provider_needs_freetext_fallback():
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("unsupported")
    llm.invoke.return_value = MagicMock(
        content="**Recommendation**: Hold\n\n**Rationale**: Limited evidence."
    )
    manager = create_research_manager(llm, use_default_report_lenses=True)

    result = manager(
        {
            "company_of_interest": "600519.SH",
            "news_report": "A dated filing is the only primary source available.",
            "investment_debate_state": {
                "history": "No consensus.",
                "bull_history": "",
                "bear_history": "",
                "current_response": "",
                "judge_decision": "",
                "count": 1,
            },
        }
    )

    assert "**Recommendation**: Hold" in result["investment_plan"]
    assert "**Independent Research Delegation**:" in result["investment_plan"]
    assert "published News Analyst report" in result["investment_plan"]
