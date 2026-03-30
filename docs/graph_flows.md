# TradingAgents Graph Flows

This is the short overview of the current graph topology.
For the node-by-node runtime reference, tool surface, and orchestration details, see [graph_execution_reference.md](./graph_execution_reference.md).

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
    H --> I
    G --> I
    I --> J["macro_synthesis"]
    J --> K([END])
```

- Phase 1 fan-out: `gatekeeper_scanner`, `geopolitical_scanner`, `market_movers_scanner`, `sector_scanner`
- Phase 1 follow-ons: `factor_alignment_scanner`, `smart_money_scanner`, `drift_scanner`
- Phase 2 fan-in: `industry_deep_dive`
- Phase 3 final synthesis: `macro_synthesis`

## Per-Ticker Pipeline

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
- Critical abort in `market_report` or `fundamentals_report` can jump directly to `Portfolio Manager`.
- Debate loop alternates bull/bear until `max_debate_rounds`.
- Risk loop rotates aggressive/conservative/neutral until `max_risk_discuss_rounds`.

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
- `review_holdings`, `macro_summary`, `micro_summary`, and `make_pm_decision` are LLM nodes.

## Auto

`auto` is imperative orchestration in `agent_os/backend/services/langgraph_engine.py`, not its own LangGraph DAG:

1. run or skip scan
2. load scan summary
3. merge scan tickers with holdings
4. run per-ticker pipelines concurrently
5. run portfolio phase or resume execution from saved PM decision
