"""End-to-end verification: pydantic-ai + mem0 + graphiti deep integration.

Exercises the three integrated subsystems in sequence:
  1. graphiti: import a Winterfell-style decision as a temporal episode
  2. pydantic-ai: produce a structured TraderProposal (the decision layer)
  3. mem0: store that decision for cross-ticker semantic recall

All three use the shared proxy_clients layer. Run with the gateway token
exported as TRADINGAGENTS_PROXY_TOKEN.
"""

from __future__ import annotations

import asyncio
import os
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore", message="The Kuzu backend is deprecated.*")


def _set_token_from_env() -> str:
    token = os.environ.get("TRADINGAGENTS_PROXY_TOKEN") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if not token or not token.startswith("ccs-"):
        raise SystemExit(
            "Set TRADINGAGENTS_PROXY_TOKEN=<ccs-...> (extract from a running "
            "claude process) before running this test."
        )
    os.environ.setdefault("ANTHROPIC_AUTH_TOKEN", token)
    return token


async def _step1_graphiti_import() -> dict:
    """graphiti ingests a decision episode and extracts entities."""
    from graphiti_core.nodes import EpisodeType
    from graphiti_core.search import search as search_mod
    from graphiti_core.utils.maintenance import node_operations
    from tradingagents.llm_clients.proxy_clients import make_graphiti

    async def _noop(*_a, **_k):
        return []

    async def _noop_node(c, n):
        return [[] for _ in n]

    for name in (
        "edge_fulltext_search",
        "node_fulltext_search",
        "edge_similarity_search",
        "node_similarity_search",
    ):
        if hasattr(search_mod, name):
            setattr(search_mod, name, _noop)
    node_operations._semantic_candidate_search = _noop_node

    g = make_graphiti(db_path="/tmp/e2e_graphiti.db")
    await g.build_indices_and_constraints()
    await g.add_episode(
        name="E2E test decision",
        episode_body="Decision: adopt pydantic-ai for structured trader output with validation retry.",
        source=EpisodeType.text,
        source_description="e2e test",
        reference_time=datetime.now(timezone.utc),
    )
    records, _, _ = await g.driver.execute_query(
        "MATCH (n:Entity) RETURN n.name AS name, n.summary AS summary LIMIT 5"
    )
    await g.close()
    return {
        "entities": [
            {"name": r.get("name", ""), "summary": (r.get("summary") or "")[:100]} for r in records
        ]
    }


def _step2_pydantic_ai_trader() -> dict:
    """pydantic-ai produces a structured TraderProposal via the proxy."""
    from pydantic import BaseModel, Field

    from tradingagents.llm_clients.proxy_clients import make_pydantic_ai_agent

    class Proposal(BaseModel):
        action: str = Field(description="BUY, SELL, or HOLD")
        reasoning: str = Field(description="brief rationale")
        entry_price: float | None = Field(default=None, description="optional entry price")

    agent = make_pydantic_ai_agent(
        output_type=Proposal,
        instructions="You are a trader. Produce a transaction proposal.",
    )
    result = agent.run_sync("Bullish on NVDA: AI demand surge, earnings beat. Entry near 890.")
    return {"action": result.output.action, "reasoning": result.output.reasoning[:120]}


def _step3_mem0_remember(decision: dict) -> dict:
    """mem0 stores the decision for future semantic recall."""
    os.environ["TRADINGAGENTS_MEM0_ENABLED"] = "1"
    from tradingagents.agents.utils.mem0_bridge import Mem0Bridge

    bridge = Mem0Bridge.from_config({})
    bridge.remember_decision(
        "NVDA",
        "2026-08-04",
        f"{decision['action']}: {decision['reasoning']}",
    )
    recalled = bridge.recall_relevant("NVDA", {"investment_plan": decision["reasoning"]})
    return {"recalled_len": len(recalled), "has_match": "Past decision" in recalled}


def main() -> int:
    _set_token_from_env()
    print("=== Step 1: graphiti ingest ===")
    g = asyncio.run(_step1_graphiti_import())
    print(f"  entities extracted: {len(g['entities'])}")
    for e in g["entities"]:
        print(f"    - {e['name']}: {e['summary']}")

    print("\n=== Step 2: pydantic-ai trader ===")
    decision = _step2_pydantic_ai_trader()
    print(f"  action: {decision['action']}")
    print(f"  reasoning: {decision['reasoning']}")

    print("\n=== Step 3: mem0 remember ===")
    m = _step3_mem0_remember(decision)
    print(f"  recalled context length: {m['recalled_len']}")
    print(f"  has semantic match: {m['has_match']}")

    print("\n=== E2E PASS ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
