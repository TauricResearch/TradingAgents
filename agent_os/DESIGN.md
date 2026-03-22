# AgentOS: Visual Observability Design

## 1. The Literal Graph Visualization (Agent Map)

The agent map is a directed graph (DAG) representing the LangGraph workflow in real-time.

### Implementation Strategy
- **Frontend:** Powered by **React Flow**. Nodes are added and connected as WebSocket events arrive.
- **Node Data Contract:**
  - `node_id`: Unique identifier for the graph node.
  - `parent_node_id`: For building edges in real-time.
  - `metrics`: `{ "tokens_in": int, "tokens_out": int, "latency_ms": float, "model": str }`.
- **Interactivity:** Clicking a node opens an **Inspector Drawer** showing:
    - **LLM Metrics:** Model name, Request/Response tokens, Latency (ms).
    - **Payload:** Raw JSON response and rationale.

### Pause & Restart (Next Phase TODO)
- **Interrupts:** Use LangGraph's `interrupt_before` features to halt execution at specific nodes (e.g., `trader_node`).
- **Control API:** `POST /api/run/{run_id}/resume` to signal the graph to continue.

---

## 2. The "Top 3" Metrics Consensus

Synthetic consensus between **Economist** (Efficiency/Risk) and **UI Designer** (Clarity/Action):

1.  **Trailing 30-Day Sharpe Ratio (Risk-Adjusted Efficiency)**
    - *Economist:* "Absolute P&L is vanity; we need to know the quality of the returns."
    - *Display:* Large gauge showing trading efficiency.

2.  **Current Market Regime & Beta (Macro Alignment)**
    - *Economist:* "Signals if we are riding the trend or fighting it."
    - *Display:* Status badge (BULL/BEAR) + Beta value relative to S&P 500.

3.  **Real-Time Drawdown & 1-Day VaR (Capital Preservation)**
    - *UI Designer:* "The 'Red Alert' metric. It must be visible if we are losing capital."
    - *Display:* Percentage bar showing distance from the All-Time High.

---

## 3. Tech Stack
- **Backend:** FastAPI, LangChain, Supabase (Postgres).
- **Frontend:** React, Chakra UI, React Flow, Axios.
- **Protocol:** REST for triggers, WebSockets for live streaming.
