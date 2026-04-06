# RFC: Auto-Research Loop for Intraday Prediction

> **Status:** Draft — seeking feedback
> **Scope:** Additive module (no changes to existing files)
> **Related:** [ARCHITECTURE_OVERVIEW.md](./ARCHITECTURE_OVERVIEW.md)

## TL;DR

Add a `tradingagents/autoresearch/` module that runs walk-forward backtesting
on the existing `TradingAgentsGraph`, using the existing `reflect_and_remember()`
memory system to iteratively improve intraday predictions. No existing files
are modified.

## The Core Idea

Apply Andrew Karpathy-style iterative research methodology to the existing TradingAgents architecture:

> **Take historical data → Predict next day → Check if right → Learn from mistakes → Predict again → Repeat**

This is essentially **walk-forward backtesting with self-improvement** — a proven concept in quantitative finance, now powered by LLM agents instead of traditional ML models.

---

## Design Tradeoffs

### Strengths of this approach

| Aspect | Why it works |
|---|---|
| **We already have the agents** | TradingAgents already does single-day analysis. We're just running it repeatedly |
| **We already have the data pipeline** | yfinance gives us free historical data — no new APIs needed |
| **Walk-forward is proven** | This is how quant funds actually test strategies |
| **Memory system exists** | `reflect_and_remember()` already learns from past trades |
| **Iterative learning** | Each wrong prediction improves the next one via memory |

### Risks requiring careful design

| Risk | Mitigation |
|---|---|
| **LLM API costs** | Each day = ~12 agent calls with LLM. 30 days = 360+ LLM calls. Reuse existing `quick_think_llm` (currently `gpt-5.4-mini` in `default_config.py`) for cheap agents; only use `deep_think_llm` where reasoning depth is required |
| **Overfitting to past data** | Don't tune prompts to specific dates — tune the APPROACH (which tools matter, what indicators to prioritize) |
| **Look-ahead bias** | When predicting day 11, the agents must ONLY see data up to day 10. Never leak future data |
| **Rate limits** | yfinance and Alpha Vantage have limits. Add delays between runs |
| **What "change everything" means** | Don't change model weights (we can't). Change: which analysts to use, debate rounds, indicator selection, prompt emphasis |

### Key design decision: no same-day retries

**Alternative considered:** If a prediction is wrong, retry the same day with a different approach.

**Rejected because:** Retrying the same day with knowledge of the actual outcome introduces look-ahead bias, which invalidates backtesting results.

**Recommended approach:** Move forward only — let memory accumulate lessons naturally.
1. Predict day 11 → Wrong → **Reflect and store lesson in memory**
2. Move to day 12 with the lesson learned
3. The memory system naturally improves future predictions
4. After all 30 days, analyze WHICH types of predictions failed and WHY

Rationale:
- Retrying the same day with knowledge of the answer is look-ahead bias
- The existing memory system already handles "learning from mistakes"
- The approach (not individual predictions) is what should be tuned

---

## How It Maps to Existing Architecture

```mermaid
%%{init: {'flowchart': {'nodeSpacing': 80, 'rankSpacing': 100}}}%%
flowchart TD
    subgraph EXISTING["What TradingAgents Already Does (Single Day)"]
        E1["propagate('NVDA', '2024-05-10')"]
        E2["4 Analysts gather data"]
        E3["Bull vs Bear debate"]
        E4["Trader + Risk debate"]
        E5["Final: BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL"]
        E1 --> E2 --> E3 --> E4 --> E5
    end

    subgraph NEW["What We're Adding (Auto-Research Loop)"]
        N1["train.py<br/>Run propagate() for each day in sequence"]
        N2["evaluation.py<br/>Compare prediction vs actual next-day price"]
        N3["reflect_and_remember()<br/>Store lessons when wrong"]
        N4["model_harness.py<br/>Manage the loop, configs, and results"]
        N5["prompt.py<br/>Define what we're looking for"]
        N1 --> N2 --> N3 --> N4
        N4 -->|"Next day"| N1
        N5 --> N1
    end

    EXISTING -.->|"We call this repeatedly"| NEW

    style EXISTING fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#01579b
    style NEW fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100
```

---

## Time Horizon Configuration

```mermaid
%%{init: {'flowchart': {'nodeSpacing': 80, 'rankSpacing': 120}}}%%
flowchart TD
    USER["User selects time horizon"]

    USER -->|"1 day"| D1["Predict: Tomorrow<br/>Training data: Last 1 month (30 days)<br/>Evaluation: Compare with actual tomorrow"]

    USER -->|"1 week"| D2["Predict: Next 5 trading days<br/>Training data: Last 3 months (60 days)<br/>Evaluation: Compare each day"]

    USER -->|"1 month"| D3["Predict: Next 20 trading days<br/>Training data: Last 6 months (120 days)<br/>Evaluation: Compare each day"]

    subgraph LOGIC["How Training Window Works"]
        L1["Take training window of historical data"]
        L2["Split: first (N - test_window) days = context<br/>last test_window days = walk-forward test<br/>(test_window is configurable;<br/>default ~20% of N, min 5 days)"]
        L3["Predict day by day through test window"]
        L4["After test: use full window to predict FUTURE"]
    end

    D1 --> LOGIC
    D2 --> LOGIC
    D3 --> LOGIC

    %% Improved styles
    style D1 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    style D2 fill:#fff9c4,stroke:#f9a825,stroke-width:2px,color:#f57f17
    style D3 fill:#ffccbc,stroke:#d84315,stroke-width:2px,color:#bf360c
```

---

## Complete Auto-Research Pipeline

```mermaid
%%{init: {'flowchart': {'nodeSpacing': 80, 'rankSpacing': 120}}}%%
flowchart TD
    subgraph SETUP["Phase 1: Setup"]
        S1["User inputs:<br/>- Ticker (e.g., NVDA)<br/>- Time horizon (1 day / 1 week / 1 month)<br/>- Start date"]
        S2["prompt.py<br/>Define analysis focus:<br/>- What indicators matter?<br/>- What news to prioritize?<br/>- Risk tolerance?"]
        S3["model_harness.py<br/>Load config + initialize TradingAgentsGraph"]
        S1 --> S3
        S2 --> S3
    end

    subgraph TRAIN["Phase 2: Walk-Forward Training (train.py)"]
        T1["Load training window<br/>(e.g., 30 days for 1-day horizon)"]
        T2["Day 1-20: Historical context<br/>(agents can see this data)"]
        T3["Day 21: First prediction target"]

        T4["Run propagate(ticker, day_20)<br/>Get prediction for day 21"]
        T5["evaluation.py:<br/>Compare prediction vs actual day 21"]

        T6{"Prediction<br/>correct?"}
        T7["reflect_and_remember(positive_return)<br/>Store: what worked"]
        T8["reflect_and_remember(negative_return)<br/>Store: what went wrong + why"]

        T9["Slide window: Add day 21 to context<br/>Now predict day 22"]

        T1 --> T2 --> T3 --> T4 --> T5 --> T6
        T6 -->|"Yes"| T7
        T6 -->|"No"| T8
        T7 --> T9
        T8 --> T9
        T9 -->|"Repeat for days 22-30"| T4
    end

    subgraph EVAL["Phase 3: Evaluation Summary (evaluation.py)"]
        EV1["Accuracy: X/10 days predicted correctly"]
        EV2["Direction accuracy: Did we get UP/DOWN right?"]
        EV3["Magnitude: How close was the prediction?"]
        EV4["Best/worst performing indicators"]
        EV5["Save results to Excel/CSV"]
    end

    subgraph PREDICT["Phase 4: Future Prediction"]
        P1["Use full 30-day window + learned memories"]
        P2["Predict next 10-30 days (based on horizon)"]
        P3["Save predictions to Excel"]
    end

    subgraph VIZ["Phase 5: Visualization"]
        V1["Left chart: Actual price history"]
        V2["Right chart: Predicted prices"]
        V3["Overlay: Where predictions matched/diverged"]
        V4["Metrics dashboard: accuracy, returns, etc."]
    end

    S3 --> T1
    T9 -->|"After all training days"| EV1
    EV1 --> EV2 --> EV3 --> EV4 --> EV5
    EV5 --> P1 --> P2 --> P3
    P3 --> V1
    V1 --> V2 --> V3 --> V4

    %% FIXED STYLES (dark text + stronger borders)
    style SETUP fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#01579b
    style TRAIN fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100
    style EVAL fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    style PREDICT fill:#fce4ec,stroke:#c2185b,stroke-width:2px,color:#880e4f
    style VIZ fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px,color:#4a148c
```

---

## File Structure for the PR

```mermaid
%%{init: {
  'themeVariables': { 
    'fontSize': '20px',
    'fontFamily': 'Arial',
    'lineColor': '#ffffff'
  },
  'flowchart': { 
    'nodeSpacing': 80, 
    'rankSpacing': 120 
  }
}}%%
flowchart TD

    subgraph NEW_FILES["New Files We'll Add"]
        direction TB
        PR["tradingagents/autoresearch/"]
        PR --> TRAIN_PY["train.py<br/>Walk-forward training loop"]
        PR --> EVAL_PY["evaluation.py<br/>Compare predictions vs actual"]
        PR --> MODEL_PY["model.py<br/>Wrapper around TradingAgentsGraph<br/>for batch prediction"]
        PR --> HARNESS["model_harness.py<br/>Orchestrates the full pipeline:<br/>setup → train → eval → predict → viz"]
        PR --> PROMPT_PY["prompt.py<br/>Configurable analysis prompts<br/>and research focus areas"]
        PR --> VIZ_PY["visualization.py<br/>Side-by-side charts<br/>(actual vs predicted)"]
    end

    OUTPUTS_NOTE["All generated artifacts (Excel, CSV, charts)<br/>are written to config['results_dir']<br/>from default_config.py — NOT committed<br/>inside the source package"]
    HARNESS -.->|"writes outputs to"| OUTPUTS_NOTE

    subgraph EXISTING_USED["Existing Files We Use (Don't Modify)"]
        EX1["tradingagents/graph/trading_graph.py<br/>TradingAgentsGraph class"]
        EX2["tradingagents/graph/reflection.py<br/>reflect_and_remember()"]
        EX3["tradingagents/agents/utils/memory.py<br/>FinancialSituationMemory"]
        EX4["tradingagents/dataflows/interface.py<br/>Data routing"]
        EX5["tradingagents/default_config.py<br/>Configuration"]
    end

    HARNESS -->|"calls"| EX1
    EVAL_PY -->|"triggers"| EX2
    EX2 -->|"stores in"| EX3
    MODEL_PY -->|"uses"| EX4
    HARNESS -->|"extends"| EX5

    %% FIXED styles (contrast + borders)
    style NEW_FILES fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    style EXISTING_USED fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#01579b
```

---

## Detailed: train.py Logic

```mermaid
flowchart TD
    START["train(ticker, horizon, start_date)"]

    WINDOW["Calculate training window<br/>1 day → 30 days lookback<br/>1 week → 90 days lookback<br/>1 month → 180 days lookback"]

    FETCH["Fetch full historical data<br/>yfinance: get_stock_data(ticker, start, end)"]

    SPLIT["Split data (configurable test_window):<br/>context_days = window[:-test_window]<br/>test_days = window[-test_window:]<br/>Default: test_window = max(5, int(0.2 * N))"]

    INIT["Initialize TradingAgentsGraph<br/>with fresh memories"]

    subgraph LOOP["Walk-Forward Loop (for each test day)"]
        DAY_N["Current test day = day[i]"]
        PROPAGATE["ta.propagate(ticker, day[i-1])<br/>Predict what happens on day[i]"]
        GET_ACTUAL["Get actual price on day[i]<br/>from historical data"]
        COMPARE["evaluation.compare(<br/>  predicted=decision,<br/>  actual=price_change<br/>)"]
        CORRECT{"Direction<br/>correct?"}
        POSITIVE["ta.reflect_and_remember(+return)<br/>Memory: 'This approach worked<br/>when indicators showed X'"]
        NEGATIVE["ta.reflect_and_remember(-return)<br/>Memory: 'This approach failed<br/>when conditions were Y'"]
        LOG["Log result to results list:<br/>{date, predicted, actual, correct, return}"]
        NEXT["i += 1"]

        DAY_N --> PROPAGATE --> GET_ACTUAL --> COMPARE --> CORRECT
        CORRECT -->|"Yes"| POSITIVE --> LOG
        CORRECT -->|"No"| NEGATIVE --> LOG
        LOG --> NEXT
        NEXT -->|"More days?"| DAY_N
    end

    RETURN["Return results list + trained memory"]

    START --> WINDOW --> FETCH --> SPLIT --> INIT --> LOOP
    NEXT -->|"Done"| RETURN

    style LOOP fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100
```

---

## Detailed: evaluation.py Logic

```mermaid
flowchart TD
    INPUT["Input: list of<br/>{date, predicted, actual, correct, return}"]

    subgraph METRICS["Calculated Metrics"]
        M1["Direction Accuracy<br/>% of days where UP/DOWN was correct"]
        M2["Signal Distribution<br/>How many BUY vs HOLD vs SELL"]
        M3["Cumulative Return<br/>If you followed every signal"]
        M4["Max Drawdown<br/>Worst losing streak"]
        M5["Win Rate by Signal Type<br/>BUY accuracy vs SELL accuracy"]
        M6["Best/Worst Days<br/>Biggest wins and losses"]
    end

    subgraph OUTPUT["Output Files (written to config['results_dir'])"]
        O1["{results_dir}/training_log.xlsx<br/>Every prediction with details"]
        O2["{results_dir}/metrics_summary.xlsx<br/>All metrics in one sheet"]
        O3["{results_dir}/memory_dump.json<br/>What the agents learned"]
    end

    INPUT --> METRICS
    METRICS --> OUTPUT

    style METRICS fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    style OUTPUT fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#01579b
```

---

## Detailed: visualization.py Layout

```mermaid
flowchart LR
    subgraph LEFT["Left Panel: Actual Data"]
        L1["Stock price line chart"]
        L2["Volume bars below"]
        L3["Key indicators overlay<br/>(SMA 50, SMA 200, RSI)"]
        L4["Green/Red markers:<br/>Days where agents were right/wrong"]
    end

    subgraph RIGHT["Right Panel: Predicted"]
        R1["Agent's predicted direction<br/>per day (arrows up/down)"]
        R2["Confidence level<br/>(BUY=high, OVERWEIGHT=medium, etc.)"]
        R3["Decision breakdown:<br/>Which agents agreed/disagreed"]
    end

    subgraph BOTTOM["Bottom Panel: Comparison"]
        B1["Overlay: actual vs predicted direction"]
        B2["Running accuracy score"]
        B3["Memory growth chart:<br/>How many lessons stored over time"]
    end

    style LEFT fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    style RIGHT fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100
    style BOTTOM fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#01579b
```

---

## Detailed: model_harness.py (The Orchestrator)

```mermaid
flowchart TD
    subgraph CLI["User Interface"]
        U1["python model_harness.py<br/>  --ticker NVDA<br/>  --horizon 1day<br/>  --start-date 2024-01-01"]
    end

    subgraph HARNESS["model_harness.py Pipeline"]
        H1["Parse arguments"]
        H2["Load/extend config from default_config.py"]
        H3["Initialize TradingAgentsGraph"]

        H4["Phase 1: TRAIN<br/>train.run_walk_forward()"]
        H5["Phase 2: EVALUATE<br/>evaluation.generate_report()"]
        H6["Phase 3: PREDICT<br/>model.predict_future()"]
        H7["Phase 4: VISUALIZE<br/>visualization.create_dashboard()"]

        H8["Save all results to config['results_dir']"]

        H1 --> H2 --> H3 --> H4 --> H5 --> H6 --> H7 --> H8
    end

    subgraph CONFIG_OPTIONS["Configurable via prompt.py"]
        C1["analysis_focus: 'intraday momentum'"]
        C2["priority_indicators: ['RSI', 'MACD', 'VWAP']"]
        C3["news_weight: 'high' or 'low'"]
        C4["debate_rounds: 1-3"]
        C5["risk_tolerance: 'aggressive' / 'moderate' / 'conservative'"]
    end

    CLI --> HARNESS
    CONFIG_OPTIONS --> H2

    style CLI fill:#f3e5f5
    style HARNESS fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#01579b
    style CONFIG_OPTIONS fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100
```

---

## How prompt.py Works

```mermaid
%%{init: {
  'themeVariables': { 'fontSize': '18px' },
  'flowchart': { 'nodeSpacing': 100, 'rankSpacing': 140 }
}}%%
flowchart TD
    subgraph PROMPT["prompt.py - Research Focus Configuration"]
        P1["RESEARCH_FOCUS = {<br/>  'mode': 'intraday',<br/>  'timeframe': '1day',<br/>  'focus_areas': [<br/>    'momentum indicators',<br/>    'volume analysis',<br/>    'news catalysts'<br/>  ],<br/>  'avoid': [<br/>    'long-term fundamentals',<br/>    'quarterly earnings'<br/>  ]<br/>}"]

        P2["This gets injected into the<br/>system prompts of each analyst"]
    end

    subgraph EFFECT["How It Changes Agent Behavior"]
        E1["Market Analyst<br/>→ Prioritizes RSI, MACD, VWAP<br/>→ Focuses on intraday patterns"]
        E2["News Analyst<br/>→ Looks for same-day catalysts<br/>→ Ignores long-term trends"]
        E3["Bull/Bear Researchers<br/>→ Debate short-term momentum<br/>→ Not long-term value"]
    end

    P1 --> P2 --> E1
    P2 --> E2
    P2 --> E3

    style PROMPT fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100
    style EFFECT fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
```

---

## Walk-Forward Example: 1-Day Horizon with NVDA

```mermaid
gantt
    title Walk-Forward Training: NVDA 1-Day Prediction
    dateFormat YYYY-MM-DD

    section Context Window
    Historical data (agents can see)     :done, ctx, 2024-04-01, 20d

    section Test Window (predict one at a time)
    Day 21 - Predict (first test)        :active, d21, 2024-04-21, 1d
    Day 22 - Predict                     :d22, 2024-04-22, 1d
    Day 23 - Predict                     :d23, 2024-04-23, 1d
    Day 24 - Predict                     :d24, 2024-04-24, 1d
    Day 25 - Predict                     :d25, 2024-04-25, 1d
    Day 26 - Predict                     :d26, 2024-04-28, 1d
    Day 27 - Predict                     :d27, 2024-04-29, 1d
    Day 28 - Predict                     :d28, 2024-04-30, 1d
    Day 29 - Predict                     :d29, 2024-05-01, 1d
    Day 30 - Predict (last test)         :crit, d30, 2024-05-02, 1d

    section After Training
    Predict FUTURE days                  :milestone, future, 2024-05-03, 0d
```

**Step-by-step for Day 21:**
1. Agents see data from Apr 1-20 only
2. `ta.propagate("NVDA", "2024-04-20")` → Predicts direction for Apr 21
3. Check actual Apr 21 price: Was prediction right?
4. `ta.reflect_and_remember(actual_return)` → Store lesson
5. Now agents see Apr 1-21 → Predict Apr 22
6. Repeat...

---

## What "Adjusting the Approach" Actually Means

When a prediction is wrong, here's what safely adjusts vs. what must remain fixed:

```mermaid
%%{init: {
  'themeVariables': { 'fontSize': '18px' },
  'flowchart': { 'nodeSpacing': 100, 'rankSpacing': 140 }
}}%%
flowchart TD
    WRONG["Prediction was WRONG"]

    subgraph AUTO_CHANGES["Automatic (via reflect_and_remember)"]
        A1["Memory updated:<br/>'When RSI was 72 and we said BUY,<br/>the stock actually dropped 3%.<br/>Next time: consider overbought signal.'"]
        A2["Next prediction naturally<br/>considers this lesson via<br/>BM25 memory retrieval"]
    end

    subgraph AFTER_TRAINING["After full training run (manual analysis)"]
        B1["Check: Which analyst was most wrong?<br/>→ Maybe disable social analyst for this stock"]
        B2["Check: Which indicators helped most?<br/>→ Update prompt.py focus_areas"]
        B3["Check: Were debate rounds enough?<br/>→ Increase max_debate_rounds"]
        B4["Check: Was risk assessment accurate?<br/>→ Adjust risk_tolerance in config"]
    end

    subgraph NEVER_CHANGE["What We DON'T Change"]
        N1["Don't retry the same day<br/>(look-ahead bias = cheating)"]
        N2["Don't modify the model weights<br/>(LLMs don't work that way)"]
        N3["Don't change data source mid-run<br/>(inconsistent comparison)"]
    end

    WRONG --> AUTO_CHANGES
    WRONG --> AFTER_TRAINING
    WRONG -.->|"AVOID"| NEVER_CHANGE

    style AUTO_CHANGES fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    style AFTER_TRAINING fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100
    style NEVER_CHANGE fill:#ffcdd2,stroke:#c62828,stroke-width:2px,color:#b71c1c
```

---

## Summary: What We're Building

```mermaid
%%{init: {
  'themeVariables': { 'fontSize': '18px' },
  'flowchart': { 'nodeSpacing': 100, 'rankSpacing': 140 }
}}%%
flowchart TD
    subgraph PR_SCOPE["PR Scope: tradingagents/autoresearch/"]
        F1["train.py — Walk-forward loop"]
        F2["evaluation.py — Metrics + Excel output"]
        F3["model.py — Batch prediction wrapper"]
        F4["model_harness.py — Full pipeline orchestrator"]
        F5["prompt.py — Intraday research focus config"]
        F6["visualization.py — Actual vs Predicted charts"]
    end

    subgraph USES["Uses Existing (No Modifications)"]
        U1["TradingAgentsGraph.propagate()"]
        U2["TradingAgentsGraph.reflect_and_remember()"]
        U3["FinancialSituationMemory (BM25)"]
        U4["All 12 agents + tools + dataflows"]
    end

    subgraph OUTPUTS["What User Gets"]
        O1["Excel: Day-by-day predictions vs actual"]
        O2["Charts: Side-by-side actual vs predicted"]
        O3["Metrics: Accuracy, returns, win rate"]
        O4["Trained memory: Lessons for future use"]
    end

    PR_SCOPE -->|"calls"| USES
    PR_SCOPE -->|"produces"| OUTPUTS

    style PR_SCOPE fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    style USES fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#01579b
    style OUTPUTS fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px,color:#4a148c
```

---

## Key Design Decisions

| Decision | Choice | Why |
|---|---|---|
| Retry same day on failure? | **No** — move forward, learn via memory | Retrying with answer knowledge = look-ahead bias |
| Modify existing agent code? | **No** — only ADD new files | Clean PR, no risk of breaking existing functionality |
| Where does learning happen? | **reflect_and_remember()** — already built | Don't reinvent the wheel |
| How to tune approach? | **prompt.py** config + post-training analysis | Separates "what to focus on" from "how it runs" |
| Output format? | **Excel + matplotlib charts** | Simple, shareable, no extra dependencies |
| Max prediction horizon? | **1 month (not 1 year)** | LLM-based analysis degrades over long horizons |

---

## Questions for Reviewers

1. **Is the approach sound?** Walk-forward backtesting with memory-based learning vs. alternative approaches the team might prefer?
2. **Module location** — `tradingagents/autoresearch/` OK, or better under `experiments/` or `research/`?
3. **API cost concern** — Training over 30 days = ~360 LLM calls. Is this acceptable, or should the design include batch/cheap-model modes?
4. **Scope** — Start with just `1day` horizon, or all three (`1day`/`1week`/`1month`) in the first iteration?
5. **Merged feature or experimental branch?** — Should this live in `main` or as a separate experimental track?

## Next Steps

If the approach is approved, a follow-up PR will implement the actual module according to the design above. This RFC is intentionally docs-only to gather feedback before implementation.
