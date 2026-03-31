# Pipeline Optimization Strategy

## 1. Slowness Root Cause Analysis

The current trading agent pipeline suffers from significant latency issues, often appearing "stuck" during long-running sessions. The primary drivers of this slowness are:

### A. Token Bloat (Context Congestion)
The system currently passes full, verbose reports from Phase 1 scanners directly into Phase 2 (`industry_deep_dive`) and Phase 3 (`macro_synthesis`). As more scanners are added, the input context for these nodes grows exponentially, leading to:
- Higher inference costs.
- Slower "Time to First Token" (TTFT).
- Increased risk of exceeding model context limits.

### B. "Novel Writing" Prompts
Many agent prompts (especially Bull/Bear Researchers) explicitly request a "conversational style" with roleplay elements (e.g., "leans forward... coffee"). This results in:
- Thousands of tokens of "fluff" that do not add financial value.
- Significant generation time spent on non-actionable text.

### C. MongoDB Quota Overhead
When the MongoDB cluster is over quota, every tool call or LLM event triggers a failure. Even with short timeouts (5s), the cumulative delay across 100+ events per run adds minutes of "dead time" where the system is simply waiting to timeout.

### D. Sequential Bottlenecks
The current graph architecture processes many research tasks sequentially or in large fan-in blocks that wait for the slowest model to finish before proceeding.

---

## 2. Proposed Solutions

### Step 1: MongoDB Optimization (Storage & Observability)
- **Cleanup**: Implementation of a script to delete historical runs from previous years (e.g., 2025) to restore quota.
- **Observability Refactoring**: Disable per-event logging to MongoDB in `RunLogger`. We will transition to "Report-Only" persistence for MongoDB, while keeping full event logs on the local filesystem. This eliminates dozens of failing network calls per run.

### Step 2: Clinical Prompt Refactoring
Redefine all system prompts to adopt a **Clinical / Quantitative** tone.
- **Persona**: Senior Economist + AI Developer.
- **Constraints**: Force bulleted, data-dense outputs. Explicitly forbid conversational filler, rhetorical phrasing, and roleplay "stage directions."
- **Focus**: Objective delta-changes, specific price levels, and verified catalysts.

### Step 3: Recursive Summarization Architecture
Introduce intermediate **Compression Nodes** in the `ScannerGraph`.
- **Flow**: `Scanner -> Summarizer -> Synthesis`.
- **Benefit**: Synthesis agents will receive 500 tokens of high-signal summaries instead of 5,000 tokens of raw prose.
- **Persona**: Senior Economist + AI Developer persona applied to summarizers.
- **Standardization**: Define strict `SummaryRuleSet` formats for every scanner type.

### Step 4: Graph Parallelization
Refactor Phase 4 (Ticker Deep Dives) to ensure maximal parallel execution of Bull/Bear debates, leveraging `OLLAMA_NUM_PARALLEL` for local inference.

---

## 3. Implementation Roadmap

1. **Branch `opt/mongodb-cleanup`**: Cleanup script and observability refactor.
2. **Branch `opt/clinical-prompts`**: Refactor analyst and scanner prompts.
3. **Branch `opt/recursive-summarization`**: Update graph setup and inject summarization nodes.
