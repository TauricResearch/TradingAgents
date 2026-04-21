# Feature 12: Fixtures and Smoke Checks

**Parent plan:** `docs/superpowers/plans/2026-04-19-json-scanner-graph-facts.md`

**Goal:** Close the feature with fixture and smoke coverage that proves both the standalone scanner-facts package and the normal backend wiring work end to end.

**Current gap in PR #219:** The scanner-facts package has focused fixture coverage, but backend smoke coverage for scanner completion, per-ticker rendering, and prompt injection is still pending.

---

## Required Coverage

- Scanner-facts package unit/integration fixtures:
  - `smart_money_summary.md`
  - `industry_deep_dive_summary.md`
  - `sector_summary.md`
  - `geopolitical_summary.md`
  - `market_movers_summary.md`
  - `gatekeeper_summary.md`
  - `macro_scan_summary.json`
- Backend smoke:
  - Scanner completion creates or loads `scanner_graph_facts.json`.
  - Per-ticker pipeline renders non-empty `scanner_graph_context_text`.
  - Analyst/trader prompt paths include `## Ticker Graph Context`.
  - Missing artifact fails loudly with rebuild guidance.
  - Operator-explicit resume without graph facts emits the warning banner.

---

## Step 1: Add smoke fixture helper

Create a small helper in tests that copies the scanner-facts fixtures into a temp report folder shaped like:

```text
reports/daily/{scan_date}/{run_id}/market/
```

The helper should return `(reports_root, scan_date, run_id)`.

---

## Step 2: Add backend smoke tests

Add smoke tests that avoid live LLM/API calls by monkeypatching the graph execution boundary:

- `test_backend_scanner_completion_builds_graph_facts`
- `test_backend_ticker_pipeline_passes_scanner_graph_context_text`
- `test_backend_missing_graph_facts_fails_with_rebuild_instruction`
- `test_resume_without_graph_facts_logs_warning_banner`

Prefer monkeypatching `ensure_scanner_graph_facts`, `load_scanner_graph_facts`, and `render_ticker_graph_context` to keep these tests fast and deterministic.

---

## Step 3: Add command-level smoke check

Add or document a local command sequence:

```bash
pytest tests/graph/scanner_facts -q
pytest tests/graph/test_propagation_scanner_context.py -q
pytest tests/graph/scanner_facts/test_backend_wiring.py -q
pytest tests/unit/agents/test_analyst_agents.py tests/unit/test_summary_nodes.py tests/unit/test_ground_truth_propagation.py -q
```

Then run:

```bash
pytest tests/ -q -m "not integration" -x
```

---

## Step 4: Graphify

After any code changes, run:

```bash
PYTHONPATH=. /opt/miniconda3/bin/python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"
```

---

## Done When

- Standalone scanner-facts tests are green.
- Backend smoke tests prove generation, load, render, injection, and fail-loud behavior.
- Broad non-integration suite either passes or has a documented unrelated blocker with file/test name.
- `graphify-out/GRAPH_REPORT.md` is regenerated after code changes.
