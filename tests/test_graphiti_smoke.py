"""Smoke test: graphiti 走代理 responses 端点 + 嵌入式 Kuzu + 本地 HF embedder。

Uses the shared proxy_clients module — see tradingagents/llm_clients/proxy_clients.py.
Kuzu fulltext search is broken in graphiti; verify via direct Cypher query.
"""

from __future__ import annotations

import asyncio
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore", message="The Kuzu backend is deprecated.*")


async def _run() -> dict:
    from graphiti_core.nodes import EpisodeType
    from tradingagents.llm_clients.proxy_clients import make_graphiti

    graphiti = make_graphiti()
    await graphiti.build_indices_and_constraints()

    await graphiti.add_episode(
        name="Tesla Q3 earnings",
        episode_body="Tesla reported Q3 earnings that beat expectations. Stock rose 5% on heavy volume.",
        source=EpisodeType.text,
        source_description="market news test",
        reference_time=datetime.now(timezone.utc),
    )
    # graphiti.search() hits Kuzu fulltext-index bugs; use a direct Cypher
    # query to verify the ingestion path (LLM extraction + embedder + write).
    driver = graphiti.driver
    records, _, _ = await driver.execute_query(
        "MATCH (n:Entity) RETURN n.name AS name, n.summary AS summary LIMIT 10"
    )
    facts = [
        {"node": r.get("name", ""), "summary": (r.get("summary") or "")[:200]} for r in records
    ]
    await graphiti.close()
    return {"facts": facts}


def test_graphiti_add_episode_and_search() -> None:
    """graphiti ingests an episode and returns extracted entities."""
    result = asyncio.run(_run())
    assert "facts" in result
    assert len(result["facts"]) > 0
    print("\n=== graphiti smoke test ===")
    print(f"entities found: {len(result['facts'])}")
    for f in result["facts"]:
        print(f"  - node: {f['node']} | summary: {f['summary']}")
    print("=== PASS ===")


if __name__ == "__main__":
    test_graphiti_add_episode_and_search()
