# TradingAgents: Development Roadmap & Status

## ✅ Phase 1: Medium-Term Positioning Upgrade (Completed 2026-03)

Major architectural overhaul to support 1–3 month investment horizons and professional-grade data integrity.

### 1. Multi-Round Agentic Debate (PR 171)
- **Status:** COMPLETED
- **Details:** Increased Investment and Risk debate depth to 2 rounds.
- **Impact:** Higher conviction decisions through direct analyst rebuttals and cross-examination.

### 2. Performance: Heuristic Summarization (PR 169)
- **Status:** COMPLETED
- **Details:** Replaced sequential LLM-based summarization with "Fast Path" heuristic aggregation.
- **Impact:** 50% reduction in per-ticker analysis latency (~20m saved per run).

### 3. Data Integrity: Scanner Context Ground-Truth (PR 172/173)
- **Status:** COMPLETED
- **Details:** Phase 1 (Scanner) now consolidates live commodity prices, FX rates, and catalyst calendars into a "God-Mode" packet passed to all downstream agents.
- **Impact:** Eliminated LLM hallucinations on external data; agents are now strictly anchored to live ground-truth values.

### 4. Advanced Fundamentals: TTM & Relative Performance (PR 171/172)
- **Status:** COMPLETED
- **Details:** 8-quarter TTM trend analysis, peer comparison tables, and sector-relative performance metrics.
- **Impact:** Shifted analysis focus from 1-week price noise to 3-month structural fundamentals.

---

## 🚀 Phase 2: Execution & Live Operations (In Progress)

### 5. Live Trading Connector (Interactive Brokers / Alpaca)
- **Assigned to:** API Integrator + Portfolio Manager
- **Objective:** Bridge the "Portfolio Manager" decision node to actual brokerage APIs.
- **Risk:** HIGH (Real capital at risk).
- **Tasks:**
  - Implement `IBKRConnector` and `AlpacaConnector`.
  - Add "Pre-Trade Compliance" agent to verify margin and order limits.
  - Implement WebSocket-based order tracking and execution logs.

### 6. RAG Optimization: Market Memory v2
- **Assigned to:** AI Architect
- **Objective:** Improve the retrieval quality of "Past Mistakes" and "Historical Lessons".
- **Tasks:**
  - Migrate from simple vector search to Hybrid Search (BM25 + Dense).
  - Implement "Reflexion" cycle: Agents evaluate their own past trades and write self-correcting memory entries.

### 7. Frontend: Real-time Graph Visualization
- **Assigned to:** Frontend Engineer
- **Objective:** Interactive React-based dashboard for the LangGraph execution.
- **Tasks:**
  - Visualize the "Multi-Round Risk Debate" fan-out/fan-in in real-time.
  - Add "Deep-Dive" drill-down into analyst reports from the map view.
