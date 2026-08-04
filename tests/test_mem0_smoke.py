"""Smoke test: mem0 走代理 anthropic 端点 + 本地 HuggingFace embedder。

Uses the shared proxy_clients module — see tradingagents/llm_clients/proxy_clients.py.
"""

from __future__ import annotations

import os
from typing import Any


def test_mem0_add_and_search() -> None:
    """mem0 stores and retrieves a memory via proxy + local embedding."""
    os.environ.setdefault("MEM0_TELEMETRY", "False")
    os.environ.setdefault("DISABLE_MEM0", "True")

    from tradingagents.llm_clients.proxy_clients import make_mem0_memory

    m = make_mem0_memory()

    m.add(
        [
            {
                "role": "user",
                "content": "I prefer low-risk trading strategies with steady returns.",
            },
            {
                "role": "assistant",
                "content": "Noted. I'll favor conservative positions and avoid high-volatility assets.",
            },
        ],
        user_id="geralt",
    )

    results = m.search("risk preference", filters={"user_id": "geralt"}, top_k=3)
    assert "results" in results
    assert len(results["results"]) > 0
    mem = results["results"][0]
    assert "memory" in mem
    print(f"\n=== mem0 smoke test ===")
    print(f"stored memory: {mem['memory'][:200]}")
    print(f"score: {mem.get('score', 'n/a')}")
    print("=== PASS ===")


if __name__ == "__main__":
    test_mem0_add_and_search()
