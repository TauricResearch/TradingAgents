"""Tests for the ChatModel type alias (tradingagents/graph/setup.py).

Verifies that ChatModel is a Union containing all three supported providers.
"""

import typing

from tradingagents.graph.setup import ChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI


def test_chat_model_union_includes_all_providers():
    """ChatModel should be a Union of ChatOpenAI, ChatAnthropic, and ChatGoogleGenerativeAI."""
    args = typing.get_args(ChatModel)
    assert ChatOpenAI in args, "ChatModel should include ChatOpenAI"
    assert ChatAnthropic in args, "ChatModel should include ChatAnthropic"
    assert ChatGoogleGenerativeAI in args, "ChatModel should include ChatGoogleGenerativeAI"
