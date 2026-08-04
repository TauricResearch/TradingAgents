from unittest.mock import MagicMock

from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher


def _state():
    return {
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
        },
        "market_report": "market",
        "sentiment_report": "sentiment",
        "news_report": "news",
        "fundamentals_report": "fundamentals",
    }


def test_bull_opening_does_not_attribute_missing_bear_argument():
    llm = MagicMock()
    llm.invoke.return_value.content = "opening case"

    create_bull_researcher(llm)(_state())

    prompt = llm.invoke.call_args.args[0]
    assert "No bear argument has been presented yet" in prompt


def test_bear_opening_does_not_attribute_missing_bull_argument():
    llm = MagicMock()
    llm.invoke.return_value.content = "opening case"

    create_bear_researcher(llm)(_state())

    prompt = llm.invoke.call_args.args[0]
    assert "No bull argument has been presented yet" in prompt
