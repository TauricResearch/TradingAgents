"""The three risk analysts argue from a long-term dividend holder's viewpoint
(total return / dividend safety / valuation and staging), not a trading
desk's high-risk vs low-risk split. These assert the rendered prompt."""
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator


def _state():
    return {
        "company_of_interest": "1155.KL",
        "market_report": "m",
        "sentiment_report": "s",
        "news_report": "n",
        "fundamentals_report": "f",
        "trader_investment_plan": "**Action**: Buy",
        "risk_debate_state": {
            "history": "", "aggressive_history": "", "conservative_history": "",
            "neutral_history": "", "latest_speaker": "", "current_aggressive_response": "",
            "current_conservative_response": "", "current_neutral_response": "", "count": 0,
        },
    }


def _prompt_for(factory) -> str:
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="argument")
    factory(llm)(_state())
    return llm.invoke.call_args[0][0]


@pytest.mark.unit
@pytest.mark.parametrize(
    "factory, expected",
    [
        (create_aggressive_debator, ["long-term total return", "do not advocate leverage"]),
        (create_conservative_debator, ["capital and dividend income", "yield trap", "fixed deposit"]),
        (create_neutral_debator, ["valuation and entry timing", "staged purchases"]),
    ],
)
def test_risk_analyst_long_term_focus(factory, expected):
    prompt = _prompt_for(factory)
    for phrase in expected:
        assert phrase in prompt
    # The trading-desk framing is gone.
    for phrase in ("high-risk approach is optimal", "the firm's assets", "outpace market norms"):
        assert phrase not in prompt
