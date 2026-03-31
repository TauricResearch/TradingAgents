<!-- Last verified: 2026-03-31 -->

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
    E --> F["factor_alignment_scanner"]
    E --> G["smart_money_scanner"]
    E --> H["drift_scanner"]
    D --> H
    B --> H
    B --> I["industry_deep_dive"]
    C --> I
    D --> I
    F --> I
    G --> I
    H --> I
    I --> J["macro_synthesis"]
    J --> K([END])
```

- Phase 1 fan-out: `gatekeeper_scanner`, `geopolitical_scanner`, `market_movers_scanner`, `sector_scanner`
- Bounded follow-ons: `factor_alignment_scanner`, `smart_money_scanner`, `drift_scanner`
- Fan-in synthesis path: `industry_deep_dive -> macro_synthesis`

## Per-Ticker Trading Pipeline

```mermaid
flowchart TD
    A([START]) --> B["Market Analyst"]
    B --> C["Msg Clear Market"]
    C --> D["Social Analyst"]
    D --> E["Msg Clear Social"]
    E --> F["News Analyst"]
    F --> G["Msg Clear News"]
    G --> H["Fundamentals Analyst"]
    H --> I["Msg Clear Fundamentals"]
    I -->|normal| J["Bull Researcher"]
    I -->|critical abort| Q["Portfolio Manager"]
    J -->|continue| K["Bear Researcher"]
    J -->|round cap| L["Research Manager"]
    J -->|critical abort| Q
    K -->|continue| J
    K -->|round cap| L
    K -->|critical abort| Q
    L --> M["Trader"]
    M --> N["Aggressive Analyst"]
    N -->|continue| O["Conservative Analyst"]
    N -->|stop or abort| Q
    O -->|continue| P["Neutral Analyst"]
    O -->|stop or abort| Q
    P -->|continue| N
    P -->|stop or abort| Q
    Q --> R([END])
```

- Analysts run sequentially in the compiled graph.
- Debate alternates bull and bear until `max_debate_rounds`.
- Risk rotates aggressive, conservative, and neutral until `max_risk_discuss_rounds`.
- Critical aborts can short-circuit directly to `Portfolio Manager`.

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
    D --> E["run per-ticker pipelines with bounded concurrency"]
    E --> F["load completed ticker analyses"]
    F --> G["run portfolio or resume from saved PM decision"]
```

## Runtime Notes

- The root identifier is always `run_id`.
- All run-scoped artifacts live under `reports/daily/{date}/{run_id}/`.
- Background tasks execute runs; WebSocket streams cached and persisted events for the same run.
