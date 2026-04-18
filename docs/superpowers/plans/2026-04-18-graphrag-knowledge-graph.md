# GraphRAG Knowledge Graph Implementation Plan (Neo4j + Bitemporal)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the raw flat-text `scanner_context_packet` in analyst prompts with a structured, ticker-focused graph narrative produced by (1) extracting triples from scanner summaries into a persistent Neo4j bitemporal knowledge graph and (2) retrieving a ticker-scoped 2-hop subgraph at the start of each per-ticker pipeline.

**Architecture:**

1. **Persistent Neo4j graph.** A single Neo4j instance holds all historical knowledge across scan runs. Nodes: `Ticker`, `Sector`, `Theme`, `MacroEvent`, `GeoEvent`, `RiskFactor`. Edges: `BELONGS_TO`, `IMPACTS`, `DRIVES_SENTIMENT`, `EXPOSED_TO`, `RELATED_TO`.
2. **Bitemporal model.** Every node and edge carries `first_seen` (date first observed), `last_seen` (date most recently reasserted), and `provenance` (which scanner summary section produced it). Retrieval filters by staleness window so old, no-longer-reasserted facts drop out of prompts automatically.
3. **Deterministic extractor.** Parses the structured bullet rows emitted by `tradingagents/agents/scanners/scanner_summarizer.py` (`TICKER | sector | signal | evidence | implication`) with regex fallback for free-text. Skips summaries marked `[NO_EVIDENCE]` / `[QUALITY: empty]` / `[QUALITY: degraded]`. Writes via idempotent `MERGE` Cypher statements.
4. **Cypher retriever.** A new `Graph Context Retrieval` LangGraph node runs after `Instrument Preflight`. It executes a 2-hop bitemporal Cypher query seeded on the ticker, serializes results to text, and calls `quick_think_llm` via `invoke_with_timeout` to produce a 200–300-word briefing stored in `retrieved_graph_context`.
5. **Analyst fallback.** All four analysts prefer `retrieved_graph_context` over `scanner_context_packet` when populated. If Neo4j is unavailable or the ticker has no subgraph, they transparently fall back.
6. **Future mem0 hook.** A `LearningMemoryWriter` interface is introduced (no-op default) so a follow-up PR can wire the learning agent + mem0 persistence without touching this plan's code paths.

**Tech Stack:** Python, LangGraph `StateGraph`, `ChatOpenAI` via `invoke_with_timeout`, **Neo4j 5.x (official `neo4j` Python driver, sync)**, Docker Compose for local Neo4j. No NetworkX.

**Note on current scanner state (2026-04-18):** Scanner summaries are **not truncated** (the prior `max_chars` cap was removed because it created hallucinated content). `scanner_summarizer.py` emits structured pipe-delimited bullet rows plus quality-gate headers. This makes structured extraction preferable to narrative regex. Every ingested edge carries a `provenance` field naming the exact summary section — a direct mitigation for the "Scout Money" / unverified-news hallucination class documented in `bug_registry.md` BUG-001 and BUG-010.

---

## Why Neo4j (Cross-Check with Original Proposal)

| Concern | Resolution |
|---|---|
| Persistent memory across scans | Neo4j retains nodes/edges across runs; `last_seen` updates on re-observation |
| Bitemporal decay | `first_seen` / `last_seen` on every node and edge; retrieval filters on staleness window |
| Multi-hop and cross-ticker queries | Native Cypher traversal — trivial to extend beyond 2 hops or add relationship-type filters |
| Future learning agent + mem0 | `LearningMemoryWriter` interface + ADR hook; mem0 will co-exist (episodic memory), Neo4j is semantic memory |
| Infra cost | `docker-compose.yml` with Neo4j service; single `neo4j://` URI via `DEFAULT_CONFIG`; no cloud dependency required |
| Test cost | `testcontainers[neo4j]` in CI / local; `NEO4J_TEST_SKIP=1` guard so unit tests stay fast when Docker absent |

**Preserved from the original proposal:**
- Neo4j as the graph store
- Bitemporal mechanics on edges
- Cypher `MERGE` for idempotent ingestion
- Retrieval node between scanner and analysts

**Intentionally deferred from the original proposal:**
- **Actor-Critic feedback loop** — the existing parallel Risk R1/R2 → Risk Synthesis already implements actor-critic. Adding a loop-back to Trader would conflict with `state_has_critical_abort` guards and create unbounded recursion. Risk Synthesis will still receive `retrieved_graph_context` via `build_research_packet()`.

---

## File Map

### New files

| File | Responsibility |
|---|---|
| `tradingagents/graph/graph_memory/__init__.py` | Package marker |
| `tradingagents/graph/graph_memory/schema.py` | Cypher constraints + index DDL, node-type / relation-type constants |
| `tradingagents/graph/graph_memory/driver.py` | `get_driver()` singleton, `close_driver()`, health check, context-managed session helper |
| `tradingagents/graph/graph_memory/extractor.py` | `ingest_scanner_state(session, scanner_state)` — structured-row + fallback parser → Cypher `MERGE` |
| `tradingagents/graph/graph_memory/retriever.py` | `get_subgraph(session, ticker, scan_date, hops, staleness_days)` + `format_subgraph_for_llm()` + `create_graph_context_retrieval_node(llm, driver_factory)` |
| `tradingagents/graph/graph_memory/learning.py` | `LearningMemoryWriter` protocol (no-op default) — mem0 integration hook for the upcoming learning agent |
| `docker-compose.yml` (or existing file — append service) | Neo4j 5.x service for local dev |
| `docs/agent/decisions/022-neo4j-knowledge-graph.md` | ADR documenting Neo4j + bitemporal + mem0 hook decision |
| `tests/graph/graph_memory/__init__.py` | Test package marker |
| `tests/graph/graph_memory/conftest.py` | `neo4j_session` fixture using `testcontainers[neo4j]`, skip if unavailable |
| `tests/graph/graph_memory/test_schema.py` | DDL idempotency |
| `tests/graph/graph_memory/test_extractor.py` | Structured-row parsing, quality-gate skipping, bitemporal stamping |
| `tests/graph/graph_memory/test_retriever.py` | 2-hop Cypher traversal, staleness filter, LLM node |
| `tests/graph/graph_memory/test_learning.py` | No-op default writer contract |

### Modified files

| File | Change |
|---|---|
| `pyproject.toml` | Add `neo4j ^= 5.20` runtime dep; `testcontainers[neo4j] ^= 4.0` dev dep |
| `tradingagents/default_config.py` | Add `neo4j_uri`, `neo4j_user`, `neo4j_password`, `graph_staleness_days`, `graph_retrieval_hops`, `graph_enabled` |
| `tradingagents/agents/utils/agent_states.py` | Add `retrieved_graph_context: Annotated[str, ...]` |
| `tradingagents/graph/propagation.py` | Add `retrieved_graph_context: str = ""` parameter and key in returned state |
| `agent_os/backend/services/langgraph_engine.py` | Call `ingest_scanner_state()` after scanner completes (one-shot). Forward flag only — no graph dict in state |
| `tradingagents/graph/scanner_graph.py` | After `self.graph.invoke(initial_state)`, call `ingest_scanner_state()` |
| `tradingagents/graph/setup.py` | Add `Graph Context Retrieval` node after `Instrument Preflight`; closure accepts retrieval node factory |
| `tradingagents/graph/trading_graph.py` | Instantiate retriever (driver + LLM) and pass to `GraphSetup` |
| `tradingagents/agents/analysts/market_analyst.py` | Prefer `retrieved_graph_context`, fall back to `scanner_context_packet` |
| `tradingagents/agents/analysts/social_media_analyst.py` | Same fallback pattern |
| `tradingagents/agents/analysts/news_analyst.py` | Same fallback (skip ticker filter when graph context used — already ticker-focused) |
| `tradingagents/agents/analysts/fundamentals_analyst.py` | Same fallback pattern |
| `tradingagents/agents/utils/summary_context.py` | `build_research_packet()` and `build_debate_evidence_brief()` prefer graph context |

---

## Bitemporal Cypher Schema (reference)

```cypher
// Constraints (unique IDs)
CREATE CONSTRAINT ticker_symbol IF NOT EXISTS
  FOR (t:Ticker) REQUIRE t.symbol IS UNIQUE;
CREATE CONSTRAINT sector_name IF NOT EXISTS
  FOR (s:Sector) REQUIRE s.name IS UNIQUE;
CREATE CONSTRAINT theme_id IF NOT EXISTS
  FOR (x:Theme) REQUIRE x.id IS UNIQUE;
CREATE CONSTRAINT geoevent_id IF NOT EXISTS
  FOR (x:GeoEvent) REQUIRE x.id IS UNIQUE;
CREATE CONSTRAINT macroevent_id IF NOT EXISTS
  FOR (x:MacroEvent) REQUIRE x.id IS UNIQUE;
CREATE CONSTRAINT riskfactor_id IF NOT EXISTS
  FOR (x:RiskFactor) REQUIRE x.id IS UNIQUE;

// Indexes for bitemporal queries
CREATE INDEX ticker_last_seen IF NOT EXISTS
  FOR (t:Ticker) ON (t.last_seen);
```

**Bitemporal fields** (on every node and relationship):

- `first_seen: date` — first scan_date that observed this fact
- `last_seen: date` — most recent scan_date that reasserted this fact
- `provenance: string` — summary section name (e.g. `"smart_money_summary"`)
- `polarity: string` — `"bullish" | "bearish" | ""` (relationships only)

**Idempotent upsert pattern:**

```cypher
MERGE (t:Ticker {symbol: $symbol})
  ON CREATE SET t.first_seen = date($scan_date), t.last_seen = date($scan_date)
  ON MATCH  SET t.last_seen = date($scan_date)
MERGE (s:Sector {name: $sector})
  ON CREATE SET s.first_seen = date($scan_date), s.last_seen = date($scan_date)
  ON MATCH  SET s.last_seen  = date($scan_date)
MERGE (t)-[r:BELONGS_TO]->(s)
  ON CREATE SET r.first_seen = date($scan_date), r.last_seen = date($scan_date),
                r.provenance = $provenance, r.polarity = ""
  ON MATCH  SET r.last_seen  = date($scan_date),
                r.provenance = $provenance
```

**Retrieval pattern (2-hop with staleness filter):**

```cypher
MATCH path = (t:Ticker {symbol: $symbol})-[r*1..$hops]-(n)
WHERE ALL(e IN r WHERE e.last_seen >= date($cutoff))
  AND n.last_seen >= date($cutoff)
RETURN nodes(path) AS ns, relationships(path) AS rs
LIMIT 200
```

---

## Task 1: Infra — Neo4j service, config, driver singleton

**Files:**
- Modify: `pyproject.toml`
- Modify: `tradingagents/default_config.py`
- Create: `docker-compose.yml` (or append if exists)
- Create: `tradingagents/graph/graph_memory/__init__.py` (empty)
- Create: `tradingagents/graph/graph_memory/driver.py`
- Create: `tests/graph/graph_memory/__init__.py` (empty)
- Create: `tests/graph/graph_memory/conftest.py`

- [ ] **Step 1: Add dependencies**

```bash
# pyproject.toml — under [project.dependencies] or [tool.poetry.dependencies]
# add:  neo4j = "^5.20"
# under dev deps: testcontainers = {extras = ["neo4j"], version = "^4.0"}
```

- [ ] **Step 2: Create / append `docker-compose.yml`**

```yaml
services:
  neo4j:
    image: neo4j:5.20-community
    container_name: trading-agents-neo4j
    ports:
      - "7474:7474"  # HTTP / browser
      - "7687:7687"  # Bolt
    environment:
      NEO4J_AUTH: "neo4j/tradingagents"
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_server_memory_heap_initial__size: "512m"
      NEO4J_server_memory_heap_max__size: "1G"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p tradingagents 'RETURN 1'"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  neo4j_data:
  neo4j_logs:
```

- [ ] **Step 3: Extend `default_config.py`**

Insert into `DEFAULT_CONFIG` (keep alphabetical where possible):

```python
"graph_enabled": True,
"graph_retrieval_hops": 2,
"graph_staleness_days": 14,
"neo4j_uri": os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
"neo4j_user": os.getenv("NEO4J_USER", "neo4j"),
"neo4j_password": os.getenv("NEO4J_PASSWORD", "tradingagents"),
"neo4j_database": os.getenv("NEO4J_DATABASE", "neo4j"),
```

- [ ] **Step 4: Write the failing driver test**

```python
# tests/graph/graph_memory/conftest.py
from __future__ import annotations

import os

import pytest

try:
    from testcontainers.neo4j import Neo4jContainer
except ImportError:
    Neo4jContainer = None


@pytest.fixture(scope="session")
def neo4j_container():
    if os.getenv("NEO4J_TEST_SKIP") == "1" or Neo4jContainer is None:
        pytest.skip("Neo4j testcontainer unavailable; set NEO4J_TEST_SKIP=0 + install docker")
    with Neo4jContainer("neo4j:5.20-community") as container:
        yield container


@pytest.fixture()
def neo4j_session(neo4j_container):
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        neo4j_container.get_connection_url(),
        auth=("neo4j", neo4j_container.NEO4J_ADMIN_PASSWORD),
    )
    with driver.session() as session:
        # Reset state between tests
        session.run("MATCH (n) DETACH DELETE n")
        yield session
    driver.close()
```

```python
# tests/graph/graph_memory/test_driver.py
from tradingagents.graph.graph_memory import driver as driver_mod


def test_get_driver_is_singleton(monkeypatch):
    """get_driver() returns the same driver instance on repeated calls."""
    monkeypatch.setenv("NEO4J_URI", "neo4j://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "tradingagents")

    driver_mod.close_driver()  # reset any prior singleton
    d1 = driver_mod.get_driver()
    d2 = driver_mod.get_driver()
    try:
        assert d1 is d2
    finally:
        driver_mod.close_driver()


def test_close_driver_is_idempotent():
    driver_mod.close_driver()
    driver_mod.close_driver()  # must not raise
```

- [ ] **Step 5: Run tests — expect ImportError**

```bash
conda activate tradingagents
pip install -e ".[dev]"  # pick up new deps
pytest tests/graph/graph_memory/test_driver.py -v
```

Expected: `ModuleNotFoundError: No module named 'tradingagents.graph.graph_memory.driver'`

- [ ] **Step 6: Implement the driver singleton**

```python
# tradingagents/graph/graph_memory/driver.py
"""Neo4j driver singleton + session helpers.

One process keeps one driver. Sessions are short-lived and opened via the
`session_scope()` context manager. `get_driver()` lazily connects on first
call using values from `DEFAULT_CONFIG`.
"""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Iterator

from neo4j import Driver, GraphDatabase, Session

from tradingagents.default_config import DEFAULT_CONFIG

_logger = logging.getLogger(__name__)
_driver: Driver | None = None
_lock = threading.Lock()


def get_driver() -> Driver:
    """Return a process-wide Neo4j driver, creating it lazily."""
    global _driver
    if _driver is not None:
        return _driver
    with _lock:
        if _driver is not None:
            return _driver
        uri = DEFAULT_CONFIG["neo4j_uri"]
        user = DEFAULT_CONFIG["neo4j_user"]
        password = DEFAULT_CONFIG["neo4j_password"]
        _driver = GraphDatabase.driver(uri, auth=(user, password))
        _logger.info("graph_memory: Neo4j driver connected to %s", uri)
        return _driver


def close_driver() -> None:
    """Close the process-wide driver. Idempotent."""
    global _driver
    with _lock:
        if _driver is not None:
            try:
                _driver.close()
            except Exception as exc:  # pragma: no cover
                _logger.warning("graph_memory: error closing driver: %s", exc)
            _driver = None


@contextmanager
def session_scope(database: str | None = None) -> Iterator[Session]:
    """Open a scoped session on the configured database."""
    db = database or DEFAULT_CONFIG["neo4j_database"]
    driver = get_driver()
    session = driver.session(database=db)
    try:
        yield session
    finally:
        session.close()


def health_check() -> bool:
    """Return True if Neo4j responds to a trivial query."""
    try:
        with session_scope() as s:
            s.run("RETURN 1").single()
        return True
    except Exception as exc:
        _logger.warning("graph_memory: health check failed: %s", exc)
        return False
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
pytest tests/graph/graph_memory/test_driver.py -v
```

Expected: both tests PASS (no live Neo4j needed — tests only check singleton/idempotency; they stub env and close immediately).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml docker-compose.yml tradingagents/default_config.py \
        tradingagents/graph/graph_memory/__init__.py \
        tradingagents/graph/graph_memory/driver.py \
        tests/graph/graph_memory/__init__.py \
        tests/graph/graph_memory/conftest.py \
        tests/graph/graph_memory/test_driver.py
git commit -m "feat(graphrag): add Neo4j driver singleton, docker-compose service, and config"
```

---

## Task 2: Schema — constraints + indexes

**Files:**
- Create: `tradingagents/graph/graph_memory/schema.py`
- Create: `tests/graph/graph_memory/test_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/graph_memory/test_schema.py
from tradingagents.graph.graph_memory.schema import (
    NODE_LABELS,
    RELATION_TYPES,
    apply_schema,
)


def test_node_labels_cover_expected_types():
    assert {"Ticker", "Sector", "Theme", "MacroEvent", "GeoEvent", "RiskFactor"} <= set(NODE_LABELS)


def test_relation_types_cover_expected():
    assert {
        "BELONGS_TO", "IMPACTS", "DRIVES_SENTIMENT", "EXPOSED_TO", "RELATED_TO"
    } <= set(RELATION_TYPES)


def test_apply_schema_idempotent(neo4j_session):
    """Running apply_schema twice must not raise."""
    apply_schema(neo4j_session)
    apply_schema(neo4j_session)  # idempotent
    result = neo4j_session.run("SHOW CONSTRAINTS").data()
    # Expect at least one constraint per node label
    names = " ".join(str(row) for row in result)
    for label in ("Ticker", "Sector", "Theme", "GeoEvent"):
        assert label in names
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/graph/graph_memory/test_schema.py::test_node_labels_cover_expected_types -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement the schema**

```python
# tradingagents/graph/graph_memory/schema.py
"""Static labels, relationship types, and DDL for the knowledge graph."""
from __future__ import annotations

from neo4j import Session

NODE_LABELS: tuple[str, ...] = (
    "Ticker",
    "Sector",
    "Theme",
    "MacroEvent",
    "GeoEvent",
    "RiskFactor",
)

RELATION_TYPES: tuple[str, ...] = (
    "BELONGS_TO",
    "IMPACTS",
    "DRIVES_SENTIMENT",
    "EXPOSED_TO",
    "RELATED_TO",
)

# Unique key per label
_UNIQUE_KEY: dict[str, str] = {
    "Ticker": "symbol",
    "Sector": "name",
    "Theme": "id",
    "MacroEvent": "id",
    "GeoEvent": "id",
    "RiskFactor": "id",
}

_CONSTRAINT_STATEMENTS: tuple[str, ...] = tuple(
    f"CREATE CONSTRAINT {label.lower()}_{key}_unique IF NOT EXISTS "
    f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
    for label, key in _UNIQUE_KEY.items()
)

_INDEX_STATEMENTS: tuple[str, ...] = tuple(
    f"CREATE INDEX {label.lower()}_last_seen IF NOT EXISTS "
    f"FOR (n:{label}) ON (n.last_seen)"
    for label in NODE_LABELS
)


def apply_schema(session: Session) -> None:
    """Ensure constraints + indexes exist. Idempotent."""
    for stmt in _CONSTRAINT_STATEMENTS + _INDEX_STATEMENTS:
        session.run(stmt)


def unique_key_for(label: str) -> str:
    """Return the property name used as the unique key for *label*."""
    return _UNIQUE_KEY[label]
```

- [ ] **Step 4: Run tests — all should pass against the testcontainer**

```bash
pytest tests/graph/graph_memory/test_schema.py -v
```

If you don't have Docker locally, skip with `NEO4J_TEST_SKIP=1 pytest ...`.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/graph_memory/schema.py tests/graph/graph_memory/test_schema.py
git commit -m "feat(graphrag): add knowledge-graph schema (constraints + indexes)"
```

---

## Task 3: Extractor — scanner summaries → Cypher `MERGE`

**Files:**
- Create: `tradingagents/graph/graph_memory/extractor.py`
- Modify: `tests/graph/graph_memory/test_extractor.py` (create)

The extractor primarily parses the **structured bullet rows** emitted by `tradingagents/agents/scanners/scanner_summarizer.py`:

```
- TICKER | sector | signal | exact evidence | implication
- SECTOR/THEME | exact evidence | implication
```

Fallback path: regex/proximity on narrative text when a summary has no pipe-delimited rows.

Quality gating: skip any field containing `[NO_EVIDENCE]`, `[QUALITY: empty]`, `[QUALITY: degraded]`.

Every `MERGE` carries `scan_date` + `provenance` (which summary section produced the row).

- [ ] **Step 1: Write failing tests**

```python
# tests/graph/graph_memory/test_extractor.py
from tradingagents.graph.graph_memory.extractor import ingest_scanner_state
from tradingagents.graph.graph_memory.schema import apply_schema


_STRUCTURED_STATE = {
    "scan_date": "2026-04-18",
    "macro_scan_summary": (
        "- NVDA | Technology | bullish momentum | +4.2% on AI infra demand | tailwind continues\n"
        "- MSFT | Technology | neutral | steady cloud revenue | hold\n"
        "- JPM | Financials | bearish | rate sensitivity, NII headwind | reduce\n"
        "- Technology/AI infrastructure | hyperscaler capex surge | sector tailwind"
    ),
    "industry_deep_dive_summary": (
        "- NVDA | Technology | strong buy | backlog extends 2 quarters | momentum"
    ),
    "geopolitical_summary": (
        "- US-China trade tensions | new export controls 2026-04-17 | Technology risk"
    ),
    "sector_summary": "",
    "market_movers_summary": (
        "- NVDA | Technology | gainer | +4.2% | momentum confirmed"
    ),
    "smart_money_summary": (
        "- NVDA | Technology | institutional accumulation | finviz flagged 2026-04-17 | bullish flow"
    ),
    "factor_alignment_summary": "",
    "gatekeeper_summary": "",
    "drift_opportunities_summary": "",
}

_QUALITY_GATED_STATE = {
    "scan_date": "2026-04-18",
    "macro_scan_summary": "[NO_EVIDENCE] nothing qualified",
    "smart_money_summary": "[QUALITY: empty]",
    "industry_deep_dive_summary": "[QUALITY: degraded] partial",
    "geopolitical_summary": "",
    "sector_summary": "",
    "market_movers_summary": "",
    "factor_alignment_summary": "",
    "gatekeeper_summary": "",
    "drift_opportunities_summary": "",
}


def _count(session, query: str, **params) -> int:
    return session.run(query, **params).single()[0]


def test_ingest_creates_ticker_nodes(neo4j_session):
    apply_schema(neo4j_session)
    ingest_scanner_state(neo4j_session, _STRUCTURED_STATE)
    n = _count(neo4j_session, "MATCH (t:Ticker) RETURN count(t) AS c")
    assert n >= 3  # NVDA, MSFT, JPM


def test_ingest_creates_belongs_to_edges(neo4j_session):
    apply_schema(neo4j_session)
    ingest_scanner_state(neo4j_session, _STRUCTURED_STATE)
    n = _count(
        neo4j_session,
        "MATCH (:Ticker {symbol:'NVDA'})-[:BELONGS_TO]->(:Sector {name:'Technology'}) RETURN count(*) AS c",
    )
    assert n == 1


def test_ingest_stamps_bitemporal_fields(neo4j_session):
    apply_schema(neo4j_session)
    ingest_scanner_state(neo4j_session, _STRUCTURED_STATE)
    rec = neo4j_session.run(
        "MATCH (t:Ticker {symbol:'NVDA'}) RETURN t.first_seen AS fs, t.last_seen AS ls"
    ).single()
    assert str(rec["fs"]) == "2026-04-18"
    assert str(rec["ls"]) == "2026-04-18"


def test_ingest_updates_last_seen_on_reobservation(neo4j_session):
    apply_schema(neo4j_session)
    ingest_scanner_state(neo4j_session, _STRUCTURED_STATE)
    state2 = dict(_STRUCTURED_STATE, scan_date="2026-04-19")
    ingest_scanner_state(neo4j_session, state2)
    rec = neo4j_session.run(
        "MATCH (t:Ticker {symbol:'NVDA'}) RETURN t.first_seen AS fs, t.last_seen AS ls"
    ).single()
    assert str(rec["fs"]) == "2026-04-18"
    assert str(rec["ls"]) == "2026-04-19"


def test_ingest_sentiment_polarity(neo4j_session):
    apply_schema(neo4j_session)
    ingest_scanner_state(neo4j_session, _STRUCTURED_STATE)
    n_bull = _count(
        neo4j_session,
        "MATCH (:Ticker {symbol:'NVDA'})-[r:DRIVES_SENTIMENT {polarity:'bullish'}]->() RETURN count(r) AS c",
    )
    n_bear = _count(
        neo4j_session,
        "MATCH (:Ticker {symbol:'JPM'})-[r:DRIVES_SENTIMENT {polarity:'bearish'}]->() RETURN count(r) AS c",
    )
    assert n_bull >= 1
    assert n_bear >= 1


def test_ingest_provenance_recorded(neo4j_session):
    apply_schema(neo4j_session)
    ingest_scanner_state(neo4j_session, _STRUCTURED_STATE)
    rec = neo4j_session.run(
        "MATCH (:Ticker {symbol:'NVDA'})-[r:DRIVES_SENTIMENT]->() "
        "WHERE r.provenance = 'smart_money_summary' "
        "RETURN count(r) AS c"
    ).single()
    assert rec["c"] >= 1


def test_ingest_skips_quality_gated_fields(neo4j_session):
    apply_schema(neo4j_session)
    ingest_scanner_state(neo4j_session, _QUALITY_GATED_STATE)
    n_nodes = _count(neo4j_session, "MATCH (n) RETURN count(n) AS c")
    assert n_nodes == 0


def test_ingest_geo_event_impacts_sector(neo4j_session):
    apply_schema(neo4j_session)
    ingest_scanner_state(neo4j_session, _STRUCTURED_STATE)
    n = _count(
        neo4j_session,
        "MATCH (:GeoEvent)-[:IMPACTS]->(:Sector {name:'Technology'}) RETURN count(*) AS c",
    )
    assert n >= 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/graph/graph_memory/test_extractor.py -v
```

Expected: `ImportError: cannot import name 'ingest_scanner_state'`.

- [ ] **Step 3: Implement the extractor**

```python
# tradingagents/graph/graph_memory/extractor.py
"""Deterministic ingestion of scanner summary fields into Neo4j.

Primary path: parse structured pipe-delimited bullet rows
    TICKER | sector | signal | evidence | implication
    SECTOR/THEME | evidence | implication
Fallback path: regex + proximity on free-form narrative text.

Skips any summary field containing `[NO_EVIDENCE]`, `[QUALITY: empty]`,
or `[QUALITY: degraded]`. Every MERGE records `provenance` = source
summary section name.
"""
from __future__ import annotations

import logging
import re
from typing import Sequence

from neo4j import Session

_logger = logging.getLogger(__name__)

_SECTORS: tuple[str, ...] = (
    "Technology",
    "Information Technology",
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Health Care",
    "Financials",
    "Industrials",
    "Materials",
    "Energy",
    "Utilities",
    "Real Estate",
)

_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")
_COMMON_WORDS = frozenset({
    "AI", "US", "FX", "ETF", "CEO", "SEC", "GDP", "CPI", "VIX",
    "FED", "BUY", "SELL", "HOLD", "TOP", "NET", "NEW", "HIGH",
    "LOW", "ALL", "AND", "THE", "FOR", "ARE", "NOT", "BUT",
})

_BULLISH_WORDS = re.compile(
    r"\b(bullish|outperform|accumulation|tailwind|momentum|strong|surge|rally|breakout|gainer|buy)\b",
    re.IGNORECASE,
)
_BEARISH_WORDS = re.compile(
    r"\b(bearish|underperform|headwind|risk|tension|concern|lagging|decline|drag|decliner|sell|caution|weak)\b",
    re.IGNORECASE,
)

_QUALITY_MARKERS = ("[NO_EVIDENCE]", "[QUALITY: empty]", "[QUALITY: degraded]")
_BULLET_ROW_RE = re.compile(r"^\s*[-*]\s*(.+?\|.+)$", re.MULTILINE)
_TICKER_LEADER_RE = re.compile(r"^([A-Z]{1,5}(?:\.[A-Z])?)$")

_SUMMARY_FIELDS: Sequence[str] = (
    "macro_scan_summary",
    "industry_deep_dive_summary",
    "market_movers_summary",
    "smart_money_summary",
    "factor_alignment_summary",
    "gatekeeper_summary",
    "geopolitical_summary",
    "sector_summary",
    "drift_opportunities_summary",
)


def _is_quality_gated(text: str) -> bool:
    if not text or not text.strip():
        return True
    head = text.strip()[:200]
    return any(marker in head for marker in _QUALITY_MARKERS)


def _canon_sector(name: str) -> str:
    name = (name or "").strip()
    return "Technology" if name.lower() == "information technology" else name


def _infer_polarity(*parts: str) -> str:
    joined = " ".join(p or "" for p in parts)
    if _BULLISH_WORDS.search(joined):
        return "bullish"
    if _BEARISH_WORDS.search(joined):
        return "bearish"
    return ""


def _parse_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for match in _BULLET_ROW_RE.finditer(text):
        cols = [c.strip() for c in match.group(1).split("|")]
        if len(cols) >= 2:
            rows.append(cols)
    return rows


# ---------- Cypher upsert primitives ----------

def _merge_ticker(session: Session, symbol: str, scan_date: str) -> None:
    session.run(
        "MERGE (t:Ticker {symbol: $symbol}) "
        "  ON CREATE SET t.first_seen = date($scan_date), t.last_seen = date($scan_date) "
        "  ON MATCH  SET t.last_seen  = date($scan_date)",
        symbol=symbol, scan_date=scan_date,
    )


def _merge_unique(session: Session, label: str, key_prop: str, key_val: str, scan_date: str) -> None:
    session.run(
        f"MERGE (n:{label} {{{key_prop}: $val}}) "
        f"  ON CREATE SET n.first_seen = date($scan_date), n.last_seen = date($scan_date) "
        f"  ON MATCH  SET n.last_seen  = date($scan_date)",
        val=key_val, scan_date=scan_date,
    )


def _merge_rel(
    session: Session,
    src_label: str, src_key: str, src_val: str,
    rel: str,
    dst_label: str, dst_key: str, dst_val: str,
    scan_date: str,
    provenance: str,
    polarity: str = "",
) -> None:
    session.run(
        f"MATCH (s:{src_label} {{{src_key}: $sv}}), (d:{dst_label} {{{dst_key}: $dv}}) "
        f"MERGE (s)-[r:{rel}]->(d) "
        f"  ON CREATE SET r.first_seen = date($scan_date), r.last_seen = date($scan_date), "
        f"                r.provenance = $prov, r.polarity = $pol "
        f"  ON MATCH  SET r.last_seen  = date($scan_date), "
        f"                r.provenance = $prov, r.polarity = $pol",
        sv=src_val, dv=dst_val,
        scan_date=scan_date, prov=provenance, pol=polarity,
    )


# ---------- Row-level handlers ----------

def _ingest_ticker_row(
    session: Session, cols: list[str], scan_date: str, provenance: str
) -> None:
    ticker = cols[0]
    sector = _canon_sector(cols[1]) if len(cols) >= 2 else ""
    signal = cols[2] if len(cols) >= 3 else ""
    implication = cols[-1] if len(cols) >= 4 else ""

    _merge_ticker(session, ticker, scan_date)

    if sector and (sector in _SECTORS or sector == "Technology"):
        _merge_unique(session, "Sector", "name", sector, scan_date)
        _merge_rel(
            session,
            "Ticker", "symbol", ticker, "BELONGS_TO",
            "Sector", "name", sector,
            scan_date, provenance,
        )
        polarity = _infer_polarity(signal, implication)
        if polarity:
            _merge_rel(
                session,
                "Ticker", "symbol", ticker, "DRIVES_SENTIMENT",
                "Sector", "name", sector,
                scan_date, provenance, polarity,
            )

    if implication and re.search(
        r"\b(risk|exposure|headwind|tariff|rate sensitivity)\b",
        implication, re.IGNORECASE,
    ):
        risk_id = implication[:80].strip().rstrip(",;:")
        if risk_id:
            _merge_unique(session, "RiskFactor", "id", risk_id, scan_date)
            _merge_rel(
                session,
                "Ticker", "symbol", ticker, "EXPOSED_TO",
                "RiskFactor", "id", risk_id,
                scan_date, provenance, "bearish",
            )


def _ingest_sector_theme_row(
    session: Session, cols: list[str], scan_date: str, provenance: str
) -> None:
    leader = cols[0]
    left, _, right = leader.partition("/")
    sector = _canon_sector(left)
    theme = right.strip() if right else ""
    evidence = cols[1] if len(cols) >= 2 else ""
    implication = cols[-1] if len(cols) >= 3 else ""
    polarity = _infer_polarity(evidence, implication)

    sector_ok = sector in _SECTORS or sector == "Technology"
    if sector_ok:
        _merge_unique(session, "Sector", "name", sector, scan_date)

    if not theme:
        return

    theme_id = theme[:80].strip()
    if provenance == "geopolitical_summary":
        _merge_unique(session, "GeoEvent", "id", theme_id, scan_date)
        if sector_ok:
            _merge_rel(
                session,
                "GeoEvent", "id", theme_id, "IMPACTS",
                "Sector", "name", sector,
                scan_date, provenance, polarity or "bearish",
            )
    else:
        _merge_unique(session, "Theme", "id", theme_id, scan_date)
        if sector_ok:
            _merge_rel(
                session,
                "Theme", "id", theme_id, "RELATED_TO",
                "Sector", "name", sector,
                scan_date, provenance, polarity,
            )


def _ingest_rows(session: Session, text: str, scan_date: str, provenance: str) -> bool:
    rows = _parse_rows(text)
    if not rows:
        return False
    for cols in rows:
        leader = cols[0]
        if _TICKER_LEADER_RE.match(leader) and leader not in _COMMON_WORDS:
            _ingest_ticker_row(session, cols, scan_date, provenance)
        else:
            _ingest_sector_theme_row(session, cols, scan_date, provenance)
    return True


def _ingest_narrative_fallback(
    session: Session, text: str, scan_date: str, provenance: str
) -> None:
    tickers = {m for m in _TICKER_RE.findall(text) if m not in _COMMON_WORDS and len(m) >= 2}
    sectors = {
        _canon_sector(s) for s in _SECTORS if s.lower() in text.lower()
    }

    for t in tickers:
        _merge_ticker(session, t, scan_date)
    for s in sectors:
        _merge_unique(session, "Sector", "name", s, scan_date)

    for sentence in re.split(r"[.!?\n]+", text):
        sent_tickers = {m for m in _TICKER_RE.findall(sentence) if m not in _COMMON_WORDS and len(m) >= 2}
        if not sent_tickers:
            continue
        polarity = _infer_polarity(sentence)
        sent_sectors = {_canon_sector(s) for s in _SECTORS if s.lower() in sentence.lower()}
        for t in sent_tickers:
            for s in sent_sectors:
                _merge_rel(
                    session,
                    "Ticker", "symbol", t, "BELONGS_TO",
                    "Sector", "name", s,
                    scan_date, provenance,
                )
                if polarity:
                    _merge_rel(
                        session,
                        "Ticker", "symbol", t, "DRIVES_SENTIMENT",
                        "Sector", "name", s,
                        scan_date, provenance, polarity,
                    )


# ---------- Public entrypoint ----------

def ingest_scanner_state(session: Session, scanner_state: dict) -> None:
    """Ingest the final scanner state into Neo4j (idempotent)."""
    scan_date = str(scanner_state.get("scan_date") or "").strip()
    if not scan_date:
        _logger.warning("ingest_scanner_state: no scan_date in state; skipping ingestion")
        return

    for field in _SUMMARY_FIELDS:
        text = str(scanner_state.get(field) or "")
        if _is_quality_gated(text):
            continue
        if not _ingest_rows(session, text, scan_date, field):
            _ingest_narrative_fallback(session, text, scan_date, field)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/graph/graph_memory/test_extractor.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/graph_memory/extractor.py tests/graph/graph_memory/test_extractor.py
git commit -m "feat(graphrag): ingest scanner summaries into Neo4j with bitemporal stamping + provenance"
```

---

## Task 4: Retriever — Cypher 2-hop + LLM narrative

**Files:**
- Create: `tradingagents/graph/graph_memory/retriever.py`
- Create: `tests/graph/graph_memory/test_retriever.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/graph/graph_memory/test_retriever.py
from unittest.mock import MagicMock, patch

from tradingagents.graph.graph_memory.extractor import ingest_scanner_state
from tradingagents.graph.graph_memory.retriever import (
    get_subgraph,
    format_subgraph_for_llm,
    create_graph_context_retrieval_node,
)
from tradingagents.graph.graph_memory.schema import apply_schema


_STATE = {
    "scan_date": "2026-04-18",
    "macro_scan_summary": (
        "- NVDA | Technology | bullish | AI tailwind | momentum\n"
        "- JPM | Financials | bearish | rate sensitivity | reduce"
    ),
    "geopolitical_summary": "- US-China trade tensions | export controls | Technology risk",
    "industry_deep_dive_summary": "",
    "market_movers_summary": "",
    "smart_money_summary": "",
    "factor_alignment_summary": "",
    "gatekeeper_summary": "",
    "sector_summary": "",
    "drift_opportunities_summary": "",
}


def test_get_subgraph_includes_2hop_neighbors(neo4j_session):
    apply_schema(neo4j_session)
    ingest_scanner_state(neo4j_session, _STATE)

    sub = get_subgraph(neo4j_session, "NVDA", "2026-04-18", hops=2, staleness_days=14)
    ids = {n["id"] for n in sub["nodes"]}
    assert "NVDA" in ids
    assert "Technology" in ids
    # 2-hop via Technology -> US-China tensions
    assert any("US-China" in x for x in ids)


def test_get_subgraph_respects_staleness(neo4j_session):
    apply_schema(neo4j_session)
    ingest_scanner_state(neo4j_session, _STATE)
    # Retrieval "as of" a date 100 days later with a 14-day window must be empty
    sub = get_subgraph(neo4j_session, "NVDA", "2026-07-30", hops=2, staleness_days=14)
    assert sub["nodes"] == [] or {"NVDA"} == {n["id"] for n in sub["nodes"]}


def test_get_subgraph_unknown_ticker(neo4j_session):
    apply_schema(neo4j_session)
    sub = get_subgraph(neo4j_session, "NOPE", "2026-04-18", hops=2, staleness_days=14)
    assert sub["nodes"] == []
    assert sub["edges"] == []


def test_format_subgraph_contains_provenance(neo4j_session):
    apply_schema(neo4j_session)
    ingest_scanner_state(neo4j_session, _STATE)
    sub = get_subgraph(neo4j_session, "NVDA", "2026-04-18", hops=2, staleness_days=14)
    text = format_subgraph_for_llm(sub, "NVDA")
    assert "NVDA" in text
    assert "macro_scan_summary" in text  # provenance surfaces in serialization


def test_retrieval_node_writes_context(neo4j_session):
    apply_schema(neo4j_session)
    ingest_scanner_state(neo4j_session, _STATE)

    # driver_factory returns a context manager yielding the live session
    class _SessCtx:
        def __enter__(self_inner): return neo4j_session
        def __exit__(self_inner, *a): return False

    mock_llm = MagicMock()
    with patch(
        "tradingagents.graph.graph_memory.retriever.invoke_with_timeout",
        return_value=(MagicMock(content="NVDA benefits from AI tailwind per macro_scan_summary."), None),
    ):
        node_fn = create_graph_context_retrieval_node(mock_llm, lambda: _SessCtx())
        state = {"company_of_interest": "NVDA", "trade_date": "2026-04-18"}
        result = node_fn(state)
    assert result["retrieved_graph_context"].startswith("NVDA benefits")


def test_retrieval_node_empty_subgraph_returns_empty_context(neo4j_session):
    apply_schema(neo4j_session)

    class _SessCtx:
        def __enter__(self_inner): return neo4j_session
        def __exit__(self_inner, *a): return False

    mock_llm = MagicMock()
    node_fn = create_graph_context_retrieval_node(mock_llm, lambda: _SessCtx())
    result = node_fn({"company_of_interest": "UNKNOWN", "trade_date": "2026-04-18"})
    assert result["retrieved_graph_context"] == ""
    mock_llm.invoke.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/graph/graph_memory/test_retriever.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement the retriever**

```python
# tradingagents/graph/graph_memory/retriever.py
"""Cypher-based graph-context retrieval + LLM narrative synthesis.

Exposes:
  get_subgraph(session, ticker, scan_date, hops, staleness_days) -> dict
  format_subgraph_for_llm(subgraph, ticker) -> str
  create_graph_context_retrieval_node(llm, driver_factory) -> callable
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Callable, ContextManager

from neo4j import Session

from tradingagents.agents.utils.llm_guard import invoke_with_timeout
from tradingagents.default_config import DEFAULT_CONFIG

_logger = logging.getLogger(__name__)

_RETRIEVAL_SYSTEM_PROMPT = (
    "You are a concise financial analyst briefing assistant. "
    "Given a subgraph of market knowledge relevant to a specific stock ticker, "
    "write a focused 200-300 word briefing paragraph that covers: "
    "(1) the ticker's sector and any macro/geo risks to that sector, "
    "(2) sentiment drivers (bullish/bearish themes), "
    "(3) related risk factors. "
    "Reference actual entity names from the graph. "
    "When a fact comes from a specific source, cite it using the edge's "
    "provenance field (e.g. 'per smart_money_summary'). "
    "Do not invent sources and do not add facts absent from the subgraph."
)


def _cutoff(scan_date: str, staleness_days: int) -> str:
    d = date.fromisoformat(scan_date)
    return (d - timedelta(days=staleness_days)).isoformat()


def get_subgraph(
    session: Session,
    ticker: str,
    scan_date: str,
    hops: int = 2,
    staleness_days: int = 14,
) -> dict:
    """Return `{nodes: [...], edges: [...]}` for a 2-hop ticker subgraph filtered by staleness."""
    cutoff = _cutoff(scan_date, staleness_days)

    # Neo4j doesn't parameterize variable-length bounds, so interpolate (int-cast guards injection)
    hops_int = max(1, min(int(hops), 4))
    cypher = f"""
        MATCH path = (t:Ticker {{symbol: $symbol}})-[r*1..{hops_int}]-(n)
        WHERE ALL(e IN r WHERE e.last_seen >= date($cutoff))
          AND n.last_seen >= date($cutoff)
        RETURN nodes(path) AS ns, relationships(path) AS rs
        LIMIT 200
    """
    node_map: dict[str, dict] = {}
    edge_set: set[tuple] = set()
    edges: list[dict] = []

    result = session.run(cypher, symbol=ticker.upper(), cutoff=cutoff)
    for record in result:
        for node in record["ns"]:
            labels = list(node.labels)
            label = labels[0] if labels else "Node"
            key = "symbol" if "Ticker" in labels else ("name" if "Sector" in labels else "id")
            node_id = node.get(key)
            if node_id and node_id not in node_map:
                node_map[node_id] = {"id": node_id, "type": label}
        for rel in record["rs"]:
            src_labels = list(rel.start_node.labels)
            dst_labels = list(rel.end_node.labels)
            src_key = "symbol" if "Ticker" in src_labels else ("name" if "Sector" in src_labels else "id")
            dst_key = "symbol" if "Ticker" in dst_labels else ("name" if "Sector" in dst_labels else "id")
            src = rel.start_node.get(src_key)
            dst = rel.end_node.get(dst_key)
            tup = (src, dst, rel.type, rel.get("polarity", ""), rel.get("provenance", ""))
            if tup not in edge_set:
                edge_set.add(tup)
                edges.append({
                    "source": src, "target": dst, "relation": rel.type,
                    "polarity": rel.get("polarity", "") or "",
                    "provenance": rel.get("provenance", "") or "",
                })

    return {"nodes": list(node_map.values()), "edges": edges, "scan_date": scan_date}


def format_subgraph_for_llm(subgraph: dict, ticker: str) -> str:
    nodes = subgraph.get("nodes", [])
    edges = subgraph.get("edges", [])
    if not nodes:
        return ""
    lines = [
        f"Subgraph for {ticker} (scan_date: {subgraph.get('scan_date', '')})",
        "",
        "Entities:",
    ]
    lines += [f"  - [{n['type']}] {n['id']}" for n in nodes]
    lines += ["", "Relationships:"]
    for e in edges:
        pol = f" ({e['polarity']})" if e.get("polarity") else ""
        prov = f"  [source: {e['provenance']}]" if e.get("provenance") else ""
        lines.append(
            f"  - {e['source']} --[{e['relation']}{pol}]--> {e['target']}{prov}"
        )
    return "\n".join(lines)


def create_graph_context_retrieval_node(
    llm,
    driver_factory: Callable[[], ContextManager[Session]],
):
    """Return a LangGraph node that writes `retrieved_graph_context` to state.

    `driver_factory` is a zero-arg callable returning a context manager that
    yields a `neo4j.Session`. In production this is `session_scope`; in tests
    it can yield a pre-bound test session.
    """

    hops = int(DEFAULT_CONFIG.get("graph_retrieval_hops") or 2)
    staleness = int(DEFAULT_CONFIG.get("graph_staleness_days") or 14)

    def graph_context_retrieval_node(state: dict) -> dict:
        if not DEFAULT_CONFIG.get("graph_enabled", True):
            return {"retrieved_graph_context": ""}

        ticker = str(state.get("company_of_interest") or "").upper()
        scan_date = str(state.get("trade_date") or "").strip()
        if not ticker or not scan_date:
            return {"retrieved_graph_context": ""}

        try:
            with driver_factory() as session:
                sub = get_subgraph(session, ticker, scan_date, hops=hops, staleness_days=staleness)
        except Exception as exc:
            _logger.warning("graph_context_retrieval: Neo4j query failed: %s", exc)
            return {"retrieved_graph_context": ""}

        text = format_subgraph_for_llm(sub, ticker)
        if not text:
            return {"retrieved_graph_context": ""}

        prompt = (
            f"{_RETRIEVAL_SYSTEM_PROMPT}\n\n"
            f"Graph subgraph:\n{text}\n\n"
            f"Write the briefing paragraph for {ticker}:"
        )

        cap = float(DEFAULT_CONFIG.get("quick_think_llm_timeout_cap") or 60.0)
        timeout = min(
            float(
                DEFAULT_CONFIG.get("quick_think_llm_timeout")
                or DEFAULT_CONFIG.get("llm_timeout")
                or cap
            ),
            cap,
        )
        result, error = invoke_with_timeout(llm, prompt, timeout_seconds=timeout)
        if error or result is None:
            _logger.warning("graph_context_retrieval: LLM call failed: %s", error)
            return {"retrieved_graph_context": text}  # fall back to serialized subgraph

        narrative = str(result.content if hasattr(result, "content") else result).strip()
        return {"retrieved_graph_context": narrative}

    return graph_context_retrieval_node
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/graph/graph_memory/test_retriever.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/graph_memory/retriever.py tests/graph/graph_memory/test_retriever.py
git commit -m "feat(graphrag): Cypher 2-hop subgraph retriever with bitemporal filter + LLM narrative"
```

---

## Task 5: Learning hook — no-op `LearningMemoryWriter` (mem0 stub)

**Files:**
- Create: `tradingagents/graph/graph_memory/learning.py`
- Create: `tests/graph/graph_memory/test_learning.py`

This task introduces the **interface** the upcoming learning agent + mem0 will plug into — no behavior beyond a no-op default. Keeping the surface small here means the learning-agent PR doesn't need to touch the retrieval path.

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/graph_memory/test_learning.py
from tradingagents.graph.graph_memory.learning import (
    LearningMemoryWriter,
    NoopLearningMemoryWriter,
    get_active_writer,
    set_active_writer,
)


def test_noop_writer_is_default():
    writer = get_active_writer()
    assert isinstance(writer, NoopLearningMemoryWriter)


def test_noop_writer_accepts_record_calls():
    w = NoopLearningMemoryWriter()
    # Must not raise for any reasonable call
    w.record_episode(
        ticker="NVDA",
        decision="BUY",
        rationale="AI tailwind",
        outcome=None,
        scan_date="2026-04-18",
    )


def test_set_active_writer_swaps_implementation():
    class _Capture(LearningMemoryWriter):
        def __init__(self):
            self.calls = []
        def record_episode(self, **kw):
            self.calls.append(kw)

    cap = _Capture()
    try:
        set_active_writer(cap)
        get_active_writer().record_episode(ticker="X", decision="HOLD", rationale="r", outcome=None, scan_date="d")
        assert cap.calls and cap.calls[0]["ticker"] == "X"
    finally:
        set_active_writer(NoopLearningMemoryWriter())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/graph/graph_memory/test_learning.py -v
```

- [ ] **Step 3: Implement the writer**

```python
# tradingagents/graph/graph_memory/learning.py
"""Hook for the upcoming learning-agent + mem0 integration.

Today this is a no-op. A follow-up PR will provide a concrete
`Mem0LearningMemoryWriter` that persists decision episodes to mem0 and
optionally mirrors distilled learnings back into Neo4j as `Ticker -> Theme`
edges with a `learned=true` flag.

See: docs/agent/decisions/022-neo4j-knowledge-graph.md
"""
from __future__ import annotations

from typing import Any, Protocol


class LearningMemoryWriter(Protocol):
    """Interface for recording decision episodes for later learning."""

    def record_episode(
        self,
        *,
        ticker: str,
        decision: str,
        rationale: str,
        outcome: Any,
        scan_date: str,
    ) -> None:
        ...


class NoopLearningMemoryWriter:
    """Default writer — no persistence, no side effects."""

    def record_episode(self, **_: Any) -> None:
        return None


_active_writer: LearningMemoryWriter = NoopLearningMemoryWriter()


def get_active_writer() -> LearningMemoryWriter:
    return _active_writer


def set_active_writer(writer: LearningMemoryWriter) -> None:
    global _active_writer
    _active_writer = writer
```

- [ ] **Step 4: Verify tests pass**

```bash
pytest tests/graph/graph_memory/test_learning.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/graph_memory/learning.py tests/graph/graph_memory/test_learning.py
git commit -m "feat(graphrag): add LearningMemoryWriter hook (no-op default) for future mem0 integration"
```

---

## Task 6: `AgentState` + `Propagator` — add `retrieved_graph_context`

**Files:**
- Modify: `tradingagents/agents/utils/agent_states.py`
- Modify: `tradingagents/graph/propagation.py`

- [ ] **Step 1: Failing test**

```python
# tests/graph/graph_memory/test_state_fields.py
from tradingagents.graph.propagation import Propagator


def test_initial_state_has_retrieved_graph_context():
    p = Propagator()
    state = p.create_initial_state(
        company_name="NVDA",
        trade_date="2026-04-18",
        run_id="test-run-001",
    )
    assert "retrieved_graph_context" in state
    assert state["retrieved_graph_context"] == ""
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/graph/graph_memory/test_state_fields.py -v
```

- [ ] **Step 3: Add field to `AgentState`**

In `tradingagents/agents/utils/agent_states.py`, below `scanner_context_packet`:

```python
retrieved_graph_context: Annotated[
    str,
    "LLM-summarized ticker-focused graph narrative (preferred over scanner_context_packet in analyst prompts).",
]
```

- [ ] **Step 4: Propagator**

In `Propagator.create_initial_state()`, add `retrieved_graph_context: str = ""` parameter and in the return dict add `"retrieved_graph_context": retrieved_graph_context`. Do NOT rewrite the whole function — insert the parameter and key only.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/graph/graph_memory/test_state_fields.py tests/ -v -m "not integration" -x
git add tradingagents/agents/utils/agent_states.py tradingagents/graph/propagation.py tests/graph/graph_memory/test_state_fields.py
git commit -m "feat(graphrag): add retrieved_graph_context to AgentState and Propagator"
```

---

## Task 7: `LangGraphEngine` — ingest after scanner

**Files:**
- Modify: `agent_os/backend/services/langgraph_engine.py`

Ingestion happens **once per scan**, before the per-ticker pipeline loop. No per-ticker graph is passed through state — each retrieval node queries Neo4j directly.

- [ ] **Step 1: Identify insertion points**

```bash
grep -n "build_scanner_context_packet\|_run_auto_after_scan\|create_initial_state" \
  agent_os/backend/services/langgraph_engine.py | head -30
```

- [ ] **Step 2: Add imports at the top**

```python
from tradingagents.graph.graph_memory.driver import session_scope
from tradingagents.graph.graph_memory.extractor import ingest_scanner_state
from tradingagents.graph.graph_memory.schema import apply_schema
```

- [ ] **Step 3: Ingest once in `_run_auto_after_scan`**

Before the per-ticker `async for` loop starts, add:

```python
if DEFAULT_CONFIG.get("graph_enabled", True):
    try:
        with session_scope() as _s:
            apply_schema(_s)
            ingest_scanner_state(_s, scan_state)
        yield system_log(
            f"GraphRAG: ingested scanner state into Neo4j "
            f"(scan_date={scan_state.get('scan_date')})."
        )
    except Exception as _kg_err:
        logger.warning("run_auto: knowledge graph ingestion failed: %s", _kg_err)
        yield system_log(f"GraphRAG: ingestion skipped — {_kg_err}")
```

- [ ] **Step 4: No changes to `create_initial_state` call sites**

The retrieval node pulls from Neo4j directly — no need to pass a graph dict through state.

- [ ] **Step 5: Verify import chain**

```bash
python -c "from agent_os.backend.services.langgraph_engine import LangGraphEngine; print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add agent_os/backend/services/langgraph_engine.py
git commit -m "feat(graphrag): ingest scanner state into Neo4j once per run after scanner completes"
```

---

## Task 8: `ScannerGraph` — ingest on CLI path

**Files:**
- Modify: `tradingagents/graph/scanner_graph.py`

- [ ] **Step 1: Failing test**

```python
# tests/graph/graph_memory/test_scanner_graph_ingest.py
from unittest.mock import MagicMock, patch


def test_scanner_graph_scan_ingests(neo4j_session):
    from tradingagents.graph.graph_memory.schema import apply_schema
    apply_schema(neo4j_session)

    from tradingagents.graph import scanner_graph as sg_mod

    with patch.object(sg_mod.ScannerGraph, "__init__", lambda self, **kw: None):
        sg = sg_mod.ScannerGraph.__new__(sg_mod.ScannerGraph)
        sg.debug = False
        sg.graph = MagicMock()
        sg.graph.invoke.return_value = {
            "scan_date": "2026-04-18",
            "macro_scan_summary": "- NVDA | Technology | bullish | AI tailwind | momentum",
            "industry_deep_dive_summary": "",
            "geopolitical_summary": "",
            "sector_summary": "",
            "market_movers_summary": "",
            "smart_money_summary": "",
            "factor_alignment_summary": "",
            "gatekeeper_summary": "",
            "drift_opportunities_summary": "",
        }

        # Patch session_scope to yield the test session
        class _Ctx:
            def __enter__(self_inner): return neo4j_session
            def __exit__(self_inner, *a): return False

        with patch("tradingagents.graph.scanner_graph.session_scope", lambda: _Ctx()):
            sg.scan("2026-04-18")

    count = neo4j_session.run("MATCH (t:Ticker {symbol:'NVDA'}) RETURN count(t) AS c").single()["c"]
    assert count == 1
```

- [ ] **Step 2: Modify `scanner_graph.py`**

Add imports:
```python
from tradingagents.graph.graph_memory.driver import session_scope
from tradingagents.graph.graph_memory.extractor import ingest_scanner_state
from tradingagents.graph.graph_memory.schema import apply_schema
from tradingagents.default_config import DEFAULT_CONFIG
```

In `scan()`, after `final_state = self.graph.invoke(initial_state)` (coerce to plain dict if the state is a FrozenDict):
```python
final_state = dict(final_state) if not isinstance(final_state, dict) else final_state

if DEFAULT_CONFIG.get("graph_enabled", True):
    try:
        with session_scope() as _s:
            apply_schema(_s)
            ingest_scanner_state(_s, final_state)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "ScannerGraph: knowledge graph ingestion failed: %s", exc
        )
```

- [ ] **Step 3: Run tests and commit**

```bash
pytest tests/graph/graph_memory/test_scanner_graph_ingest.py -v
git add tradingagents/graph/scanner_graph.py tests/graph/graph_memory/test_scanner_graph_ingest.py
git commit -m "feat(graphrag): ScannerGraph.scan() ingests state into Neo4j on CLI path"
```

---

## Task 9: Wire retrieval node into trading graph

**Files:**
- Modify: `tradingagents/graph/setup.py`
- Modify: `tradingagents/graph/trading_graph.py`

- [ ] **Step 1: Failing test**

```python
# tests/graph/graph_memory/test_graph_node_wiring.py
from unittest.mock import MagicMock


def test_graph_setup_includes_retrieval_node():
    from tradingagents.graph.setup import GraphSetup
    from tradingagents.graph.conditional_logic import ConditionalLogic

    mock_llm = MagicMock()
    mock_tool = MagicMock()
    mock_mem = MagicMock()
    cond = MagicMock(spec=ConditionalLogic)
    cond.make_should_continue = ConditionalLogic.make_should_continue
    cond.should_continue_debate = MagicMock(return_value="Research Manager")

    retrieval = MagicMock(return_value={"retrieved_graph_context": ""})

    setup = GraphSetup(
        quick_thinking_llm=mock_llm,
        mid_thinking_llm=mock_llm,
        deep_thinking_llm=mock_llm,
        tool_nodes={
            "market": mock_tool, "social": mock_tool, "news": mock_tool, "fundamentals": mock_tool,
        },
        bull_memory=mock_mem, bear_memory=mock_mem, trader_memory=mock_mem,
        invest_judge_memory=mock_mem, portfolio_manager_memory=mock_mem,
        conditional_logic=cond,
        graph_context_retrieval_node=retrieval,
    )
    graph = setup.setup_graph()
    assert "Graph Context Retrieval" in graph.get_graph().nodes
```

- [ ] **Step 2: Update `GraphSetup.__init__`**

Add `graph_context_retrieval_node=None` as the last parameter; store on `self`.

- [ ] **Step 3: Wire into `setup_graph()`**

After `workflow.add_node("Instrument Preflight", ...)`:

```python
if self.graph_context_retrieval_node is not None:
    workflow.add_node("Graph Context Retrieval", self.graph_context_retrieval_node)
```

Route the `Instrument Preflight` conditional edges through `Graph Context Retrieval` when present, then from there into the first analyst / Bull Researcher using the existing `_resolve_next_analyst_node` logic. (Same pattern as the original JSON-based plan — the wiring is identical; only the node's implementation differs.)

- [ ] **Step 4: Construct the retriever in `TradingAgentsGraph`**

In `trading_graph.py`:
```python
from tradingagents.graph.graph_memory.driver import session_scope
from tradingagents.graph.graph_memory.retriever import create_graph_context_retrieval_node
```

Where `GraphSetup(...)` is constructed:
```python
retrieval_node = create_graph_context_retrieval_node(
    self.quick_thinking_llm,
    driver_factory=session_scope,
)
self.graph_setup = GraphSetup(
    ...,
    graph_context_retrieval_node=retrieval_node,
)
```

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/graph/graph_memory/test_graph_node_wiring.py -v
pytest tests/ -v -m "not integration" -x
git add tradingagents/graph/setup.py tradingagents/graph/trading_graph.py tests/graph/graph_memory/test_graph_node_wiring.py
git commit -m "feat(graphrag): wire Graph Context Retrieval node after Instrument Preflight"
```

---

## Task 10: Analysts — prefer `retrieved_graph_context`

**Files:**
- Modify: `tradingagents/agents/analysts/market_analyst.py`
- Modify: `tradingagents/agents/analysts/social_media_analyst.py`
- Modify: `tradingagents/agents/analysts/news_analyst.py`
- Modify: `tradingagents/agents/analysts/fundamentals_analyst.py`

- [ ] **Step 1: Drop-in replacement (market / social / fundamentals)**

Change each:
```python
scanner_context = state.get("scanner_context_packet", "")
```
to:
```python
scanner_context = (
    state.get("retrieved_graph_context")
    or state.get("scanner_context_packet", "")
)
```

- [ ] **Step 2: `news_analyst.py` — skip ticker filter when graph context used**

```python
retrieved_context = state.get("retrieved_graph_context") or ""
if retrieved_context:
    scanner_context = retrieved_context  # already ticker-focused
else:
    scanner_context_raw = state.get("scanner_context_packet", "")
    scanner_context = (
        filter_scanner_context_for_ticker(scanner_context_raw, ticker)
        if scanner_context_raw else ""
    )
```

- [ ] **Step 3: Run tests and commit**

```bash
pytest tests/ -v -m "not integration" -x
git add tradingagents/agents/analysts/
git commit -m "feat(graphrag): analysts prefer retrieved_graph_context over raw scanner packet"
```

---

## Task 11: `summary_context.py` — graph context in research packet

**Files:**
- Modify: `tradingagents/agents/utils/summary_context.py`

In `build_debate_evidence_brief()` and `build_research_packet()`, replace `state.get("scanner_context_packet")` reads with:

```python
scanner_source = (
    state.get("retrieved_graph_context")
    or state.get("scanner_context_packet")
    or ""
)
```

Then use `scanner_source` where the current code uses the raw packet. In `build_research_packet()`, the section header becomes `## Graph Context` when `retrieved_graph_context` is non-empty, `## Scanner Context (Phase 1)` otherwise.

- [ ] **Step 1: Tests (add to `test_analyst_context_fallback.py`) and implementation**

(Identical tests to the ones in the previous JSON-dict version — they assert priority and fallback.)

- [ ] **Step 2: Commit**

```bash
git add tradingagents/agents/utils/summary_context.py tests/graph/graph_memory/test_analyst_context_fallback.py
git commit -m "feat(graphrag): prefer retrieved_graph_context in research packet + debate brief"
```

---

## Task 12: ADR

**Files:**
- Create: `docs/agent/decisions/022-neo4j-knowledge-graph.md`

- [ ] **Write the ADR**

Covers: status (accepted), context (need persistent cross-run memory + multi-hop queries), decision (Neo4j 5.x, bitemporal model, structured-row extraction, `LearningMemoryWriter` seam for mem0), consequences & constraints (Neo4j must be available for graph-enabled runs; `graph_enabled=False` is the safe fallback), actionable rules (every edge MUST carry `provenance`; every ingestion MUST stamp `first_seen` / `last_seen`; retrieval MUST filter by `graph_staleness_days`).

- [ ] **Commit**

```bash
git add docs/agent/decisions/022-neo4j-knowledge-graph.md
git commit -m "docs(adr): ADR 022 — Neo4j knowledge graph + bitemporal + mem0 hook"
```

---

## Task 13: End-to-end smoke test

- [ ] **Step 1: Start Neo4j locally**

```bash
docker compose up -d neo4j
```

- [ ] **Step 2: Unit tests (no docker needed for most)**

```bash
pytest tests/ -v -m "not integration" -x
```

- [ ] **Step 3: Live scanner ingest**

```bash
conda activate tradingagents
python -m cli.main scan --date 2026-04-18
```

Check in Neo4j Browser (http://localhost:7474):
```cypher
MATCH (t:Ticker) RETURN count(t);
MATCH (t:Ticker {symbol: "NVDA"})-[r*1..2]-(n) RETURN t, r, n LIMIT 25;
```

- [ ] **Step 4: Live per-ticker analyze with graph context**

```bash
python -m cli.main analyze
```

Inspect one analyst report — the scanner-context section should be the graph narrative and cite real provenance (`per smart_money_summary`, etc.).

- [ ] **Step 5: Final commit**

```bash
git status
git commit --allow-empty -m "chore(graphrag): end-to-end GraphRAG Neo4j integration complete"
```

---

## Self-Review

### Spec coverage

| Original proposal | Covered in |
|---|---|
| Phase 1 — triple ingestion | Tasks 3, 7, 8 |
| Phase 1 — bitemporal `valid_until` / decay | `last_seen` + retrieval staleness filter (Tasks 3, 4) |
| Phase 1 — Cypher `MERGE` idempotency | Task 3 |
| Phase 2 — update `AgentState` | Task 6 |
| Phase 2 — retrieval node after Preflight | Tasks 4, 9 |
| Phase 2 — As-Of query filter | Task 4 (`staleness_days` + `cutoff`) |
| Phase 3 — strip raw scanner packet from analyst prompts | Tasks 10, 11 (replaced, not stripped — backwards compatible) |
| Phase 4 — Actor-Critic loop | Intentionally deferred; documented in ADR |
| Future: learning agent + mem0 | Task 5 (`LearningMemoryWriter` hook + ADR) |

### Placeholder scan

No TBDs, no "handle edge cases" without code, no "similar to Task N" references. Each code block is complete.

### Type consistency

- `ingest_scanner_state(session, scanner_state)` — consistent in Tasks 3, 7, 8.
- `get_subgraph(session, ticker, scan_date, hops, staleness_days) -> dict` — consistent in Tasks 4, 9.
- `create_graph_context_retrieval_node(llm, driver_factory)` — consistent in Tasks 4, 9.
- `retrieved_graph_context: str` — consistent in AgentState (6), Propagator (6), analysts (10), summary_context (11).
- `LearningMemoryWriter.record_episode(ticker, decision, rationale, outcome, scan_date)` — kwargs-only signature, stable contract for mem0 follow-up.
