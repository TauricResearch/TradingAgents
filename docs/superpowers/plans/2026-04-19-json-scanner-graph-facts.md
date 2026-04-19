# JSON Scanner Graph Facts v1 Implementation Plan

> **For agentic workers:** This is a **feature-level** plan. Each Feature below defines scope, contracts, rules, and tests. A separate task document will be authored per feature before execution. Neo4j (ADR 023) consumes this artifact later and is out of scope here.

## Status

- **ADR for this plan:** `022-json-scanner-graph-facts.md`
- **ADR for Neo4j successor:** `023-graphrag-knowledge-graph.md`
- **Ship order:** this plan first, Neo4j plan (`docs/superpowers/plans/2026-04-18-graphrag-knowledge-graph.md`) second.

## Implementation Status (2026-04-19)

PR #219 currently implements and tests **Feature 1 through Feature 9**:

| Feature | Status | Notes |
|---|---|---|
| F1-F5 | Implemented | Schema, normalization, adapters, builder, immutable persistence |
| F6 | Implemented | Historical rebuild CLI with narrow markdown-only fallback for malformed macro JSON |
| F7 | Implemented | JSON graph search, including curated alias fallback |
| F8 | Implemented | Prompt renderer and LangChain tool named `render_ticker_graph_context` |
| F9 | Implemented | `scanner_graph_context_text` state field and propagation |
| F10 | Not implemented | Backend scanner/ticker wiring still uses `scanner_context_packet` |
| F11 | Not implemented | Analyst/trader/summary prompts still consume `scanner_context_packet` |
| F12 | Partially implemented | Scanner-facts suite exists; end-to-end backend smoke coverage is pending |
| F13 | Implemented | ADR 022 added at `docs/agent/decisions/022-json-scanner-graph-facts.md` |

The broader end-to-end goal is **not complete** until F10-F12 land. Until then, the repository can build, search, and render `scanner_graph_facts.json` directly, but normal backend runs do not automatically generate the artifact or inject rendered graph context into analyst prompts.

## Project Philosophy (binding)

This repo is under active production development. Plans must follow:

- **Single path.** No silent dual implementations, no "try A then B" compatibility shims.
- **Minimize fallbacks.** A fallback exists only when it is a strictly degraded but still-structured version of the primary input (e.g., LLM JSON fails, but the same node produced a parseable structured-Markdown section).
- **Fail loud on important nodes.** If a scanner-phase input that the graph depends on is missing or corrupt, the scanner run fails. Do not continue with empty context and do not silently substitute `scanner_context_packet`.
- **Quality over reach.** Better to refuse to emit an edge than to emit a low-confidence guessed edge.
- **Immutability is a rule, not a suggestion.** Only the rebuild utility may overwrite an existing artifact.

## Goal

Create an immutable, scanner-phase-only JSON graph facts artifact per scanner run, then use deterministic JSON graph search to provide compact ticker-specific context to analysts, researchers, trader, risk, and portfolio manager.

Canonical artifact:

```text
reports/daily/{scan_date}/{run_id}/market/scanner_graph_facts.json
```

Generated once after scanner completion. Never modified by ticker analysis. If it already exists in normal execution, load it. Historical folders are rebuilt only by the explicit rebuild utility.

## Decisions Locked In

- One **global scan graph** per scanner run. Not one per ticker.
- Persist under the run's `market/` folder.
- v1 inputs:
  - `market/*_summary.md`
  - `market/macro_scan_summary.json`
- v1 excludes: raw `*_report.md`, `complete_report.md`, ticker analyst reports, prose notes, Neo4j.
- Retrieval = ticker's 2-hop connected subgraph + compact global-regime block.
- Broad macro/index assets are nodes of their own type. Never coerced into `Ticker`.
- `scanner_context_packet` remains for resume/rebuild-only paths (see Resume Rule), not as a silent fallback in normal execution.

## Current Report Structure Observed

Historical folder shape:

```text
reports/daily/2026-04-16/01KPBZ79XBDWWYSXVZF0APEYPW/market/
  gatekeeper_summary.md
  geopolitical_summary.md
  industry_deep_dive_summary.md
  market_movers_summary.md
  sector_summary.md
  smart_money_summary.md
  macro_scan_summary.json
```

Markdown summaries use repeatable sections:

```text
Candidate Rows
Sector / Macro Implication
Dates and Exact Numbers
Risk / Failure Modes
```

Useful bullets are pipe-delimited:

```text
* NVDA | Technology | Dominance | Ranked 1st by market cap and volume | High market cap concentration.
* ON  | Technology | Breakout Accumulation | $79.93 price level | Implies institutional accumulation.
- TECHNOLOGY | Positive acceleration across all timeframes | Sustained growth sector strength.
```

## Canonical Schema

```json
{
  "schema_version": "scanner_graph_facts.v1",
  "scan_date": "2026-04-16",
  "run_id": "01KPBZ79XBDWWYSXVZF0APEYPW",
  "source_dir": "reports/daily/2026-04-16/01KPBZ79XBDWWYSXVZF0APEYPW/market",
  "global_regime": {
    "summary": "Markets are in a pronounced Risk-On regime...",
    "bullets": [
      "Risk-On regime with S&P 500 and Nasdaq reaching new highs.",
      "Technology leads 1-month returns; Real Estate shows YTD strength.",
      "Key macro risks include Brent supply premium, German CDS stress, and VIX reversal risk."
    ],
    "source": "macro_scan_summary.json"
  },
  "nodes": [
    {
      "id": "ON",
      "type": "Ticker",
      "label": "ON",
      "aliases": ["ON Semiconductor", "Onsemi"],
      "provenance": ["smart_money_summary.md#Candidate Rows"],
      "evidence": ["Breakout accumulation at $79.93 with 52-week high on high volume"],
      "confidence": 0.95
    }
  ],
  "edges": [
    {
      "source": "ON",
      "relation": "BELONGS_TO",
      "target": "Technology",
      "polarity": "",
      "provenance": "smart_money_summary.md#Candidate Rows",
      "evidence": "ON | Technology | Breakout Accumulation | ...",
      "confidence": 0.95
    }
  ],
  "metadata": {
    "node_count": 0,
    "edge_count": 0,
    "generated_at": "2026-04-19T00:00:00Z",
    "inputs": []
  }
}
```

## Node Types

```text
Ticker
Sector
Theme
RiskFactor
MarketIndex
MacroIndicator
Commodity
CurrencyPair
CryptoAsset
```

`MacroEvent`/`GeoEvent` are deferred. Current summaries describe conditions, not discrete events.

### Classification Rules

- `Ticker`: individual equities only (`NVDA`, `ON`, `MSFT`).
- `Sector`: normalized sector names (`Technology`, `Real Estate`, `Energy`).
- `Theme`: investable or explanatory themes (`AI Infrastructure`, `Risk-On Rotation`).
- `RiskFactor`: explicit risk/failure mode (`Technology concentration risk`).
- `MarketIndex`: `S&P 500`, `NASDAQ`, `Russell 2000`, `Dow Jones`.
- `MacroIndicator`: `VIX`, sovereign CDS, CPI, rates, yields.
- `Commodity`: `Brent Crude`, `WTI Crude`, `Gold`.
- `CurrencyPair`: `EUR/USD`, `JPY/USD`, `CNY/USD`.
- `CryptoAsset`: `Bitcoin`.

Rows whose first column is `N/A`, `Not Applicable`, or `SECTOR/THEME` are not `Ticker` rows.

## Relation Types

```text
BELONGS_TO
DRIVES_SENTIMENT
EXPOSED_TO
IMPACTS
RELATED_TO
HAS_CATALYST
```

### HAS_CATALYST vs DRIVES_SENTIMENT (discriminator rule)

Both connect `Ticker -> Theme`. Pick exactly one:

- **`HAS_CATALYST`** — Theme is a **forward-looking named event/trigger** attached to the ticker in `macro_scan_summary.json` fields like `key_themes`, `stocks_to_investigate[].catalyst`, or `stocks_to_investigate[].thesis`. Characteristics:
  - sourced from `macro_scan_summary.json`
  - references an upcoming event, product cycle, earnings window, policy decision, or structural driver
  - implication text contains catalyst-like language (e.g., "earnings", "launch", "approval", "cycle", "announcement", "guidance")
- **`DRIVES_SENTIMENT`** — Theme is a **current-flow or sentiment classification** inferred from a Markdown `Candidate Rows` signal column (`Breakout Accumulation`, `Distribution`, `Momentum`, `Dominance`, `Weakness`). Characteristics:
  - sourced from `*_summary.md` pipe rows
  - describes observed price/flow/positioning state, not an upcoming trigger
  - polarity is inferable now

Decision algorithm:

```text
if source is macro_scan_summary.json AND (
    field is key_themes OR
    implication text matches catalyst lexicon
): HAS_CATALYST
else if source is *_summary.md AND row is Candidate Rows: DRIVES_SENTIMENT
else: RELATED_TO
```

### Other Relations

- `BELONGS_TO`: `Ticker -> Sector`.
- `EXPOSED_TO`: `Ticker|Sector|Theme -> RiskFactor`.
- `IMPACTS`: `MacroIndicator|MarketIndex|Commodity|CurrencyPair|RiskFactor -> Sector|Theme`.
- `RELATED_TO`: safe default when no more specific relation is justified.

Every edge must include `source`, `relation`, `target`, `provenance`, `evidence`, `confidence`.

## Confidence Computation (binding)

Confidence is computed at emit-time, not guessed. Never default to `1.0`.

Per-emission base confidence by source + structure:

| Source / Structure | Base |
|---|---|
| `macro_scan_summary.json` structured field (e.g., `stocks_to_investigate`) | 0.90 |
| `macro_scan_summary.json` free text in `executive_summary` / `macro_context` | 0.70 |
| `*_summary.md` pipe row with 5 columns AND non-empty evidence column | 0.95 |
| `*_summary.md` pipe row with partial columns (3–4) AND non-empty evidence | 0.75 |
| `*_summary.md` free bullet line (no pipes) anchored to a known node | 0.55 |
| Inferred edge (e.g., `IMPACTS` from implication phrasing, no direct pipe) | 0.50 |

Adjustments (clamped to `[0.1, 0.99]`):

- `-0.10` if the row contains hedging language: `"may"`, `"could"`, `"if"`, `"potential"`, `"uncertain"`.
- `-0.05` if `polarity == ""` on a sentiment-style edge.
- `-0.15` if the node was classified by lexical heuristic only (e.g., `is_equity_ticker` fallback).
- `+0.05` if the same `(source, relation, target)` is corroborated by ≥ 2 distinct provenance files.

Node confidence after merge = `max(component_confidences)`.
Edge confidence = computed once at emit, not recomputed on merge; ties broken by highest `confidence` retained.

Rows whose final confidence would be `< 0.50` are dropped, not emitted.

## Aliases

Aliases are not optional. An empty `aliases: []` on a `Ticker` or `Sector` node is allowed only if no alias entry is known. Every node type that can be referenced by analysts gets alias resolution during search.

### Alias Sources (priority order)

1. **Curated alias registry** (checked in):
   - `tradingagents/graph/scanner_facts/aliases.py` exports:
     ```python
     TICKER_ALIASES: dict[str, list[str]]   # "ON" -> ["ON Semiconductor", "Onsemi"]
     SECTOR_ALIASES: dict[str, list[str]]   # "Technology" -> ["Information Technology", "Tech"]
     INDEX_ALIASES: dict[str, list[str]]    # "S&P 500" -> ["SPX", "S&P"]
     MACRO_ALIASES: dict[str, list[str]]    # "VIX" -> ["CBOE Volatility Index"]
     COMMODITY_ALIASES: dict[str, list[str]]# "Brent Crude" -> ["Brent"]
     FX_ALIASES: dict[str, list[str]]       # "EUR/USD" -> ["EURUSD"]
     ```
2. **Normalization rules** (`normalize.py`) — sector name canonicalization produces alias entries automatically.
3. **Observed-label capture** — during build, if a node is referenced by a label that canonicalizes to an existing node `id`, add the observed label to that node's `aliases` (deduped).

### Alias Registry Maintenance Rule

The alias registry is a living file. When a new ticker/sector/etc. appears in scanner output with an alternative surface form the extractors did not recognize, the registry must be updated in the same PR. The build must log a warning line for every observed label that fell back to heuristic classification — these warnings are the source-of-truth backlog for alias additions.

## Prompt Context Shape

Ticker rendering stays compact and relevance-bound:

```md
## Global Market Regime
- Risk-On regime; S&P 500 and Nasdaq reached new highs.
- Technology leads 1-month returns; Real Estate shows YTD strength.
- Key macro risks: Brent supply premium, German CDS stress, VIX reversal risk.

## Ticker Graph Context: ON
- ON belongs to Technology.
- ON is linked to Breakout Accumulation, with evidence: "$79.93 price level".
- Technology is linked to AI Infrastructure and Risk-On Rotation.
- Technology is exposed to concentration risk and valuation premium risk.

## Provenance
- ON -> Technology: smart_money_summary.md#Candidate Rows
- ON -> Breakout Accumulation: industry_deep_dive_summary.md#Candidate Rows
- Technology -> concentration risk: gatekeeper_summary.md#Risk / Failure Modes
```

Retrieval rule:

```text
rendered_context = compact global_regime + retrieve_ticker_subgraph(ticker, hops=2)
```

Do not add every macro/index node to every ticker context. Macro/index context enters only through graph connectivity, plus the compact `global_regime` block.

### Per-Node-Type Summarization Templates

Rendering uses different one-line templates per node type to keep voice consistent:

| Node Type | Template |
|---|---|
| `Ticker` | `{ticker} belongs to {sector}.` / `{ticker} is linked to {theme} ({polarity}), with evidence: "{evidence}".` |
| `Sector` | `{sector} is {polarity} with evidence: "{evidence}".` |
| `Theme` | `Theme {theme} is active: "{evidence}".` |
| `RiskFactor` | `{subject} is exposed to {risk}: "{evidence}".` |
| `MarketIndex` | `{index}: {evidence}.` |
| `MacroIndicator` | `{indicator}: {evidence}.` |
| `Commodity` | `{commodity}: {evidence}.` |
| `CurrencyPair` | `{pair}: {evidence}.` |
| `CryptoAsset` | `{asset}: {evidence}.` |

Concrete per-template prompt strings are authored in each feature's task document, not here.

### Render Budget and Dedup

The renderer must:

- Cap total output at a declared **character budget** (default: 2400 chars; configurable) and an advisory **token budget** (default: 600 tokens, measured by shared tokenizer used elsewhere in the repo). Exceeding character budget hard-truncates **provenance lines first**, then oldest fact lines.
- Dedupe rendered fact lines by `(subject, relation, object)` across adapters so the same `ON -> Technology BELONGS_TO` is never printed twice even if both `smart_money_summary.md` and `industry_deep_dive_summary.md` emitted it.
- Dedup preserves the **highest-confidence** provenance for the Provenance section.
- If budget forces truncation, append a single trailing line: `... (N more facts omitted)`.

## File Map

### New files

| File | Responsibility |
|---|---|
| `tradingagents/graph/scanner_facts/__init__.py` | Package marker, public exports |
| `tradingagents/graph/scanner_facts/schema.py` | Typed schema, allowed node/relation types, validation |
| `tradingagents/graph/scanner_facts/aliases.py` | Curated alias registry (living file) |
| `tradingagents/graph/scanner_facts/normalize.py` | Canonical IDs, sector names, node classification, polarity, confidence adjustments |
| `tradingagents/graph/scanner_facts/from_macro_json.py` | `macro_scan_summary.json` adapter |
| `tradingagents/graph/scanner_facts/from_markdown.py` | `*_summary.md` adapter |
| `tradingagents/graph/scanner_facts/builder.py` | Merge/dedupe, build/save/load, immutability enforcement |
| `tradingagents/graph/scanner_facts/search.py` | Exact/alias lookup, 1/2-hop subgraph retrieval |
| `tradingagents/graph/scanner_facts/render.py` | Subgraph + global regime to prompt text (char/token budget, dedup) |
| `tradingagents/graph/scanner_facts/rebuild.py` | Historical rebuild API + CLI |
| `tests/graph/scanner_facts/...` | Test package, fixtures, per-feature tests |

### Modified files

| File | Change |
|---|---|
| `tradingagents/report_paths.py` | Add `get_scanner_graph_facts_path(date, run_id)` |
| `tradingagents/agents/utils/agent_states.py` | Add `scanner_graph_context_text` only |
| `tradingagents/graph/propagation.py` | Initialize `scanner_graph_context_text` |
| `agent_os/backend/services/langgraph_engine.py` | Build/load artifact after scanner; retrieve + render per ticker |
| `tradingagents/graph/scanner_graph.py` | Generate artifact on direct scanner runs when `run_id` present |
| `tradingagents/agents/analysts/*.py` | Use `scanner_graph_context_text` directly; no silent fallback (see Resume Rule) |
| `tradingagents/agents/trader/trader.py` | Same |
| `tradingagents/agents/utils/summary_context.py` | Use graph context in `build_research_packet()` / `build_debate_evidence_brief()` |
| `tradingagents/agents/managers/context_summaries.py` | Graph context participates in cache/fingerprint |

### State Fields (pruned)

Only **one** new field is added to `AgentState`:

```python
scanner_graph_context_text: Annotated[str, "Prompt-ready ticker graph context rendered from scanner graph facts"]
```

The previously proposed `scanner_graph_facts_path` and `scanner_graph_context` dict are **not** added. The artifact path is derivable from `scan_date` + `run_id`, and analysts consume rendered text, not the raw dict.

## Resume / Partial-Run Rule (binding)

There is exactly one way this plan handles resumed or partial runs:

1. **Normal execution** builds the artifact after scanner completion. If `macro_scan_summary.json` or a required `*_summary.md` is missing OR quality-gated (`[NO_EVIDENCE]`, `[QUALITY: empty]`, `[QUALITY: degraded]` on a file the build depends on), the build **fails loudly** and the scanner run is marked failed. Do not silently continue.
2. **Ticker analysis** always loads `scanner_graph_facts.json` for its `(scan_date, run_id)`. If the artifact is missing, the ticker analysis call fails loudly with a clear error pointing at the rebuild CLI. No silent fallback to `scanner_context_packet`.
3. **Rebuild-only fallback** (narrow exception): when the rebuild utility is invoked on a historical folder whose `macro_scan_summary.json` is malformed JSON but whose Markdown summaries are structurally valid, the rebuild may proceed using the Markdown adapters only and emit a `global_regime` reconstructed from the Markdown sector/geopolitical summaries. This is the only sanctioned fallback: "LLM JSON broke but structured Markdown is present." The emitted artifact's `metadata.inputs` must flag the degraded source.
4. `scanner_context_packet` remains as an emergency input available to `pipeline_from_phase` / `run_pipeline_from_phase` **only** when an operator explicitly invokes a resume without building graph facts. This path must log a single explicit warning banner and is not used by the normal backend flow. The Neo4j plan (ADR 023) must mirror this same rule.

## Immutability Invariant (binding)

- `save_scanner_graph_facts(..., overwrite=False)` is the only path invoked from normal execution.
- `overwrite=True` is accepted **only** from `rebuild.py`. Builder code asserts the caller module name.
- If the artifact exists and `overwrite=False`, the function must short-circuit to load-and-return. It must not write.
- Tampering (file mtime changed vs `generated_at` by more than tolerance) is logged but not auto-repaired.

## Features

Each feature below is a self-contained shipping unit. A per-feature task document (`docs/superpowers/plans/tasks/2026-04-19-json-scanner-graph-facts/<NN>-<slug>.md`) will be authored before execution. Each task document will contain the TDD step breakdown.

### Feature 1 — Schema, Validation, Alias Registry

**Scope:**
- `schema.py` with `SCHEMA_VERSION`, `NODE_TYPES`, `RELATION_TYPES`, TypedDicts, `validate_graph_facts`.
- `aliases.py` with initial registries seeded from observed 2026-04-16 fixtures.
- Tests: valid facts, invalid node type, invalid relation type, missing endpoint, missing provenance, alias registry shape.

**Done when:** `validate_graph_facts` returns `[]` for a valid fixture and non-empty for each invalid case.

### Feature 2 — Normalization, Classification, Confidence, Polarity

**Scope:**
- `normalize.py`: sector canonicalization, macro/index/commodity/FX/crypto classification, `is_equity_ticker`, polarity inference, confidence base table + adjustments.
- Warning log for any label that falls through to heuristic-only classification (alias backlog signal).

**Done when:** classification and confidence computation match the Confidence Computation table on representative inputs.

### Feature 3 — Macro JSON Adapter

**Scope:**
- `from_macro_json.py`: populate `global_regime`, create `Theme`, `Ticker`, `Sector`, `RiskFactor` nodes, and `BELONGS_TO`, `HAS_CATALYST`, `DRIVES_SENTIMENT`, `EXPOSED_TO` edges per the discriminator rule.
- Fail loudly if the file is missing. Do not substitute empty facts.

**Done when:** a small real fixture of `macro_scan_summary.json` yields the expected nodes/edges and discriminator outcomes.

### Feature 4 — Markdown Summary Adapter

**Scope:**
- `from_markdown.py`: section splitting (`## Heading` and `**Heading**`), pipe-row parsing, candidate-row behavior, sector/macro-row behavior, risk-section behavior, dates-and-numbers attachment-only rule.
- Skip quality-gated files (`[NO_EVIDENCE]`, `[QUALITY: empty]`, `[QUALITY: degraded]`). A skipped file required by Feature 9's wiring escalates per the Resume Rule.

**Done when:** fixtures based on `smart_money_summary.md`, `industry_deep_dive_summary.md`, `sector_summary.md`, `geopolitical_summary.md` parse to expected nodes/edges.

### Feature 5 — Builder, Merge, Immutable Persistence

**Scope:**
- `builder.py`: `build_scanner_graph_facts_from_market_dir`, `save_scanner_graph_facts`, `load_scanner_graph_facts`, `ensure_scanner_graph_facts`.
- Node merge by `(type, id)`, edge merge by `(source, relation, target, provenance, evidence)`.
- Node confidence on merge = `max`. Edge confidence not recomputed on merge.
- Stable JSON ordering + indentation for diffability.
- Enforces Immutability Invariant (only `rebuild.py` may pass `overwrite=True`).

**Done when:** double-build without rebuild does not rewrite the file and returns byte-identical content.

**Open question for this feature's task document:** scope of corruption/round-trip tests — whether we assert byte equality across `save -> load -> save` or only semantic equality. Decide while writing the task doc.

### Feature 6 — Historical Rebuild Utility + CLI

**Scope:**
- `rebuild.py` with `rebuild_scanner_graph_facts(scan_date, run_id, ...)` and CLI:
  ```bash
  python -m tradingagents.graph.scanner_facts.rebuild --date 2026-04-16 --run-id 01KPBZ79XBDWWYSXVZF0APEYPW
  ```
- Flags: `--date`, `--run-id`, `--reports-root`, `--no-overwrite`.
- Applies the narrow rebuild-only fallback in the Resume Rule.

**Done when:** CLI regenerates an artifact for a temp-fixture folder and, for a malformed-JSON fixture, emits a degraded-source artifact flagged in `metadata.inputs`.

### Feature 7 — JSON Graph Search

**Scope:**
- `search.py`: `retrieve_ticker_subgraph(facts, ticker, hops=2, node_types=None, max_edges=80)`.
- Exact + alias lookup (uses Feature 1's registry).
- Undirected traversal for retrieval, direction preserved in output.
- Unknown ticker → fail loudly (raise), not return empty.

**Done when:** exact, alias, unknown-ticker-raises, 1-hop, 2-hop, `max_edges` cases pass.

### Feature 8 — Prompt Renderer + Render Tool

**Scope:**
- `render.py`: `render_ticker_graph_context(...)` with character/token budget, per-node-type templates, dedup across adapters, provenance truncation order.
- **Render tool**: expose rendering as a LangChain-compatible tool (name: `render_ticker_graph_context`) so analysts and debate/research nodes may call it on demand from state `(scan_date, run_id, ticker)`. Determinism preserved (no LLM in rendering).
- If subgraph empty and global regime empty → return `""`. If ticker missing → raise (search feature decides).

**Done when:** dedup + budget + per-type templates verified on fixture, tool invocation from a minimal harness produces identical text to direct function call.

### Feature 9 — State Field + Propagation

**Scope:**
- Add `scanner_graph_context_text: str` to `AgentState`.
- `Propagator.create_initial_state()` accepts `scanner_graph_context_text: str = ""` and stores it.
- Drop `scanner_graph_facts_path` and `scanner_graph_context` from scope.

**Done when:** existing tests pass; new field roundtrips through propagation.

### Feature 10 — Backend Wiring (Fail-Loud)

**Scope:**
- `agent_os/backend/services/langgraph_engine.py`: after scanner completion, build or load the artifact. Build failure → run fails. Missing artifact at per-ticker stage → ticker call fails with rebuild instruction. No silent `scanner_context_packet` substitution.
- `tradingagents/graph/scanner_graph.py`: generate artifact on direct scanner runs when `scan_date` and `run_id` are present; fail loud on build error.
- Per ticker: load facts, call `retrieve_ticker_subgraph`, call `render_ticker_graph_context`, inject `scanner_graph_context_text` into `create_initial_state()`.
- Task doc: `docs/superpowers/plans/tasks/2026-04-19-json-scanner-graph-facts/10-backend-wiring-fail-loud.md`.

**Done when:** a broken scanner input causes a visible run failure with actionable message; a healthy run produces non-empty `scanner_graph_context_text` for each ticker.

### Feature 11 — Analyst / Trader / Summary Prompt Integration

**Scope:**
- Analysts and trader read `scanner_graph_context_text` directly. No `or scanner_context_packet` fallback in normal execution paths.
- `news_analyst.py`: skip ticker filtering when graph context is present (already ticker-focused).
- `build_research_packet()` uses section header `## Scanner Graph Context`.
- `build_debate_evidence_brief()` uses graph context for ground-truth section.
- `context_summaries.py`: fingerprint/cache keyed on graph context.
- **Per-node-type prompt copy**: each analyst/trader/researcher has a dedicated one-sentence briefing paragraph explaining how to read the `## Ticker Graph Context` block (e.g., market analyst emphasizes sector+index edges; news analyst emphasizes theme+risk edges; trader emphasizes catalyst edges). Exact copy lives in the per-feature task document.
- Task doc: `docs/superpowers/plans/tasks/2026-04-19-json-scanner-graph-facts/11-analyst-trader-summary-prompt-integration.md`.

**Done when:** prompts render differently per node as designed, and no call path silently substitutes the raw scanner packet.

### Feature 12 — Fixtures and Smoke Checks

**Scope:**
- `tests/graph/scanner_facts/fixtures/` with tiny representative versions of `smart_money_summary.md`, `industry_deep_dive_summary.md`, `sector_summary.md`, `geopolitical_summary.md`, `macro_scan_summary.json`.
- Backend smoke tests proving normal scanner-to-ticker execution builds the artifact and passes non-empty `scanner_graph_context_text`.
- Resume-path smoke tests proving operator-explicit resumes keep `scanner_context_packet` only with a warning banner.
- Runs:
  ```bash
  pytest tests/graph/scanner_facts -v
  pytest tests/ -v -m "not integration" -x
  ```
- Task doc: `docs/superpowers/plans/tasks/2026-04-19-json-scanner-graph-facts/12-fixtures-smoke-checks.md`.

**Done when:** both commands green.

### Feature 13 — ADR 022

**Scope:**
- `docs/agent/decisions/022-json-scanner-graph-facts.md`:
  - JSON graph facts are the canonical scanner graph contract.
  - Artifact is immutable scanner-phase evidence.
  - Missing/corrupt inputs fail the run; no silent substitution.
  - Neo4j (ADR 023) ingests this artifact later.
  - v1 parses summaries only.
  - `scanner_context_packet` is operator-resume-only.
  - Ticker retrieval is 2-hop plus compact global regime.
  - Confidence is computed per the Confidence Computation table.
  - Alias registry is a living file; unknown labels produce warnings that drive updates.
- Task doc: `docs/superpowers/plans/tasks/2026-04-19-json-scanner-graph-facts/13-adr-022-json-scanner-graph-facts.md`.

## Companion Change in ADR 023 / Neo4j Plan

The Neo4j plan (`docs/superpowers/plans/2026-04-18-graphrag-knowledge-graph.md`) must be updated separately to:

- Renumber its ADR from 022 to **023**.
- Declare that it ingests `scanner_graph_facts.json` rather than reparsing scanner summaries.
- Adopt the same Resume Rule (no silent `scanner_context_packet` fallback; `pipeline_from_phase` / `run_pipeline_from_phase` resume path is operator-explicit with a warning banner).
- Adopt the same fail-loud posture on missing inputs.

## Non-Goals for v1

- No Neo4j service, driver, schema, or testcontainers.
- No LLM graph extraction.
- No free-form Markdown prose extraction.
- No analyst-enriched graph mutation.
- No cross-run memory.
- No ticker report ingestion.
- No raw scanner report ingestion.
- No silent fallback to `scanner_context_packet` in normal execution.

## Open Follow-Up Questions

1. Should v2 add an LLM fallback for unparseable semi-structured summary sections (bounded by the "LLM JSON fails, structured MD present" rule)?
2. Should v2 add `MacroEvent` / `GeoEvent` once reliable event extraction exists?
3. Should ticker-level analysis produce a separate `{TICKER}/analysis_graph_facts.json` artifact?
4. Should the render tool (Feature 8) later be accompanied by a search tool exposed to agents, or stay deterministic-context-only?
