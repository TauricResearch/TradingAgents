# TroddeAgents — WebUI Setup & Specification

**Version:** 1.1  
**Status:** Built  
**Last updated:** 2026-05-16

> **Intent:** This document is written for a Claude Code agent. Follow it top-to-bottom without asking the user anything. Every command, path, and decision is specified.

---

## 1. Overview

TroddeAgents is a Tron-themed single-page web application that wraps the TradingAgents LangGraph pipeline for interactive, on-demand stock analysis. A FastAPI backend streams agent progress via Server-Sent Events (SSE) while a vanilla-JS frontend renders results in real time.

---

## 2. Repository Layout

```
TradingAgents/              ← repo root (also Python package root)
├── pyproject.toml          ← package definition; pip-installable as "tradingagents"
├── uv.lock                 ← locked dependency tree (managed by uv)
├── .env                    ← secrets and config overrides (not committed)
├── .env.example            ← template to copy from
├── tradingagents/          ← core LangGraph engine
│   └── default_config.py   ← all runtime defaults; env-var overrides applied here
├── web/
│   ├── __init__.py
│   ├── app.py              ← FastAPI application entry point
│   └── static/
│       └── index.html      ← single-page application (all HTML + CSS + JS)
├── tests/                  ← pytest test suite
└── docs/
    └── WEBUI_SPEC.md       ← this file
```

---

## 3. Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | ≥ 3.10 | 3.12 used in production |
| uv | any recent | Install via `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Git | any | To clone the repo |
| API key | at least one LLM provider | See §5 |

No Node.js, no build step, no Docker required for local development.

---

## 4. Installation

### 4.1 Clone

```bash
git clone <repo-url> TradingAgents
cd TradingAgents
```

### 4.2 Create virtual environment and install all dependencies

```bash
uv venv
uv pip install -e .
```

This installs the `tradingagents` package in editable mode plus all dependencies declared in `pyproject.toml`.

### 4.3 Install web-layer dependencies

These are not yet declared in `pyproject.toml` and must be added manually:

```bash
uv pip install fastapi uvicorn[standard] mistune python-dotenv
```

### 4.4 Install test dependencies

```bash
uv pip install pytest
```

### 4.5 Verify installation

```bash
.venv/bin/python -c "
import tradingagents, fastapi, uvicorn, mistune, dotenv
print('all imports ok')
"
```

Expected output: `all imports ok`

---

## 5. Configuration

### 5.1 Create `.env`

```bash
cp .env.example .env
```

### 5.2 Set at least one LLM provider API key

Edit `.env` and set **one** of the following (Anthropic shown as default):

```env
ANTHROPIC_API_KEY=sk-ant-...
```

Other supported providers:

```env
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
XAI_API_KEY=...
DEEPSEEK_API_KEY=...
```

For Ollama (local, no key needed), leave all keys blank. Ollama must be running at `http://localhost:11434`.

### 5.3 Optional runtime overrides

These `TRADINGAGENTS_*` variables override `default_config.py` at startup. All are optional.

```env
# Override default LLM provider and models shown in UI on first load
TRADINGAGENTS_LLM_PROVIDER=anthropic
TRADINGAGENTS_DEEP_THINK_LLM=claude-opus-4-7
TRADINGAGENTS_QUICK_THINK_LLM=claude-sonnet-4-6

# Tune debate depth (lower = faster + cheaper)
TRADINGAGENTS_MAX_DEBATE_ROUNDS=1
TRADINGAGENTS_MAX_RISK_ROUNDS=1

# Enable checkpoint/resume for long runs
TRADINGAGENTS_CHECKPOINT_ENABLED=false
```

### 5.4 Runtime data directories

Created automatically on first run. No manual action needed.

| Path | Purpose |
|------|---------|
| `~/.tradingagents/logs/` | Analysis reports (markdown + JSON) |
| `~/.tradingagents/cache/` | Data cache |
| `~/.tradingagents/memory/` | Reflection memory log |

---

## 6. Running the Server

```bash
.venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000` in a browser.

**To run in the background:**

```bash
.venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000 &
```

**To stop:**

```bash
kill $(lsof -ti:8000)
```

---

## 7. API Surface

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/analyze` | Start analysis job; returns `{ "job_id": "..." }` |
| `GET`  | `/api/stream/{job_id}` | SSE stream of agent events |
| `GET`  | `/api/reports` | List all completed analyses |
| `GET`  | `/api/reports/{ticker}/{date}` | Parsed report for a single analysis |
| `GET`  | `/` | Serves `index.html` |

---

## 8. Analysis Request Body

`POST /api/analyze`

```json
{
  "ticker": "NVDA",
  "date": "2026-05-16",
  "analysts": ["market", "social", "news", "fundamentals"],
  "language": "English",
  "research_depth": 1,
  "llm_provider": "anthropic",
  "quick_llm": "claude-sonnet-4-6",
  "deep_llm": "claude-opus-4-7",
  "effort": "high"
}
```

**Field notes:**

| Field | Values | Notes |
|-------|--------|-------|
| `analysts` | any subset of `["market","social","news","fundamentals"]` | All four recommended |
| `research_depth` | `1` (shallow) · `3` (medium) · `5` (deep) | Controls debate rounds |
| `llm_provider` | `anthropic` · `openai` · `google` · `xai` · `deepseek` · `ollama` | Must match API key in `.env` |
| `effort` | `"low"` · `"medium"` · `"high"` · omit | Anthropic extended thinking; **only valid when both models are Opus-class** — omit for Sonnet/Haiku |

---

## 9. SSE Event Schema

`GET /api/stream/{job_id}` — `text/event-stream`

| Event `type` | Fields |
|-------------|--------|
| `agent_update` | `node`, `label`, `stage` (1–5), `msg_type`, `content`, `tokens_in`, `tokens_out` |
| `done` | `signal`, `decision`, `market_report`, `news_report`, `sentiment_report`, `fundamentals_report` |
| `error` | `message`, `detail` |
| `heartbeat` | _(none)_ |
| `complete` | _(none)_ |

---

## 10. LLM Routing Rules

- **Quick LLM** handles analyst agents (stages 1): market, social, news, fundamentals
- **Deep LLM** handles reasoning-heavy agents (stages 2–5): research team, risk management, portfolio manager
- `effort` parameter is forwarded to Anthropic **only when both** quick and deep models contain `"opus"` — Haiku and Sonnet return HTTP 400 if `effort` is present

---

## 11. Five-Stage Pipeline

| Stage | Agents | Progress weight |
|-------|--------|----------------|
| 1 — Analyst Team | Market · Social · News · Fundamentals | 35% |
| 2 — Research Team | Bull · Bear · Research Manager | 25% |
| 3 — Trader | Investment decision | 15% |
| 4 — Risk Management | Aggressive · Neutral · Conservative | 15% |
| 5 — Portfolio Manager | Final decision | 10% |

---

## 12. Frontend Behaviour

### Report Persistence
After a successful analysis, `app.py` writes seven markdown files to `~/.tradingagents/logs/{TICKER}/{DATE}/reports/`:

| File | Source field |
|------|-------------|
| `final_trade_decision.md` | `final_trade_decision` |
| `trader_investment_plan.md` | `trader_investment_plan` |
| `investment_plan.md` | `investment_plan` |
| `market_report.md` | `market_report` |
| `sentiment_report.md` | `sentiment_report` |
| `news_report.md` | `news_report` |
| `fundamentals_report.md` | `fundamentals_report` |

`GET /api/reports` detects the entry by the presence of `final_trade_decision.md`. Failed analyses write nothing and do not appear in Prior Analyses.

### Job State Persistence
- Job state is serialised to browser `localStorage` on every SSE event
- On page reload: state is restored and rendered immediately without re-running the analysis
- Jobs flagged `done` or `error` in localStorage render their final state; no SSE reconnect is attempted

### Progress Tracker
- Displays live stage progress while the analysis runs
- On completion: signal badge (`BUY` / `SELL` / `HOLD`) + full decision text
- On error: error message, expandable traceback (`<details>`), and **Dismiss** button that clears state

### Pipeline Indicator (sidebar)
- Compact `01 → 02 → 03 → 04 → 05` horizontal strip below "Prior Analyses"
- Node states: `pending` · `running` (pulsing blue glow) · `complete` (green)
- Driven by the `stage` field of each incoming `agent_update` event

### Effort Level Dropdown
- Hidden unless **both** quick-LLM and deep-LLM selectors contain the string `"opus"`
- Re-evaluated on every provider or model change event

### Prior Analyses
- Listed in sidebar; click any entry to open the report panel
- Reports for failed analyses show "no report available" rather than a raw 404 error

---

## 13. Validation Steps

Run these in order after installation to confirm everything is working.

### 13.1 Unit tests (no API key needed)

```bash
.venv/bin/python -m pytest tests/ -m "not integration" -q
```

Expected: all tests pass (warnings are expected and safe to ignore).

### 13.2 Import smoke test

```bash
.venv/bin/python -c "
from tradingagents.graph.trading_graph import TradingAgentsGraph
from web.app import app
print('imports ok')
"
```

Expected: `imports ok`

### 13.3 Server starts

```bash
.venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8000 &
sleep 2
curl -s http://127.0.0.1:8000/ | grep -c "TroddeAgents"
kill $(lsof -ti:8000)
```

Expected: `1` (the string `TroddeAgents` appears in the HTML response).

### 13.4 Reports API

```bash
.venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8000 &
sleep 2
curl -s http://127.0.0.1:8000/api/reports
kill $(lsof -ti:8000)
```

Expected: `[]` (empty array if no analyses have been run yet) or a JSON array of past analyses.

### 13.5 End-to-end analysis (requires API key)

With the server running, POST a short analysis request:

```bash
curl -s -X POST http://127.0.0.1:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AAPL",
    "date": "2026-05-16",
    "analysts": ["market"],
    "language": "English",
    "research_depth": 1,
    "llm_provider": "anthropic",
    "quick_llm": "claude-haiku-4-5-20251001",
    "deep_llm": "claude-haiku-4-5-20251001"
  }'
```

Then stream the result (replace `JOB_ID` with the returned `job_id`):

```bash
curl -s -N http://127.0.0.1:8000/api/stream/JOB_ID
```

Expected: a stream of `data: {...}` lines ending with `"type":"done"` or `"type":"complete"`.

---

## 14. Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `No module named uvicorn` | Web deps not installed | `uv pip install fastapi uvicorn[standard] mistune python-dotenv` |
| `No module named tradingagents` | Package not installed | `uv pip install -e .` from repo root |
| HTTP 400 on Anthropic runs | `effort` sent to non-Opus model | Do not set `effort` unless both models contain `"opus"` |
| `Report not found` (404) | Analysis failed — no log written | Expected; UI shows "no report available" message |
| SSE stream never starts | `.env` missing or API key blank | Check `.env` exists and the right `*_API_KEY` is set |
| Form disabled after page reload | Stale localStorage from an errored job | Click **Dismiss** in the progress tracker, or clear localStorage |
| Port 8000 already in use | Previous server still running | `kill $(lsof -ti:8000)` |
