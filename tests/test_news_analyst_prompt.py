"""Guard the news analyst prompt against tool-signature drift (#1116).

The prompt used to advertise ``get_news(query, ...)`` while the tool takes a
``ticker``, tricking the LLM into hallucinating free-text query calls.
"""

import pytest

from tradingagents.agents.tools import get_news
from tradingagents.prompts.loader import load_prompt


@pytest.mark.unit
def test_get_news_takes_ticker_not_query():
    arg_names = set(get_news.args.keys())
    assert "ticker" in arg_names
    assert "query" not in arg_names


@pytest.mark.unit
def test_news_prompt_matches_get_news_signature():
    prompt = load_prompt("analysts/news.txt")
    assert "get_news(ticker, start_date, end_date)" in prompt
    assert "get_news(query" not in prompt