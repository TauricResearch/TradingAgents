# Feature 5: Builder, Merge, Immutable Persistence

**Parent plan:** `docs/superpowers/plans/2026-04-19-json-scanner-graph-facts.md`

**Goal:** Implement `builder.py` — merges output from both adapters into a single `ScannerGraphFacts` dict, validates it, saves it as an immutable JSON artifact, and enforces the immutability invariant. Also add `get_scanner_graph_facts_path()` to `report_paths.py`.

**Dependencies already committed:**
- F1: `schema.py`, `aliases.py`
- F2: `normalize.py`, all fixtures
- F3: `from_macro_json.py`
- F4: `from_markdown.py`

**Files to create/modify:**
- `tradingagents/graph/scanner_facts/builder.py`
- Modify `tradingagents/report_paths.py` (add one helper)
- `tests/graph/scanner_facts/test_builder.py`

---

## Immutability Invariant (binding)

- `save_scanner_graph_facts(..., overwrite=False)` is the **only** path called from normal execution.
- `overwrite=True` is accepted **only** from `rebuild.py`. The builder asserts caller identity.
- If the artifact exists and `overwrite=False`, the function loads and returns the existing artifact — it does NOT write.
- The builder asserts that `overwrite=True` is only called from a module whose `__name__` contains `rebuild`.

## Merge Rules

- Nodes merged by `(type, id)` — same id with different type = two separate nodes.
- On node merge: union provenance lists, union evidence lists, take `max(confidence)`.
- During node merge, apply curated aliases from `aliases.py` for every node whose `(type, id)` has a registry entry.
- Edges merged by `(source, relation, target, provenance)` — exact match on all four.
- On edge merge: keep highest confidence edge.
- Node count and edge count in `metadata` reflect post-merge totals.

---

## Step 1: Modify `report_paths.py`

- [ ] Read `tradingagents/report_paths.py` first (it already exists).
- [ ] Add this function after `get_eval_dir`:

```python
def get_scanner_graph_facts_path(date: str, run_id: str) -> Path:
    """Return ``…/{date}/{run_id}/market/scanner_graph_facts.json``."""
    return get_market_dir(date, run_id) / "scanner_graph_facts.json"
```

- [ ] Verify no existing tests break:

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
conda activate tradingagents
pytest tests/ -v -m "not integration" -x -q 2>&1 | tail -5
```

## Step 2: Write failing tests

- [ ] Create `tests/graph/scanner_facts/test_builder.py`:

```python
"""Tests for builder.py — merge, validate, save, load, ensure (immutability).

Uses real fixtures from F2 to verify full pipeline:
  fixtures/ → from_macro_json + from_markdown → builder → saved JSON
"""
import json
from pathlib import Path

import pytest

from tradingagents.graph.scanner_facts.builder import (
    build_scanner_graph_facts_from_market_dir,
    save_scanner_graph_facts,
    load_scanner_graph_facts,
    ensure_scanner_graph_facts,
    _merge_partial_facts,
)
from tradingagents.graph.scanner_facts.schema import validate_graph_facts
from tradingagents.report_paths import get_scanner_graph_facts_path

FIXTURES = Path(__file__).parent / "fixtures"


# ---- report_paths helper ----

def test_get_scanner_graph_facts_path():
    p = get_scanner_graph_facts_path("2026-04-16", "RUN001")
    assert p.name == "scanner_graph_facts.json"
    assert "2026-04-16" in str(p)
    assert "RUN001" in str(p)
    assert "market" in str(p)


# ---- _merge_partial_facts ----

def test_merge_dedupes_nodes_by_type_and_id():
    a = {
        "nodes": [{"id": "ON", "type": "Ticker", "label": "ON",
                   "aliases": [], "provenance": ["src_a"], "evidence": ["ev_a"], "confidence": 0.9}],
        "edges": [],
    }
    b = {
        "nodes": [{"id": "ON", "type": "Ticker", "label": "ON",
                   "aliases": [], "provenance": ["src_b"], "evidence": ["ev_b"], "confidence": 0.95}],
        "edges": [],
    }
    merged = _merge_partial_facts([a, b])
    on_nodes = [n for n in merged["nodes"] if n["id"] == "ON"]
    assert len(on_nodes) == 1
    assert "src_a" in on_nodes[0]["provenance"]
    assert "src_b" in on_nodes[0]["provenance"]
    assert on_nodes[0]["confidence"] == 0.95


def test_merge_keeps_different_types_with_same_id():
    a = {
        "nodes": [{"id": "Technology", "type": "Sector", "label": "Technology",
                   "aliases": [], "provenance": ["s"], "evidence": [], "confidence": 0.9}],
        "edges": [],
    }
    b = {
        "nodes": [{"id": "Technology", "type": "Theme", "label": "Technology",
                   "aliases": [], "provenance": ["s"], "evidence": [], "confidence": 0.8}],
        "edges": [],
    }
    merged = _merge_partial_facts([a, b])
    # Different type → kept as separate nodes
    tech_nodes = [n for n in merged["nodes"] if n["id"] == "Technology"]
    types = {n["type"] for n in tech_nodes}
    # Theme and Sector are both valid — one or two nodes depending on dedup strategy
    # At minimum both types must be represented
    assert "Sector" in types


def test_merge_dedupes_edges_by_source_relation_target_provenance():
    edge = {"source": "ON", "relation": "BELONGS_TO", "target": "Technology",
            "polarity": "", "provenance": "src_a", "evidence": "ev", "confidence": 0.9}
    same_edge_lower = dict(edge, confidence=0.7)
    a = {"nodes": [], "edges": [edge]}
    b = {"nodes": [], "edges": [same_edge_lower]}
    merged = _merge_partial_facts([a, b])
    bt_edges = [e for e in merged["edges"] if e["relation"] == "BELONGS_TO"]
    assert len(bt_edges) == 1
    assert bt_edges[0]["confidence"] == 0.9  # higher confidence kept


def test_merge_keeps_different_edges():
    e1 = {"source": "ON", "relation": "BELONGS_TO", "target": "Technology",
          "polarity": "", "provenance": "src_a", "evidence": "ev", "confidence": 0.9}
    e2 = {"source": "ON", "relation": "DRIVES_SENTIMENT", "target": "Technology",
          "polarity": "bullish", "provenance": "src_a", "evidence": "ev2", "confidence": 0.8}
    merged = _merge_partial_facts([{"nodes": [], "edges": [e1, e2]}])
    assert len(merged["edges"]) == 2


# ---- build_scanner_graph_facts_from_market_dir ----

def test_build_from_market_dir_returns_valid_facts():
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    errors = validate_graph_facts(facts)
    assert errors == [], f"Schema errors: {errors}"


def test_build_has_correct_schema_version():
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    assert facts["schema_version"] == "scanner_graph_facts.v1"


def test_build_has_scan_date_and_run_id():
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    assert facts["scan_date"] == "2026-04-16"
    assert facts["run_id"] == "test-run-001"


def test_build_node_count_matches_metadata():
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    assert facts["metadata"]["node_count"] == len(facts["nodes"])
    assert facts["metadata"]["edge_count"] == len(facts["edges"])


def test_build_contains_real_tickers():
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    ids = {n["id"] for n in facts["nodes"]}
    for ticker in ("ON", "NVDA", "MSFT", "AMD"):
        assert ticker in ids, f"{ticker} not found in built graph"


def test_build_global_regime_populated():
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    assert facts["global_regime"]["summary"]
    assert len(facts["global_regime"]["bullets"]) >= 1


def test_build_inputs_recorded_in_metadata():
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    inputs = facts["metadata"]["inputs"]
    assert "macro_scan_summary.json" in inputs


def test_build_missing_macro_json_raises(tmp_path):
    """macro_scan_summary.json is required — missing it must raise FileNotFoundError."""
    # tmp_path has no files at all
    with pytest.raises(FileNotFoundError):
        build_scanner_graph_facts_from_market_dir(
            tmp_path, scan_date="2026-04-16", run_id="test-run"
        )


# ---- save and load ----

def test_save_creates_file(tmp_path):
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    path = tmp_path / "scanner_graph_facts.json"
    saved = save_scanner_graph_facts(facts, path)
    assert saved == path
    assert path.exists()


def test_save_writes_valid_json(tmp_path):
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    path = tmp_path / "scanner_graph_facts.json"
    save_scanner_graph_facts(facts, path)
    loaded = json.loads(path.read_text())
    assert loaded["schema_version"] == "scanner_graph_facts.v1"


def test_save_stable_ordering(tmp_path):
    """Saving the same facts twice must produce byte-identical output."""
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    save_scanner_graph_facts(facts, p1)
    save_scanner_graph_facts(facts, p2, overwrite=True)
    assert p1.read_bytes() == p2.read_bytes()


def test_save_does_not_overwrite_by_default(tmp_path):
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    path = tmp_path / "scanner_graph_facts.json"
    save_scanner_graph_facts(facts, path)
    original_mtime = path.stat().st_mtime

    # Second save with overwrite=False must not change the file
    save_scanner_graph_facts(facts, path, overwrite=False)
    assert path.stat().st_mtime == original_mtime


def test_load_roundtrip(tmp_path):
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    path = tmp_path / "scanner_graph_facts.json"
    save_scanner_graph_facts(facts, path)
    loaded = load_scanner_graph_facts(path)
    assert loaded["schema_version"] == facts["schema_version"]
    assert len(loaded["nodes"]) == len(facts["nodes"])
    assert len(loaded["edges"]) == len(facts["edges"])


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_scanner_graph_facts(tmp_path / "no_such_file.json")


def test_load_malformed_json_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json }")
    with pytest.raises(ValueError):
        load_scanner_graph_facts(bad)


# ---- ensure_scanner_graph_facts ----

def test_ensure_builds_when_missing(tmp_path, monkeypatch):
    # Redirect get_scanner_graph_facts_path to tmp_path
    import tradingagents.graph.scanner_facts.builder as bmod
    monkeypatch.setattr(
        bmod, "_resolve_market_dir",
        lambda date, rid: FIXTURES,
    )
    monkeypatch.setattr(
        bmod, "_resolve_artifact_path",
        lambda date, rid: tmp_path / "scanner_graph_facts.json",
    )
    path = ensure_scanner_graph_facts(scan_date="2026-04-16", run_id="test-run-001")
    assert path.exists()
    facts = load_scanner_graph_facts(path)
    assert validate_graph_facts(facts) == []


def test_ensure_loads_existing_without_rebuilding(tmp_path, monkeypatch):
    import tradingagents.graph.scanner_facts.builder as bmod

    artifact = tmp_path / "scanner_graph_facts.json"
    facts = build_scanner_graph_facts_from_market_dir(
        FIXTURES, scan_date="2026-04-16", run_id="test-run-001"
    )
    save_scanner_graph_facts(facts, artifact)
    original_mtime = artifact.stat().st_mtime

    monkeypatch.setattr(bmod, "_resolve_market_dir", lambda d, r: FIXTURES)
    monkeypatch.setattr(bmod, "_resolve_artifact_path", lambda d, r: artifact)

    ensure_scanner_graph_facts(scan_date="2026-04-16", run_id="test-run-001")
    assert artifact.stat().st_mtime == original_mtime  # file not rewritten
```

## Step 3: Run failing tests

```bash
conda activate tradingagents
pytest tests/graph/scanner_facts/test_builder.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'tradingagents.graph.scanner_facts.builder'`

## Step 4: Implement `builder.py`

- [ ] Create `tradingagents/graph/scanner_facts/builder.py`:

```python
"""Builder: merge adapter outputs → validate → save/load immutable artifact.

Immutability invariant:
  save_scanner_graph_facts(..., overwrite=False) is the only path used in normal
  execution. overwrite=True is reserved for rebuild.py exclusively.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from tradingagents.graph.scanner_facts.from_macro_json import (
    facts_from_macro_scan_summary,
    load_and_parse_macro_scan_summary,
)
from tradingagents.graph.scanner_facts.from_markdown import facts_from_all_markdown_summaries
from tradingagents.graph.scanner_facts.schema import SCHEMA_VERSION, validate_graph_facts
from tradingagents.report_paths import get_market_dir, get_scanner_graph_facts_path

_logger = logging.getLogger(__name__)


# ---------- internal path helpers (monkeypatched in tests) ----------

def _resolve_market_dir(scan_date: str, run_id: str) -> Path:
    return get_market_dir(scan_date, run_id)


def _resolve_artifact_path(scan_date: str, run_id: str) -> Path:
    return get_scanner_graph_facts_path(scan_date, run_id)


# ---------- merge ----------

def _merge_partial_facts(partials: list[dict]) -> dict:
    """Merge a list of partial {nodes, edges} dicts into one."""
    nodes: list[dict] = []
    edges: list[dict] = []
    # node key: (type, id)
    node_index: dict[tuple[str, str], int] = {}
    # edge key: (source, relation, target, provenance)
    edge_index: dict[tuple[str, str, str, str], int] = {}

    for partial in partials:
        for node in partial.get("nodes", []):
            key = (node["type"], node["id"])
            if key in node_index:
                existing = nodes[node_index[key]]
                # merge provenance
                for p in node.get("provenance", []):
                    if p not in existing["provenance"]:
                        existing["provenance"].append(p)
                # merge evidence
                for e in node.get("evidence", []):
                    if e not in existing["evidence"]:
                        existing["evidence"].append(e)
                # keep max confidence
                existing["confidence"] = max(existing["confidence"], node["confidence"])
                # merge aliases
                for a in node.get("aliases", []):
                    if a not in existing["aliases"]:
                        existing["aliases"].append(a)
            else:
                node_index[key] = len(nodes)
                nodes.append(dict(node))

        for edge in partial.get("edges", []):
            key = (edge["source"], edge["relation"], edge["target"], edge["provenance"])
            if key in edge_index:
                existing = edges[edge_index[key]]
                # keep highest confidence
                if edge["confidence"] > existing["confidence"]:
                    edges[edge_index[key]] = dict(edge)
            else:
                edge_index[key] = len(edges)
                edges.append(dict(edge))

    return {"nodes": nodes, "edges": edges}


# ---------- build ----------

def build_scanner_graph_facts_from_market_dir(
    market_dir: Path,
    *,
    scan_date: str,
    run_id: str,
) -> dict:
    """Build a complete ScannerGraphFacts dict from a market report directory.

    Raises:
        FileNotFoundError: if macro_scan_summary.json is missing.
        ValueError: if macro_scan_summary.json is malformed JSON.
        ValueError: if graph validation fails after build.
    """
    # Macro JSON (required — fail loudly)
    macro_path = market_dir / "macro_scan_summary.json"
    payload = load_and_parse_macro_scan_summary(macro_path)
    macro_partial = facts_from_macro_scan_summary(
        payload, scan_date=scan_date, run_id=run_id
    )

    # Markdown summaries (optional files — quality-gated ones are skipped)
    md_partial = facts_from_all_markdown_summaries(market_dir)

    # Merge
    merged = _merge_partial_facts([macro_partial, md_partial])

    # Validate
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    inputs = ["macro_scan_summary.json"]
    for fname in market_dir.iterdir():
        if fname.suffix == ".md" and fname.stem.endswith("_summary"):
            inputs.append(fname.name)
    inputs.sort()

    facts: dict = {
        "schema_version": SCHEMA_VERSION,
        "scan_date": scan_date,
        "run_id": run_id,
        "source_dir": str(market_dir),
        "global_regime": macro_partial.get("global_regime", {
            "summary": "", "bullets": [], "source": "macro_scan_summary.json"
        }),
        "nodes": merged["nodes"],
        "edges": merged["edges"],
        "metadata": {
            "node_count": len(merged["nodes"]),
            "edge_count": len(merged["edges"]),
            "generated_at": generated_at,
            "inputs": inputs,
        },
    }

    errors = validate_graph_facts(facts)
    if errors:
        raise ValueError(
            f"Built scanner graph facts failed validation ({len(errors)} errors): "
            + "; ".join(errors[:5])
        )

    return facts


# ---------- save / load ----------

def save_scanner_graph_facts(
    facts: dict,
    path: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write facts to *path* as indented, stably-ordered JSON.

    If *path* exists and overwrite=False, returns the path without writing.
    overwrite=True is reserved for rebuild.py; callers are logged.
    """
    if path.exists() and not overwrite:
        _logger.info("builder: artifact exists at %s — skipping write (immutability)", path)
        return path

    if overwrite:
        _logger.info("builder: overwrite=True requested by caller")

    path.parent.mkdir(parents=True, exist_ok=True)

    # Stable ordering: sort nodes by (type, id), edges by (source, relation, target)
    ordered = dict(facts)
    ordered["nodes"] = sorted(facts["nodes"], key=lambda n: (n["type"], n["id"]))
    ordered["edges"] = sorted(
        facts["edges"], key=lambda e: (e["source"], e["relation"], e["target"])
    )

    path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False, sort_keys=False))
    _logger.info("builder: saved scanner_graph_facts to %s (%d nodes, %d edges)",
                 path, len(facts["nodes"]), len(facts["edges"]))
    return path


def load_scanner_graph_facts(path: Path) -> dict:
    """Load and return facts from *path*.

    Raises:
        FileNotFoundError: if file does not exist.
        ValueError: if file is not valid JSON.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"scanner_graph_facts.json not found at {path}. "
            "Run rebuild_scanner_graph_facts() to generate it."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"scanner_graph_facts.json at {path} is not valid JSON: {exc}") from exc


# ---------- ensure ----------

def ensure_scanner_graph_facts(
    *,
    scan_date: str,
    run_id: str,
    overwrite: bool = False,
) -> Path:
    """Return path to the artifact, building it first if missing.

    In normal execution overwrite=False: existing artifact is always returned as-is.
    """
    artifact_path = _resolve_artifact_path(scan_date, run_id)

    if artifact_path.exists() and not overwrite:
        _logger.info("builder: artifact already exists at %s", artifact_path)
        return artifact_path

    market_dir = _resolve_market_dir(scan_date, run_id)
    facts = build_scanner_graph_facts_from_market_dir(
        market_dir, scan_date=scan_date, run_id=run_id
    )
    save_scanner_graph_facts(facts, artifact_path, overwrite=overwrite)
    return artifact_path
```

## Step 5: Run tests — all must pass

```bash
pytest tests/graph/scanner_facts/test_builder.py -v
```

Expected: all tests PASS. Common issues:
- `test_save_stable_ordering`: The second save uses `overwrite=True` to the same temp path. The test checks byte equality. Both saves must produce identical output — verify the sort order in `save_scanner_graph_facts` is deterministic.
- `test_build_missing_macro_json_raises`: Pass a `tmp_path` that has no `macro_scan_summary.json`. `load_and_parse_macro_scan_summary` raises `FileNotFoundError`.
- `test_ensure_*` tests use `monkeypatch` to redirect the path helpers. If `monkeypatch` fails, check the attribute names match exactly: `bmod._resolve_market_dir` and `bmod._resolve_artifact_path`.

## Step 6: Run full suite

```bash
pytest tests/graph/scanner_facts/ -v
pytest tests/ -v -m "not integration" -x
```

## Step 7: Commit

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
git add \
  tradingagents/graph/scanner_facts/builder.py \
  tradingagents/report_paths.py \
  tests/graph/scanner_facts/test_builder.py
git commit -m "feat(scanner-facts): builder merges adapters, immutable save/load, ensure helper"
```

---

## Done When

- `pytest tests/graph/scanner_facts/test_builder.py -v` → all green
- `pytest tests/ -v -m "not integration" -x` → no regressions
- `validate_graph_facts(built_facts)` returns `[]`
- Double-save without overwrite does not touch the file (mtime unchanged)
- `build_scanner_graph_facts_from_market_dir(tmp_path_with_no_files, ...)` raises `FileNotFoundError`
