# Feature 11: Analyst / Trader / Summary Prompt Integration

**Parent plan:** `docs/superpowers/plans/2026-04-19-json-scanner-graph-facts.md`

**Goal:** Make downstream prompts consume the rendered scanner graph context instead of the raw scanner packet in normal execution.

**Current gap in PR #219:** `AgentState` has `scanner_graph_context_text`, but analysts, trader, research packet builders, debate evidence brief, and context summary nodes still read `scanner_context_packet`.

**Files to modify:**
- `tradingagents/agents/analysts/market_analyst.py`
- `tradingagents/agents/analysts/social_media_analyst.py`
- `tradingagents/agents/analysts/news_analyst.py`
- `tradingagents/agents/analysts/fundamentals_analyst.py`
- `tradingagents/agents/trader/trader.py`
- `tradingagents/agents/utils/summary_context.py`
- `tradingagents/agents/managers/context_summaries.py`

**Files to create or extend:**
- `tests/unit/agents/test_analyst_agents.py`
- `tests/unit/test_summary_nodes.py`
- `tests/unit/test_ground_truth_propagation.py`

---

## Rules

- Normal prompt paths read `scanner_graph_context_text`.
- Do not use `scanner_graph_context_text or scanner_context_packet` in normal paths.
- `scanner_context_packet` remains available only for operator-explicit resume paths from Feature 10.
- The rendered graph block is already ticker-focused; `news_analyst.py` must not run ticker filtering over it.
- Summary helpers use the section header `## Scanner Graph Context`.
- Cache/fingerprint logic includes `scanner_graph_context_text` so prompt summaries invalidate when graph context changes.

---

## Prompt Copy

Use one short role-specific paragraph before the graph block:

- Market analyst: "Use the scanner graph context as verified cross-market context: sector, index, volatility, commodity, and FX edges are ground truth for this run."
- Social analyst: "Use the scanner graph context to anchor social sentiment against verified scanner themes and risk factors."
- News analyst: "Use the scanner graph context as ticker-focused prior context; do not re-filter it by ticker string because it has already been retrieved for this ticker."
- Fundamentals analyst: "Use the scanner graph context to keep sector, catalyst, risk, and macro exposures consistent with the scanner run."
- Trader: "Use the scanner graph context to preserve catalysts, exposure edges, and risk factors when translating research into a trade plan."
- Research/debate summaries: "Treat scanner graph context as the compact ground-truth scanner evidence block for this ticker."

---

## Step 1: Write failing tests

Add tests that construct minimal state with:

```python
{
    "scanner_graph_context_text": "## Global Market Regime\n- Risk-On\n\n## Ticker Graph Context: ON\n- ON belongs to Technology.",
    "scanner_context_packet": "RAW PACKET SHOULD NOT APPEAR",
}
```

Assert:
- Analyst prompt inputs include `Ticker Graph Context`.
- Analyst prompt inputs do not include `RAW PACKET SHOULD NOT APPEAR`.
- Trader prompt inputs include graph context and exclude raw packet.
- `build_research_packet()` emits `## Scanner Graph Context`.
- `build_debate_evidence_brief()` uses graph context in its ground-truth section.
- `context_summaries.py` considers `scanner_graph_context_text` when deciding whether context exists.

Run:
```bash
pytest tests/unit/agents/test_analyst_agents.py tests/unit/test_summary_nodes.py tests/unit/test_ground_truth_propagation.py -q
```

Expected: fail before implementation because current prompt code reads `scanner_context_packet`.

---

## Step 2: Update analysts and trader

For each analyst/trader node:

```python
scanner_graph_context = state.get("scanner_graph_context_text", "")
```

Use the role-specific paragraph above and include the graph block when non-empty.

Do not silently fallback to `scanner_context_packet`.

---

## Step 3: Update summary helpers

In `summary_context.py`:

- `build_research_packet()` reads `scanner_graph_context_text`.
- Section header is `## Scanner Graph Context`.
- `build_debate_evidence_brief()` uses graph context as ground truth.

In `context_summaries.py`, include `scanner_graph_context_text` in the "has context" check and any fingerprint/cache inputs.

---

## Step 4: Run tests

```bash
pytest tests/unit/agents/test_analyst_agents.py tests/unit/test_summary_nodes.py tests/unit/test_ground_truth_propagation.py -q
pytest tests/graph/scanner_facts tests/graph/test_propagation_scanner_context.py -q
pytest tests/ -q -m "not integration" -x
```

Known current blocker before this feature: the broad suite stops at `tests/unit/agents/test_analyst_agents.py::test_fundamentals_analyst_tool_loop`.

---

## Done When

- Normal analyst/trader prompts consume `scanner_graph_context_text`.
- Raw `scanner_context_packet` does not appear in normal prompt tests.
- News prompt does not ticker-filter graph context.
- Research/debate summaries include scanner graph context.
- Resume fallback behavior is isolated to Feature 10 paths.
