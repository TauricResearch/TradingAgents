"""Integration test: mem0 bridge stores and recalls trading decisions.

Verifies the Mem0Bridge round-trip: remember_decision() stores a decision,
recall_relevant() retrieves it by semantic similarity (cross-ticker).
"""

from __future__ import annotations

import os

# Enable mem0 before importing.
os.environ["TRADINGAGENTS_MEM0_ENABLED"] = "1"


def test_mem0_bridge_remember_and_recall() -> None:
    from tradingagents.agents.utils.mem0_bridge import Mem0Bridge

    bridge = Mem0Bridge.from_config({})
    assert bridge.enabled, "mem0 bridge should be enabled when env var is set"

    # Store two decisions — one Fed-related, one earnings-related.
    bridge.remember_decision(
        "AAPL",
        "2026-08-01",
        "Buy AAPL: earnings beat, heavy volume, positive sentiment. Entry 228, stop 215.",
    )
    bridge.remember_decision(
        "TSLA",
        "2026-08-02",
        "Hold TSLA: Fed pivot uncertainty, valuation stretched. Wait for clarity.",
    )

    # Probe with Fed-pivot language — should surface the TSLA decision.
    state = {
        "investment_plan": "Cautious on valuation, Fed pivot uncertainty",
        "trader_investment_plan": "Hold, wait for Fed clarity",
        "final_trade_decision": "Hold",
    }
    recalled = bridge.recall_relevant("NVDA", state)
    assert recalled != "", "expected non-empty semantic recall"
    assert "Past decision" in recalled
    print("\n=== mem0 bridge integration ===")
    print(recalled[:500])
    print("=== PASS ===")


if __name__ == "__main__":
    test_mem0_bridge_remember_and_recall()
