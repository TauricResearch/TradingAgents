"""Smoke test: pydantic-ai 走代理 anthropic 端点产出结构化 TradeSignal。

Uses the shared proxy_clients module — see tradingagents/llm_clients/proxy_clients.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pydantic_ai import Agent


class TradeSignal(BaseModel):
    action: str = Field(description="BUY, SELL, or HOLD")
    confidence: float = Field(description="Confidence score 0-1", ge=0.0, le=1.0)
    reasoning: str = Field(description="Brief rationale for the trade signal")


def _make_agent() -> "Agent":
    from tradingagents.llm_clients.proxy_clients import make_pydantic_ai_agent

    return make_pydantic_ai_agent(
        output_type=TradeSignal,
        instructions=(
            "You are a trading analyst. Analyze the given market data and "
            "return a trade signal with action (BUY/SELL/HOLD), confidence "
            "(0-1), and brief reasoning."
        ),
    )


def test_agent_produces_structured_trade_signal_sync() -> None:
    """Agent returns a validated TradeSignal via the proxy's anthropic endpoint."""
    agent = _make_agent()
    result = agent.run_sync("AAPL is up 3% on heavy volume after an earnings beat.")

    assert isinstance(result.output, TradeSignal)
    assert result.output.action in {"BUY", "SELL", "HOLD"}
    assert 0.0 <= result.output.confidence <= 1.0
    assert len(result.output.reasoning) > 0


if __name__ == "__main__":
    agent = _make_agent()
    result = agent.run_sync("AAPL is up 3% on heavy volume after an earnings beat.")
    print("\n=== pydantic-ai smoke test ===")
    print(f"action: {result.output.action}")
    print(f"confidence: {result.output.confidence}")
    print(f"reasoning: {result.output.reasoning[:300]}")
    print("=== PASS ===")
