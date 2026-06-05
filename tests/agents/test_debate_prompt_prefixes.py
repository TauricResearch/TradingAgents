from tradingagents.agents.researchers.bear_researcher import (
    BEAR_RESEARCHER_SYSTEM_PROMPT,
    build_bear_researcher_user_prompt,
)
from tradingagents.agents.researchers.bull_researcher import (
    BULL_RESEARCHER_SYSTEM_PROMPT,
    build_bull_researcher_user_prompt,
)
from tradingagents.agents.utils.prompt_cache import DYNAMIC_CONTEXT_MARKER, prompt_prefix_fingerprint


def _debate_state(ticker: str) -> dict:
    return {
        "company_of_interest": ticker,
        "asset_type": "stock",
        "market_report": f"{ticker} market report",
        "sentiment_report": f"{ticker} sentiment report",
        "news_report": f"{ticker} news report",
        "fundamentals_report": f"{ticker} fundamentals report",
        "derivatives_report": f"{ticker} derivatives report",
        "investment_debate_state": {
            "history": f"{ticker} history",
            "bull_history": "",
            "bear_history": "",
            "current_response": f"{ticker} last response",
            "count": 1,
        },
    }


def test_bull_and_bear_static_prompts_are_run_agnostic():
    for system_prompt in (BULL_RESEARCHER_SYSTEM_PROMPT, BEAR_RESEARCHER_SYSTEM_PROMPT):
        assert "NVDA" not in system_prompt
        assert "AAPL" not in system_prompt
        assert "stock" not in system_prompt.lower()


def test_bull_prefix_ignores_dynamic_state_values():
    messages_a = [
        {"role": "system", "content": BULL_RESEARCHER_SYSTEM_PROMPT},
        {"role": "user", "content": build_bull_researcher_user_prompt(_debate_state("NVDA"))},
    ]
    messages_b = [
        {"role": "system", "content": BULL_RESEARCHER_SYSTEM_PROMPT},
        {"role": "user", "content": build_bull_researcher_user_prompt(_debate_state("AAPL"))},
    ]

    assert prompt_prefix_fingerprint(messages_a) == prompt_prefix_fingerprint(messages_b)
    assert messages_a[1]["content"].startswith(DYNAMIC_CONTEXT_MARKER)
    assert "NVDA market report" in messages_a[1]["content"]


def test_bear_prefix_ignores_dynamic_state_values():
    messages_a = [
        {"role": "system", "content": BEAR_RESEARCHER_SYSTEM_PROMPT},
        {"role": "user", "content": build_bear_researcher_user_prompt(_debate_state("NVDA"))},
    ]
    messages_b = [
        {"role": "system", "content": BEAR_RESEARCHER_SYSTEM_PROMPT},
        {"role": "user", "content": build_bear_researcher_user_prompt(_debate_state("AAPL"))},
    ]

    assert prompt_prefix_fingerprint(messages_a) == prompt_prefix_fingerprint(messages_b)
    assert messages_a[1]["content"].startswith(DYNAMIC_CONTEXT_MARKER)
    assert "NVDA last response" in messages_a[1]["content"]
