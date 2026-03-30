---
type: decision
status: active
date: 2026-03-27
agent_author: "codex"
tags: [scanner, gap-detector, ranking, yfinance, finviz]
related_files: [tradingagents/dataflows/yfinance_scanner.py, tradingagents/agents/utils/scanner_tools.py, tradingagents/graph/scanner_graph.py, tradingagents/agents/scanners/macro_synthesis.py]
---

## Context

The scanner now has stronger global-only stages for factor alignment and drift context, but three gaps remain between the current implementation and the target 1–3 month discovery engine:

1. The system does not compute a real market-data gap signal from OHLC data.
2. Candidate overlap is still mostly resolved by LLM synthesis rather than a deterministic ranking layer.
3. True analyst revision diffusion is still missing because we do not yet have the right structured data source.

The user explicitly wants:

- documentation first
- a live integration test before any gap-detector tool is implemented
- true revision diffusion deferred to a future section until a suitable data source exists

## Capability Check

### yfinance

`yfinance` does not expose a dedicated “gap detector” helper or preset screener. However, it does expose the raw ingredients needed to compute one:

- bounded candidate discovery via `yf.screen(...)`
- OHLC data via `yf.download(...)` / `Ticker.history(...)`

This is sufficient to build a deterministic gap detector from:

```text
gap_pct = (today_open - previous_close) / previous_close
```

plus optional confirmation such as relative volume and intraday hold (`close_vs_open`).

### Finviz / finvizfinance

In this environment, `finvizfinance` is not installed, so we cannot rely on it for immediate implementation or live local inspection.

Separately, Finviz’s screener documentation confirms that the platform has:

- a `Gap` technical field
- `Unusual Volume`
- `Upgrades` / `Downgrades`
- earnings-before / earnings-after signals

This means Finviz remains a viable future gap source, but not the first implementation path here.

## The Decision

### 1. Build the first real gap detector on yfinance, not Finviz

Reason:

- available locally now
- deterministic from raw market data
- no dependence on scraper-specific filter strings
- easier to validate with a no-mock live integration test

### 2. Require a live integration test before the tool exists

The first implementation step is a live test that proves the chosen data path can produce a valid gap calculation from real data without mocks. The tool must only be added after this test passes.

### 3. Add a deterministic candidate-ranking layer

Golden Overlap should not be left entirely to LLM synthesis. We will add a Python ranking layer that rewards names appearing across:

- leading sectors
- market-data gap / continuation signals
- smart-money signals
- geopolitical or macro-theme support
- factor-alignment support

The LLM should explain and package the result, not invent the overlap rule.

### 4. Defer true revision diffusion

True revision diffusion requires structured analyst estimate data. We do not have that source yet, so this stays in an upcoming section rather than being approximated further.

## Planned Implementation

### Phase A — live validation

Add a live integration test that:

1. fetches a bounded real universe from `yfinance` screeners
2. downloads recent OHLC data for that universe
3. computes gap percentage from open vs previous close
4. verifies the test returns a structurally valid table of candidates or an explicit “no candidates today” result

No mocks are allowed in this test.

### Phase B — real gap detector

After live validation passes:

1. add a `yfinance_scanner` function that computes real gap candidates
2. expose it through `scanner_tools.py`
3. use it inside the drift scanner instead of gap-themed news alone

The first version should stay bounded:

- use a short universe from movers / actives / gainers
- avoid full-market scans
- filter by meaningful absolute gap and liquidity thresholds

### Phase C — candidate-ranking layer

Add a deterministic ranking step before final synthesis:

1. collect candidate tickers from each scanner stream
2. normalize them into a merged Python structure
3. score them by overlap across streams
4. pass the ranked top set into macro synthesis

The scoring model should be explicit and testable.

## Upcoming (Deferred)

### True Revision-Diffusion Metric

Deferred until we have a source that exposes:

- upward vs downward estimate revisions
- analyst coverage counts
- multi-period estimate drift
- ideally rating-change metadata

Until then, factor alignment remains a qualitative / news-backed approximation and must not be described as true diffusion.

## Constraints

- Do not implement per-ticker fan-out across the whole market.
- Do not claim revision diffusion exists until the structured data source exists.
- Do not introduce a gap-detector tool before the no-mock live integration test proves the data path.
- Keep overlap scoring deterministic and inspectable in Python.

## Actionable Rules

- Prefer `yfinance` for the first real gap implementation.
- Keep the candidate universe bounded and cheap.
- Use Finviz only as a future enhancement path unless `finvizfinance` is installed and validated.
- Treat revision diffusion as upcoming work, not current capability.
