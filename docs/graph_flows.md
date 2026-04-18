<!-- Last verified: 2026-04-18 -->

# Graph Flows

This is the shortest current overview of the runtime topology.
For exact node behavior, tool usage, and state writes, use [`graph_execution_reference.md`](./graph_execution_reference.md).

## Scanner

```mermaid
flowchart TD
    A([START]) --> B["gatekeeper_scanner"]
    A --> C["geopolitical_scanner"]
    A --> D["market_movers_scanner"]
    A --> E["sector_scanner"]
    
    B --> S_B["summarize_gatekeeper"]
    C --> S_C["summarize_geopolitical"]
    D --> S_D["summarize_market_movers"]
    E --> S_E["summarize_sector"]

    S_E --> F["factor_alignment_scanner"]
    S_E --> G["smart_money_scanner"]
    S_E --> H["drift_scanner"]
    S_D --> H
    S_B --> H

    F --> S_F["summarize_factor_alignment"]
    G --> S_G["summarize_smart_money"]
    H --> S_H["summarize_drift"]

    S_B --> I["industry_deep_dive"]
    S_C --> I
    S_D --> I
    S_F --> I
    S_G --> I
    S_H --> I

    I --> S_I["summarize_industry_deep_dive"]
    
    S_I --> J["macro_synthesis"]
    S_B --> J
    S_C --> J
    S_D --> J
    S_E --> J
    S_F --> J
    S_G --> J
    S_H --> J
    
    J --> K([END])
```

- Phase 1a fan-out: `gatekeeper_scanner`, `geopolitical_scanner`, `market_movers_scanner`, `sector_scanner`
- Summary Compression 1: `summarize_*` heuristic fast-paths to reduce LLM context token spam.
- Phase 1b/c bounded follow-ons: `factor_alignment_scanner`, `smart_money_scanner`, `drift_scanner`
- Summary Compression 2: `summarize_*` for Phase 1b/c nodes.
- Fan-in synthesis path: `industry_deep_dive -> summarize_industry_deep_dive -> macro_synthesis`

## Per-Ticker Trading Pipeline

```mermaid
flowchart TD
    A([START]) --> P["Instrument Preflight"]
    P --> B["Market Analyst"]
    B --> C["Msg Clear Market"]
    C --> D["Social Analyst"]
    D --> E["Msg Clear Social"]
    E --> F["News Analyst"]
    F --> G["Msg Clear News"]
    G --> G1["News Fact Checker"]
    G1 --> H["Fundamentals Analyst"]
    H --> I["Msg Clear Fundamentals"]
    I -->|normal| J["Bull Researcher"]
    I -->|critical abort| Q["Portfolio Manager / CRITICAL ABORT"]
    J -->|continue| K["Bear Researcher"]
    J -->|round cap| L["Research Manager"]
    K -->|continue| J
    K -->|round cap| L
    L --> M["Trader"]
    
    M --> R1_A["Aggressive R1"]
    M --> R1_C["Conservative R1"]
    M --> R1_N["Neutral R1"]
    
    R1_A --> Barrier["Risk Round Barrier"]
    R1_C --> Barrier
    R1_N --> Barrier
    
    Barrier --> R2_A["Aggressive R2"]
    Barrier --> R2_C["Conservative R2"]
    Barrier --> R2_N["Neutral R2"]
    
    R2_A --> Synth["Risk Synthesis"]
    R2_C --> Synth
    R2_N --> Synth
    
    Synth --> Q
    Q --> Z([END])
```

- Analysts run sequentially in the compiled graph, bypassing unsupported instruments dynamically at `Instrument Preflight`.
- Debate alternates bull and bear until `max_debate_rounds`.
- Risk debate is now a 2-round parallel map-reduce structure (`R1` parallel -> `Barrier` -> `R2` parallel -> `Risk Synthesis`).
- Critical aborts can short-circuit directly to `Portfolio Manager` or `END`.

## Portfolio

```mermaid
flowchart TD
    A([START]) --> B["load_portfolio"]
    B --> C["compute_risk"]
    C --> D["review_holdings"]
    D --> E["prioritize_candidates"]
    E --> F["macro_summary"]
    E --> G["micro_summary"]
    F --> H["make_pm_decision"]
    G --> H
    H --> I["cash_sweep"]
    I --> J["execute_trades"]
    J --> K([END])
```

- `load_portfolio`, `compute_risk`, `prioritize_candidates`, `cash_sweep`, and `execute_trades` are Python closure nodes.
- `review_holdings` is the only portfolio node with inline tool usage.
- `macro_summary` and `micro_summary` run in parallel and fan in to `make_pm_decision`.

## Auto

`auto` is imperative orchestration in `agent_os/backend/services/langgraph_engine.py`, not its own LangGraph DAG.

```mermaid
flowchart TD
    A["run_auto()"] --> B["run or reuse scan"]
    B --> C["load scan summary"]
    C --> D["merge scan candidates with holdings"]
    D --> E["run per-ticker pipelines with bounded concurrency and structured task ownership"]
    E --> F["load completed ticker analyses"]
    F --> G["run portfolio or resume from saved PM decision"]
```

## Runtime Notes

- The root identifier is always `run_id`.
- All run-scoped artifacts live under `reports/daily/{date}/{run_id}/`.
- Background tasks execute runs; WebSocket streams cached and persisted events for the same run.
- Auto Phase 2 uses structured `TaskGroup` ownership so queued ticker pipelines are cancelled if the parent run closes or fails.
- Future auto-run concurrency changes should avoid detached child tasks; otherwise run status and backend activity can diverge.
