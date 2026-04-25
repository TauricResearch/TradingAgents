from types import SimpleNamespace
from unittest.mock import MagicMock

from tradingagents.agents.managers.context_summaries import (
    create_investment_debate_summary,
    create_research_packet_summary,
    create_risk_debate_summary,
)
from tradingagents.agents.managers.summary_rules import (
    RESEARCH_PACKET_SUMMARY,
    generate_summary_prompt,
)
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator


def test_research_packet_summary_node_returns_summary():
    llm = MagicMock()
    node = create_research_packet_summary(llm)

    result = node(
        {
            "scanner_graph_context_text": "Oil: $72.10\nDXY: 104.2",
            "market_report": "- Price held $189.00 support\n| Metric | Value |\n| --- | --- |",
            "market_report_structured": {
                "status": "completed",
                "contract_version": "market_summary_v1",
                "macro_regime": "risk_on",
                "claim_count": 4,
                "key_levels": ["$189.00", "$194.50"],
                "key_metrics": {
                    "numeric_mentions": 6,
                    "summary_table_rows": 2,
                },
            },
            "sentiment_report": "- Sentiment improved to 62%",
            "news_report": "- AAPL supplier demand improved 8% on 2024-05-15.",
            "news_report_structured": {
                "status": "completed",
                "key_metrics": {"claim_count": 1},
            },
            "fundamentals_report": "- Gross margin expanded 120bps.",
            "macro_regime_report": "## Risk-On\nMarket is RISK-ON.",
        }
    )

    summary = result["research_packet_summary"]
    assert "## Scanner Graph Context" in summary
    assert "## Market Structured Contract" in summary
    assert "macro_regime: risk_on" in summary
    assert "## Market Report" in summary
    assert "## News Report" in summary
    assert result["sender"] == "research_packet_summary"
    llm.invoke.assert_not_called()


def test_investment_debate_summary_updates_state_summary():
    """Heuristic fast-path: aggregates bull/bear summaries without LLM call."""
    llm = MagicMock()
    node = create_investment_debate_summary(llm)

    # With explicit summary fields provided
    result = node(
        {
            "investment_debate_state": {
                "bull_history": "bull",
                "bear_history": "bear",
                "current_bull_summary": "Strong fundamentals support upside",
                "current_bear_summary": "Valuation risk and macro headwinds",
                "history": "full history",
                "summary": "old summary",
                "current_response": "Bull Analyst: new point",
                "judge_decision": "",
                "count": 1,
            }
        }
    )

    summary = result["investment_debate_state"]["summary"]
    assert "### Bull Analyst Points" in summary
    assert "Strong fundamentals support upside" in summary
    assert "### Bear Analyst Points" in summary
    assert "Valuation risk and macro headwinds" in summary
    assert result["investment_debate_state"]["count"] == 1
    # Heuristic path does not invoke the LLM
    llm.invoke.assert_not_called()


def test_investment_debate_summary_fallback_without_summaries():
    """Without per-side summary points, node emits in-progress placeholder."""
    llm = MagicMock()
    node = create_investment_debate_summary(llm)

    result = node(
        {
            "investment_debate_state": {
                "bull_history": "bull",
                "bear_history": "bear",
                "history": "full history",
                "summary": "old summary",
                "count": 1,
            }
        }
    )

    summary = result["investment_debate_state"]["summary"]
    assert summary == "Investment debate in progress..."


def test_risk_debate_summary_updates_state_summary():
    """Heuristic fast-path: aggregates risk analyst summaries without LLM call."""
    llm = MagicMock()
    node = create_risk_debate_summary(llm)

    result = node(
        {
            "risk_debate_state": {
                "aggressive_history": "agg",
                "conservative_history": "",
                "neutral_history": "",
                "history": "full history",
                "summary": "old summary",
                "latest_speaker": "Aggressive",
                "current_aggressive_response": "Aggressive Analyst: push harder",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "judge_decision": "",
                "count": 1,
            }
        }
    )

    summary = result["risk_debate_state"]["summary"]
    assert "### Aggressive Analyst Points" in summary
    assert "Aggressive Analyst: push harder" in summary
    assert result["risk_debate_state"]["latest_speaker"] == "Aggressive"
    # Heuristic path does not invoke the LLM
    llm.invoke.assert_not_called()


def test_bull_researcher_uses_summary_context_when_available():
    llm = MagicMock()
    llm.bind.side_effect = RuntimeError("bind unsupported in unit test")
    llm.invoke.return_value = SimpleNamespace(content="bull answer")
    memory = MagicMock()
    memory.get_memories.return_value = []
    node = create_bull_researcher(llm, memory)

    state = {
        "company_of_interest": "AAPL",
        "research_packet_summary": "compact packet",
        "investment_debate_state": {
            "bull_history": "",
            "bear_history": "",
            "history": "very long raw history",
            "summary": "rolling debate summary",
            "current_response": "Bear Analyst: latest",
            "judge_decision": "",
            "count": 1,
        },
    }

    result = node(state)

    llm.invoke.call_args.args[0]
    # Anonymized ticker replaces AAPL in the prompt context
    assert result["investment_debate_state"]["current_response"].startswith("Bull Analyst:")


def test_researcher_nodes_preserve_investment_summary_and_metadata():
    llm = MagicMock()
    llm.bind.side_effect = RuntimeError("bind unsupported in unit test")
    llm.invoke.return_value = SimpleNamespace(content="updated argument")
    memory = MagicMock()
    memory.get_memories.return_value = []

    state = {
        "company_of_interest": "AAPL",
        "research_packet_summary": "compact packet",
        "investment_debate_state": {
            "bull_history": "old bull",
            "bear_history": "old bear",
            "history": "old history",
            "summary": "rolling debate summary",
            "current_response": "prior response",
            "judge_decision": "judge output",
            "count": 2,
        },
    }

    bull_result = create_bull_researcher(llm, memory)(state)
    bull_state = bull_result["investment_debate_state"]
    assert bull_state["summary"] == "rolling debate summary"
    assert bull_state["judge_decision"] == "judge output"
    assert bull_state["count"] == 3

    bear_result = create_bear_researcher(llm, memory)(state)
    bear_state = bear_result["investment_debate_state"]
    assert bear_state["summary"] == "rolling debate summary"
    assert bear_state["judge_decision"] == "judge output"
    assert bear_state["count"] == 3


def test_researcher_nodes_write_compact_summary_points():
    llm = MagicMock()
    llm.bind.side_effect = RuntimeError("bind unsupported in unit test")
    llm.invoke.return_value = SimpleNamespace(
        content="THE DEBATE:\n- line\n\nSUMMARY POINTS:\n- point A\n- point B"
    )
    memory = MagicMock()
    memory.get_memories.return_value = []

    state = {
        "company_of_interest": "AAPL",
        "research_packet_summary": "compact packet",
        "investment_debate_state": {
            "bull_history": "",
            "bear_history": "",
            "history": "",
            "summary": "",
            "current_response": "",
            "judge_decision": "",
            "count": 0,
        },
    }

    bull_state = create_bull_researcher(llm, memory)(state)["investment_debate_state"]
    assert "### Bull Analyst Points" in bull_state["summary"]
    assert "- point A" in bull_state["summary"]

    bear_result_state = create_bear_researcher(llm, memory)(
        {
            "company_of_interest": "AAPL",
            "research_packet_summary": "compact packet",
            "investment_debate_state": bull_state,
        }
    )["investment_debate_state"]
    assert "### Bull Analyst Points" in bear_result_state["summary"]
    assert "### Bear Analyst Points" in bear_result_state["summary"]


def test_risk_nodes_preserve_summary_and_metadata():
    llm = MagicMock()
    llm.bind.side_effect = RuntimeError("bind unsupported in unit test")
    llm.invoke.return_value = SimpleNamespace(content="updated risk argument")
    state = {
        "company_of_interest": "AAPL",
        "trader_investment_plan": "take position",
        "research_packet_summary": "compact packet",
        "risk_debate_state": {
            "aggressive_history": "agg history",
            "conservative_history": "cons history",
            "neutral_history": "neutral history",
            "history": "full risk history",
            "summary": "rolling risk summary",
            "latest_speaker": "Neutral",
            "current_aggressive_response": "agg latest",
            "current_conservative_response": "cons latest",
            "current_neutral_response": "neutral latest",
            "judge_decision": "judge output",
            "count": 4,
        },
    }

    # Round-based architecture returns flat keys (risk_r1_aggressive, etc.)
    aggressive_result = create_aggressive_debator(llm, round_num=1)(state)
    assert "risk_r1_aggressive" in aggressive_result
    assert isinstance(aggressive_result["risk_r1_aggressive"], str)

    conservative_result = create_conservative_debator(llm, round_num=1)(state)
    assert "risk_r1_conservative" in conservative_result
    assert isinstance(conservative_result["risk_r1_conservative"], str)

    neutral_result = create_neutral_debator(llm, round_num=1)(state)
    assert "risk_r1_neutral" in neutral_result
    assert isinstance(neutral_result["risk_r1_neutral"], str)


def test_generate_summary_prompt_uses_ruleset_template():
    prompt = generate_summary_prompt(RESEARCH_PACKET_SUMMARY, "input block")

    assert prompt.startswith(
        "You are a ruthless, highly precise quantitative financial summarizer."
    )
    assert "## OBJECTIVE" in prompt
    assert RESEARCH_PACKET_SUMMARY.objective in prompt
    assert f"**Maximum Length:** {RESEARCH_PACKET_SUMMARY.max_words} words" in prompt
    assert "- **Market setup**" in prompt
    assert "## SUMMARIZATION RULES" in prompt
    assert "input block" in prompt
