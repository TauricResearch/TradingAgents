# AgentOS: Visual Observability & Command Center

AgentOS is a real-time observability and command center for the TradingAgents framework. It provides a visual interface to monitor multi-agent workflows, analyze portfolio risk metrics, and trigger automated trading pipelines.

## System Architecture

- **Backend:** FastAPI (Python)
  - Orchestrates LangGraph executions.
  - Streams real-time events via WebSockets.
  - Serves portfolio data from Supabase.
  - Port: `8088` (default)
- **Frontend:** React (TypeScript) + Vite
  - Visualizes agent workflows using React Flow.
  - Displays high-fidelity risk metrics (Sharpe, Regime, Drawdown).
  - Provides a live terminal for deep tracing.
  - Port: `5173` (default)

## Getting Started

### 1. Prerequisites
- Python 3.10+
- Node.js 18+
- [uv](https://github.com/astral-sh/uv) (recommended for Python environment management)

### 2. Backend Setup
```bash
# From the project root
export PYTHONPATH=$PYTHONPATH:.
uv run python agent_os/backend/main.py
```
The backend will start on `http://127.0.0.1:8088`.

### 3. Frontend Setup
```bash
cd agent_os/frontend
npm install
npm run dev
```
The frontend will start on `http://localhost:5173`.

## Key Features

- **Literal Graph Visualization:** Real-time DAG rendering of agent interactions.
- **Top 3 Metrics:** High-level summary of Sharpe Ratio, Market Regime, and Risk/Drawdown.
- **Live Terminal:** Color-coded logs with token usage and latency metrics.
- **Run Controls:** Trigger Market Scans, Analysis Pipelines, and Portfolio Rebalancing directly from the UI.

## Port Configuration
AgentOS uses port **8088** for the backend to avoid conflicts with common macOS services. The frontend is configured to communicate with `127.0.0.1:8088`.
