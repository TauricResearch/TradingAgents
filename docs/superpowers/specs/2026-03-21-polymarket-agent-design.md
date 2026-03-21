# TradingAgents → Polymarket Prediction Agent Design

## Overview

Fork the TradingAgents multi-agent financial analysis framework to analyze Polymarket prediction markets. The system accepts any event category (politics, crypto, sports, economics, etc.), produces a structured YES/NO/SKIP recommendation with confidence and edge calculations, and outputs analysis reports.

**Phase 1**: Analysis and reporting only (human executes bets manually).
**Phase 2** (future): Automated betting via Relayer API.

## Approach

Incremental replacement (Approach A). Modify the existing codebase layer by layer:

1. Data layer (tool functions → Polymarket API)
2. Agent prompts (stock → prediction market context)
3. Output format (BUY/SELL/HOLD → YES/NO/SKIP + structured JSON)
4. CLI (ticker input → event URL/scan)

---

## 1. Data Layer

Replace `tradingagents/agents/utils/agent_utils.py` tool functions with Polymarket API calls.

### Tool Mapping

| Old Tool | New Tool | API Source | Description |
|---|---|---|---|
| `get_stock_data` | `get_market_data` | Gamma + CLOB | Event/market metadata, current price, spread, volume |
| `get_indicators` | `get_price_history` | CLOB `prices-history` | Price timeseries with self-computed trend indicators |
| `get_news` | `get_event_news` | Tavily API | Event keyword-based web search |
| `get_global_news` | `get_global_news` | Tavily API | Macro news (similar to existing) |
| `get_insider_transactions` | `get_whale_activity` | Data API `holders` + `trades` | Whale/smart money position changes |
| `get_fundamentals` | `get_event_details` | Gamma `events/{id}` | Resolution criteria, deadline, description, resolutionSource |
| `get_balance_sheet` | `get_orderbook` | CLOB `book` | Orderbook depth (bid/ask distribution) |
| `get_cashflow` | `get_market_stats` | Data API `openInterest` + Gamma | OI, volume trends, liquidity |
| `get_income_statement` | `get_leaderboard_signals` | Data API `leaderboard` | Top trader performance + market positions |

### New Tools

| Tool | API | Description |
|---|---|---|
| `get_social_sentiment` | X API / Reddit API | Social sentiment for event keywords |
| `search_markets` | Gamma `events` + filters | Auto-scan: discover events by volume, deadline, category |

### Data Flow

```
User input (event URL/ID or auto-scan)
    ↓
search_markets or URL parsing → event_id, token_ids extraction
    ↓
Each Analyst receives tool access for that event
```

### Multi-Market Events

Polymarket events can contain multiple markets (e.g., "Who will win?" has YES/NO tokens per candidate). Handling:
- Single-market events: Analyze directly.
- Multi-market events: CLI displays the list of markets within the event, user selects one specific market to analyze. Each market is a binary YES/NO outcome.

### Error Handling

Polymarket APIs (Gamma, CLOB, Data) can fail due to rate limits, downtime, or unexpected data.
- Retry with exponential backoff (max 3 retries) for transient failures.
- Timeout: 30s per API call.
- If a tool fails after retries, the analyst produces a partial report noting which data was unavailable.

---

## 2. Agent Structure

### Phase 1: 4 Analysts (Parallel)

| Agent | Tools | Output Field | Prompt Focus |
|---|---|---|---|
| **Odds Analyst** | `get_market_data`, `get_price_history`, `get_orderbook` | `odds_report` | Price trends, orderbook asymmetry, volume patterns, smart money direction |
| **News Analyst** | `get_event_news`, `get_global_news` | `news_report` | Latest event-related news, macro impact, timeline analysis |
| **Social Analyst** | `get_social_sentiment`, `get_whale_activity` | `sentiment_report` | Social opinion + whale/top trader position direction |
| **Event Analyst** | `get_event_details`, `get_market_stats`, `get_leaderboard_signals` | `event_report` | Resolution criteria interpretation, deadline, base probability estimation, similar event comparison |

### Phase 2: 3-Way Debate (Sequential)

Expanded from Bull/Bear 2-way to YES/NO/Timing 3-way debate.

| Agent | Role | Memory |
|---|---|---|
| **YES Advocate** | Argues for event occurrence. Based on existing Bull. | Yes |
| **NO Advocate** | Argues against event occurrence. Based on existing Bear. | Yes |
| **Timing Advocate** | "Might be right, but not now" — market timing / probability distortion perspective | Yes |
| **Research Manager** | Judges 3-way debate → `investment_plan` (YES/NO/SKIP + confidence) | Yes |

Debate flow:
```
YES → NO → Timing → YES → NO → Timing → ... → Judge
```

### Phase 3: Trader

Input: `investment_plan` + 4 analyst reports.
Output: `trader_plan` with YES/NO/SKIP + confidence + edge + position_size.

### Phase 4: Risk Debate (Existing structure retained)

Aggressive/Conservative/Neutral 3-way debate → Risk Manager judgment.
Prompts modified from stock to prediction market context only.

Final output: `final_decision` in JSON format.

---

## 3. AgentState Changes

```python
class InvestDebateState(TypedDict):
    yes_history: str           # was bull_history
    no_history: str            # was bear_history
    timing_history: str        # new
    history: str
    current_yes_response: str  # per-advocate responses (mirrors RiskDebateState)
    current_no_response: str
    current_timing_response: str
    latest_speaker: str        # new — mirrors RiskDebateState pattern
    judge_decision: str
    count: int

class RiskDebateState(TypedDict):
    # unchanged — Aggressive/Conservative/Neutral retained
    aggressive_history: str
    conservative_history: str
    neutral_history: str
    history: str
    latest_speaker: str
    current_aggressive_response: str
    current_conservative_response: str
    current_neutral_response: str
    judge_decision: str
    count: int

class AgentState(MessagesState):
    event_id: str              # was company_of_interest
    event_question: str        # new — "Will X happen?"
    trade_date: str
    sender: str
    odds_report: str           # was market_report
    sentiment_report: str      # retained
    news_report: str           # retained
    event_report: str          # was fundamentals_report
    investment_debate_state: InvestDebateState
    investment_plan: str
    trader_plan: str           # was trader_investment_plan
    risk_debate_state: RiskDebateState
    final_decision: str        # was final_trade_decision
```

---

## 4. Graph Workflow Changes

### setup.py — Node composition

```
Old: Market → Social → News → Fundamentals (parallel)
     → Bull ↔ Bear (2-way cycle) → Research Manager

New: Odds → Social → News → Event (parallel)
     → YES ↔ NO ↔ Timing (3-way cycle) → Research Manager
```

### conditional_logic.py — Debate routing

Mirrors the existing risk debate pattern using `latest_speaker` inspection (not count-modulo).
Rename analyst methods: `should_continue_market` → `should_continue_odds`, `should_continue_fundamentals` → `should_continue_event`.

```python
def should_continue_debate(self, state):  # method on ConditionalLogic class
    count = state["investment_debate_state"]["count"]
    if count >= 3 * self.max_debate_rounds:  # 3 speakers per round
        return "Research Manager"
    latest = state["investment_debate_state"].get("latest_speaker", "")
    if latest.startswith("YES"):
        return "NO Advocate"
    elif latest.startswith("NO"):
        return "Timing Advocate"
    else:  # Initial entry or after Timing → start with YES
        return "YES Advocate"
```

### setup.py — 3-Way debate edge definitions

Each debater node gets conditional edges to the next speaker or Research Manager:

```python
# Last analyst's Msg Clear → YES Advocate (was Bull Researcher)
graph.add_edge(f"{last_analyst}_clear", "YES Advocate")

# YES Advocate → {NO Advocate, Research Manager}
graph.add_conditional_edges("YES Advocate", should_continue_debate,
    {"NO Advocate": "NO Advocate", "Research Manager": "Research Manager"})

# NO Advocate → {Timing Advocate, Research Manager}
graph.add_conditional_edges("NO Advocate", should_continue_debate,
    {"Timing Advocate": "Timing Advocate", "Research Manager": "Research Manager"})

# Timing Advocate → {YES Advocate, Research Manager}
graph.add_conditional_edges("Timing Advocate", should_continue_debate,
    {"YES Advocate": "YES Advocate", "Research Manager": "Research Manager"})
```

### 3-Way advocate state preservation

Each advocate node reads all three histories but only writes its own. Pseudocode:

```python
# In YES Advocate node:
def yes_node(state):
    # Read: no_history, timing_history, yes_history (for context)
    # Write: yes_history (append), current_response, latest_speaker = "YES Advocate"
    # Preserve: no_history, timing_history unchanged

# Same pattern for NO and Timing advocates
```

### propagation.py — Initial state

- `company_name` parameter → `event_id` + `event_question`
- Report field names updated: `market_report` → `odds_report`, `fundamentals_report` → `event_report`
- `InvestDebateState` gains `timing_history: ""`, `latest_speaker: ""`
- `propagate()` signature: `propagate(self, event_id, event_question, trade_date)`

### signal_processing.py — Output parsing

Old: Extract `BUY/SELL/HOLD` from text.
New: Extract structured JSON using Pydantic validation:

```python
from pydantic import BaseModel

class PredictionDecision(BaseModel):
    action: Literal["YES", "NO", "SKIP"]
    confidence: float    # 0.0 ~ 1.0
    edge: float          # estimated probability - market price
    position_size: float # recommended bet size
    reasoning: str
    time_horizon: str
```

Use `llm.with_structured_output(PredictionDecision)` where supported, fallback to JSON extraction + Pydantic parse.

### trading_graph.py — Memory/tool initialization

- `bull_memory` → `yes_memory`, `bear_memory` → `no_memory`, new `timing_memory`
- `_create_tool_nodes()` maps to new Polymarket tools
- `GraphSetup.__init__` signature updated to accept `timing_memory`
- `propagate()` updated: signature, field name references (`final_decision` not `final_trade_decision`)
- `_log_state()` updated: all field names changed (`odds_report`, `event_report`, `yes_history`, `no_history`, `timing_history`, `trader_plan`, `final_decision`)
- `reflect_and_remember()` updated: calls `reflect_yes_advocate`, `reflect_no_advocate`, `reflect_timing_advocate`

### reflection.py

- Rename methods: `reflect_bull_researcher` → `reflect_yes_advocate`, `reflect_bear_researcher` → `reflect_no_advocate`
- Add: `reflect_timing_advocate` (same pattern, new `timing_memory`)
- Update `_extract_current_situation`: `market_report` → `odds_report`, `fundamentals_report` → `event_report`

### agents/__init__.py

Update exports: remove `create_bull_researcher`, `create_bear_researcher`. Add `create_yes_advocate`, `create_no_advocate`, `create_timing_advocate`. Rename `create_market_analyst` → `create_odds_analyst`, `create_fundamentals_analyst` → `create_event_analyst`.

---

## 5. CLI Changes

### Input Flow

```
Old: Ticker → Date → Analysts → Depth → Provider → Model
New: Mode → Event → Analysts → Depth → Provider → Model
```

**Step 1: Mode Selection**
- `Manual` — Enter event URL or ID directly
- `Scan` — Auto-discover by filters (category, min volume, deadline, etc.)

**Step 2: Event Specification**
- Manual: Parse URL (`polymarket.com/event/xxx` → event_id) or direct ID input
- Scan: Call `search_markets` → select from result list

**Steps 3-6**: Same flow, but analyst keys change: `market` → `odds`, `fundamentals` → `event`. CLI constants updated:
- `ANALYST_MAPPING`: `{"odds": "Odds Analyst", "social": "Social Analyst", "news": "News Analyst", "event": "Event Analyst"}`
- `REPORT_SECTIONS`: `odds_report`, `event_report` etc.
- `ANALYST_ORDER`: `["odds", "social", "news", "event"]`

### Output Display

- `MessageBuffer` agent names and report sections updated to new names
- `FIXED_AGENTS`: Research Team adds `"Timing Advocate"` → `["YES Advocate", "NO Advocate", "Timing Advocate", "Research Manager"]`
- `REPORT_SECTIONS` field names: `odds_report`, `event_report`, `trader_plan`, `final_decision`
- Final result: Structured JSON decision + reports

### Report Saving

```
reports/{event_id}_{timestamp}/
├── 1_analysts/
│   ├── odds.md
│   ├── sentiment.md
│   ├── news.md
│   └── event.md
├── 2_research/
│   ├── yes_advocate.md
│   ├── no_advocate.md
│   ├── timing_advocate.md
│   └── manager.md
├── 3_trading/
│   └── trader.md
├── 4_risk/
│   ├── aggressive.md
│   ├── conservative.md
│   └── neutral.md
├── 5_risk_manager/
│   └── decision.json
└── complete_report.md
```

---

## 6. Configuration & Dependencies

### default_config.py

```python
DEFAULT_CONFIG = {
    # Retained
    "llm_provider": "openrouter",
    "deep_think_llm": "z-ai/glm-4.5-air:free",
    "quick_think_llm": "nvidia/nemotron-3-nano-30b-a3b:free",
    "max_debate_rounds": 1,        # 1 round = 3 turns in 3-way debate
    "max_risk_discuss_rounds": 1,

    # New
    "tavily_api_key": None,         # loaded from TAVILY_API_KEY env
    "twitter_bearer_token": None,   # loaded from env
    "reddit_client_id": None,       # loaded from env
    "polymarket_relayer_key": None, # Phase 2 auto-betting (unused in Phase 1)

    # Auto-scan defaults
    "scan_defaults": {
        "min_volume_24h": 10000,
        "min_liquidity": 5000,
        "max_days_to_end": 30,
        "categories": [],           # empty = all
    },
}
```

### .env Additions

```
TAVILY_API_KEY=...
TWITTER_BEARER_TOKEN=...      # optional
REDDIT_CLIENT_ID=...          # optional
REDDIT_CLIENT_SECRET=...      # optional
```

### New Dependencies (requirements.txt)

```
py-clob-client          # Polymarket CLOB API client
tavily-python           # Web search
tweepy                  # X API (optional)
praw                    # Reddit API (optional)
```

Social APIs (tweepy, praw) gracefully skip when keys are absent — the corresponding analyst produces a "no social data available" report instead.

---

## 7. Reflection & Memory (Phase 1)

In Phase 1 (analysis only, no bet execution), there are no realized returns to learn from. `reflect_and_remember` is **disabled** in Phase 1. Memory will be seeded when Phase 2 (auto-betting) provides actual outcomes to reflect on. Alternatively, a post-resolution accuracy check can be added as a Phase 1.5 enhancement: after an event resolves, compare the agent's prediction against the outcome and store reflections.

---

## Non-Goals (Phase 1)

- Automated bet execution (Phase 2)
- Backtesting framework
- Multi-event portfolio optimization
- Real-time WebSocket streaming (batch analysis only)
