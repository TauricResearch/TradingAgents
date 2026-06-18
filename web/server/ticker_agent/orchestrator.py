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

from web.server.ticker_agent import scorer
from web.server.ticker_agent.universe import discover_universe, UniverseConfig
from web.server.ticker_agent.memory import read_memory, append_memory
from web.server.ticker_agent.missing_capabilities import log_missing
from web.server.ticker_agent.capabilities import discover_api_capabilities
from web.server.ticker_agent.config import load_config, save_config, config_to_dict
from web.server import storage, queries

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
    cfg = load_config()

    watchlist = queries.read_watchlist()
    watchlist_tickers = [w["ticker"] for w in watchlist]

    universe_cfg = UniverseConfig(
        sp500_enabled=cfg.sp500_enabled,
        yahoo_sectors_enabled=cfg.yahoo_sectors_enabled,
        custom_file_path=cfg.custom_universe_path,
        watchlist_tickers=watchlist_tickers,
    )
    universe = discover_universe(universe_cfg)

    # Gather runs per ticker
    runs_by_ticker: dict[str, list[dict]] = {}
    for td in storage.walk_data_dir():
        ticker = td.name
        runs = list(storage.list_ticker_runs(ticker, limit=100))
        if runs:
            runs_by_ticker[ticker] = runs

    scores = scorer.compute_ticker_scores(runs_by_ticker, min_samples=cfg.min_samples)

    coverage_gaps = [t for t in universe if t not in scores][:50]

    memory = read_memory(limit=10)

    return {
        "watchlist_size": len(watchlist_tickers),
        "watchlist_tickers": watchlist_tickers,
        "universe_size": len(universe),
        "universe": universe[:30],
        "scored_tickers": len(scores),
        "top_scores": dict(list(scores.items())[:10]),
        "coverage_gaps": coverage_gaps[:20],
        "memory": memory,
    }


def _build_strategy_prompt(context: dict) -> str:
    """Build the LLM prompt for the strategy decision."""
    scores_text = ""
    if context.get("top_scores"):
        scores_text = "Current accuracy scores:\n" + json.dumps(
            {t: {"win_rate": s.win_rate, "total_runs": s.total_runs} for t, s in context["top_scores"].items()},
            indent=2,
        )

    gaps_text = ""
    if context.get("coverage_gaps"):
        gaps_text = "Tickers needing more data:\n" + "\n".join(f"- {t}" for t in context["coverage_gaps"])

    memory_text = ""
    if context.get("memory"):
        memory_text = "Past learning conclusions:\n" + json.dumps(context["memory"], indent=2)

    universe_sample = context.get("universe", [])
    universe_text = ""
    if universe_sample:
        universe_text = "Broader universe candidates:\n" + "\n".join(f"- {t}" for t in universe_sample)

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

    Falls back to empty plan on LLM failure.
    """
    import re
    try:
        from tradingagents.llm_clients import create_llm_client
        from tradingagents.default_config import DEFAULT_CONFIG

        llm_config = DEFAULT_CONFIG.copy()

        client = create_llm_client(
            provider=llm_config.get("llm_provider", "openai"),
            model=llm_config.get("quick_think_llm", "gpt-4o-mini"),
        )
        llm = client.get_llm()

        response = llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)

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
    runs_by_ticker: dict[str, list[dict]] = {}
    for td in storage.walk_data_dir():
        ticker = td.name
        runs = list(storage.list_ticker_runs(ticker, limit=200))
        if runs:
            runs_by_ticker[ticker] = runs

    cfg = load_config()
    scores = scorer.compute_ticker_scores(runs_by_ticker, min_samples=cfg.min_samples)

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

    import json
    state_path = storage.ticker_agent_path("agent_state.json")
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
        context = _gather_context()

        prompt = _build_strategy_prompt(context)
        llm_response = _call_llm_strategy(prompt)

        execution_result = _execute_plan(llm_response)

        scores_result = _rank_and_store(context)

        _write_memory(context, llm_response, execution_result, scores_result)

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
            _next_cycle_at = _now_iso()

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
