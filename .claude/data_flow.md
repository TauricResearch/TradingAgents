# TradingAgents — Memory Data Flow

Traces the full path from user input at the CLI to context retrieval and memory insertion.

---

## Overview

```
User Input (CLI)
      │
      ▼
TradingAgentsGraph.propagate()
      │
      ├──► Analyst Team (parallel nodes)
      │         │  calls external APIs, builds reports
      │         ▼
      │    AgentState: market_report, sentiment_report,
      │                news_report, fundamentals_report
      │
      ├──► Researcher Team (Bull / Bear loop)
      │         │  1. READ memory  ← FinancialSituationMemory.get_memories()
      │         │  2. invoke LLM with memories injected into prompt
      │         ▼
      │    InvestDebateState: bull_history, bear_history, judge_decision
      │
      ├──► Trader
      │         │  1. READ memory  ← FinancialSituationMemory.get_memories()
      │         │  2. invoke LLM
      │         ▼
      │    trader_investment_plan
      │
      ├──► Risk Management (Aggressive / Conservative / Neutral loop)
      │         │  pure LLM, no memory read
      │         ▼
      │    RiskDebateState
      │
      └──► Portfolio Manager
                │  1. READ memory  ← FinancialSituationMemory.get_memories()
                │  2. invoke LLM
                ▼
           final_trade_decision
                │
                ▼
      [optional] TradingAgentsGraph.reflect_and_remember()
                │  WRITE memory  ← FinancialSituationMemory.add_situations()
                ▼
           Memory updated for next run
```

---

## Step-by-Step Detail

### 1. User Input — CLI (`cli/main.py`)

The user provides:
- **Ticker symbol** (e.g., `NVDA`)
- **Trade date** (e.g., `2026-01-15`)
- **LLM provider / models**
- **Selected analysts** (market, social, news, fundamentals)
- **Research depth** (controls `max_debate_rounds`, `max_risk_discuss_rounds`)

These are collected interactively via `typer` and passed to:

```python
ta = TradingAgentsGraph(selected_analysts=[...], config=config)
final_state, decision = ta.propagate(ticker, trade_date)
```

---

### 2. Graph Initialisation — `TradingAgentsGraph.__init__()` (`tradingagents/graph/trading_graph.py`)

Five `FinancialSituationMemory` instances are created — one per agent role:

| Variable | Owner agent |
|---|---|
| `bull_memory` | Bull Researcher |
| `bear_memory` | Bear Researcher |
| `trader_memory` | Trader |
| `invest_judge_memory` | Research Manager |
| `portfolio_manager_memory` | Portfolio Manager |

Each instance holds two parallel Python lists (`documents`, `recommendations`) and a `BM25Okapi` index built over those lists. All data is **in-memory only** — nothing is persisted to disk.

---

### 3. Initial State — `Propagator.create_initial_state()` (`tradingagents/graph/propagation.py`)

```python
{
    "messages": [("human", ticker)],
    "company_of_interest": ticker,
    "trade_date": trade_date,
    "market_report": "",
    "sentiment_report": "",
    "news_report": "",
    "fundamentals_report": "",
    "investment_debate_state": { bull_history, bear_history, history, count, ... },
    "risk_debate_state":       { aggressive_history, conservative_history, ... },
}
```

This `AgentState` object flows through the LangGraph state machine.

---

### 4. Analyst Team — no memory interaction

Each analyst node (`market`, `social`, `news`, `fundamentals`) runs sequentially:

```
Market Analyst
  └─► tools_market  (get_stock_data, get_indicators, get_fibonacci_retracement)
        └─► external API (Binance / Alpha Vantage)
              └─► writes AgentState["market_report"]
  └─► Msg Clear Market  (drops messages from state to free context)

Social Analyst → sentiment_report
News Analyst   → news_report
Fundamentals   → fundamentals_report
```

After all analysts finish, `AgentState` carries four populated report strings. These are the **raw context** that memory will be queried against in the next phase.

---

### 5. Memory READ — Researcher Team (`tradingagents/agents/researchers/bull_researcher.py`)

This is the first point where memory is consumed:

```python
# Build a composite situation string from all four analyst reports
curr_situation = (
    f"{market_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
)

# Query BM25 index for the top-2 most similar past situations
past_memories = memory.get_memories(curr_situation, n_matches=2)
```

**Inside `FinancialSituationMemory.get_memories()`** (`tradingagents/agents/utils/memory.py`):

```
query_tokens = tokenize(curr_situation)          # lowercase, split on non-alphanum
scores       = bm25.get_scores(query_tokens)     # BM25Okapi score per stored document
top_indices  = argsort(scores, descending)[:n]   # pick top-n
return [{ matched_situation, recommendation, similarity_score }, ...]
```

The returned `recommendation` strings are concatenated and injected verbatim into the LLM prompt:

```
Reflections from similar situations and lessons learned: {past_memory_str}
```

The same READ pattern repeats for:
- **Bear Researcher** — queries `bear_memory`
- **Trader** — queries `trader_memory`
- **Research Manager** — queries `invest_judge_memory`
- **Portfolio Manager** — queries `portfolio_manager_memory`

---

### 6. LLM Invocation — per agent

With past memories injected, the agent calls the LLM:

```
prompt (system + analyst reports + debate history + past memories)
      │
      ▼
LLM (claude-opus-4-6 or claude-sonnet-4-6)
      │
      ▼
agent response → written back to AgentState
```

Debate agents (Bull ↔ Bear, Aggressive ↔ Conservative ↔ Neutral) loop until
`count >= max_debate_rounds` / `max_risk_discuss_rounds`.

---

### 7. Final State Returned — `propagate()` returns

```python
return final_state, process_signal(final_state["final_trade_decision"])
```

`final_state` contains all four analyst reports, full debate histories, and the
final trade decision. It is also serialised to
`eval_results/<ticker>/TradingAgentsStrategy_logs/full_states_log_<date>.json`.

---

### 8. Memory WRITE — `reflect_and_remember()` (optional, caller-triggered)

The CLI does **not** call this automatically. The caller must explicitly invoke:

```python
ta.reflect_and_remember(returns_losses=+0.05)  # e.g., after observing actual P&L
```

**Inside `Reflector._reflect_on_component()`** (`tradingagents/graph/reflection.py`):

```
messages = [
    ("system", reflection_system_prompt),
    ("human", f"Returns: {returns_losses}\n\nAnalysis: {report}\n\nMarket Reports: {situation}"),
]
reflection_text = llm.invoke(messages).content   # LLM generates lesson summary
```

**Then written to memory:**

```python
memory.add_situations([(curr_situation, reflection_text)])
```

**Inside `FinancialSituationMemory.add_situations()`**:

```
documents.append(situation)           # raw situation string (4 analyst reports)
recommendations.append(reflection)   # LLM-generated lesson
_rebuild_index()                      # BM25Okapi rebuilt from scratch over all docs
```

This runs once per agent role per call to `reflect_and_remember()`:

| Call | Memory written |
|---|---|
| `reflect_bull_researcher()` | `bull_memory` |
| `reflect_bear_researcher()` | `bear_memory` |
| `reflect_trader()` | `trader_memory` |
| `reflect_invest_judge()` | `invest_judge_memory` |
| `reflect_portfolio_manager()` | `portfolio_manager_memory` |

---

## Data Flow Summary Table

| Phase | Operation | File | Memory involved |
|---|---|---|---|
| CLI input | user provides ticker + date | `cli/main.py` | — |
| Graph init | 5 memory objects created (empty) | `graph/trading_graph.py` | all 5 |
| Analyst nodes | fetch external data, build reports | `agents/analysts/*.py` | none |
| Bull/Bear researcher | **READ** past memories via BM25 | `agents/researchers/*.py` | `bull_memory`, `bear_memory` |
| Research Manager | **READ** past memories via BM25 | `agents/managers/research_manager.py` | `invest_judge_memory` |
| Trader | **READ** past memories via BM25 | `agents/trader/trader.py` | `trader_memory` |
| Portfolio Manager | **READ** past memories via BM25 | `agents/managers/portfolio_manager.py` | `portfolio_manager_memory` |
| reflect_and_remember | **WRITE** LLM reflection into memory | `graph/reflection.py` | all 5 |

---

## Current Limitations

| Limitation | Detail |
|---|---|
| No size cap | `documents` list grows unboundedly — RAM grows with each reflection |
| No persistence | All 5 memory objects are recreated empty on every process start |
| BM25 rebuilt on every write | `_rebuild_index()` is O(n·len) on each `add_situations()` call |
| No deduplication | Identical or near-identical situations accumulate duplicate entries |
| Documents are large | Each key is 4 full analyst reports concatenated (~thousands of tokens) |

---

## Proposed Fix (Option C — cap + persist)

Add `max_documents: int` and a `storage_path: Path` to `FinancialSituationMemory`:

```
FinancialSituationMemory.__init__()
  └─► load from <memory_dir>/<name>.json   ← restore across runs

add_situations()
  ├─► if len(documents) >= max_documents: pop oldest (FIFO)
  ├─► append new document + recommendation
  ├─► _rebuild_index()
  └─► save to <memory_dir>/<name>.json     ← persist immediately

get_memories()
  └─► unchanged (BM25 query)
```

Storage path wires into `config["results_dir"]` or a new `config["memory_dir"]` key.
