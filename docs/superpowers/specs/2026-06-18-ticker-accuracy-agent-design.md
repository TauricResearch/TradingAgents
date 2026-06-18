# Ticker Accuracy Agent — Design

**Date:** 2026-06-18
**Status:** Draft (pending user review)
**Scope:** New autonomous agent + dedicated dashboard drawer + backend orchestrator + universe discovery + accuracy scoring + capabilities inventory + self-improvement loop

## Goal

Add an autonomous Ticker Accuracy Agent to the TradingAgents system. The agent continuously discovers tickers (from multiple sources), validates prediction accuracy via historical backtests, ranks tickers by correctness, and learns from its own past cycles.

## Architecture

```
Dashboard Header: [Settings] [Past Runs] [History] [🤖 Agent]
                                          │
                                    ┌─────▼──────┐
                                    │ Agent Drawer│
                                    │ (right-side)│
                                    └─────┬──────┘
                                          │
   ┌──────────────────────────────────────┴─────────────────────────┐
   │                 FastAPI Server (web/server/app.py)             │
   │  ┌──────────────────────────────────────────────────────────┐ │
   │  │  ticker_agent/  (new router: /api/ticker-agent/*)       │ │
   │  │  ┌────────────┐ ┌──────────┐ ┌───────────┐ ┌─────────┐ │ │
   │  │  │Orchestrator│ │Universe  │ │Scorer     │ │Caps     │ │ │
   │  │  │(loop+LLM)  │ │(discovery)│ │(accuracy) │ │Inventory│ │ │
   │  │  └─────┬──────┘ └──────────┘ └─────┬─────┘ └─────────┘ │ │
   │  │        │                           │                    │ │
   │  │        └─── uses ────┐             │                    │ │
   │  └──────────────────────┼─────────────────────────────────┘ │
   │                         │                                    │
   │  ┌──────────────────────▼─────────────────────────────────┐ │
   │  │ Existing: background_runs, runs, watchlist, history    │ │
   │  └────────────────────────────────────────────────────────┘ │
   └──────────────────────────────────────────────────────────────┘
```

The agent is a FastAPI sub-module (`web/server/ticker_agent/`) that has direct Python access to all existing backend modules. It runs as a background thread on a configurable schedule. Its outputs (accuracy scores) are persisted server-side and consumed by existing UI components.

## Agent Orchestrator — 7-Step Loop

### Cycle flow

```
1. READ MEMORY
   Load past conclusions from agent_memory.jsonl (last 10 entries).
   Include in LLM prompt context.

2. GATHER CONTEXT
   ├─ Sector performance (yfinance price data, grouped)
   ├─ Current accuracy scores from agent_state.json
   ├─ Coverage gaps (tickers with < min_samples runs)
   └─ Broader universe candidates (S&P 500 + sectors + custom file)

3. LLM STRATEGY CALL (reuses existing quick_thinking_llm)
   Prompt receives: sector heat map, accuracy gaps, past conclusions, candidates.
   Returns structured plan:
   {
     investigation_plan: [
       {ticker: "NVDA", priority: "high",
        rationale: "Hot semi sector, only 2 backtests",
        backtests_needed: 5}
     ],
     sectors_to_watch: ["Semiconductors"],
     reasoning_summary: "Earnings season approaching for semi stocks"
   }

4. EXECUTE
   ├─ Schedule background_runs for chosen tickers via existing background_runs
   └─ Run will appear in Past Runs drawer automatically

5. RANK & REFLECT
   ├─ Recompute accuracy scores from all completed runs
   ├─ Sort tickers by win rate (right / (right + wrong))
   ├─ Apply min_sample filter (configurable, default 3)
   ├─ Persist to agent_state.json
   └─ Watchlist + History panel pick up new scores automatically

6. WRITE MEMORY
   ├─ Generate 3-5 learning conclusions from this cycle:
   │  "Tickers in sector X during earnings season had 80%+ accuracy"
   │  "High-volume tickers predict better than low-volume ones"
   │  "Mid-caps have highest prediction reliability"
   └─ Append to agent_memory.jsonl (timestamped, structured)

7. SELF-IMPROVEMENT
   ├─ Ask: "What data/tools would help me find better tickers?"
   ├─ Ask: "What new API endpoint would make analysis more precise?"
   └─ Log structured entries to missing_capabilities.jsonl
      → Visible in Agent drawer with [Implement →] button
```

### Schedule

- Default: every 6 hours
- Configurable in Settings panel
- "Run Now" button in Agent drawer triggers immediate cycle
- Pause/Resume via Agent drawer

## Ticker Universe Discovery

```
UNIVERSE SOURCES (merged by ticker, de-duped):
├─ 1. S&P 500 constituents (fetched programmatically)
├─ 2. Yahoo Finance sectors — browse sector ETFs,
│     extract top holdings per sector
├─ 3. Custom universe file — ~/.tradingagents/custom_universe.json
├─ 4. Watchlist — always included, has accuracy data
└─ 5. Cross-references — tickers mentioned in news/social feeds

Filter: validate_ticker_exists (existing) for each candidate.
Each candidate gets a source tag for LLM provenance reasoning.

Cached in: ~/.tradingagents/data/ticker_agent/universe_candidates.json
```

## Accuracy Scoring Engine

Server-side computation using existing run data:

```
FOR EACH TICKER:
├─ Gather all completed runs from storage (walk_data_dir)
├─ For each run, compute verdict (right/wrong/unknown)
│  using existing verdict logic at multiple Δ windows
├─ Aggregate:
│  ├─ total_runs, right_count, wrong_count, win_rate
│  ├─ avg_confidence, target_hit_rate
│  ├─ sample_size
│  └─ trending_accuracy (last 10 runs vs all-time)
└─ Store in agent_state.json

Verdict logic port matches the existing frontend verdicts.ts
computation — same rules for target_hit, direction, HOLD threshold.
```

## Data Storage

```
~/.tradingagents/data/ticker_agent/
├─ agent_state.json            — ticker scores, cycle status, next ETA
├─ agent_memory.jsonl          — append-only conclusions (for LLM context)
├─ missing_capabilities.jsonl  — append-only missing features log
├─ config.json                 — schedule, min_samples, universe toggles
└─ universe_candidates.json    — cached broader universe

~/.tradingagents/data/background_runs/   ← agent schedules here (existing)
~/.tradingagents/data/{TICKER}/          ← agent reads here (existing)
```

### `agent_state.json` schema

```json
{
  "status": "running",
  "last_cycle_at": "2026-06-18T12:00:00Z",
  "next_cycle_at": "2026-06-18T18:00:00Z",
  "cycles_completed": 12,
  "scores": {
    "NVDA": {
      "win_rate": 0.83,
      "total_runs": 10,
      "right": 8,
      "wrong": 2,
      "avg_confidence": 0.72,
      "target_hit_rate": 0.6,
      "trending_accuracy": 0.9,
      "sector": "Semiconductors",
      "last_evaluated": "2026-06-18T12:00:00Z"
    },
    "AAPL": {
      "win_rate": 0.75,
      "total_runs": 20,
      "right": 15,
      "wrong": 5,
      ...
    }
  },
  "activity_log": [
    {
      "cycle": 12,
      "started_at": "2026-06-18T12:00:00Z",
      "tickers_analyzed": 15,
      "backtests_scheduled": 8,
      "summary": "Analyzed semi sector, NVDA has 83% accuracy (10 runs)"
    }
  ]
}
```

### `agent_memory.jsonl` entry

```json
{
  "cycle": 12,
  "timestamp": "2026-06-18T12:00:00Z",
  "conclusions": [
    "Semi sector tickers during earnings window had 80%+ accuracy vs 55% off-season",
    "High-volume tickers (>10M/day) predict 15% better than low-volume",
    "Mid-caps ($2B-$10B) show highest prediction reliability at 78%"
  ],
  "strategies_validated": ["earnings-season sector focus"],
  "strategies_invalidated": ["low-volatility ticker picking"],
  "next_iteration_focus": "Financial sector ahead of Fed meeting"
}
```

## API Endpoints

All under `/api/ticker-agent/*`:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/ticker-agent/status` | GET | Agent status, last cycle, next cycle ETA |
| `/api/ticker-agent/run-now` | POST | Trigger an immediate cycle |
| `/api/ticker-agent/pause` | POST | Pause background scheduling |
| `/api/ticker-agent/resume` | POST | Resume scheduling |
| `/api/ticker-agent/accuracy-leaderboard` | GET | All scored tickers sorted by accuracy |
| `/api/ticker-agent/activity-log` | GET | Last N cycle summaries |
| `/api/ticker-agent/missing-capabilities` | GET | Missing capabilities list |
| `/api/ticker-agent/capabilities` | GET | API inventory (what agent can use) |
| `/api/ticker-agent/config` | GET | Agent configuration |
| `/api/ticker-agent/config` | PUT | Update config |

Existing endpoints get additional data so existing views reflect agent output:
- `GET /api/watchlist` → adds optional accuracy fields per ticker (when agent has scored them)
- `GET /api/tickers/{ticker}/history` → adds an aggregate accuracy summary

## Frontend Components

### New: `TickerAccuracyAgentDrawer.tsx`

Right-side drawer (same pattern as `HistoricalAnalysisDrawer.tsx`), triggered by a `[🤖 Agent]` button in the dashboard header.

Sections:
1. **Status bar** — Running/Paused, next cycle countdown, [Run Now] [Pause] [Resume]
2. **Activity log** — Last 5 cycle summaries (expandable)
3. **Accuracy leaderboard** — Sorted tickers with win rate, runs count, trend indicator. Reuses logic from existing `DecisionAccuracyLeaderboard.tsx`
4. **Capabilities inventory** — Table of available APIs with status indicators
5. **Missing capabilities** — Each entry has a description and `[Implement →]` button that triggers opencode CLI with implementation instructions

### Changes to existing components

| Component | Change |
|---|---|
| `App.tsx` | Add `[🤖 Agent]` button in header, mount `TickerAccuracyAgentDrawer` |
| `store/ui.ts` | Add `tickerAgentOpen` boolean + setter (not persisted) |
| `TickerRow.tsx` | Show accuracy badge (win rate %) when agent has scored the ticker |
| `WatchlistRail.tsx` | Add "Sort by Accuracy" option |
| `HistoricalAnalysisDrawer.tsx` | Show accuracy summary chip in header when agent data exists |
| `DecisionAccuracyLeaderboard.tsx` | Wire to server-side agent data instead of in-memory event buffer |
| `SettingsPanel.tsx` | Add "Ticker Accuracy Agent" config section (min samples, schedule, universe toggles) |

### `lib/api.ts` additions

Type definitions and fetchers for all `/api/ticker-agent/*` endpoints, matching the existing pattern.

## Settings Panel Config

A new collapsible section in the existing `SettingsPanel.tsx`:

```
🤖 Ticker Accuracy Agent
├─ Min samples before ranking: [3 ▾]
├─ Schedule interval: [6h ▾]
├─ Max tickers per cycle: [20]
└─ Universe sources:
   ☑ S&P 500
   ☑ Yahoo sectors
   ☑ Custom universe file
```

## Files Touched

### Backend (new)

| File | Action |
|---|---|
| `web/server/ticker_agent/__init__.py` | new |
| `web/server/ticker_agent/orchestrator.py` | new — background loop, LLM strategy call, lifecycle |
| `web/server/ticker_agent/universe.py` | new — ticker discovery from all sources |
| `web/server/ticker_agent/scorer.py` | new — accuracy computation from existing runs |
| `web/server/ticker_agent/capabilities.py` | new — API inventory discovery |
| `web/server/ticker_agent/missing_capabilities.py` | new — missing capability tracking |
| `web/server/ticker_agent/router.py` | new — FastAPI router (10 endpoints) |

### Backend (extend)

| File | Action |
|---|---|
| `web/server/app.py` | register ticker_agent router, start background orchestrator in lifespan |
| `web/server/queries.py` | add accuracy lookup helpers |
| `web/server/storage.py` | add ticker_agent storage paths |

### Frontend (new)

| File | Action |
|---|---|
| `web/frontend/src/components/TickerAccuracyAgentDrawer.tsx` | new — agent drawer |
| `web/frontend/src/components/TickerAccuracyAgentDrawer.test.tsx` | new — tests |

### Frontend (extend)

| File | Action |
|---|---|
| `web/frontend/src/App.tsx` | add Agent button + mount drawer |
| `web/frontend/src/store/ui.ts` | add `tickerAgentOpen` state |
| `web/frontend/src/lib/api.ts` | add types + fetchers for agent endpoints |
| `web/frontend/src/components/TickerRow.tsx` | add accuracy badge |
| `web/frontend/src/components/WatchlistRail.tsx` | add accuracy sort option |
| `web/frontend/src/components/HistoricalAnalysisDrawer.tsx` | add accuracy summary chip |
| `web/frontend/src/components/DecisionAccuracyLeaderboard.tsx` | wire to server data |
| `web/frontend/src/components/SettingsPanel.tsx` | add agent config section |

## Testing

### Backend unit (`web/server/ticker_agent/tests/`)

- Orchestrator cycle runs and calls LLM strategy prompt
- Universe discovery resolves S&P 500 / sector / custom sources
- Scorer computes correct accuracy from seeded run data
- Capabilities inventory lists all known endpoints
- Missing capabilities append/read cycle
- Agent memory append/truncate to last N entries
- Config get/set round-trips correctly

### Backend API (`web/server/tests/test_api.py` — extend)

- Each `/api/ticker-agent/*` endpoint returns expected status codes
- Bad config values return 422
- Run-now triggers a cycle (verify via mock on orchestrator)
- Pause/resume lifecycle

### Frontend

- Agent drawer renders all sections
- Accuracy leaderboard renders sorted scores
- Missing capabilities show `[Implement →]` button
- Settings config section renders and saves
- Watchlist shows accuracy badge when agent data present
- Empty states: no cycles yet, no scores yet, no missing caps

## Out-of-Scope Follow-Ups

- **Multi-agent coordination** (multiple agents sharing conclusions)
- **Performance benchmarking** (comparing agent-discovered accuracy vs random selection)
- **Automated A/B testing** of different discovery strategies
- **Real-time market event triggers** (breaking news triggers immediate cycle)
