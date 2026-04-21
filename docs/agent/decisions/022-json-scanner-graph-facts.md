# ADR 022: JSON Scanner Graph Facts

## Status

Accepted

## Context

Scanner output is currently passed downstream largely through `scanner_context_packet`, a broad text packet assembled from scanner artifacts. That packet is useful for operator resume paths, but it is too large and too weakly structured for normal ticker analysis prompts. It also makes provenance and confidence harder to preserve once analysts, researchers, trader, risk, and portfolio manager consume the scanner phase.

The scanner already emits structured summaries:

- `market/macro_scan_summary.json`
- `market/*_summary.md` files with repeatable sections and pipe-delimited rows

The Neo4j GraphRAG plan is intentionally deferred. It needs a stable scanner-phase semantic input rather than reparsing raw summaries independently.

## Decision

Introduce `scanner_graph_facts.json` as the canonical scanner-phase graph facts artifact:

```text
reports/daily/{scan_date}/{run_id}/market/scanner_graph_facts.json
```

The artifact is generated once after scanner completion, is immutable during normal execution, and contains:

- `global_regime`
- typed nodes
- typed edges
- provenance
- evidence
- confidence
- metadata

Ticker analysis retrieves a ticker-focused subgraph from this artifact, renders compact prompt text, and passes it through `scanner_graph_context_text`.

ADR 023 Neo4j consumes `scanner_graph_facts.json` later. It does not reparse raw scanner summaries as its primary ingestion path.

## Rules

- Normal execution builds or loads `scanner_graph_facts.json` after scanner completion.
- Ticker analysis loads the artifact and renders graph context for the ticker before creating `AgentState`.
- Missing or corrupt required scanner inputs fail loudly in normal execution.
- There is no silent fallback to `scanner_context_packet` in normal execution.
- `scanner_context_packet` remains only for operator-explicit resume paths, and those paths must emit a warning banner when graph facts are absent.
- Historical rebuild is the only overwrite path.
- v1 inputs are `market/*_summary.md` and `market/macro_scan_summary.json`.
- v1 excludes raw scanner reports, complete reports, ticker analyst reports, analyst prose, and Neo4j writes.
- Retrieval is ticker 2-hop connected subgraph plus compact global regime.
- Broad macro/index assets are modeled as `MarketIndex`, `MacroIndicator`, `Commodity`, `CurrencyPair`, or `CryptoAsset`, never coerced into `Ticker`.
- Confidence is computed at emit time from the plan's confidence table and is not defaulted to `1.0`.
- The alias registry is a living file. Unknown labels that fall back to heuristic classification should generate warnings that drive future alias additions.

## Consequences

The scanner graph becomes reproducible, diffable, and provenance-preserving. Prompt context becomes smaller and ticker-focused while retaining the scanner phase as the source of truth.

Normal backend wiring must fail loudly until the artifact exists. This is intentional: continuing with empty context or a silent raw-packet fallback would violate the graph contract.

The explicit rebuild utility is required for historical folders and is the only place where overwrite is allowed.

## Relationship To ADR 023

ADR 023 covers the persistent Neo4j successor. It must ingest `scanner_graph_facts.json` as its scanner semantic input, preserve this ADR's resume/fail-loud rule, and treat Neo4j as a later memory/indexing layer rather than a replacement for the immutable scanner artifact.
