"""Shared type definitions for the TradingAgents framework.

This module provides TypedDict classes and type aliases used across
the framework for consistent type checking and documentation.
"""

from typing import Any

from typing_extensions import TypedDict


class MarketData(TypedDict):
    """Market data structure for stock price information.

    Attributes:
        ticker: Stock ticker symbol.
        date: Trading date string.
        open: Opening price.
        high: Highest price of the day.
        low: Lowest price of the day.
        close: Closing price.
        volume: Trading volume.
    """

    ticker: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class AgentResponse(TypedDict):
    """Response from an agent node execution.

    Attributes:
        messages: List of messages to add to the conversation.
        report: Generated report content (if applicable).
        sender: Name of the sending agent.
    """

    messages: list[Any]
    report: str
    sender: str


class ConfigDict(TypedDict, total=False):
    """Configuration dictionary structure.

    Attributes:
        project_dir: Project root directory.
        results_dir: Directory for storing results.
        data_cache_dir: Directory for caching data.
        llm_provider: LLM provider name.
        deep_think_llm: Model for complex reasoning.
        quick_think_llm: Model for fast responses.
        backend_url: API endpoint URL.
        google_thinking_level: Thinking level for Google models.
        openai_reasoning_effort: Reasoning effort for OpenAI models.
        max_debate_rounds: Maximum debate rounds between researchers.
        max_risk_discuss_rounds: Maximum risk discussion rounds.
        max_recur_limit: Maximum recursion limit for graph.
        data_vendors: Category-level vendor configuration.
        tool_vendors: Tool-level vendor configuration.
    """

    project_dir: str
    results_dir: str
    data_cache_dir: str
    llm_provider: str
    deep_think_llm: str
    quick_think_llm: str
    backend_url: str
    google_thinking_level: str | None
    openai_reasoning_effort: str | None
    max_debate_rounds: int
    max_risk_discuss_rounds: int
    max_recur_limit: int
    data_vendors: dict[str, str]
    tool_vendors: dict[str, str]


class MemoryMatch(TypedDict):
    """Result from memory similarity matching.

    Attributes:
        matched_situation: The stored situation that matched.
        recommendation: The associated recommendation.
        similarity_score: BM25 similarity score (0-1 normalized).
    """

    matched_situation: str
    recommendation: str
    similarity_score: float
