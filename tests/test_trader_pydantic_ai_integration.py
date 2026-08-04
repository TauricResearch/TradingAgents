"""Integration test: Trader node with pydantic-ai backend enabled.

Verifies that enabling TRADINGAGENTS_USE_PYDANTIC_AI=1 routes the Trader's
structured-output call through pydantic-ai (validation-retry loop) and still
produces a valid markdown render of TraderProposal with the BUY/HOLD/SELL signal.
"""

from __future__ import annotations

import os

# Enable the pydantic-ai backend BEFORE importing the agent module.
os.environ["TRADINGAGENTS_USE_PYDANTIC_AI"] = "1"


def test_trader_node_produces_structured_proposal_via_pydantic_ai() -> None:
    from tradingagents.agents.trader.trader import create_trader

    # The pydantic-ai backend ignores the langchain `llm` for the structured
    # call (it uses proxy_clients internally), but the agent still needs one
    # for the fallback path. Pass a lightweight stub.
    class _StubLLM:
        def invoke(self, _prompt):
            raise AssertionError("fallback should not fire when pydantic-ai succeeds")

    trader_node = create_trader(_StubLLM())

    state = {
        "company_of_interest": "AAPL",
        "investment_plan": (
            "Bullish on AAPL: strong earnings, heavy volume, positive sentiment. "
            "Recommend gradual accumulation."
        ),
        "instrument_context": "Instrument: AAPL (NASDAQ equity, USD).",
    }
    # Patch the instrument-context helper to avoid heavy state requirements.
    import tradingagents.agents.trader.trader as trader_mod

    orig = trader_mod.get_instrument_context_from_state
    trader_mod.get_instrument_context_from_state = lambda _s: "Instrument: AAPL (NASDAQ, USD)."

    try:
        result = trader_node(state)
    finally:
        trader_mod.get_instrument_context_from_state = orig

    plan = result["trader_investment_plan"]
    assert "**Action**:" in plan
    assert "FINAL TRANSACTION PROPOSAL:" in plan
    # Action must be one of the three valid values.
    assert any(tag in plan for tag in ("**BUY**", "**HOLD**", "**SELL**"))
    print("\n=== Trader pydantic-ai integration ===")
    print(plan[:400])
    print("=== PASS ===")


if __name__ == "__main__":
    test_trader_node_produces_structured_proposal_via_pydantic_ai()
