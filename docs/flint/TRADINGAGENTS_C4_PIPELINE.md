# TradingAgents C4 Pipeline Schema

This document maps the end-to-end TradingAgents pipeline as it is wired in this
Flint shadow-analysis repo. The repo is an advisory sidecar: it writes evidence
artifacts under `output/` and does not write into Flint or place broker orders.

## Scope

- Primary entrypoint: `scripts/flint/run_shadow_analysis.py`
- Orchestrator: `tradingagents/graph/trading_graph.py`
- Graph assembly: `tradingagents/graph/setup.py`
- Runtime state: `tradingagents/agents/utils/agent_states.py`
- Local artifacts: `output/logs`, `output/cache`, `output/memory`

## C4 Level 1: System Context

```mermaid
C4Context
title TradingAgents Flint Shadow - System Context

Person(operator, "Operator", "Runs advisory shadow analysis for a ticker and analysis date.")

System_Boundary(shadowBoundary, "tradingagents-flint-shadow") {
  System(shadow, "TradingAgents Flint Shadow", "Python / LangGraph advisory sidecar that runs TradingAgents and emits evidence artifacts.")
}

System_Ext(flint, "Flint", "Downstream execution/governance system. Reads normalized evidence later; this repo does not write into it.")
System_Ext(llmProvider, "LLM Provider", "OpenAI-compatible local or remote chat provider, for example Ollama.")
System_Ext(dataVendors, "Market Data Vendors", "YFinance and Alpha Vantage data sources.")

Rel(operator, shadow, "Runs ticker/date shadow analysis", "CLI")
Rel(shadow, llmProvider, "Requests chat completions and structured outputs", "Provider API")
Rel(shadow, dataVendors, "Fetches prices, indicators, news, fundamentals, and insider data", "HTTP/API")
Rel(flint, shadow, "Can ingest advisory artifacts after the run", "File/artifact handoff")
```

## C4 Level 2: Containers

```mermaid
C4Container
title TradingAgents Flint Shadow - Containers

Person(operator, "Operator", "Runs a shadow pass.")
System_Ext(llmProvider, "LLM Provider", "Chat and structured output API.")
System_Ext(dataVendors, "Market Data Vendors", "YFinance and Alpha Vantage.")

System_Boundary(shadowBoundary, "tradingagents-flint-shadow") {
  Container(runner, "Flint Shadow Runner", "Python CLI wrapper", "Loads `.env.flint-shadow`, pins repo-local output paths, parses ticker/date/analysts, and prints the normalized run summary.")
  Container(cli, "Upstream Interactive CLI", "Typer / Rich / questionary", "Optional terminal UI. Useful for exploration, but must be launched with repo-local env path overrides for Flint shadow work.")
  Container(graph, "TradingAgentsGraph", "Python orchestrator", "Creates LLM clients, tool nodes, memory log, conditional logic, graph setup, propagation, reflection, and signal processing.")
  Container(workflow, "LangGraph Agent Workflow", "LangGraph StateGraph", "Executes selected analysts, research debate, trader proposal, risk debate, and portfolio decision.")
  Container(tools, "Data Tool Layer", "LangChain tools", "Routes analyst tool calls to configured market/news/fundamental data vendors.")
  Container(llmClient, "LLM Client Layer", "LangChain chat clients", "Builds provider-specific quick and deep thinking clients.")
  ContainerDb(store, "Repo-local Output Store", "JSON / Markdown / CSV / SQLite", "Stores final state logs, data cache, memory log, and optional checkpoints under `output/`.")
}

Rel(operator, runner, "Runs non-interactive shadow command", "shell")
Rel(operator, cli, "Can run terminal UI", "shell")
Rel(runner, graph, "Builds config and calls `propagate(ticker, date)`", "Python")
Rel(cli, graph, "Builds selections and calls analysis", "Python")
Rel(graph, llmClient, "Creates quick/deep LLMs", "Python")
Rel(graph, workflow, "Compiles and invokes graph", "LangGraph")
Rel(workflow, tools, "Executes analyst tool calls", "LangChain ToolNode")
Rel(tools, dataVendors, "Routes data requests", "HTTP/API")
Rel(workflow, llmClient, "Invokes analyst, debate, trader, and manager prompts", "LLM API")
Rel(graph, store, "Reads memory/checkpoints and writes run artifacts", "filesystem")
```

## C4 Level 3: Workflow Components

```mermaid
C4Component
title TradingAgents Flint Shadow - LangGraph Workflow Components

Container_Boundary(workflowBoundary, "LangGraph Agent Workflow") {
  Component(analystLoop, "Selected Analyst Tool Loops", "Analyst nodes + ToolNode", "Market, social, news, and fundamentals analysts run in configured order. Each analyst can call tools repeatedly until no tool calls remain.")
  Component(messageClear, "Message Clear Nodes", "LangGraph state cleanup", "Drops analyst tool-call chatter and leaves a placeholder before the next analyst.")
  Component(researchDebate, "Bull/Bear Research Debate", "Quick LLM nodes", "Bull and Bear researchers debate the reports for `max_debate_rounds`.")
  Component(researchManager, "Research Manager", "Deep LLM structured output", "Converts the bull/bear debate into a rendered `ResearchPlan` markdown investment plan, with free-text fallback.")
  Component(trader, "Trader", "Quick LLM structured output", "Converts the investment plan and reports into a rendered `TraderProposal` markdown transaction proposal, with free-text fallback.")
  Component(riskDebate, "Risk Debate", "Quick LLM nodes", "Aggressive, Conservative, and Neutral analysts debate the trader plan for `max_risk_discuss_rounds`.")
  Component(portfolioManager, "Portfolio Manager", "Deep LLM structured output", "Produces the final rendered `PortfolioDecision` markdown decision, with free-text fallback.")
}

Container_Ext(tools, "Data Tool Layer", "LangChain tools", "Stock, indicator, news, insider, and fundamentals tools.")
Container_Ext(store, "Repo-local Output Store", "JSON / Markdown / CSV / SQLite", "State log, memory log, cache, checkpoints.")
Container_Ext(llmClient, "LLM Client Layer", "LangChain chat clients", "Quick and deep model calls.")

Rel(analystLoop, tools, "Calls tools until analyst emits no tool calls")
Rel(analystLoop, messageClear, "Hands off after report is finalized")
Rel(messageClear, analystLoop, "Continues to next selected analyst when configured")
Rel(messageClear, researchDebate, "After last selected analyst")
Rel(researchDebate, researchManager, "Hands debate history to manager")
Rel(researchManager, trader, "Writes `investment_plan`")
Rel(trader, riskDebate, "Writes `trader_investment_plan`")
Rel(riskDebate, portfolioManager, "Hands risk debate history to PM")
Rel(portfolioManager, store, "Final decision is persisted by graph after completion")
Rel(analystLoop, llmClient, "Analyst prompts")
Rel(researchDebate, llmClient, "Bull/Bear prompts")
Rel(researchManager, llmClient, "Structured ResearchPlan")
Rel(trader, llmClient, "Structured TraderProposal")
Rel(riskDebate, llmClient, "Risk analyst prompts")
Rel(portfolioManager, llmClient, "Structured PortfolioDecision")
```

## End-to-End Runtime Flow

```mermaid
sequenceDiagram
  autonumber
  participant O as Operator
  participant R as Flint Shadow Runner
  participant G as TradingAgentsGraph
  participant M as Memory Log
  participant CP as Optional Checkpointer
  participant W as LangGraph Workflow
  participant T as Data Tool Layer
  participant D as Data Vendors
  participant L as LLM Provider
  participant S as Output Store

  O->>R: ticker, trade_date, selected_analysts, provider/model overrides
  R->>R: load .env.flint-shadow and force output paths under output/
  R->>G: instantiate graph and call propagate()
  G->>M: load prior resolved lessons and same-ticker pending entries
  G->>D: fetch outcome returns for resolvable pending entries
  G->>L: reflect on resolved pending decisions when needed
  G->>CP: compile with per-ticker SQLite saver if --checkpoint
  G->>W: invoke initial AgentState
  loop For each selected analyst
    W->>L: ask analyst for report or tool calls
    W->>T: execute requested tools
    T->>D: fetch vendor data
    D-->>T: data payloads
    T-->>W: tool results
  end
  W->>L: bull/bear research debate
  W->>L: research manager investment plan
  W->>L: trader transaction proposal
  W->>L: aggressive/conservative/neutral risk debate
  W->>L: portfolio manager final decision
  W-->>G: final AgentState
  G->>S: write full state JSON
  G->>M: append pending decision entry
  G->>CP: clear checkpoint after successful completion
  G-->>R: final state and parsed rating
  R-->>O: JSON summary with decision, log path, and memory path
```

## Pipeline State Contract

The graph passes one `AgentState` through every node. The important fields are:

| Field | Producer | Consumer |
| --- | --- | --- |
| `company_of_interest`, `trade_date` | Propagator | All agents and tool prompts |
| `past_context` | Memory log lookup | Portfolio Manager prompt context |
| `market_report` | Market Analyst | Bull/Bear, Trader, Risk analysts |
| `sentiment_report` | Social Analyst | Bull/Bear, Trader, Risk analysts |
| `news_report` | News Analyst | Bull/Bear, Trader, Risk analysts |
| `fundamentals_report` | Fundamentals Analyst | Bull/Bear, Trader, Risk analysts |
| `investment_debate_state` | Bull/Bear, Research Manager | Research debate routing and Research Manager |
| `investment_plan` | Research Manager | Trader and Portfolio Manager |
| `trader_investment_plan` | Trader | Risk analysts and Portfolio Manager |
| `risk_debate_state` | Risk analysts, Portfolio Manager | Risk debate routing and Portfolio Manager |
| `final_trade_decision` | Portfolio Manager | State logger, memory log, signal parser |

## Agent And Tool Mapping

| Stage | Graph nodes | LLM tier | Tool surface | Output |
| --- | --- | --- | --- | --- |
| Market analysis | `Market Analyst`, `tools_market`, `Msg Clear Market` | quick | `get_stock_data`, `get_indicators` | `market_report` |
| Social analysis | `Social Analyst`, `tools_social`, `Msg Clear Social` | quick | `get_news` | `sentiment_report` |
| News analysis | `News Analyst`, `tools_news`, `Msg Clear News` | quick | `get_news`, `get_global_news`, `get_insider_transactions` | `news_report` |
| Fundamentals analysis | `Fundamentals Analyst`, `tools_fundamentals`, `Msg Clear Fundamentals` | quick | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` | `fundamentals_report` |
| Investment debate | `Bull Researcher`, `Bear Researcher` | quick | none | `investment_debate_state` |
| Investment synthesis | `Research Manager` | deep | none | `investment_plan` |
| Trade translation | `Trader` | quick | none | `trader_investment_plan` |
| Risk debate | `Aggressive Analyst`, `Conservative Analyst`, `Neutral Analyst` | quick | none | `risk_debate_state` |
| Final decision | `Portfolio Manager` | deep | none | `final_trade_decision` |
| Rating parse | `SignalProcessor` | deterministic parser | none | `Buy`, `Overweight`, `Hold`, `Underweight`, or `Sell` |

## Control Logic

```mermaid
flowchart TD
  Start([START]) --> A1[First selected analyst]
  A1 --> HasToolCalls{Last analyst message has tool calls?}
  HasToolCalls -->|yes| ToolNode[Matching tools_* ToolNode]
  ToolNode --> A1
  HasToolCalls -->|no| Clear[Msg Clear selected analyst]
  Clear --> MoreAnalysts{More selected analysts?}
  MoreAnalysts -->|yes| NextAnalyst[Next selected analyst]
  NextAnalyst --> HasToolCalls
  MoreAnalysts -->|no| Bull[Bull Researcher]
  Bull --> DebateDone{investment count >= 2 * max_debate_rounds?}
  DebateDone -->|no, bull spoke| Bear[Bear Researcher]
  DebateDone -->|no, bear spoke| Bull
  Bear --> DebateDone
  DebateDone -->|yes| RM[Research Manager]
  RM --> Trader[Trader]
  Trader --> Agg[Aggressive Analyst]
  Agg --> RiskDone{risk count >= 3 * max_risk_discuss_rounds?}
  RiskDone -->|no, aggressive spoke| Cons[Conservative Analyst]
  Cons --> RiskDone2{risk count >= 3 * max_risk_discuss_rounds?}
  RiskDone2 -->|no, conservative spoke| Neutral[Neutral Analyst]
  Neutral --> RiskDone3{risk count >= 3 * max_risk_discuss_rounds?}
  RiskDone3 -->|no, neutral spoke| Agg
  RiskDone -->|yes| PM[Portfolio Manager]
  RiskDone2 -->|yes| PM
  RiskDone3 -->|yes| PM
  PM --> End([END])
```

## Artifact Flow

```mermaid
flowchart LR
  Env[.env.flint-shadow] --> Config[Runtime config]
  Args[ticker/date/analysts/options] --> Config
  Config --> Logs[output/logs/<ticker>/TradingAgentsStrategy_logs/full_states_log_<date>.json]
  Config --> Cache[output/cache]
  Config --> Memory[output/memory/trading_memory.md]
  Config --> Checkpoints[output/cache/checkpoints/<TICKER>.db when checkpointed]
  Logs --> FlintIngest[Future Flint evidence ingestion]
  Memory --> NextRun[Next same-ticker or cross-ticker context]
  Cache --> NextRun
```

## Flint Shadow Boundary

- The wrapper pins `results_dir` to `output/logs`.
- The wrapper pins `data_cache_dir` to `output/cache`.
- The wrapper pins `memory_log_path` to `output/memory/trading_memory.md`.
- The wrapper only prints a JSON summary and writes local artifacts.
- The graph has no broker-order container in this repo-specific model.
- Flint ingestion is a downstream consumer, not a write target from this repo.

## C4InterFlow Model

A YAML Architecture-as-Code model for this schema is stored at:

- `Architecture/TradingAgentsFlintShadow.yaml`

The prepared render command is:

```bash
C4InterFlow.Cli draw-diagrams \
  --aac-input-paths "./Architecture" \
  --aac-reader-strategy "C4InterFlow.Automation.Readers.YamlAaCReaderStrategy,C4InterFlow.Automation" \
  --interfaces "TradingAgentsFlintShadow.SoftwareSystems.*.Containers.*.Components.*.Interfaces.*" \
  --interfaces "TradingAgentsFlintShadow.SoftwareSystems.*.Containers.*.Interfaces.*" \
  --types c4 c4-static c4-sequence sequence \
  --levels-of-details context container component \
  --formats svg png md \
  --output-dir "./diagrams/tradingagents-flint-shadow"
```

This command was prepared but not executed here because `C4InterFlow.Cli` is not
currently installed on PATH.

## Source Map

- `scripts/flint/run_shadow_analysis.py`: wrapper entrypoint, env loading, repo-local path overrides, graph invocation, JSON summary.
- `tradingagents/graph/trading_graph.py`: graph orchestration, LLM client setup, tool node setup, memory resolution, checkpointing, state logging, memory logging, rating parsing.
- `tradingagents/graph/setup.py`: LangGraph nodes and edges.
- `tradingagents/graph/conditional_logic.py`: analyst tool-loop routing, bull/bear debate loop, risk debate loop.
- `tradingagents/graph/propagation.py`: initial `AgentState` construction and graph invocation config.
- `tradingagents/agents/utils/agent_states.py`: canonical state fields.
- `tradingagents/agents/schemas.py`: structured `ResearchPlan`, `TraderProposal`, and `PortfolioDecision` schemas.
- `tradingagents/agents/utils/structured.py`: structured-output wrapper with free-text fallback.
- `tradingagents/dataflows/interface.py`: vendor routing and fallback.
- `tradingagents/agents/utils/memory.py`: append-only decision log and prior-context injection.
