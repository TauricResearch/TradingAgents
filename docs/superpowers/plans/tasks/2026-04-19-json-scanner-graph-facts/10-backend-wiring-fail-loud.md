# Feature 10: Backend Wiring (Fail-Loud)

**Parent plan:** `docs/superpowers/plans/2026-04-19-json-scanner-graph-facts.md`

**Goal:** Wire the already-built JSON scanner graph facts package into normal execution. Scanner completion must build or load `scanner_graph_facts.json`; each ticker pipeline must load, retrieve, render, and pass `scanner_graph_context_text` into `Propagator.create_initial_state()`.

**Current gap in PR #219:** F1-F9 exist, but `agent_os/backend/services/langgraph_engine.py`, `tradingagents/graph/scanner_graph.py`, and `tradingagents/graph/trading_graph.py` still run on `scanner_context_packet`. Normal backend execution does not yet generate the artifact or inject rendered graph context.

**Files to modify:**
- `agent_os/backend/services/langgraph_engine.py`
- `tradingagents/graph/scanner_graph.py`
- `tradingagents/graph/trading_graph.py`

**Files to create or extend:**
- `tests/graph/scanner_facts/test_backend_wiring.py` or focused tests near existing backend service tests

---

## Rules

- Normal scanner execution calls `ensure_scanner_graph_facts(scan_date=date, run_id=root_run_id)` after scanner summaries are written.
- If the artifact build fails, the scanner/backend run fails loudly with an actionable error. Do not continue with `scanner_context_packet`.
- Ticker execution loads the artifact with `load_scanner_graph_facts(get_scanner_graph_facts_path(date, root_run_id))`.
- For each ticker, call `render_ticker_graph_context(facts, ticker)` and pass the result to `create_initial_state(..., scanner_graph_context_text=rendered)`.
- If the artifact is missing during ticker execution, raise with a message that includes the rebuild CLI command shape.
- Existing operator-explicit resume paths may keep using `scanner_context_packet`, but must log one warning banner:
  ```text
  WARNING: Resuming without scanner_graph_facts.json - scanner_context_packet fallback active.
  ```
- Do not pass the raw graph dict through `AgentState`.

---

## Step 1: Write failing backend tests

Add focused tests that monkeypatch the graph facts functions rather than running a full live scan:

- Healthy backend path calls `ensure_scanner_graph_facts()` after scanner completion.
- Healthy ticker path calls `load_scanner_graph_facts()` and `render_ticker_graph_context()`.
- `create_initial_state()` receives non-empty `scanner_graph_context_text`.
- Missing artifact in ticker phase raises `FileNotFoundError` or a domain-specific `ValueError` containing `python -m tradingagents.graph.scanner_facts.rebuild`.
- Build failure after scanner completion propagates and marks the run failed.

Run:
```bash
pytest tests/graph/scanner_facts/test_backend_wiring.py -v
```

Expected: fail before implementation because backend paths do not call graph facts helpers.

---

## Step 2: Build/load artifact after scanner completion

In `agent_os/backend/services/langgraph_engine.py`, identify the scanner completion point where `scan_state` and `root_run_id` are available and scanner summaries have been written to the report directory.

Add:
```python
from tradingagents.graph.scanner_facts.builder import ensure_scanner_graph_facts
```

Call:
```python
graph_facts_path = ensure_scanner_graph_facts(scan_date=date, run_id=root_run_id)
```

Log the path and surface failures. Do not catch and downgrade this exception in normal execution.

---

## Step 3: Render per-ticker graph context

In the ticker pipeline setup, replace the current normal-path packet-only context with:

```python
from tradingagents.graph.scanner_facts.builder import load_scanner_graph_facts
from tradingagents.graph.scanner_facts.render import render_ticker_graph_context
from tradingagents.report_paths import get_scanner_graph_facts_path

facts = load_scanner_graph_facts(get_scanner_graph_facts_path(date, root_run_id))
scanner_graph_context_text = render_ticker_graph_context(facts, ticker)
```

Pass:
```python
scanner_graph_context_text=scanner_graph_context_text
```

to every normal `create_initial_state()` call. Keep `scanner_context_packet` only for explicit resume paths covered by the warning rule.

---

## Step 4: Direct scanner graph entrypoint

In `tradingagents/graph/scanner_graph.py`, call `ensure_scanner_graph_facts()` when the scanner run has both `scan_date` and `run_id`. This keeps direct scanner runs consistent with AgentOS backend runs.

If `run_id` is missing, fail loudly unless the caller is a documented test-only path.

---

## Step 5: Run tests

```bash
pytest tests/graph/scanner_facts/test_backend_wiring.py -v
pytest tests/graph/scanner_facts tests/graph/test_propagation_scanner_context.py -q
pytest tests/ -q -m "not integration" -x
```

Known current blocker before this feature: the broad suite stops at `tests/unit/agents/test_analyst_agents.py::test_fundamentals_analyst_tool_loop`.

---

## Done When

- Normal scanner completion creates or loads `market/scanner_graph_facts.json`.
- Normal ticker execution receives non-empty `scanner_graph_context_text`.
- Missing/corrupt graph facts fail loudly with rebuild guidance.
- `scanner_context_packet` is not used as a silent normal-path fallback.
