"""Import Winterfell wiki Markdown as graphiti temporal episodes.

Builds a dynamic knowledge graph from the wiki, parallel to (not replacing)
the static Markdown store. Each .md file becomes an episode with:
  - reference_time from frontmatter ``date`` (or ``created`` fallback)
  - source_description noting the wiki directory and status

Priority content (by temporal value):
  1. Collisions/ — cross-domain contradiction points (cluster_a/cluster_b edges)
  2. Decisions/ — decision evolution records
  3. Analysis/ — evolving analysis with spine_trace dependencies
  4. Insights/ — point-in-time snapshots (superseded ones especially)

Kuzu limitation: graphiti's dedup candidate search hits Kuzu fulltext/vector
index bugs. We monkey-patch ``_semantic_candidate_search`` to return empty
results, so graphiti skips dedup and creates fresh nodes each time. This means
duplicate entities across episodes aren't merged — acceptable for an initial
import; re-run on Neo4j/FalkorDB for full dedup.

Usage::

    python scripts/import_winterfell_to_graphiti.py [--dir ~/Winterfell/wiki]
    python scripts/import_winterfell_to_graphiti.py --section Collisions
    python scripts/import_winterfell_to_graphiti.py --db /tmp/winterfell_graph.db
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("winterfell_import")

# Wiki directories by temporal-graph value (highest first).
SECTIONS = ["Collisions", "Decisions", "Analysis", "Insights"]


def _patch_kuzu_skip_dedup() -> None:
    """Monkey-patch graphiti's search functions to no-op on Kuzu.

    Kuzu's fulltext/vector index is broken in graphiti (the backend is
    deprecated for this reason). We patch the search functions at every
    module that imports them by name (search.py binds them at import time,
    so patching search_utils is not enough). Returning empty results makes
    graphiti skip dedup/contradiction-detection and always create fresh
    nodes/edges — acceptable for an initial import; re-run on Neo4j/FalkorDB
    for full dedup and temporal invalidation.
    """
    import graphiti_core.search.search as search_mod
    from graphiti_core.utils.maintenance import node_operations

    async def _noop_search(*_a, **_k):
        return []

    async def _noop_node_search(clients, extracted_nodes):
        return [[] for _ in extracted_nodes]

    # Patch the module-level bound symbols in search.py
    for name in (
        "edge_fulltext_search",
        "node_fulltext_search",
        "edge_similarity_search",
        "node_similarity_search",
        "episode_fulltext_search",
        "community_fulltext_search",
        "community_similarity_search",
    ):
        if hasattr(search_mod, name):
            setattr(search_mod, name, _noop_search)

    # Patch the node dedup candidate search
    node_operations._semantic_candidate_search = _noop_node_search
    logger.info("patched graphiti search functions to skip Kuzu fulltext/vector indices")


def parse_frontmatter(content: str) -> dict[str, str]:
    """Extract YAML frontmatter fields from a Markdown file."""
    fm: dict[str, str] = {}
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return fm
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm


def resolve_reference_time(fm: dict[str, str], file_path: Path) -> datetime:
    """Pick the best reference_time from frontmatter (date > created > file mtime)."""
    for field in ("date", "created"):
        raw = fm.get(field)
        if raw:
            try:
                return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)


def collect_episodes(wiki_root: Path, section: str | None = None) -> list[tuple[Path, str, dict]]:
    """Collect (path, content, frontmatter) for all .md files in the section(s)."""
    episodes: list[tuple[Path, str, dict]] = []
    sections = [section] if section else SECTIONS
    for sec in sections:
        sec_dir = wiki_root / sec
        if not sec_dir.is_dir():
            logger.warning("section dir not found: %s", sec_dir)
            continue
        for md in sorted(sec_dir.rglob("*.md")):
            if md.name.startswith("_index"):
                continue
            content = md.read_text(encoding="utf-8")
            fm = parse_frontmatter(content)
            episodes.append((md, content, fm))
    return episodes


async def import_section(wiki_root: Path, db_path: str, section: str | None = None) -> dict:
    """Import wiki episodes into graphiti. Returns a summary dict."""
    from graphiti_core.nodes import EpisodeType
    from tradingagents.llm_clients.proxy_clients import make_graphiti

    _patch_kuzu_skip_dedup()

    graphiti = make_graphiti(db_path=db_path)
    await graphiti.build_indices_and_constraints()

    episodes = collect_episodes(wiki_root, section)
    logger.info("collected %d episodes from %s", len(episodes), section or "all sections")

    succeeded, failed = 0, 0
    for md_path, content, fm in episodes:
        ref_time = resolve_reference_time(fm, md_path)
        rel = md_path.relative_to(wiki_root)
        status = fm.get("status", "unknown")
        try:
            await graphiti.add_episode(
                name=f"Winterfell: {rel}",
                episode_body=content[:4000],
                source=EpisodeType.text,
                source_description=f"winterfell wiki | {rel.parent} | status={status}",
                reference_time=ref_time,
            )
            succeeded += 1
            logger.info("imported %s (status=%s, ref=%s)", rel, status, ref_time.date())
        except Exception as exc:
            failed += 1
            logger.warning("failed %s: %s", rel, exc)

    await graphiti.close()
    return {"succeeded": succeeded, "failed": failed, "total": len(episodes)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir",
        default=str(Path.home() / "Winterfell" / "wiki"),
        help="Winterfell wiki root (default: ~/Winterfell/wiki)",
    )
    parser.add_argument(
        "--db",
        default="/tmp/winterfell_graph.db",
        help="Kuzu database path (default: /tmp/winterfell_graph.db)",
    )
    parser.add_argument(
        "--section",
        default=None,
        choices=SECTIONS,
        help="Import only one section (default: all, in priority order)",
    )
    args = parser.parse_args()

    wiki_root = Path(args.dir).expanduser()
    if not wiki_root.is_dir():
        logger.error("wiki root not found: %s", wiki_root)
        return 1

    summary = asyncio.run(import_section(wiki_root, args.db, args.section))
    logger.info(
        "done: %d/%d imported, %d failed", summary["succeeded"], summary["total"], summary["failed"]
    )
    return 0 if summary["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
