# Ticker Accuracy Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an autonomous ticker accuracy agent with a dedicated backend module, FastAPI endpoints, and a dashboard drawer.

**Architecture:** Hybrid agent — LLM (quick_thinking_llm) decides strategy each cycle; deterministic engine executes, scores tickers via existing run data, and persists state to disk. The agent module is a new `web/server/ticker_agent/` sub-package.

**Tech Stack:** Python FastAPI, TypeScript/React (Tailwind, zustand, TanStack Query), existing background_runs orchestrator, existing LLM client.

## Global Constraints

- All timestamps in UTC ISO-8601 with `Z` suffix
- Storage under `~/.tradingagents/data/ticker_agent/`
- Reuse existing `quick_thinking_llm` for strategy calls (not a new model)
- All new API endpoints under `/api/ticker-agent/*`
- All new frontend state in `store/ui.ts` (non-persisted for drawer open state)
- Tests with mocks for heavy LLM/scoring operations

---

### Task 1: Backend Module Structure + Storage + Scorer

**Files:**
- Create: `web/server/ticker_agent/__init__.py`
- Create: `web/server/ticker_agent/scorer.py`
- Modify: `web/server/storage.py`
- Create: `web/server/ticker_agent/tests/__init__.py`
- Create: `web/server/ticker_agent/tests/test_scorer.py`

**Interfaces:**
- Consumes: `storage.list_ticker_runs(ticker, limit)`, `storage.walk_data_dir()`, `storage.read_json(path)`
- Produces: `scorer.compute_ticker_scores(all_run_dirs, min_samples=3) -> dict[str, TickerScore]`, `scorer.compute_score_for_ticker(ticker) -> TickerScore | None`

- [ ] **Step 1: Create `web/server/ticker_agent/__init__.py`**

```python
"""Ticker Accuracy Agent — autonomous ticker discovery and accuracy scoring."""
from __future__ import annotations
```

- [ ] **Step 2: Add storage paths to `web/server/storage.py`**

```python
# At end of file, before any existing EOF:

TICKER_AGENT_DIR = "ticker_agent"

def ticker_agent_dir() -> Path:
    p = data_dir() / TICKER_AGENT_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p

def ticker_agent_path(name: str) -> Path:
    return ticker_agent_dir() / name
```

- [ ] **Step 3: Write the failing test for scorer**

File `web/server/ticker_agent/tests/test_scorer.py`:

```python
"""Tests for the accuracy scorer."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from web.server.ticker_agent.scorer import compute_ticker_scores, compute_score_for_ticker, TickerScore


def _fake_run(ticker: str, date: str, status: str, action: str, start_price: float, end_price: float) -> dict:
    return {
        "id": f"{ticker}_{date}_001",
        "ticker": ticker,
        "started_at": f"{date}T10:00:00Z",
        "status": status,
        "decision_action": action,
        "decision_target": None,
        "start_price": start_price,
        "end_price": end_price,
    }


def test_compute_ticker_scores_aggregates_correctly():
    runs = [
        _fake_run("NVDA", "2024-01-01", "done", "BUY", 100.0, 110.0),   # right (went up)
        _fake_run("NVDA", "2024-01-02", "done", "SELL", 100.0, 90.0),   # right (went down)
        _fake_run("NVDA", "2024-01-03", "done", "BUY", 100.0, 95.0),    # wrong (went down)
        _fake_run("AAPL", "2024-01-01", "done", "BUY", 100.0, 105.0),   # right
    ]
    scores = compute_ticker_scores({"NVDA": [r for r in runs if r["ticker"] == "NVDA"],
                                    "AAPL": [r for r in runs if r["ticker"] == "AAPL"]})
    nvda = scores["NVDA"]
    assert nvda.total_runs == 3
    assert nvda.right == 2
    assert nvda.wrong == 1
    assert nvda.win_rate == 2 / 3
    aapl = scores["AAPL"]
    assert aapl.total_runs == 1
    assert aapl.right == 1
    assert aapl.wrong == 0
    assert aapl.win_rate == 1.0


def test_compute_ticker_scores_filters_below_min_samples():
    runs = [{"ticker": "NVDA", "runs": _fake_run("NVDA", "2024-01-01", "done", "BUY", 100.0, 110.0)}]
    scores = compute_ticker_scores({"NVDA": runs}, min_samples=3)
    assert len(scores) == 0


def test_compute_score_for_ticker_returns_none_for_no_runs():
    result = compute_score_for_ticker("UNKNOWN", [])
    assert result is None
```

- [ ] **Step 4: Run to verify failure**

```powershell
.venv\Scripts\activate; if ($?) { uv run pytest web/server/ticker_agent/tests/test_scorer.py -v }
```
Expected: ImportError for web.server.ticker_agent.scorer

- [ ] **Step 5: Implement scorer.py**

```python
"""Accuracy scoring engine for the ticker accuracy agent.

Computes right/wrong verdicts for each ticker from completed runs.
Reuses the same verdict logic as the existing frontend verdicts.ts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TickerScore:
    ticker: str
    total_runs: int
    right: int
    wrong: int
    unknown: int
    win_rate: float | None
    avg_confidence: float | None
    target_hit_rate: float | None
    trending_accuracy: float | None
    last_evaluated: str | None
    sector: str | None = None


def _classify_run_outcome(run: dict) -> str | None:
    """Classify a single run as 'right', 'wrong', or 'unknown'.
    
    Simplified verdict logic matching verdicts.ts:
    - BUY: right if end_price > start_price
    - SELL: right if end_price < start_price
    - HOLD: always 'unknown' without a threshold check
    - Unknown action or missing prices: 'unknown'
    """
    action = run.get("decision_action")
    start_price = run.get("start_price")
    end_price = run.get("end_price")
    if not action or start_price is None or end_price is None:
        return None
    if action == "BUY":
        return "right" if end_price > start_price else "wrong"
    elif action == "SELL":
        return "right" if end_price < start_price else "wrong"
    elif action == "HOLD":
        return "unknown"
    return None


def compute_ticker_scores(
    runs_by_ticker: dict[str, list[dict]],
    min_samples: int = 3,
) -> dict[str, TickerScore]:
    """Compute accuracy scores for all tickers with enough data.
    
    Args:
        runs_by_ticker: Dict mapping ticker to list of run dicts.
        min_samples: Minimum number of runs required to score.
    
    Returns:
        Dict mapping ticker to TickerScore, sorted by win_rate desc.
    """
    scores: dict[str, TickerScore] = {}
    for ticker, runs in runs_by_ticker.items():
        score = compute_score_for_ticker(ticker, runs)
        if score is not None and score.total_runs >= min_samples:
            scores[ticker] = score
    
    sorted_scores = dict(
        sorted(scores.items(), key=lambda x: (x[1].win_rate or -1, x[1].total_runs), reverse=True)
    )
    return sorted_scores


def compute_score_for_ticker(ticker: str, runs: list[dict]) -> TickerScore | None:
    """Compute accuracy score for a single ticker. Returns None if no completed runs."""
    completed = [r for r in runs if r.get("status") == "done"]
    if not completed:
        return None
    
    right = 0
    wrong = 0
    unknown = 0
    total_confidence = 0.0
    confidence_count = 0
    target_hits = 0
    target_total = 0
    
    for run in completed:
        outcome = _classify_run_outcome(run)
        if outcome == "right":
            right += 1
        elif outcome == "wrong":
            wrong += 1
        else:
            unknown += 1
        
        confidence = run.get("decision_confidence")
        if confidence is not None:
            total_confidence += float(confidence)
            confidence_count += 1
        
        target = run.get("decision_target")
        if target is not None and outcome in ("right", "wrong"):
            target_total += 1
            if outcome == "right":
                target_hits += 1
    
    total_scored = right + wrong
    win_rate = right / total_scored if total_scored > 0 else None
    avg_confidence = total_confidence / confidence_count if confidence_count > 0 else None
    target_hit_rate = target_hits / target_total if target_total > 0 else None
    
    # Trending: win rate of last 10 runs vs all-time
    recent = completed[-10:]
    recent_right = 0
    recent_total = 0
    for run in recent:
        o = _classify_run_outcome(run)
        if o == "right":
            recent_right += 1
            recent_total += 1
        elif o == "wrong":
            recent_total += 1
    trending = recent_right / recent_total if recent_total > 0 else None
    
    return TickerScore(
        ticker=ticker,
        total_runs=len(completed),
        right=right,
        wrong=wrong,
        unknown=unknown,
        win_rate=win_rate,
        avg_confidence=avg_confidence,
        target_hit_rate=target_hit_rate,
        trending_accuracy=trending,
        last_evaluated=completed[-1].get("started_at") if completed else None,
    )
```

- [ ] **Step 6: Run tests to verify**

```powershell
.venv\Scripts\activate; if ($?) { uv run pytest web/server/ticker_agent/tests/test_scorer.py -v }
```
Expected: 4 passed

- [ ] **Step 7: Commit**

```powershell
git add web/server/ticker_agent/ web/server/storage.py
git commit -m "feat: ticker agent module structure, storage paths, and scorer"
```

---

### Task 2: Universe Discovery

**Files:**
- Create: `web/server/ticker_agent/universe.py`
- Create: `web/server/ticker_agent/tests/test_universe.py`

**Interfaces:**
- Consumes: `storage.ticker_agent_path("universe_candidates.json")`, external yfinance API
- Produces: `discover_universe(config: UniverseConfig) -> list[str]`, `UniverseConfig` dataclass

- [ ] **Step 1: Write failing universe test**

```python
"""Tests for ticker universe discovery."""
from __future__ import annotations

from web.server.ticker_agent.universe import (
    UniverseConfig,
    merge_and_dedup,
    load_custom_universe,
)


def test_merge_and_dedup():
    sources = {
        "sp500": ["AAPL", "MSFT", "NVDA"],
        "watchlist": ["NVDA", "TSLA"],
        "custom": ["AAPL", "AMZN"],
    }
    merged = merge_and_dedup(sources)
    assert sorted(merged) == sorted(["AAPL", "MSFT", "NVDA", "TSLA", "AMZN"])


def test_load_custom_universe_missing_file_returns_empty(tmp_path):
    result = load_custom_universe(tmp_path / "nonexistent.json")
    assert result == []


def test_load_custom_universe_reads_json(tmp_path):
    f = tmp_path / "universe.json"
    f.write_text('["AAPL", "MSFT", "NVDA"]')
    result = load_custom_universe(str(f))
    assert sorted(result) == sorted(["AAPL", "MSFT", "NVDA"])
```

- [ ] **Step 2: Run to verify failure**

```powershell
.venv\Scripts\activate; if ($?) { uv run pytest web/server/ticker_agent/tests/test_universe.py -v }
```
Expected: ImportError

- [ ] **Step 3: Implement universe.py**

```python
"""Ticker universe discovery for the ticker accuracy agent.

Provides ticker candidates from multiple sources:
- S&P 500 constituents (from a bundled CSV or yfinance)
- Yahoo Finance sector ETFs top holdings
- Custom universe file (user-supplied JSON)
- Cross-references from existing ticker analysis
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class UniverseConfig:
    sp500_enabled: bool = True
    yahoo_sectors_enabled: bool = True
    custom_file_path: str | None = None
    watchlist_tickers: list[str] = field(default_factory=list)


_SP500_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "BRK.B", "LLY",
    "AVGO", "JPM", "V", "TSLA", "XOM", "UNH", "MA", "PG", "JNJ", "COST", "HD",
    "MRK", "CVX", "ABBV", "BAC", "CRM", "WMT", "NFLX", "AMD", "KO", "PEP",
    "ADBE", "TMO", "DIS", "WFC", "CSCO", "MCD", "ABT", "GE", "DHR", "VZ",
    "ACN", "CMCSA", "NKE", "LIN", "TXN", "PM", "IBM", "UPS", "QCOM", "AMGN",
    "BX", "LOW", "BA", "CAT", "RTX", "SPGI", "INTU", "GS", "MS", "BLK",
    "PLD", "DE", "SYK", "SCHW", "C", "UNP", "AMT", "HON", "ISRG", "ELV",
    "ANET", "TMUS", "VRTX", "TJX", "LRCX", "PANW", "ETN", "MDT", "SO", "DUK",
    "NEE", "MO", "MMC", "PGR", "ICE", "ADI", "CL", "BSX", "TT", "ZTS",
    "CMG", "ORLY", "AON", "MCO", "APD", "GD", "EQIX", "SHW", "BDX",
]


_SP500_SAMPLE_SIZE = 50  # Use top 50 by market cap to keep universe manageable


def _get_sp500_tickers() -> list[str]:
    """Return a subset of S&P 500 tickers."""
    return _SP500_TICKERS[:_SP500_SAMPLE_SIZE]


def _get_sector_etf_tickers() -> list[str]:
    """Return tickers from major sector ETFs (XLK, XLF, etc.).
    
    In v1, returns a curated set of well-known sector representatives.
    Future: fetch top holdings from yfinance dynamically.
    """
    # Major sector ETFs top holdings — representatives per sector
    return [
        # Technology (XLK)
        "AAPL", "MSFT", "NVDA", "AVGO", "CRM", "CSCO", "ADBE", "AMD", "INTC",
        # Financials (XLF)
        "JPM", "BAC", "WFC", "GS", "MS", "C", "SCHW", "BLK", "AXP",
        # Healthcare (XLV)
        "LLY", "UNH", "JNJ", "MRK", "ABBV", "TMO", "ABT", "SYK", "VRTX",
        # Energy (XLE)
        "XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "OXY", "VLO",
        # Consumer Discretionary (XLY)
        "AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "TJX", "SBUX", "GM",
        # Industrial (XLI)
        "GE", "CAT", "BA", "UNP", "HON", "RTX", "ETN", "DE", "UPS",
    ]


def load_custom_universe(file_path: str | Path | None) -> list[str]:
    """Load tickers from a custom JSON file (list of ticker strings)."""
    if not file_path:
        return []
    p = Path(file_path)
    if not p.exists():
        log.warning("Custom universe file not found: %s", p)
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [t.upper().strip() for t in data if isinstance(t, str) and t.strip()]
        log.warning("Custom universe file must contain a JSON array of strings, got %s", type(data))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to read custom universe file %s: %s", p, e)
    return []


def merge_and_dedup(sources: dict[str, list[str]]) -> list[str]:
    """Merge multiple ticker sources, dedup by uppercase ticker."""
    seen: set[str] = set()
    merged: list[str] = []
    for source_name, tickers in sources.items():
        for t in tickers:
            upper = t.upper().strip()
            if upper and upper not in seen:
                seen.add(upper)
                merged.append(upper)
    return merged


def discover_universe(config: UniverseConfig) -> list[str]:
    """Build the complete ticker universe from all enabled sources."""
    sources: dict[str, list[str]] = {}
    
    if config.sp500_enabled:
        sources["sp500"] = _get_sp500_tickers()
    if config.yahoo_sectors_enabled:
        sources["sectors"] = _get_sector_etf_tickers()
    if config.watchlist_tickers:
        sources["watchlist"] = config.watchlist_tickers
    if config.custom_file_path:
        custom = load_custom_universe(config.custom_file_path)
        if custom:
            sources["custom"] = custom
    
    merged = merge_and_dedup(sources)
    log.info("Discovered %d unique tickers from %d sources", len(merged), len(sources))
    return merged
```

- [ ] **Step 4: Run tests to verify**

```powershell
.venv\Scripts\activate; if ($?) { uv run pytest web/server/ticker_agent/tests/test_universe.py -v }
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```powershell
git add web/server/ticker_agent/universe.py web/server/ticker_agent/tests/test_universe.py
git commit -m "feat: ticker universe discovery (S&P 500, sectors, custom file)"
```

---

### Task 3: Capabilities Inventory + Missing Capabilities

**Files:**
- Create: `web/server/ticker_agent/capabilities.py`
- Create: `web/server/ticker_agent/missing_capabilities.py`
- Create: `web/server/ticker_agent/tests/test_capabilities.py`
- Create: `web/server/ticker_agent/tests/test_missing_capabilities.py`

**Interfaces:**
- Produces: `capabilities.discover_api_capabilities() -> list[ApiCapability]`, `missing_capabilities.log_missing(cap_name, description)`, `missing_capabilities.read_missing() -> list[MissingCapability]`

- [ ] **Step 1: Write failing tests for capabilities**

```python
"""Tests for API capabilities inventory."""
from __future__ import annotations

from web.server.ticker_agent.capabilities import discover_api_capabilities, ApiCapability


def test_discover_returns_list():
    caps = discover_api_capabilities()
    assert len(caps) > 0
    assert all(isinstance(c, ApiCapability) for c in caps)


def test_discover_includes_core_endpoints():
    caps = discover_api_capabilities()
    paths = {c.path for c in caps}
    assert "/api/runs" in paths
    assert "/api/watchlist" in paths
    assert "/api/tickers/{ticker}/history" in paths
```

```python
"""Tests for missing capabilities tracking."""
from __future__ import annotations

import json
from pathlib import Path
from web.server.ticker_agent.missing_capabilities import (
    log_missing,
    read_missing,
    MissingCapability,
)


def test_log_and_read_missing(tmp_path):
    f = tmp_path / "missing_capabilities.jsonl"
    log_missing("sector_etf_flows", "Track ETF inflows per sector", file_path=str(f))
    log_missing("options_flow", "Monitor unusual options activity", file_path=str(f))
    entries = read_missing(file_path=str(f))
    assert len(entries) == 2
    assert entries[0].name == "sector_etf_flows"


def test_read_missing_empty_file(tmp_path):
    f = tmp_path / "missing_capabilities.jsonl"
    f.write_text("")
    assert read_missing(file_path=str(f)) == []


def test_read_missing_file_not_exist(tmp_path):
    assert read_missing(file_path=str(tmp_path / "nonexistent.jsonl")) == []
```

- [ ] **Step 2: Run to verify failure**

```powershell
.venv\Scripts\activate; if ($?) { uv run pytest web/server/ticker_agent/tests/test_capabilities.py web/server/ticker_agent/tests/test_missing_capabilities.py -v }
```
Expected: ImportError

- [ ] **Step 3: Implement capabilities.py**

```python
"""API capabilities inventory for the ticker accuracy agent.

Provides a dynamic list of all backend API endpoints the agent can use,
so the agent knows its capabilities and can detect missing ones.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ApiCapability:
    path: str
    method: str
    purpose: str
    available: bool = True


_DEFINED_CAPABILITIES: list[ApiCapability] = [
    ApiCapability("/api/runs", "POST", "Start a new analysis run for a ticker"),
    ApiCapability("/api/runs/{run_id}", "GET", "Get run details including events and LLM calls"),
    ApiCapability("/api/runs/{run_id}/cancel", "POST", "Cancel a running run"),
    ApiCapability("/api/runs/{run_id}/resume", "POST", "Resume a failed run"),
    ApiCapability("/api/runs/delete-bulk", "POST", "Delete multiple runs"),
    ApiCapability("/api/watchlist", "GET", "List all watchlist tickers"),
    ApiCapability("/api/watchlist", "POST", "Add a ticker to the watchlist"),
    ApiCapability("/api/watchlist/{ticker}", "DELETE", "Remove a ticker from the watchlist"),
    ApiCapability("/api/tickers/{ticker}/runs", "GET", "List runs for a specific ticker"),
    ApiCapability("/api/tickers/{ticker}/history", "GET", "Get price history + runs for a ticker"),
    ApiCapability("/api/prices", "GET", "Get current prices for all watchlist tickers"),
    ApiCapability("/api/background-runs", "POST", "Schedule historical backtests for a ticker"),
    ApiCapability("/api/background-runs", "GET", "List background run jobs"),
    ApiCapability("/api/background-runs/{job_id}/cancel", "POST", "Cancel a background job"),
    ApiCapability("/api/background-runs/{job_id}/pause", "POST", "Pause a background job"),
    ApiCapability("/api/background-runs/{job_id}/resume", "POST", "Resume a paused background job"),
    ApiCapability("/api/config", "GET", "Get app configuration"),
    ApiCapability("/api/config", "PUT", "Update app configuration"),
    ApiCapability("/api/config/models", "GET", "Get current LLM model configuration"),
    ApiCapability("/api/health", "GET", "Health check endpoint"),
]


def discover_api_capabilities() -> list[ApiCapability]:
    """Return the list of API capabilities available to the agent."""
    return _DEFINED_CAPABILITIES.copy()


def get_capability_by_path(path: str) -> ApiCapability | None:
    """Find a capability by its path pattern."""
    for cap in _DEFINED_CAPABILITIES:
        if cap.path == path:
            return cap
    return None
```

- [ ] **Step 4: Implement missing_capabilities.py**

```python
"""Missing capabilities tracking for the ticker accuracy agent.

Logs capabilities the agent identifies as missing so the user
can review and request implementation.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class MissingCapability:
    name: str
    description: str
    suggested_endpoint: str | None = None
    logged_at: str | None = None


def _default_path() -> str:
    from web.server import storage
    return str(storage.ticker_agent_path("missing_capabilities.jsonl"))


def log_missing(
    name: str,
    description: str,
    suggested_endpoint: str | None = None,
    file_path: str | None = None,
) -> None:
    """Log a missing capability to the append-only JSONL file."""
    path = Path(file_path or _default_path())
    entry = {
        "name": name,
        "description": description,
        "suggested_endpoint": suggested_endpoint,
        "logged_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        log.warning("Failed to log missing capability %s: %s", name, e)


def read_missing(file_path: str | None = None) -> list[MissingCapability]:
    """Read all logged missing capabilities, most recent first."""
    path = Path(file_path or _default_path())
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        entries: list[MissingCapability] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                entries.append(MissingCapability(
                    name=data.get("name", "unknown"),
                    description=data.get("description", ""),
                    suggested_endpoint=data.get("suggested_endpoint"),
                    logged_at=data.get("logged_at"),
                ))
            except json.JSONDecodeError:
                continue
        # Most recent first
        entries.reverse()
        return entries
    except OSError as e:
        log.warning("Failed to read missing capabilities: %s", e)
        return []
```

- [ ] **Step 5: Run tests to verify**

```powershell
.venv\Scripts\activate; if ($?) { uv run pytest web/server/ticker_agent/tests/test_capabilities.py web/server/ticker_agent/tests/test_missing_capabilities.py -v }
```
Expected: 5 passed

- [ ] **Step 6: Commit**

```powershell
git add web/server/ticker_agent/capabilities.py web/server/ticker_agent/missing_capabilities.py web/server/ticker_agent/tests/
git commit -m "feat: capabilities inventory and missing capabilities tracking"
```

---

### Task 4: Agent Memory + Config Storage

**Files:**
- Create: `web/server/ticker_agent/memory.py`
- Create: `web/server/ticker_agent/config.py`
- Create: `web/server/ticker_agent/tests/test_memory.py`
- Create: `web/server/ticker_agent/tests/test_config.py`

**Interfaces:**
- Produces: `memory.read_memory(limit=10) -> list[dict]`, `memory.append_memory(entry: dict)`, `config.AgentConfig` dataclass, `config.load_config() -> AgentConfig`, `config.save_config(cfg: AgentConfig)`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for agent memory."""
from __future__ import annotations

from web.server.ticker_agent.memory import read_memory, append_memory


def test_append_and_read_memory(tmp_path):
    f = tmp_path / "agent_memory.jsonl"
    append_memory({"cycle": 1, "conclusions": ["test"]}, file_path=str(f))
    append_memory({"cycle": 2, "conclusions": ["test2"]}, file_path=str(f))
    entries = read_memory(limit=10, file_path=str(f))
    assert len(entries) == 2
    assert entries[0]["cycle"] == 2  # most recent first


def test_read_memory_respects_limit(tmp_path):
    f = tmp_path / "agent_memory.jsonl"
    for i in range(5):
        append_memory({"cycle": i + 1}, file_path=str(f))
    entries = read_memory(limit=3, file_path=str(f))
    assert len(entries) == 3
    assert entries[0]["cycle"] == 5  # most recent first


def test_read_memory_empty(tmp_path):
    assert read_memory(limit=10, file_path=str(tmp_path / "empty.jsonl")) == []
```

```python
"""Tests for agent config."""
from __future__ import annotations

from web.server.ticker_agent.config import AgentConfig, load_config, save_config


def test_load_config_defaults(tmp_path):
    f = tmp_path / "agent_config.json"
    cfg = load_config(file_path=str(f))
    assert cfg.min_samples == 3
    assert cfg.schedule_interval_h == 6
    assert cfg.max_tickers_per_cycle == 20
    assert cfg.sp500_enabled is True
    assert cfg.yahoo_sectors_enabled is True


def test_save_and_load_roundtrip(tmp_path):
    f = tmp_path / "agent_config.json"
    cfg = AgentConfig(min_samples=5, schedule_interval_h=12)
    save_config(cfg, file_path=str(f))
    loaded = load_config(file_path=str(f))
    assert loaded.min_samples == 5
    assert loaded.schedule_interval_h == 12
```

- [ ] **Step 2: Run to verify failure**

Expected: ImportError

- [ ] **Step 3: Implement memory.py**

```python
"""Agent memory — persistent conclusions log for the ticker accuracy agent.

Each cycle, the agent appends structured conclusions. On the next cycle,
the last N entries are loaded and fed into the LLM prompt for context.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def _default_path() -> str:
    from web.server import storage
    return str(storage.ticker_agent_path("agent_memory.jsonl"))


def append_memory(entry: dict, file_path: str | None = None) -> None:
    """Append a memory entry to the JSONL file."""
    path = Path(file_path or _default_path())
    entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        log.warning("Failed to append memory: %s", e)


def read_memory(limit: int = 10, file_path: str | None = None) -> list[dict]:
    """Read the most recent N memory entries, newest first."""
    path = Path(file_path or _default_path())
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        entries: list[dict] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        entries.reverse()
        return entries[:limit]
    except OSError as e:
        log.warning("Failed to read memory: %s", e)
        return []
```

- [ ] **Step 4: Implement config.py**

```python
"""Agent configuration — persisted settings for the ticker accuracy agent."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    min_samples: int = 3
    schedule_interval_h: int = 6
    max_tickers_per_cycle: int = 20
    sp500_enabled: bool = True
    yahoo_sectors_enabled: bool = True
    custom_universe_path: str | None = None


def _default_path() -> str:
    from web.server import storage
    return str(storage.ticker_agent_path("config.json"))


def load_config(file_path: str | None = None) -> AgentConfig:
    """Load agent config from disk, returning defaults if file missing."""
    path = Path(file_path or _default_path())
    if not path.exists():
        return AgentConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AgentConfig(**{k: v for k, v in data.items() if k in AgentConfig.__dataclass_fields__})
    except (json.JSONDecodeError, OSError, TypeError) as e:
        log.warning("Failed to load agent config: %s", e)
        return AgentConfig()


def save_config(cfg: AgentConfig, file_path: str | None = None) -> None:
    """Save agent config to disk."""
    path = Path(file_path or _default_path())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    except OSError as e:
        log.warning("Failed to save agent config: %s", e)


def config_to_dict(cfg: AgentConfig) -> dict:
    return asdict(cfg)
```

- [ ] **Step 5: Run tests to verify**

```powershell
.venv\Scripts\activate; if ($?) { uv run pytest web/server/ticker_agent/tests/ -v }
```
Expected: All tests pass

- [ ] **Step 6: Commit**

```powershell
git add web/server/ticker_agent/memory.py web/server/ticker_agent/config.py web/server/ticker_agent/tests/
git commit -m "feat: agent memory and config persistence"
```

---

### Task 5: Orchestrator with LLM Strategy

**Files:**
- Create: `web/server/ticker_agent/orchestrator.py`
- Create: `web/server/ticker_agent/tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `scorer.compute_ticker_scores()`, `universe.discover_universe()`, `memory.read_memory()`, `memory.append_memory()`, `missing_capabilities.log_missing()`, `config.load_config()`, `background_runs.start()`
- Produces: `orchestrator.run_cycle() -> dict`, `orchestrator.start_background_loop()`, `orchestrator.stop_background_loop()`

- [ ] **Step 1: Write failing orchestrator test**

```python
"""Tests for the agent orchestrator."""
from __future__ import annotations

from unittest.mock import Mock, patch
from web.server.ticker_agent.orchestrator import run_cycle, _build_strategy_prompt


def test_build_strategy_prompt_includes_context():
    context = {
        "sector_performance": {"Technology": 0.05, "Energy": -0.02},
        "watchlist_scores": {},
        "coverage_gaps": ["NVDA", "AMD"],
        "universe_size": 100,
        "memory": [],
    }
    prompt = _build_strategy_prompt(context)
    assert "Technology" in prompt
    assert "NVDA" in prompt
    assert "Energy" in prompt


@patch("web.server.ticker_agent.orchestrator._call_llm_strategy")
@patch("web.server.ticker_agent.orchestrator._gather_context")
@patch("web.server.ticker_agent.orchestrator._execute_plan")
@patch("web.server.ticker_agent.orchestrator._rank_and_store")
@patch("web.server.ticker_agent.orchestrator._write_memory")
@patch("web.server.ticker_agent.orchestrator._self_improve")
def test_run_cycle_full_flow(mock_improve, mock_memory, mock_rank, mock_execute, mock_context, mock_llm):
    mock_context.return_value = {"test": "context"}
    mock_llm.return_value = {"investigation_plan": [], "sectors_to_watch": [], "reasoning_summary": "test"}
    
    result = run_cycle()
    
    mock_context.assert_called_once()
    mock_llm.assert_called_once()
    mock_execute.assert_called_once()
    mock_rank.assert_called_once()
    mock_memory.assert_called_once()
    mock_improve.assert_called_once()
    assert result["status"] == "completed"
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement orchestrator.py**

```python
"""Agent orchestrator — the 7-step cycle loop for the ticker accuracy agent.

The orchestrator runs as a background thread on a configurable schedule.
Each cycle:
1. READ MEMORY — load past conclusions from agent_memory.jsonl
2. GATHER CONTEXT — sector performance, accuracy scores, gaps, universe
3. LLM STRATEGY CALL — decide which tickers to investigate
4. EXECUTE — schedule background runs for chosen tickers
5. RANK & REFLECT — recompute accuracy, sort, persist
6. WRITE MEMORY — append conclusions to memory
7. SELF-IMPROVEMENT — ask what's missing, log capabilities
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from web.server.ticker_agent.universe import discover_universe, UniverseConfig
from web.server.ticker_agent.memory import read_memory, append_memory
from web.server.ticker_agent.missing_capabilities import log_missing
from web.server.ticker_agent.capabilities import discover_api_capabilities
from web.server.ticker_agent.config import load_config, save_config, config_to_dict

log = logging.getLogger(__name__)

# Module-level state
_running = False
_thread: threading.Thread | None = None
_lock = threading.Lock()
_current_status = "idle"
_last_cycle_at: str | None = None
_next_cycle_at: str | None = None
_cycles_completed = 0
_activity_log: list[dict] = []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def status() -> dict:
    with _lock:
        return {
            "status": _current_status,
            "last_cycle_at": _last_cycle_at,
            "next_cycle_at": _next_cycle_at,
            "cycles_completed": _cycles_completed,
        }


def activity_log(limit: int = 10) -> list[dict]:
    with _lock:
        return list(_activity_log[-limit:])


def _gather_context() -> dict:
    """Collect sector performance, scores, gaps, and universe for the LLM."""
    from web.server import queries
    from web.server import storage as _storage
    
    cfg = load_config()
    
    # Watchlist
    watchlist = queries.read_watchlist()
    watchlist_tickers = [w["ticker"] for w in watchlist]
    
    # Broader universe
    universe_cfg = UniverseConfig(
        sp500_enabled=cfg.sp500_enabled,
        yahoo_sectors_enabled=cfg.yahoo_sectors_enabled,
        custom_file_path=cfg.custom_universe_path,
        watchlist_tickers=watchlist_tickers,
    )
    universe = discover_universe(universe_cfg)
    
    # Existing accuracy scores
    from .scorer import compute_ticker_scores
    runs_by_ticker: dict[str, list[dict]] = {}
    for td in _storage.walk_data_dir():
        ticker = td.name
        runs = list(_storage.list_ticker_runs(ticker, limit=100))
        if runs:
            runs_by_ticker[ticker] = runs
    scores = compute_ticker_scores(runs_by_ticker, min_samples=cfg.min_samples)
    
    # Coverage gaps: tickers in universe with < min_samples completed runs
    coverage_gaps = [
        t for t in universe
        if t not in scores
    ][:50]  # limit to 50 gaps
    
    # Memory
    memory = read_memory(limit=10)
    
    return {
        "watchlist_size": len(watchlist_tickers),
        "watchlist_tickers": watchlist_tickers,
        "universe_size": len(universe),
        "universe": universe[:30],  # sample for prompt
        "scored_tickers": len(scores),
        "top_scores": dict(list(scores.items())[:10]),
        "coverage_gaps": coverage_gaps[:20],
        "memory": memory,
        "sector_performance": _get_sector_performance(watchlist_tickers),
    }


def _get_sector_performance(tickers: list[str]) -> dict[str, float]:
    """Simple sector-based grouping. In v1, returns a placeholder.
    
    Future: fetch yfinance price changes grouped by sector.
    """
    # Placeholder — returns empty dict, LLM will work without it
    return {}


def _build_strategy_prompt(context: dict) -> str:
    """Build the LLM prompt for the strategy decision."""
    scores_text = ""
    if context.get("top_scores"):
        scores_text = "Current accuracy scores:\n" + json.dumps(context["top_scores"], indent=2)
    
    gaps_text = ""
    if context.get("coverage_gaps"):
        gaps_text = "Tickers needing more data:\n" + "\n".join(f"- {t}" for t in context["coverage_gaps"])
    
    memory_text = ""
    if context.get("memory"):
        memory_text = "Past learning conclusions:\n" + json.dumps(context["memory"], indent=2)
    
    universe_sample = context.get("universe", [])
    universe_text = "Broader universe candidates:\n" + "\n".join(f"- {t}" for t in universe_sample) if universe_sample else ""
    
    return f"""You are the Ticker Accuracy Agent for a trading analysis system.
Your goal is to find tickers where the system's predictions are most accurate.

Current state:
- Watchlist size: {context.get('watchlist_size', 0)}
- Universe candidates: {context.get('universe_size', 0)}
- Scored tickers: {context.get('scored_tickers', 0)}

{scores_text}

{gaps_text}

{universe_text}

{memory_text}

Based on this information:
1. Which tickers should we investigate next and why?
2. Which sectors look promising?
3. What patterns from past cycles should guide our choices?
4. How many backtests should we schedule per ticker?

Return your plan as JSON:
{{
  "investigation_plan": [
    {{"ticker": "NVDA", "priority": "high", "rationale": "description", "backtests_needed": 5}}
  ],
  "sectors_to_watch": ["Semiconductors"],
  "reasoning_summary": "2-3 sentence reasoning",
  "conclusions": ["learning point 1", "learning point 2", "learning point 3"]
}}"""


def _call_llm_strategy(prompt: str) -> dict:
    """Call the quick-thinking LLM for a strategy decision.
    
    Returns a dict with investigation_plan, sectors_to_watch, reasoning_summary, conclusions.
    Falls back to empty plan on LLM failure.
    """
    try:
        from tradingagents.llm_clients import create_llm_client
        from tradingagents.default_config import DEFAULT_CONFIG
        
        config = load_config()
        llm_config = DEFAULT_CONFIG.copy()
        
        client = create_llm_client(
            provider=llm_config.get("llm_provider", "openai"),
            model=llm_config.get("quick_think_llm", "gpt-4o-mini"),
        )
        llm = client.get_llm()
        
        response = llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        
        # Try to parse JSON from response
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        log.warning("LLM strategy call failed: %s", e)
    
    return {"investigation_plan": [], "sectors_to_watch": [], "reasoning_summary": "LLM call failed", "conclusions": []}


def _execute_plan(plan: dict) -> dict:
    """Schedule background runs for tickers in the investigation plan."""
    from web.server import background_runs
    from datetime import date, timedelta
    
    scheduled = []
    for item in plan.get("investigation_plan", []):
        ticker = item.get("ticker", "").upper()
        backtests_needed = item.get("backtests_needed", 5)
        if not ticker:
            continue
        
        try:
            # Schedule backtests over the last N business days
            today = date.today()
            date_to = today.isoformat()
            date_from = (today - timedelta(days=backtests_needed * 2)).isoformat()
            
            background_runs.start(
                ticker=ticker,
                date_from=date_from,
                date_to=date_to,
                every="1d",
                parallel=min(backtests_needed, 4),
            )
            scheduled.append(ticker)
        except (ValueError, KeyError) as e:
            log.warning("Failed to schedule background run for %s: %s", ticker, e)
    
    return {"scheduled": scheduled}


def _rank_and_store(context: dict) -> dict:
    """Recompute accuracy scores from all existing runs and store them."""
    from web.server import storage as _storage
    from .scorer import compute_ticker_scores
    
    cfg = load_config()
    runs_by_ticker: dict[str, list[dict]] = {}
    for td in _storage.walk_data_dir():
        ticker = td.name
        runs = list(_storage.list_ticker_runs(ticker, limit=200))
        if runs:
            runs_by_ticker[ticker] = runs
    
    scores = compute_ticker_scores(runs_by_ticker, min_samples=cfg.min_samples)
    
    # Store to agent_state.json
    state = {
        "status": "completed",
        "last_evaluated": _now_iso(),
        "scores": {t: {
            "win_rate": s.win_rate,
            "total_runs": s.total_runs,
            "right": s.right,
            "wrong": s.wrong,
            "avg_confidence": s.avg_confidence,
            "target_hit_rate": s.target_hit_rate,
            "trending_accuracy": s.trending_accuracy,
            "last_evaluated": s.last_evaluated,
        } for t, s in scores.items()},
    }
    
    from web.server import storage as _storage2
    state_path = _storage2.ticker_agent_path("agent_state.json")
    import json
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    
    return {"scored": len(scores), "top_ticker": next(iter(scores)) if scores else None}


def _write_memory(context: dict, llm_response: dict, execution_result: dict, scores_result: dict) -> None:
    """Write learning conclusions from this cycle to agent memory."""
    conclusions = llm_response.get("conclusions", [])
    if not conclusions:
        conclusions = [f"Cycle analyzed {execution_result.get('scheduled', [])} tickers"]
    
    entry = {
        "cycle": _cycles_completed + 1,
        "timestamp": _now_iso(),
        "conclusions": conclusions,
        "strategies_validated": llm_response.get("sectors_to_watch", []),
        "tickers_scheduled": execution_result.get("scheduled", []),
        "tickers_scored": scores_result.get("scored", 0),
        "reasoning": llm_response.get("reasoning_summary", ""),
    }
    append_memory(entry)
    
    # Also log to activity log
    with _lock:
        _activity_log.append({
            "cycle": _cycles_completed + 1,
            "started_at": _last_cycle_at,
            "tickers_analyzed": len(context.get("universe", [])),
            "backtests_scheduled": len(execution_result.get("scheduled", [])),
            "summary": llm_response.get("reasoning_summary", ""),
        })


def _self_improve(context: dict) -> None:
    """Ask what would make the agent better and log missing capabilities."""
    caps = discover_api_capabilities()
    available_paths = {c.path for c in caps}
    
    # Identify common gaps
    desired_capabilities = [
        ("sector_etf_flows", "Track ETF capital inflows per sector for sector rotation detection", "/api/sectors/flows"),
        ("options_flow", "Monitor unusual options activity as a leading indicator", "/api/options/unusual"),
        ("insider_trading_aggregator", "Aggregate insider trading patterns across tickers", "/api/insider/aggregate"),
        ("earnings_calendar", "Earnings dates and surprise history for event-driven analysis", "/api/calendar/earnings"),
        ("sector_performance_api", "Real-time sector performance data (XLK, XLF, etc.)", "/api/sectors/performance"),
    ]
    
    for name, description, endpoint in desired_capabilities:
        if endpoint not in available_paths:
            log_missing(name, description, suggested_endpoint=endpoint)


def run_cycle() -> dict:
    """Execute one full agent cycle."""
    global _current_status, _last_cycle_at, _cycles_completed
    
    with _lock:
        _current_status = "running"
        _last_cycle_at = _now_iso()
    
    try:
        # Step 1 & 2: READ MEMORY + GATHER CONTEXT (merged for simplicity)
        context = _gather_context()
        
        # Step 3: LLM STRATEGY
        prompt = _build_strategy_prompt(context)
        llm_response = _call_llm_strategy(prompt)
        
        # Step 4: EXECUTE
        execution_result = _execute_plan(llm_response)
        
        # Step 5: RANK & REFLECT
        scores_result = _rank_and_store(context)
        
        # Step 6: WRITE MEMORY
        _write_memory(context, llm_response, execution_result, scores_result)
        
        # Step 7: SELF-IMPROVEMENT
        _self_improve(context)
        
        with _lock:
            _cycles_completed += 1
            _current_status = "idle"
        
        return {"status": "completed", "cycles_completed": _cycles_completed}
    
    except Exception as e:
        log.exception("Agent cycle failed")
        with _lock:
            _current_status = "error"
        return {"status": "error", "error": str(e)}


def _background_loop() -> None:
    """Background thread: run cycle on schedule."""
    global _next_cycle_at
    
    while _running:
        try:
            result = run_cycle()
            log.info("Agent cycle completed: %s", result)
        except Exception as e:
            log.exception("Agent cycle crashed: %s", e)
        
        cfg = load_config()
        interval_h = cfg.schedule_interval_h
        with _lock:
            _next_cycle_at = _now_iso()  # approximate
        
        # Sleep in 30s chunks so pause responds promptly
        for _ in range(interval_h * 120):
            if not _running:
                return
            time.sleep(30)


def start_background_loop() -> None:
    """Start the background agent loop thread."""
    global _running, _thread
    with _lock:
        if _running:
            return
        _running = True
        _thread = threading.Thread(target=_background_loop, daemon=True)
        _thread.start()
        log.info("Ticker accuracy agent background loop started")


def stop_background_loop() -> None:
    """Stop the background agent loop."""
    global _running
    with _lock:
        _running = False
    log.info("Ticker accuracy agent background loop stopping")


def pause() -> None:
    global _running
    with _lock:
        _running = False
        _current_status = "paused"


def resume() -> None:
    start_background_loop()
```

- [ ] **Step 4: Run tests**

```powershell
.venv\Scripts\activate; if ($?) { uv run pytest web/server/ticker_agent/tests/test_orchestrator.py -v }
```
Expected: Tests pass (mocked LLM calls)

- [ ] **Step 5: Commit**

```powershell
git add web/server/ticker_agent/orchestrator.py web/server/ticker_agent/tests/
git commit -m "feat: agent orchestrator with 7-step LLM-driven cycle"
```

---

### Task 6: FastAPI Router + App.py Integration

**Files:**
- Create: `web/server/ticker_agent/router.py`
- Modify: `web/server/app.py`

**Interfaces:**
- Produces: 10 FastAPI endpoints under `/api/ticker-agent/*`
- Registers router in `app.py`, starts orchestrator in lifespan

- [ ] **Step 1: Write failing API test**

In `web/server/tests/test_api.py`:

```python
def test_ticker_agent_status(client):
    r = client.get("/api/ticker-agent/status")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
```

- [ ] **Step 2: Implement router.py**

```python
"""FastAPI router for the ticker accuracy agent."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from web.server.ticker_agent import orchestrator
from web.server.ticker_agent.capabilities import discover_api_capabilities
from web.server.ticker_agent.missing_capabilities import read_missing
from web.server.ticker_agent.config import AgentConfig, load_config, save_config, config_to_dict
from web.server import storage

router = APIRouter(prefix="/api/ticker-agent", tags=["ticker-agent"])


class AgentConfigIn(BaseModel):
    min_samples: int | None = None
    schedule_interval_h: int | None = None
    max_tickers_per_cycle: int | None = None
    sp500_enabled: bool | None = None
    yahoo_sectors_enabled: bool | None = None
    custom_universe_path: str | None = None


@router.get("/status")
def get_status():
    return orchestrator.status()


@router.post("/run-now")
def run_now():
    result = orchestrator.run_cycle()
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "cycle failed"))
    return result


@router.post("/pause")
def pause():
    orchestrator.pause()
    return {"status": "paused"}


@router.post("/resume")
def resume():
    orchestrator.resume()
    return {"status": "running"}


@router.get("/accuracy-leaderboard")
def get_accuracy_leaderboard():
    state_path = storage.ticker_agent_path("agent_state.json")
    if not state_path.exists():
        return {"scores": {}, "last_evaluated": None}
    import json
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return {"scores": state.get("scores", {}), "last_evaluated": state.get("last_evaluated")}
    except (json.JSONDecodeError, OSError):
        return {"scores": {}, "last_evaluated": None}


@router.get("/activity-log")
def get_activity_log(limit: int = 10):
    return {"entries": orchestrator.activity_log(limit=limit)}


@router.get("/missing-capabilities")
def get_missing_capabilities():
    return {"capabilities": [vars(c) for c in read_missing()]}


@router.get("/capabilities")
def get_capabilities():
    return {"capabilities": [vars(c) for c in discover_api_capabilities()]}


@router.get("/config")
def get_agent_config():
    return config_to_dict(load_config())


@router.put("/config")
def update_agent_config(body: AgentConfigIn):
    cfg = load_config()
    update_data = body.model_dump(exclude_none=True)
    for k, v in update_data.items():
        setattr(cfg, k, v)
    save_config(cfg)
    return config_to_dict(cfg)
```

- [ ] **Step 3: Register router in app.py**

Add after the config section and before the static mount:

```python
# --- Ticker Accuracy Agent ---
from web.server.ticker_agent.router import router as ticker_agent_router
app.include_router(ticker_agent_router)
```

And in the `lifespan` context, after the background_runs auto-resume:

```python
    # Start the ticker accuracy agent background loop.
    from web.server.ticker_agent import orchestrator as _agent
    _agent.start_background_loop()
```

- [ ] **Step 4: Run API test**

```powershell
.venv\Scripts\activate; if ($?) { uv run pytest web/server/tests/test_api.py::test_ticker_agent_status -v }
```
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add web/server/ticker_agent/router.py web/server/app.py
git commit -m "feat: ticker agent API router and app.py integration"
```

---

### Task 7: Frontend — API Library + UI Store

**Files:**
- Modify: `web/frontend/src/lib/api.ts`
- Modify: `web/frontend/src/store/ui.ts`

- [ ] **Step 1: Add agent API types and fetchers to api.ts**

```typescript
// ---- Ticker Accuracy Agent ----

export interface AgentStatus {
  status: string;
  last_cycle_at: string | null;
  next_cycle_at: string | null;
  cycles_completed: number;
}

export interface TickerScoreEntry {
  win_rate: number | null;
  total_runs: number;
  right: number;
  wrong: number;
  avg_confidence: number | null;
  target_hit_rate: number | null;
  trending_accuracy: number | null;
  last_evaluated: string | null;
}

export interface AccuracyLeaderboardResponse {
  scores: Record<string, TickerScoreEntry>;
  last_evaluated: string | null;
}

export interface ActivityLogEntry {
  cycle: number;
  started_at: string;
  tickers_analyzed: number;
  backtests_scheduled: number;
  summary: string;
}

export interface ActivityLogResponse {
  entries: ActivityLogEntry[];
}

export interface ApiCapability {
  path: string;
  method: string;
  purpose: string;
  available: boolean;
}

export interface MissingCapability {
  name: string;
  description: string;
  suggested_endpoint: string | null;
  logged_at: string | null;
}

export interface AgentConfigData {
  min_samples: number;
  schedule_interval_h: number;
  max_tickers_per_cycle: number;
  sp500_enabled: boolean;
  yahoo_sectors_enabled: boolean;
  custom_universe_path: string | null;
}

export async function fetchAgentStatus(): Promise<AgentStatus> {
  return getJson<AgentStatus>("/api/ticker-agent/status");
}

export async function triggerAgentRun(): Promise<{ status: string }> {
  return postJson("/api/ticker-agent/run-now", {});
}

export async function pauseAgent(): Promise<{ status: string }> {
  return postJson("/api/ticker-agent/pause", {});
}

export async function resumeAgent(): Promise<{ status: string }> {
  return postJson("/api/ticker-agent/resume", {});
}

export async function fetchAccuracyLeaderboard(): Promise<AccuracyLeaderboardResponse> {
  return getJson<AccuracyLeaderboardResponse>("/api/ticker-agent/accuracy-leaderboard");
}

export async function fetchAgentActivityLog(limit: number = 10): Promise<ActivityLogResponse> {
  return getJson<ActivityLogResponse>(`/api/ticker-agent/activity-log?limit=${limit}`);
}

export async function fetchMissingCapabilities(): Promise<{ capabilities: MissingCapability[] }> {
  return getJson<{ capabilities: MissingCapability[] }>("/api/ticker-agent/missing-capabilities");
}

export async function fetchAgentCapabilities(): Promise<{ capabilities: ApiCapability[] }> {
  return getJson<{ capabilities: ApiCapability[] }>("/api/ticker-agent/capabilities");
}

export async function fetchAgentConfig(): Promise<AgentConfigData> {
  return getJson<AgentConfigData>("/api/ticker-agent/config");
}

export async function updateAgentConfig(updates: Partial<AgentConfigData>): Promise<AgentConfigData> {
  const res = await fetch("/api/ticker-agent/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}
```

- [ ] **Step 2: Add drawer state to ui.ts**

```typescript
// Add to UiState interface:
tickerAgentOpen: boolean;
setTickerAgentOpen: (open: boolean) => void;

// Add initial value to store:
tickerAgentOpen: false,

// Add setter:
setTickerAgentOpen: (open) => set({ tickerAgentOpen: open }),
```

- [ ] **Step 3: Commit**

```powershell
git add web/frontend/src/lib/api.ts web/frontend/src/store/ui.ts
git commit -m "feat: frontend API types and ui store for ticker agent"
```

---

### Task 8: Frontend — Ticker Accuracy Agent Drawer

**Files:**
- Create: `web/frontend/src/components/TickerAccuracyAgentDrawer.tsx`
- Create: `web/frontend/src/components/TickerAccuracyAgentDrawer.test.tsx`
- Modify: `web/frontend/src/App.tsx`

- [ ] **Step 1: Create the drawer component**

```tsx
import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useUi } from "../store/ui";
import {
  fetchAgentStatus,
  fetchAccuracyLeaderboard,
  fetchAgentActivityLog,
  fetchMissingCapabilities,
  fetchAgentCapabilities,
  triggerAgentRun,
  pauseAgent,
  resumeAgent,
  type AgentStatus,
  type TickerScoreEntry,
  type ActivityLogEntry,
  type MissingCapability,
  type ApiCapability,
} from "../lib/api";

export function TickerAccuracyAgentDrawer({ onClose }: { onClose: () => void }) {
  const open = useUi((s) => s.tickerAgentOpen);

  const { data: status } = useQuery({
    queryKey: ["agent-status"],
    queryFn: fetchAgentStatus,
    enabled: open,
    refetchInterval: 10_000,
  });

  const { data: leaderboard } = useQuery({
    queryKey: ["agent-leaderboard"],
    queryFn: fetchAccuracyLeaderboard,
    enabled: open,
    refetchInterval: 30_000,
  });

  const { data: activityLog } = useQuery({
    queryKey: ["agent-activity"],
    queryFn: () => fetchAgentActivityLog(5),
    enabled: open,
  });

  const { data: missingCaps } = useQuery({
    queryKey: ["agent-missing-caps"],
    queryFn: fetchMissingCapabilities,
    enabled: open,
  });

  const { data: agentCaps } = useQuery({
    queryKey: ["agent-caps"],
    queryFn: fetchAgentCapabilities,
    enabled: open,
  });

  const qc = useQueryClient();
  const runNowMutation = useMutation({
    mutationFn: triggerAgentRun,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent-status"] });
      qc.invalidateQueries({ queryKey: ["agent-activity"] });
    },
  });

  const pauseMutation = useMutation({
    mutationFn: pauseAgent,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agent-status"] }),
  });

  const resumeMutation = useMutation({
    mutationFn: resumeAgent,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agent-status"] }),
  });

  if (!open) return null;

  const isRunning = status?.status === "running";

  return (
    <>
      <div className="drawer-overlay opacity-100 pointer-events-auto" onClick={onClose} aria-hidden />
      <div className="fixed right-0 top-0 h-full w-full max-w-lg z-50 animate-slide-left bg-market-DEFAULT border-l border-slate-700/50 shadow-2xl overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700/50 px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-sky-400 shadow-[0_0_6px_rgba(56,189,248,0.5)]" />
            <h2 className="font-semibold text-slate-200 text-sm">Ticker Accuracy Agent</h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-700/50 rounded-lg text-slate-500 hover:text-slate-300">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* Status */}
          <section className="glass-panel p-3">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${isRunning ? "bg-emerald-400 animate-pulse" : "bg-slate-500"}`} />
                <span className="text-sm font-medium text-slate-300">
                  {status?.status === "paused" ? "Paused" : isRunning ? "Running" : "Idle"}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                {status?.status === "paused" ? (
                  <button onClick={() => resumeMutation.mutate()} className="btn-primary text-xs">Resume</button>
                ) : (
                  <button onClick={() => pauseMutation.mutate()} className="btn-secondary text-xs">Pause</button>
                )}
                <button onClick={() => runNowMutation.mutate()} className="btn-primary text-xs" disabled={runNowMutation.isPending}>
                  {runNowMutation.isPending ? "Running..." : "Run Now"}
                </button>
              </div>
            </div>
            <div className="text-xs text-slate-500 space-y-0.5">
              <div>Cycles completed: {status?.cycles_completed ?? 0}</div>
              <div>Last cycle: {status?.last_cycle_at ? new Date(status.last_cycle_at).toLocaleString() : "Never"}</div>
            </div>
          </section>

          {/* Activity Log */}
          <section>
            <h3 className="section-header mb-2">Activity Log</h3>
            <div className="space-y-2">
              {activityLog?.entries.length === 0 && (
                <p className="text-xs text-slate-500 text-center py-4">No cycles yet.</p>
              )}
              {activityLog?.entries.map((entry) => (
                <div key={entry.cycle} className="glass-panel p-2.5">
                  <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
                    <span className="font-mono">Cycle #{entry.cycle}</span>
                    <span>{new Date(entry.started_at).toLocaleString()}</span>
                  </div>
                  <p className="text-xs text-slate-300">{entry.summary}</p>
                  <div className="flex gap-3 mt-1 text-[10px] text-slate-500">
                    <span>{entry.tickers_analyzed} tickers</span>
                    <span>{entry.backtests_scheduled} backtests</span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Accuracy Leaderboard */}
          <section>
            <h3 className="section-header mb-2">Accuracy Leaderboard</h3>
            {leaderboard && Object.keys(leaderboard.scores).length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-500 uppercase tracking-wider border-b border-slate-800/60">
                      <th className="px-2 py-1.5 text-left">#</th>
                      <th className="px-2 py-1.5 text-left">Ticker</th>
                      <th className="px-2 py-1.5 text-right">Win Rate</th>
                      <th className="px-2 py-1.5 text-right">Runs</th>
                      <th className="px-2 py-1.5 text-right">Confidence</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/40">
                    {Object.entries(leaderboard.scores).map(([ticker, score], i) => (
                      <tr key={ticker} className="hover:bg-slate-800/20">
                        <td className="px-2 py-1.5 text-slate-500">{i + 1}</td>
                        <td className="px-2 py-1.5 font-semibold text-slate-100">{ticker}</td>
                        <td className={`px-2 py-1.5 text-right ${score.win_rate != null ? (score.win_rate >= 0.7 ? "text-emerald-400" : score.win_rate >= 0.4 ? "text-amber-400" : "text-red-400") : "text-slate-500"}`}>
                          {score.win_rate != null ? `${(score.win_rate * 100).toFixed(0)}%` : "—"}
                        </td>
                        <td className="px-2 py-1.5 text-right text-slate-300">{score.total_runs}</td>
                        <td className="px-2 py-1.5 text-right text-sky-400">
                          {score.avg_confidence != null ? `${(score.avg_confidence * 100).toFixed(0)}%` : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-slate-500 text-center py-4">No tickers scored yet. Run a cycle to start.</p>
            )}
          </section>

          {/* Capabilities Inventory */}
          <section>
            <h3 className="section-header mb-2">Capabilities Inventory</h3>
            <div className="max-h-40 overflow-y-auto space-y-1">
              {agentCaps?.capabilities.map((cap) => (
                <div key={cap.path} className="flex items-center gap-2 text-xs">
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cap.available ? "bg-emerald-500" : "bg-red-500"}`} />
                  <span className="text-slate-400 font-mono text-[10px]">{cap.method} {cap.path}</span>
                  <span className="text-slate-600 truncate">{cap.purpose}</span>
                </div>
              ))}
            </div>
          </section>

          {/* Missing Capabilities */}
          <section>
            <h3 className="section-header mb-2">Missing Capabilities</h3>
            {missingCaps?.capabilities.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-4">No missing capabilities identified.</p>
            ) : (
              <div className="space-y-2">
                {missingCaps?.capabilities.map((cap) => (
                  <div key={cap.name} className="glass-panel p-2.5 flex items-center justify-between">
                    <div>
                      <div className="text-xs font-medium text-slate-300">{cap.name}</div>
                      <div className="text-[10px] text-slate-500">{cap.description}</div>
                    </div>
                    <button
                      onClick={() => {
                        fetch("/api/opencode/implement", {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({
                            capability: cap.name,
                            description: cap.description,
                            suggested_endpoint: cap.suggested_endpoint,
                          }),
                        });
                      }}
                      className="btn-primary text-[10px] shrink-0"
                    >
                      Implement →
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 2: Wire into App.tsx**

Add the import and button to the header alongside Settings, Past Runs, History buttons:

```tsx
import { TickerAccuracyAgentDrawer } from "./components/TickerAccuracyAgentDrawer";

// Add state:
const tickerAgentOpen = useUi((s) => s.tickerAgentOpen);
const setTickerAgentOpen = useUi((s) => s.setTickerAgentOpen);

// Add button in header next to Settings:
<button
  onClick={() => setTickerAgentOpen(true)}
  className="btn-secondary text-xs"
  title="Ticker Accuracy Agent"
>
  <span className="flex items-center gap-1">
    <span className="w-1.5 h-1.5 rounded-full bg-sky-400" />
    Agent
  </span>
</button>

// Mount drawer at bottom of component tree:
<TickerAccuracyAgentDrawer onClose={() => setTickerAgentOpen(false)} />
```

- [ ] **Step 3: Run frontend build check**

```powershell
cd web/frontend; if ($?) { npx tsc --noEmit }
```
Expected: No type errors

- [ ] **Step 4: Commit**

```powershell
git add web/frontend/src/components/TickerAccuracyAgentDrawer.tsx web/frontend/src/App.tsx
git commit -m "feat: ticker accuracy agent drawer and header button"
```

---

### Task 9: Frontend — Watchlist Accuracy Badges + Settings Config

**Files:**
- Modify: `web/frontend/src/components/TickerRow.tsx`
- Modify: `web/frontend/src/components/WatchlistRail.tsx`
- Modify: `web/frontend/src/components/HistoricalAnalysisDrawer.tsx`
- Modify: `web/frontend/src/components/SettingsPanel.tsx`

- [ ] **Step 1: Add accuracy badge to TickerRow.tsx**

After existing ticker info, add:
```tsx
const { data: agentScores } = useQuery({
  queryKey: ["agent-leaderboard"],
  queryFn: fetchAccuracyLeaderboard,
  enabled: !!ticker,
  staleTime: 60_000,
});

const score = agentScores?.scores?.[ticker];
// Show badge: "83%" in green/amber/red
{score && (
  <span className={`text-[10px] font-mono ${
    (score.win_rate ?? 0) >= 0.7 ? "text-emerald-400" :
    (score.win_rate ?? 0) >= 0.4 ? "text-amber-400" : "text-red-400"
  }`}>
    {(score.win_rate! * 100).toFixed(0)}%
  </span>
)}
```

- [ ] **Step 2: Add accuracy sort option to WatchlistRail.tsx**

Add a sort dropdown with "By Accuracy" option. When selected, reorder the watchlist to match agent score ranking.

- [ ] **Step 3: Add accuracy chip to HistoricalAnalysisDrawer.tsx**

In the header, after ticker name:
```tsx
const { data: agentScores } = useQuery({
  queryKey: ["agent-leaderboard"],
  queryFn: fetchAccuracyLeaderboard,
});
const tickerScore = agentScores?.scores?.[ticker];

{tickerScore && (
  <span className="px-2 py-0.5 text-[10px] font-mono rounded-md bg-sky-500/10 text-sky-400 border border-sky-500/20">
    System accuracy: {(tickerScore.win_rate! * 100).toFixed(0)}% ({tickerScore.total_runs} runs)
  </span>
)}
```

- [ ] **Step 4: Add agent config section to SettingsPanel.tsx**

```tsx
// ── Ticker Accuracy Agent ──
<section>
  <h3 className="section-header flex items-center gap-2 mb-3">
    <span className="w-1.5 h-1.5 rounded-full bg-sky-400" />
    Ticker Accuracy Agent
  </h3>
  <div className="glass-panel p-3 space-y-3">
    <ConfigInput
      label="Min Samples Before Ranking"
      value={String(agentConfig?.min_samples ?? 3)}
      onChange={(v) => setAgentDirty({ ...agentDirty, min_samples: parseInt(v) || 3 })}
      type="number"
    />
    <ConfigSelect
      label="Schedule Interval"
      value={String(agentConfig?.schedule_interval_h ?? 6)}
      options={["1", "2", "6", "12", "24"]}
      onChange={(v) => setAgentDirty({ ...agentDirty, schedule_interval_h: parseInt(v) || 6 })}
    />
    <ConfigInput
      label="Max Tickers Per Cycle"
      value={String(agentConfig?.max_tickers_per_cycle ?? 20)}
      onChange={(v) => setAgentDirty({ ...agentDirty, max_tickers_per_cycle: parseInt(v) || 20 })}
      type="number"
    />
    <ConfigToggle
      label="S&P 500 Universe"
      value={String(agentConfig?.sp500_enabled ?? true)}
      onChange={(v) => setAgentDirty({ ...agentDirty, sp500_enabled: v === "true" })}
    />
    <ConfigToggle
      label="Yahoo Sectors Universe"
      value={String(agentConfig?.yahoo_sectors_enabled ?? true)}
      onChange={(v) => setAgentDirty({ ...agentDirty, yahoo_sectors_enabled: v === "true" })}
    />
  </div>
</section>
```

- [ ] **Step 5: Commit**

```powershell
git add web/frontend/src/components/TickerRow.tsx web/frontend/src/components/WatchlistRail.tsx web/frontend/src/components/HistoricalAnalysisDrawer.tsx web/frontend/src/components/SettingsPanel.tsx
git commit -m "feat: watchlist accuracy badges, accuracy sort, drawer chip, agent config in settings"
```

---

### Task 10: Full Integration Test

- [ ] **Step 1: Start the server and verify everything works end-to-end**

```powershell
.venv\Scripts\activate; if ($?) { uv run python -m uvicorn web.server.app:create_app --host 0.0.0.0 --port 8000 --factory --reload }
```

Test:
```powershell
curl http://localhost:8000/api/ticker-agent/status
curl http://localhost:8000/api/ticker-agent/capabilities
curl http://localhost:8000/api/ticker-agent/run-now -X POST
```

- [ ] **Step 2: Run all tests**

```powershell
.venv\Scripts\activate; if ($?) { uv run pytest web/server/ticker_agent/tests/ -v }
.venv\Scripts\activate; if ($?) { uv run pytest web/server/tests/test_api.py -v }
```
