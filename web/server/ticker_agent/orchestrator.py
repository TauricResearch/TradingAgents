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
from typing import Optional

from web.server.ticker_agent import scorer
from web.server.ticker_agent.universe import discover_universe, UniverseConfig
from web.server.ticker_agent.memory import read_memory, append_memory
from web.server.ticker_agent.missing_capabilities import log_missing
from web.server.ticker_agent.capabilities import discover_api_capabilities
from web.server.ticker_agent.config import load_config
from web.server import storage, queries

log = logging.getLogger(__name__)

# Module-level state
_running = False
_stop_event = threading.Event()
_thread: threading.Thread | None = None
_lock = threading.Lock()
_current_status = "idle"
_last_cycle_at: str | None = None
_next_cycle_at: str | None = None
_cycles_completed = 0
_activity_log: list[dict] = []
_current_step: int = 0
_live_events: list[dict] = []
_event_id_counter: int = 0

STEP_NAMES = [
    "Idle",
    "Read Memory",
    "Gather Context",
    "LLM Strategy Call",
    "Execute",
    "Rank & Reflect",
    "Write Memory",
    "Self-Improvement",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _emit_live(step: int, message: str) -> None:
    global _event_id_counter
    with _lock:
        _event_id_counter += 1
        _live_events.append({
            "id": _event_id_counter,
            "step": step,
            "step_name": STEP_NAMES[step] if 0 <= step < len(STEP_NAMES) else "Unknown",
            "message": message,
            "timestamp": _now_iso(),
        })
        if len(_live_events) > 200:
            _live_events[:50] = []


def status() -> dict:
    with _lock:
        return {
            "status": _current_status,
            "last_run_at": _last_cycle_at,
            "next_scheduled_at": _next_cycle_at,
            "cycles_completed": _cycles_completed,
            "current_step": _current_step,
            "current_step_name": STEP_NAMES[_current_step] if 0 <= _current_step < len(STEP_NAMES) else "Unknown",
        }


def activity_log(limit: int = 10) -> list[dict]:
    with _lock:
        return list(_activity_log[-limit:])


def live_events(since: int = 0) -> dict:
    with _lock:
        events = [e for e in _live_events if e["id"] > since]
        return {
            "events": events,
            "current_step": _current_step,
            "current_step_name": STEP_NAMES[_current_step] if 0 <= _current_step < len(STEP_NAMES) else "Unknown",
        }


_MAX_UNIVERSE_SAMPLE = 30
_MAX_TOP_SCORES = 10
_MAX_COVERAGE_GAPS = 20
_RUN_LIMIT_PER_TICKER = 200


def _get_sector_performance() -> str:
    """Fetch recent performance for sector ETFs via yfinance."""
    try:
        import yfinance as yf
        sector_etfs = {
            "XLK": "Technology",
            "XLF": "Financials",
            "XLV": "Healthcare",
            "XLE": "Energy",
            "XLY": "Consumer Discretionary",
            "XLI": "Industrials",
        }
        lines = ["Sector performance (5d return):"]
        for etf, label in sector_etfs.items():
            ticker = yf.Ticker(etf)
            hist = ticker.history(period="5d")
            if len(hist) >= 2:
                ret = ((hist["Close"].iloc[-1] - hist["Close"].iloc[0]) / hist["Close"].iloc[0]) * 100
                lines.append(f"  {label} ({etf}): {ret:+.1f}%")
        return "\n".join(lines)
    except Exception as e:
        log.warning("Failed to fetch sector performance: %s", e)
        return ""


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

    runs_by_ticker: dict[str, list[dict]] = {}
    for td in storage.walk_data_dir():
        ticker = td.name
        runs = list(storage.list_ticker_runs(ticker, limit=_RUN_LIMIT_PER_TICKER))
        if runs:
            runs_by_ticker[ticker] = runs

    scores = scorer.compute_ticker_scores(runs_by_ticker, min_samples=cfg.min_samples)

    coverage_gaps = [t for t in universe if t not in scores][:_MAX_COVERAGE_GAPS]

    memory = read_memory(limit=10)

    sector_perf = _get_sector_performance()

    return {
        "watchlist_size": len(watchlist_tickers),
        "watchlist_tickers": watchlist_tickers,
        "universe_size": len(universe),
        "universe": universe[:_MAX_UNIVERSE_SAMPLE],
        "scored_tickers": len(scores),
        "top_scores": dict(list(scores.items())[:_MAX_TOP_SCORES]),
        "coverage_gaps": coverage_gaps,
        "memory": memory,
        "sector_performance": sector_perf,
        "runs_by_ticker": runs_by_ticker,
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

    sector_perf = context.get("sector_performance", "")
    sector_text = f"\n{sector_perf}\n" if sector_perf else ""

    return f"""You are the Ticker Accuracy Agent for a trading analysis system.
Your goal is to find tickers where the system's predictions are most accurate.

Current state:
- Watchlist size: {context.get('watchlist_size', 0)}
- Universe candidates: {context.get('universe_size', 0)}
- Scored tickers: {context.get('scored_tickers', 0)}

{scores_text}

{gaps_text}

{universe_text}

{sector_text}

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
            base_url=llm_config.get("backend_url") or None,
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

    cfg = load_config()
    max_tickers = cfg.max_tickers_per_cycle or 20
    plan_items = plan.get("investigation_plan", [])[:max_tickers]
    if len(plan.get("investigation_plan", [])) > max_tickers:
        log.info("Limiting investigation plan from %d to %d tickers", len(plan["investigation_plan"]), max_tickers)

    scheduled = []
    for item in plan_items:
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
    runs_by_ticker = context.get("runs_by_ticker")
    if runs_by_ticker is None:
        runs_by_ticker = {}
        for td in storage.walk_data_dir():
            ticker = td.name
            runs = list(storage.list_ticker_runs(ticker, limit=_RUN_LIMIT_PER_TICKER))
            if runs:
                runs_by_ticker[ticker] = runs

    cfg = load_config()
    scores = scorer.compute_ticker_scores(runs_by_ticker, min_samples=cfg.min_samples)

    state = {
        "status": "completed",
        "last_evaluated": _now_iso(),
        "scores": {t: {
            "accuracy_pct": round((s.win_rate or 0) * 100, 1) if s.win_rate is not None else None,
            "total_runs": s.total_runs,
            "right": s.right,
            "wrong": s.wrong,
            "avg_confidence": s.avg_confidence,
            "target_hit_rate": s.target_hit_rate,
            "trending_accuracy": s.trending_accuracy,
            "last_evaluated": s.last_evaluated,
            "win_rate": s.win_rate,
        } for t, s in scores.items()},
    }

    state_path = storage.ticker_agent_path("agent_state.json")
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    return {"scored": len(scores), "top_ticker": next(iter(scores)) if scores else None}


def _write_memory(context: dict, llm_response: dict, execution_result: dict, scores_result: dict) -> None:
    """Write learning conclusions from this cycle to agent memory."""
    conclusions = llm_response.get("conclusions", [])
    if not conclusions:
        conclusions = [f"Cycle analyzed {execution_result.get('scheduled', [])} tickers"]

    with _lock:
        next_cycle = _cycles_completed + 1

    entry = {
        "cycle": next_cycle,
        "timestamp": _now_iso(),
        "conclusions": conclusions,
        "strategies_validated": llm_response.get("sectors_to_watch", []),
        "tickers_scheduled": execution_result.get("scheduled", []),
        "tickers_scored": scores_result.get("scored", 0),
        "reasoning": llm_response.get("reasoning_summary", ""),
    }
    append_memory(entry)

    with _lock:
        scheduled_count = len(execution_result.get("scheduled", []))
        _activity_log.append({
            "timestamp": _last_cycle_at or _now_iso(),
            "message": f"Cycle {next_cycle}: {llm_response.get('reasoning_summary', '')} "
                       f"[{scheduled_count} backtests scheduled]",
            "cycle": next_cycle,
            "tickers_analyzed": len(context.get("universe", [])),
            "backtests_scheduled": scheduled_count,
        })


def _ask_llm_for_missing_capabilities(caps_text: str) -> list[tuple[str, str, str]]:
    """Ask the LLM what capabilities are missing, fallback on failure."""
    prompt = f"""You are the Ticker Accuracy Agent, a system that analyzes stock tickers to find
the best candidates for trading analysis. You score tickers on prediction accuracy.

Currently available API capabilities:
{caps_text}

Based on your purpose (ticker accuracy analysis) and what you already have, suggest
3-5 capabilities that would make you more effective. Focus on practical, implementable
API endpoints that provide real market data.

Return JSON:
{{
  "suggested_capabilities": [
    {{"name": "short_slug_name", "description": "what it does", "suggested_endpoint": "/api/some/path"}}
  ]
}}"""

    try:
        import re
        from tradingagents.llm_clients import create_llm_client
        from tradingagents.default_config import DEFAULT_CONFIG

        llm_config = DEFAULT_CONFIG.copy()
        client = create_llm_client(
            provider=llm_config.get("llm_provider", "openai"),
            model=llm_config.get("quick_think_llm", "gpt-4o-mini"),
            base_url=llm_config.get("backend_url") or None,
        )
        llm = client.get_llm()

        response = llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)

        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            suggestions = data.get("suggested_capabilities", [])
            return [
                (s.get("name", "unknown"), s.get("description", ""), s.get("suggested_endpoint", ""))
                for s in suggestions
            ]
    except Exception as e:
        log.warning("LLM capability suggestion failed: %s", e)

    return []


_FALLBACK_CAPABILITIES = [
    ("sector_etf_flows", "Track ETF capital inflows per sector for sector rotation detection", "/api/sectors/flows"),
    ("options_flow", "Monitor unusual options activity as a leading indicator", "/api/options/unusual"),
    ("insider_trading_aggregator", "Aggregate insider trading patterns across tickers", "/api/insider/aggregate"),
    ("earnings_calendar", "Earnings dates and surprise history for event-driven analysis", "/api/calendar/earnings"),
    ("sector_performance_api", "Real-time sector performance data (XLK, XLF, etc.)", "/api/sectors/performance"),
]


def _self_improve(context: dict) -> None:
    """Ask what would make the agent better and log missing capabilities."""
    caps = discover_api_capabilities()
    available_paths = {c.path for c in caps}

    caps_text = "\n".join(
        f"- {c.path} ({c.method}): {c.purpose}" for c in caps if c.available
    ) if caps else "No API capabilities discovered."

    suggestions = _ask_llm_for_missing_capabilities(caps_text)
    if not suggestions:
        suggestions = _FALLBACK_CAPABILITIES

    for name, description, endpoint in suggestions:
        if endpoint not in available_paths:
            log_missing(name, description, suggested_endpoint=endpoint)


def run_cycle() -> dict:
    """Execute one full agent cycle."""
    global _current_status, _current_step, _last_cycle_at, _cycles_completed

    with _lock:
        _current_status = "running"
        _current_step = 1
        _last_cycle_at = _now_iso()
    _emit_live(1, "Reading past conclusions from memory...")

    try:
        _emit_live(2, "Gathering context: watchlist, universe, accuracy scores...")
        context = _gather_context()

        _emit_live(3, "Calling LLM for strategy plan...")
        prompt = _build_strategy_prompt(context)
        llm_response = _call_llm_strategy(prompt)

        _emit_live(4, "Scheduling execution for planned tickers...")
        execution_result = _execute_plan(llm_response)

        _emit_live(5, "Ranking accuracy scores from completed runs...")
        scores_result = _rank_and_store(context)

        _emit_live(6, "Writing learning conclusions to memory...")
        _write_memory(context, llm_response, execution_result, scores_result)

        _emit_live(7, "Checking for missing capabilities...")
        _self_improve(context)

        with _lock:
            _current_step = 0
            _cycles_completed += 1
            _current_status = "idle"
        _emit_live(0, "Cycle complete.")

        return {"status": "completed", "cycles_completed": _cycles_completed}

    except Exception as e:
        log.exception("Agent cycle failed")
        with _lock:
            _current_step = 0
            _current_status = "error"
        _emit_live(0, f"Cycle failed: {e}")
        return {"status": "error", "error": str(e)}


def _background_loop() -> None:
    """Background thread: run cycle on schedule."""
    global _next_cycle_at

    while not _stop_event.is_set():
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
            if _stop_event.is_set():
                return
            time.sleep(30)


def start_background_loop() -> None:
    """Start the background agent loop thread."""
    global _running, _thread
    with _lock:
        if _running:
            return
        _running = True
        _stop_event.clear()
        _thread = threading.Thread(target=_background_loop, daemon=True)
        _thread.start()
        log.info("Ticker accuracy agent background loop started")


def stop_background_loop() -> None:
    """Stop the background agent loop."""
    global _running
    with _lock:
        _running = False
    _stop_event.set()
    log.info("Ticker accuracy agent background loop stopping")


def pause() -> None:
    global _running
    with _lock:
        _running = False
        _current_status = "paused"
    _stop_event.set()


def resume() -> None:
    start_background_loop()
