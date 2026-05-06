# Web UI Design: TradingAgents Browser Interface

**Date:** 2026-05-06  
**Status:** Approved

## Overview

Replace the terminal CLI with a local web application that exposes the same TradingAgents analysis pipeline through a two-tab browser UI. The app runs entirely on the user's machine; no deployment or authentication is required.

## Goals

- Enter a ticker and date, run analysis, and watch results stream in real time
- Persist LLM provider, model, and analysis settings between sessions
- Zero change to the existing `cli/` and `tradingagents/` packages

## Non-Goals

- Multi-user access or remote deployment
- Authentication
- Historical run browsing (reports are still saved to disk by the existing save logic)
- Replacing or modifying the existing CLI

---

## Architecture

### Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + uvicorn |
| Streaming | Server-Sent Events (SSE) |
| Frontend | React 18 + Vite + TypeScript |
| Markdown rendering | react-markdown |
| Settings persistence | JSON file at `~/.tradingagents/web_config.json` |

### Folder Structure

```
TradingAgents/
├── cli/                        ← untouched
├── tradingagents/              ← untouched
└── web/
    ├── __main__.py             ← `python -m web` entry point (starts uvicorn)
    ├── server.py               ← FastAPI app, API routes, SSE stream
    ├── settings.py             ← read/write web_config.json, build run config
    └── frontend/               ← React + Vite project
        ├── package.json
        ├── vite.config.ts
        ├── src/
        │   ├── main.tsx
        │   ├── App.tsx         ← tab shell
        │   └── components/
        │       ├── AnalysisTab.tsx
        │       ├── SettingsTab.tsx
        │       ├── ProgressTracker.tsx
        │       └── ReportFeed.tsx
        └── dist/               ← built output, served by FastAPI as static files
```

### Launch

```bash
# First-time setup
cd web/frontend && npm install && npm run build && cd ../..

# Every subsequent launch
python -m web
# → opens http://localhost:7860
```

Development workflow: run `npm run dev` in `web/frontend/` (Vite dev server on port 5173) alongside `python -m web --dev` (FastAPI on port 7860 with CORS enabled for localhost:5173).

---

## Backend

### API Routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serves the built React app (`frontend/dist/index.html`) |
| `GET` | `/assets/*` | Serves React static assets |
| `GET` | `/api/settings` | Returns current settings as JSON |
| `POST` | `/api/settings` | Saves settings to `web_config.json` |
| `POST` | `/api/analyze` | Starts analysis; returns SSE stream |
| `POST` | `/api/stop` | Cancels the in-progress analysis |

### SSE Event Format

Each event is a JSON object on a `data:` line, followed by a blank line (standard SSE). The `type` field determines the shape.

All agent status events use `"in_progress"` (not `"active"`) to match the existing codebase string convention in `cli/main.py`.

```jsonc
// Agent status update — status is "pending" | "in_progress" | "completed"
{"type": "agent_status", "agent": "Market Analyst", "status": "in_progress"}
{"type": "agent_status", "agent": "Market Analyst", "status": "completed"}

// Report section (markdown content) — one event per section, emitted when
// the section first appears in a stream chunk. No token-level streaming.
{"type": "report_section", "section": "market_report", "title": "Market Analysis", "content": "### NVDA...\n..."}

// Live stats — emitted on each stream chunk
{"type": "stats", "llm_calls": 14, "tool_calls": 31, "tokens_in": 48000, "tokens_out": 12000, "elapsed_seconds": 222}

// Analysis complete — decision is the result of graph.process_signal(final_state["final_trade_decision"])
// which returns a normalised string e.g. "BUY", "SELL", or "HOLD"
{"type": "complete", "decision": "BUY"}

// Error
{"type": "error", "message": "API key not found for provider 'anthropic'"}
```

**Note on streaming:** `graph.graph.stream()` yields complete state chunks, not token-by-token content. Report sections appear complete when first emitted — there is no partial/append streaming. The UI shows a "waiting" state for sections not yet received, and switches to "complete" when the event arrives.

### Settings File

Location: `~/.tradingagents/web_config.json`

```jsonc
{
  "llm_provider": "anthropic",
  "backend_url": "https://api.anthropic.com/",
  "quick_think_llm": "claude-sonnet-4-6",
  "deep_think_llm": "claude-opus-4-6",
  "anthropic_effort": "high",
  "google_thinking_level": null,
  "openai_reasoning_effort": null,
  "research_depth": 1,
  "analysts": ["market", "news", "fundamentals"],
  "output_language": "English",
  "data_vendors": {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",
    "news_data": "yfinance"
  }
}
```

**Settings → run config translation** (`web/settings.py`):

`web_config.json` stores a `research_depth` integer (1 / 3 / 5) as a UI concept. When building the run config, `settings.py` must translate this into the two keys `DEFAULT_CONFIG` actually uses:

```python
run_config["max_debate_rounds"] = web_config["research_depth"]
run_config["max_risk_discuss_rounds"] = web_config["research_depth"]
```

`backend_url` is stored explicitly in `web_config.json` and written when the provider is saved. The provider-to-default-URL mapping (used to pre-populate the field) must mirror `cli/utils.py:select_llm_provider()`:

```python
PROVIDER_URLS = {
    "openai":     "https://api.openai.com/v1",
    "anthropic":  "https://api.anthropic.com/",
    "xai":        "https://api.x.ai/v1",
    "deepseek":   "https://api.deepseek.com",
    "qwen":       "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "glm":        "https://open.bigmodel.cn/api/paas/v4/",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama":     "http://localhost:11434/v1",
    "google":     None,
    "azure":      None,
}
```

**Settings merge strategy:** `settings.py` performs a deep merge — `DEFAULT_CONFIG` is the base, and only keys present in `web_config.json` are overridden. For nested dicts (`data_vendors`, `tool_vendors`), individual sub-keys are merged rather than replacing the whole dict. This preserves `tool_vendors` (and any future nested keys) from `DEFAULT_CONFIG` even when absent from the settings file.

```python
def build_run_config(web_config: dict) -> dict:
    config = DEFAULT_CONFIG.copy()
    # Deep merge nested dicts
    for key, value in web_config.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key] = {**config[key], **value}
        else:
            config[key] = value
    # Translate research_depth → the two real config keys; remove the UI-only key
    depth = web_config.get("research_depth", 1)
    config["max_debate_rounds"] = depth
    config["max_risk_discuss_rounds"] = depth
    config.pop("research_depth", None)
    return config
```

### Analysis Execution

The `/api/analyze` route:
1. Reads persisted settings, merges with ticker + date from request body using `build_run_config()`
2. Spawns `TradingAgentsGraph` in a `ThreadPoolExecutor` thread (FastAPI is async; the graph is synchronous)
3. Iterates `graph.graph.stream()`, appending each chunk to a `trace` list and translating it into SSE events using the same logic as `cli/main.py` (`update_analyst_statuses`, investment/risk debate state handling)
4. After exhausting the stream, accesses the final state as `final_state = trace[-1]` (mirroring `cli/main.py:1056–1157`), calls `graph.process_signal(final_state["final_trade_decision"])`, and emits `{"type": "complete", "decision": "<BUY|HOLD|SELL>"}`
5. On exception, emits `{"type": "error", "message": str(e)}`
6. A `threading.Event` cancellation flag allows `/api/stop` to break the stream loop mid-run

---

## Frontend

### Tab 1 — Analysis

**Inputs (always visible at top):**
- Ticker text input (uppercase, validated non-empty)
- Analysis date picker (defaults to today, must not be future)
- Run / Stop button (toggles based on run state)

**Progress Tracker (appears when run starts):**

The tracker shows individual agents grouped visually into teams. The full agent list, in order:

| Team | Agents |
|------|--------|
| Analyst Team | Only selected analysts shown: Market Analyst, Social Analyst, News Analyst, Fundamentals Analyst |
| Research Team | Bull Researcher, Bear Researcher, Research Manager |
| Trading Team | Trader |
| Risk Management | Aggressive Analyst, Neutral Analyst, Conservative Analyst |
| Portfolio | Portfolio Manager |

Each agent is one dot. Dot states driven by `agent_status` SSE events:
- `"pending"` → grey dot
- `"in_progress"` → purple pulsing dot
- `"completed"` → green dot

Teams are separated by a `›` divider. Right side: live stats (LLM calls, tool calls, tokens in/out, elapsed time) from `stats` events.

**Report Feed (accumulates as agents complete):**
- Each `report_section` event appends a new card at the bottom of the feed
- Cards stack in arrival order; the user can scroll freely
- Section headers: section title + "Completed" badge
- Content rendered as Markdown (react-markdown)
- While a section has not yet arrived, no placeholder is shown — the feed simply grows as events come in
- After the `complete` event, a decision banner appears at the bottom: `BUY` (green) / `HOLD` (amber) / `SELL` (red)

### Tab 2 — Settings

**LLM Provider card:**
- Provider dropdown (Anthropic, OpenAI, Google, xAI, DeepSeek, Qwen, GLM, OpenRouter, Azure, Ollama)
- When provider changes, `backend_url` is pre-filled from `PROVIDER_URLS` (editable text field for Ollama/Azure/custom)
- Quick-thinking model dropdown — options from `MODEL_OPTIONS[provider]["quick"]` when the provider key exists in `MODEL_OPTIONS`; otherwise a free-text input field is shown (covers OpenRouter, Azure, and any future provider not yet in the catalog)
- Deep-thinking model dropdown — same rule using `MODEL_OPTIONS[provider]["deep"]`
- Provider-specific thinking config — only the relevant control is shown:
  - Anthropic → Effort Level pills: High / Medium / Low
  - OpenAI → Reasoning Effort pills: High / Medium / Low
  - Google → Thinking Mode pills: Enable / Minimal
  - All others → hidden

**Analysis Defaults card:**
- Analysts multi-select pills (Market, News, Fundamentals, Social Media) — at least one must remain selected
- Research Depth pills (Shallow = 1 / Medium = 3 / Deep = 5)
- Output Language dropdown (same list as the CLI)

**Data Sources card (full width):**
- Four dropdowns: Stock Data, Technical Indicators, Fundamentals, News
- Options: `yfinance (free)` / `Alpha Vantage`

**Save button:** POSTs to `/api/settings`, shows brief "Saved ✓" confirmation inline. Settings take effect on the next analysis run.

When the provider changes in the UI, the frontend must null out all provider-specific effort fields not applicable to the new provider before saving (`anthropic_effort`, `google_thinking_level`, `openai_reasoning_effort` — only the one for the active provider carries a value; the rest are `null`).

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Missing API key | `error` SSE event; UI shows red banner with message |
| Network timeout to LLM | Error propagated through SSE stream |
| Invalid ticker | Caught by existing graph validation; surfaced as SSE error |
| Analysis already running | Run button disabled; second `/api/analyze` returns 409 |
| Frontend SSE disconnect | Backend thread continues; reconnect not supported (user must re-run) |

---

## Build Sequence

1. `web/settings.py` — `build_run_config()`, deep merge, `research_depth` translation, `PROVIDER_URLS` map, read/write `web_config.json`
2. `web/server.py` — FastAPI routes, SSE streaming, static file serving, cancellation flag
3. `web/__main__.py` — uvicorn launcher with `--dev` flag for CORS
4. `web/frontend/` — Vite + React + TypeScript scaffold
5. `ProgressTracker` component — individual agent dots, team grouping, stats display
6. `ReportFeed` component — card-per-section, react-markdown, decision banner
7. `AnalysisTab` — ticker/date inputs, EventSource wiring, state management
8. `SettingsTab` — provider-conditional model dropdowns, OpenRouter/Azure free-text fallback, save
9. `App.tsx` — tab shell, loads settings on mount via `GET /api/settings`
10. End-to-end test: run analysis against a real ticker, verify SSE streaming, settings persist across restart
