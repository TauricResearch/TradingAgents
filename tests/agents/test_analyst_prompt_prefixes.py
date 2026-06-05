from tradingagents.agents.analysts.derivative_analyst import (
    DERIVATIVES_SYSTEM_MESSAGE,
    build_derivatives_user_prompt,
)
from tradingagents.agents.analysts.sentiment_analyst import (
    SENTIMENT_SYSTEM_MESSAGE,
    build_sentiment_user_prompt,
)
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.prompt_cache import DYNAMIC_CONTEXT_MARKER, prompt_prefix_fingerprint


def test_sentiment_static_prefix_ignores_ticker_date_and_source_blocks():
    messages_a = [
        {"role": "system", "content": SENTIMENT_SYSTEM_MESSAGE},
        {
            "role": "user",
            "content": build_sentiment_user_prompt(
                ticker="NVDA",
                instrument_context=build_instrument_context("NVDA"),
                start_date="2026-05-29",
                end_date="2026-06-05",
                news_block="NVDA news",
                stocktwits_block="NVDA stocktwits",
                reddit_block="NVDA reddit",
            ),
        },
    ]
    messages_b = [
        {"role": "system", "content": SENTIMENT_SYSTEM_MESSAGE},
        {
            "role": "user",
            "content": build_sentiment_user_prompt(
                ticker="AAPL",
                instrument_context=build_instrument_context("AAPL"),
                start_date="2026-05-28",
                end_date="2026-06-04",
                news_block="AAPL news",
                stocktwits_block="AAPL stocktwits",
                reddit_block="AAPL reddit",
            ),
        },
    ]

    assert prompt_prefix_fingerprint(messages_a) == prompt_prefix_fingerprint(messages_b)
    assert DYNAMIC_CONTEXT_MARKER in messages_a[1]["content"]
    assert "NVDA news" in messages_a[1]["content"]
    assert "NVDA" not in SENTIMENT_SYSTEM_MESSAGE
    assert "2026" not in SENTIMENT_SYSTEM_MESSAGE


def test_derivatives_system_message_has_no_dynamic_context():
    user_prompt = build_derivatives_user_prompt(
        current_date="2026-06-05",
        instrument_context=build_instrument_context("NVDA"),
    )

    assert "2026-06-05" not in DERIVATIVES_SYSTEM_MESSAGE
    assert "NVDA" not in DERIVATIVES_SYSTEM_MESSAGE
    assert DYNAMIC_CONTEXT_MARKER in user_prompt
    assert "2026-06-05" in user_prompt
    assert "NVDA" in user_prompt
