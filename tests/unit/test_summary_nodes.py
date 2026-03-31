from types import SimpleNamespace
from unittest.mock import MagicMock

from tradingagents.agents.managers.context_summaries import (
    create_investment_debate_summary,
    create_research_packet_summary,
    create_risk_debate_summary,
)
from tradingagents.agents.managers.summary_rules import (
    INVESTMENT_DEBATE_SUMMARY,
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
    llm.invoke.return_value = SimpleNamespace(content="Market setup\nFundamentals\n...")
    node = create_research_packet_summary(llm)

    result = node(
        {
            "market_report": "market",
            "sentiment_report": "sentiment",
            "news_report": "news",
            "fundamentals_report": "fundamentals",
            "macro_regime_report": "macro",
        }
    )

    assert result["research_packet_summary"] == "Market setup\nFundamentals\n..."
    assert result["sender"] == "research_packet_summary"
    prompt = llm.invoke.call_args.args[0]
    assert "## OBJECTIVE" in prompt
    assert RESEARCH_PACKET_SUMMARY.objective in prompt
    assert "- **Market setup**" in prompt
    assert "## INPUT TEXT TO SUMMARIZE:" in prompt


def test_investment_debate_summary_updates_state_summary():
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content="Bull case\nBear case\nCurrent lean")
    node = create_investment_debate_summary(llm)

    result = node(
        {
            "investment_debate_state": {
                "bull_history": "bull",
                "bear_history": "bear",
                "history": "full history",
                "summary": "old summary",
                "current_response": "Bull Analyst: new point",
                "judge_decision": "",
                "count": 1,
            }
        }
    )

    assert result["investment_debate_state"]["summary"] == "Bull case\nBear case\nCurrent lean"
    assert result["investment_debate_state"]["count"] == 1
    prompt = llm.invoke.call_args.args[0]
    assert INVESTMENT_DEBATE_SUMMARY.objective in prompt
    assert "- **Bull case**" in prompt
    assert "Previous summary:" in prompt
    assert "Latest response:" in prompt


def test_risk_debate_summary_updates_state_summary():
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content="Upside case\nRisk case\nControls")
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

    assert result["risk_debate_state"]["summary"] == "Upside case\nRisk case\nControls"
    assert result["risk_debate_state"]["latest_speaker"] == "Aggressive"


def test_bull_researcher_uses_summary_context_when_available():
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content="bull answer")
    memory = MagicMock()
    memory.get_memories.return_value = []
    node = create_bull_researcher(llm, memory)

    state = {
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

    prompt = llm.invoke.call_args.args[0]
    assert "Compressed research packet: compact packet" in prompt
    assert "Rolling debate summary: rolling debate summary" in prompt
    assert result["investment_debate_state"]["current_response"].startswith("Bull Analyst:")


def test_researcher_nodes_preserve_investment_summary_and_metadata():
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content="updated argument")
    memory = MagicMock()
    memory.get_memories.return_value = []

    state = {
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


def test_risk_nodes_preserve_summary_and_metadata():
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content="updated risk argument")
    state = {
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

    aggressive_state = create_aggressive_debator(llm)(state)["risk_debate_state"]
    assert aggressive_state["summary"] == "rolling risk summary"
    assert aggressive_state["judge_decision"] == "judge output"
    assert aggressive_state["count"] == 5

    conservative_state = create_conservative_debator(llm)(state)["risk_debate_state"]
    assert conservative_state["summary"] == "rolling risk summary"
    assert conservative_state["judge_decision"] == "judge output"
    assert conservative_state["count"] == 5

    neutral_state = create_neutral_debator(llm)(state)["risk_debate_state"]
    assert neutral_state["summary"] == "rolling risk summary"
    assert neutral_state["judge_decision"] == "judge output"
    assert neutral_state["count"] == 5


def test_generate_summary_prompt_uses_ruleset_template():
    prompt = generate_summary_prompt(RESEARCH_PACKET_SUMMARY, "input block")

    assert prompt.startswith("You are a ruthless, highly precise quantitative financial summarizer.")
    assert "## OBJECTIVE" in prompt
    assert RESEARCH_PACKET_SUMMARY.objective in prompt
    assert f"**Maximum Length:** {RESEARCH_PACKET_SUMMARY.max_words} words" in prompt
    assert "- **Market setup**" in prompt
    assert "## SUMMARIZATION RULES" in prompt
    assert "input block" in prompt
