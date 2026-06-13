from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.trader.trader import create_trader
from tradingagents.dataflows.config import set_config


REPO_ROOT = Path(__file__).resolve().parents[1]

INDIA_ANALYST_PROMPTS = [
    "tradingagents/agents/analysts/india_market_analyst.py",
    "tradingagents/agents/analysts/india_fundamentals_analyst.py",
    "tradingagents/agents/analysts/india_news_filings_analyst.py",
    "tradingagents/agents/analysts/india_macro_policy_analyst.py",
    "tradingagents/agents/analysts/india_flows_analyst.py",
    "tradingagents/agents/analysts/india_sentiment_analyst.py",
    "tradingagents/agents/analysts/india_compliance_risk_analyst.py",
]


def _text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


@pytest.mark.unit
@pytest.mark.parametrize("path", INDIA_ANALYST_PROMPTS)
def test_india_analyst_prompts_are_research_only_and_data_quality_aware(path):
    text = _text(path)
    assert "research" in text.lower()
    assert any(marker in text for marker in ("data-quality", "Data-quality", "UNAVAILABLE", "unavailable"))
    assert "Do not fabricate" in text or "do not fake" in text.lower() or "unsupported" in text.lower()


@pytest.mark.unit
def test_structured_trader_render_uses_model_view_not_transaction_language():
    from tradingagents.agents.schemas import TraderAction, TraderProposal, render_trader_proposal

    rendered = render_trader_proposal(
        TraderProposal(action=TraderAction.HOLD, reasoning="No edge until filings improve.")
    )

    assert "FINAL MODEL VIEW: **HOLD**" in rendered
    assert "FINAL TRANSACTION PROPOSAL" not in rendered


def _base_state():
    return {
        "company_of_interest": "RELIANCE.NS",
        "asset_type": "stock",
        "trade_date": "2026-06-05",
        "market_report": "Market report. Data Quality: medium.",
        "sentiment_report": "Sentiment report. UNAVAILABLE social channel.",
        "news_report": "News report.",
        "fundamentals_report": "Fundamentals report.",
        "india_macro_policy_report": "Macro report. UNAVAILABLE official datapoint.",
        "india_flows_report": "Flows report. UNAVAILABLE FII/DII.",
        "india_compliance_report": "Compliance report.",
        "investment_plan": "Research plan.",
        "trader_investment_plan": "Research proposal.",
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
        },
        "risk_debate_state": {
            "history": "",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 0,
        },
    }


class CapturingTextLLM:
    def __init__(self):
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return MagicMock(content="captured")


def _capture_structured_prompt(factory, state):
    captured = {}
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: captured.setdefault("prompt", prompt)
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    node = factory(llm)
    try:
        node(state)
    except AttributeError:
        pass
    return captured["prompt"]


@pytest.mark.unit
def test_trader_india_prompt_uses_research_plan_and_no_order_instructions():
    set_config({"market_scope": "india"})
    prompt = _capture_structured_prompt(create_trader, _base_state())
    combined = "\n".join(message["content"] for message in prompt)

    assert "Proposed Research Plan" in combined
    assert "research-only model view" in combined
    assert "not a live trading instruction" in combined
    assert "order-placement instructions" in combined
    assert "Proposed Investment Plan" not in combined


@pytest.mark.unit
def test_portfolio_manager_india_prompt_uses_final_research_view_language():
    set_config({"market_scope": "india"})
    prompt = _capture_structured_prompt(create_portfolio_manager, _base_state())

    assert "final research/model view" in prompt
    assert "Research proposal" in prompt
    assert "order-placement instructions" in prompt
    assert "place orders" in prompt
    assert "final trading decision" not in prompt
    assert "transaction proposal" not in prompt


@pytest.mark.unit
@pytest.mark.parametrize(
    "factory",
    [
        create_bull_researcher,
        create_bear_researcher,
        create_aggressive_debator,
        create_conservative_debator,
        create_neutral_debator,
    ],
)
def test_debate_prompts_include_research_only_and_no_fabrication_guards(factory):
    llm = CapturingTextLLM()
    node = factory(llm)
    node(_base_state())
    prompt = llm.prompts[0]

    assert "research and education only" in prompt
    assert "order-placement instructions" in prompt
    assert "execute trade now" in prompt
    assert "Do not fabricate" in prompt or "do not fabricate" in prompt
    assert "UNAVAILABLE" in prompt
