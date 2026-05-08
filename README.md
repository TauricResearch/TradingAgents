# TradingAgents Dashboard

A Bloomberg terminal-style web dashboard that runs the TradingAgents multi-agent pipeline on multiple tickers simultaneously, streaming agent activity live to your browser.

## Architecture

```
TradingAgents repo  ←→  backend.py (FastAPI)  ←→  dashboard.html (WebSocket)
```

- **backend.py** — FastAPI server that wraps TradingAgents, runs agent pipelines in a thread pool, and streams progress to connected browsers via WebSocket.
- **dashboard.html** — Single-file frontend. Served by the backend at `http://localhost:8000`.

## Quick Start

### 1. Clone TradingAgents

```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

### 2. Install dependencies

```bash
conda create -n tradingagents python=3.13
conda activate tradingagents

pip install -r requirements.txt
pip install fastapi uvicorn
```

### 3. Set your API keys

Copy `.env.example` to `.env` and fill in at minimum:

```env
ANTHROPIC_API_KEY=sk-ant-...
ALPHA_VANTAGE_API_KEY=...       # for market data
```

Or export them directly:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export ALPHA_VANTAGE_API_KEY=...
```

### 4. Copy dashboard files

Copy `backend.py` and `dashboard.html` into the root of the TradingAgents repo:

```bash
cp /path/to/backend.py .
cp /path/to/dashboard.html .
```

### 5. Run

```bash
python backend.py
```

Open **http://localhost:8000** in your browser.

---

## Features

| Feature | Description |
|---|---|
| Multi-ticker grid | Watch any number of tickers simultaneously |
| Live agent stream | See each agent's output as it runs |
| Agent pills | Visual progress tracker for all 9 agents |
| Decision badges | BUY / SELL / HOLD with confidence bar |
| Auto-refresh | Configurable interval (1 min → 1 hr) |
| Demo mode | Works without TradingAgents installed (simulated data) |
| WebSocket | Auto-reconnects if connection drops |

## Agent Pipeline

Each ticker card runs the full TradingAgents pipeline:

```
Fundamentals Analyst
  → Sentiment Analyst
    → News Analyst
      → Technical Analyst
        → Bull Researcher ←→ Bear Researcher (debate)
          → Trader
            → Risk Manager
              → Portfolio Manager
                → Decision (BUY / SELL / HOLD)
```

## Configuration

The backend uses Claude by default:

```python
# In backend.py
config["llm_provider"]   = "anthropic"
config["deep_think_llm"] = "claude-opus-4-6"
config["quick_think_llm"]= "claude-sonnet-4-6"
```

To switch to another provider, edit those lines:

```python
config["llm_provider"]   = "openai"
config["deep_think_llm"] = "gpt-5"
config["quick_think_llm"]= "gpt-5-mini"
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/tickers` | List watched tickers + state |
| POST | `/api/tickers` | Add ticker `{"ticker": "NVDA"}` |
| DELETE | `/api/tickers/{ticker}` | Remove ticker |
| POST | `/api/tickers/{ticker}/refresh` | Force re-analysis |
| PATCH | `/api/config` | Update refresh interval |
| GET | `/api/status` | Server status |
| WS | `/ws` | Real-time event stream |

## Notes

- TradingAgents analyses can take **3–10 minutes** per ticker depending on model and research depth. The dashboard streams progress live so you can follow along.
- Set `config["max_debate_rounds"] = 1` (default in backend) for faster runs.
- The `DEMO_MODE` fallback activates automatically if TradingAgents isn't installed — useful for frontend development.
- **Not financial advice.** See [TauricResearch disclaimer](https://tauric.ai/disclaimer/).
