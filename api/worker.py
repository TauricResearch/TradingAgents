"""
Background worker — processes analysis requests from an asyncio queue.
Runs TradingAgentsGraph in a thread-pool executor so it doesn't block
the event loop.
"""
from __future__ import annotations

import asyncio
import datetime
import io
import os
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from langchain_core.callbacks import BaseCallbackHandler

from api.db import (
    DB_PATH,
    defer_due_google_pending_requests,
    get_request,
    get_google_llm_calls_used_between,
    list_due_pending_requests,
    reschedule_running_request,
    update_request_completed,
    update_request_failed,
    update_request_running,
)
from cli.stats_handler import StatsCallbackHandler

# ---------------------------------------------------------------------------
# Live LLM call counter — tracks in-flight calls before they are flushed to DB
# ---------------------------------------------------------------------------
_live_lock = threading.Lock()
# provider_lower -> total calls currently in-flight (for running requests)
_live_provider_calls: dict[str, int] = {}


def _live_register_call(provider: str) -> None:
    key = (provider or "unknown").lower()
    with _live_lock:
        _live_provider_calls[key] = _live_provider_calls.get(key, 0) + 1


def _live_deregister_calls(provider: str, count: int) -> None:
    """Remove 'count' in-flight calls once they are committed to DB."""
    key = (provider or "unknown").lower()
    with _live_lock:
        _live_provider_calls[key] = max(0, _live_provider_calls.get(key, 0) - count)


def get_live_provider_calls() -> dict[str, int]:
    """Return a snapshot of the current in-flight LLM call counts."""
    with _live_lock:
        return dict(_live_provider_calls)


class _TrackingStatsHandler(StatsCallbackHandler):
    """StatsCallbackHandler that also updates the module-level live counter."""

    def __init__(self, provider: str) -> None:
        super().__init__()
        self._provider = (provider or "unknown").lower()

    def on_llm_start(self, serialized, prompts, **kwargs):
        super().on_llm_start(serialized, prompts, **kwargs)
        _live_register_call(self._provider)

    def on_chat_model_start(self, serialized, messages, **kwargs):
        super().on_chat_model_start(serialized, messages, **kwargs)
        _live_register_call(self._provider)


ANALYSIS_DIR = "/data/analysis"
CACHE_DIR = "/data/cache"
RESULTS_DIR = "/data/logs"
MEMORY_LOG_PATH = "/data/memory/trading_memory.md"
API_DEBUG_MODE = os.getenv("API_DEBUG_MODE", "true").strip().lower() in ("1", "true", "yes", "on")
_executor = ThreadPoolExecutor(max_workers=1)
GOOGLE_429_RETRY_DELAY_SECONDS = 300
GOOGLE_429_MAX_RETRIES = 1
GOOGLE_MISSING_KEY_RETRY_DELAY_SECONDS = 60
OPENROUTER_429_RETRY_DELAY_SECONDS = 70  # free-tier rate limits reset per minute
OPENROUTER_429_MAX_RETRIES = 2

# Populated by main.py at startup
task_queue: asyncio.Queue[tuple[str, str, str]] = asyncio.Queue()

SUPPORTED_PROVIDERS = {
    "ollama",
    "google",
    "openrouter",
}


def _append_request_log(req_id: str, message: str) -> None:
    Path(ANALYSIS_DIR).mkdir(parents=True, exist_ok=True)
    log_path = Path(ANALYSIS_DIR) / f"{req_id}.live.log"
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def _is_google_429_error(exc: Exception, provider: Optional[str]) -> bool:
    if (provider or "").strip().lower() != "google":
        return False
    msg = str(exc).lower()
    return "429" in msg and (
        "resource_exhausted" in msg
        or "quota" in msg
        or "rate limit" in msg
        or "retry" in msg
    )


def _is_openrouter_429_error(exc: Exception, provider: Optional[str]) -> bool:
    if (provider or "").strip().lower() != "openrouter":
        return False
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg


def _google_daily_call_limit() -> int:
    raw = os.getenv("GOOGLE_DAILY_CALL_LIMIT", "800").strip()
    try:
        value = int(raw)
        return value if value > 0 else 800
    except ValueError:
        return 800


def _next_midnight_utc_iso(now: Optional[datetime.datetime] = None) -> str:
    current = now or datetime.datetime.now(datetime.timezone.utc)
    next_day = (current + datetime.timedelta(days=1)).date()
    return datetime.datetime.combine(next_day, datetime.time.min, tzinfo=datetime.timezone.utc).isoformat()


def _in_one_day_window_iso(now: Optional[datetime.datetime] = None) -> tuple[str, str]:
    current = now or datetime.datetime.now(datetime.timezone.utc)
    start = datetime.datetime.combine(current.date(), datetime.time.min, tzinfo=datetime.timezone.utc)
    end = start + datetime.timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _pick_provider_config(request_provider: Optional[str]) -> tuple[str, Optional[str], str, str]:
    provider = (request_provider or "ollama").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        provider = "ollama"

    if provider == "google":
        backend_url = os.getenv("GOOGLE_BASE_URL") or None
        deep_model = os.getenv("GOOGLE_DEEP_THINK_MODEL", "gemini-2.5-pro")
        quick_model = os.getenv("GOOGLE_QUICK_THINK_MODEL", "gemini-2.5-flash-lite")
        return provider, backend_url, deep_model, quick_model

    if provider == "openrouter":
        backend_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        # Default to free-tier models on OpenRouter; callers can override via env vars.
        deep_model = os.getenv("OPENROUTER_DEEP_THINK_MODEL", "deepseek/deepseek-r1-0528:free")
        quick_model = os.getenv("OPENROUTER_QUICK_THINK_MODEL", "qwen/qwen3-coder:free")
        return provider, backend_url, deep_model, quick_model

    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    backend_url = ollama_host.rstrip("/") + "/v1"
    # Keep Ollama defaults on Qwen models unless explicitly overridden.
    deep_model = os.getenv("DEEP_THINK_MODEL", "qwen3:latest")
    quick_model = os.getenv("QUICK_THINK_MODEL", "qwen3:latest")
    return provider, backend_url, deep_model, quick_model


def _estimate_cost_usd(provider: str, deep_model: str, quick_model: str, tokens_in: int, tokens_out: int) -> float:
    provider = provider.lower()
    if provider == "ollama":
        return 0.0
    if provider != "google":
        return 0.0

    model_name = f"{deep_model} {quick_model}".lower()

    # Rough per-1M-token estimates; override with env vars as needed.
    if "flash-lite" in model_name:
        in_rate = float(os.getenv("GOOGLE_FLASH_LITE_INPUT_PER_1M", "0.10"))
        out_rate = float(os.getenv("GOOGLE_FLASH_LITE_OUTPUT_PER_1M", "0.40"))
    elif "flash" in model_name:
        in_rate = float(os.getenv("GOOGLE_FLASH_INPUT_PER_1M", "0.35"))
        out_rate = float(os.getenv("GOOGLE_FLASH_OUTPUT_PER_1M", "1.05"))
    else:
        in_rate = float(os.getenv("GOOGLE_PRO_INPUT_PER_1M", "3.50"))
        out_rate = float(os.getenv("GOOGLE_PRO_OUTPUT_PER_1M", "10.50"))

    cost = (tokens_in / 1_000_000.0) * in_rate + (tokens_out / 1_000_000.0) * out_rate
    return round(cost, 6)


class _LLMTimingCallback(BaseCallbackHandler):
    """Log elapsed time for each individual LLM call."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._started_at: dict[str, float] = {}

    def _run_key(self, **kwargs) -> Optional[str]:
        run_id = kwargs.get("run_id")
        return str(run_id) if run_id is not None else None

    def _model_name(self, serialized: dict) -> str:
        kwargs = serialized.get("kwargs", {}) if isinstance(serialized, dict) else {}
        return str(kwargs.get("model") or serialized.get("name") or "unknown-model")

    def _mark_start(self, event_name: str, serialized: dict, **kwargs) -> None:
        key = self._run_key(**kwargs)
        if not key:
            return
        model_name = self._model_name(serialized)
        started = time.perf_counter()
        with self._lock:
            if key not in self._started_at:
                self._started_at[key] = started
        print(f"[LLM] start event={event_name} run_id={key} model={model_name}")

    def on_llm_start(self, serialized, prompts, **kwargs):
        self._mark_start("llm", serialized, **kwargs)

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self._mark_start("chat", serialized, **kwargs)

    def on_llm_end(self, response, **kwargs):
        key = self._run_key(**kwargs)
        if not key:
            return
        ended = time.perf_counter()
        with self._lock:
            started = self._started_at.pop(key, None)
        if started is None:
            print(f"[LLM] end run_id={key} duration_seconds=unknown")
            return
        duration = ended - started
        print(f"[LLM] end run_id={key} duration_seconds={duration:.3f}")

    def on_llm_error(self, error, **kwargs):
        key = self._run_key(**kwargs)
        if not key:
            return
        ended = time.perf_counter()
        with self._lock:
            started = self._started_at.pop(key, None)
        if started is None:
            print(f"[LLM] error run_id={key} duration_seconds=unknown error={error}")
            return
        duration = ended - started
        print(f"[LLM] error run_id={key} duration_seconds={duration:.3f} error={error}")


def _run_analysis(req_id: str, ticker: str, analysis_date: str, llm_provider: Optional[str]) -> tuple[str, str, dict, str, str, str, float, dict]:
    """Blocking: runs TradingAgents and returns recommendation, file path, usage stats, and agent recommendations."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG

    provider, backend_url, deep_model, quick_model = _pick_provider_config(llm_provider)

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = provider
    config["backend_url"] = backend_url
    config["deep_think_llm"] = deep_model
    config["quick_think_llm"] = quick_model
    config["data_cache_dir"] = CACHE_DIR
    config["results_dir"] = RESULTS_DIR
    config["memory_log_path"] = MEMORY_LOG_PATH
    config["data_vendors"] = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    }
    config["max_recur_limit"] = int(os.getenv("MAX_RECUR_LIMIT", "500"))

    class _TeeOutput:
        def __init__(self, streams: list[io.TextIOBase]):
            self._streams = streams

        def write(self, data: str) -> int:
            for s in self._streams:
                s.write(data)
                s.flush()
            return len(data)

        def flush(self) -> None:
            for s in self._streams:
                s.flush()

    # Capture stdout and persist live logs while the request is running.
    captured = io.StringIO()
    old_stdout = sys.stdout
    Path(ANALYSIS_DIR).mkdir(parents=True, exist_ok=True)
    live_log_path = Path(ANALYSIS_DIR) / f"{req_id}.live.log"
    live_log = open(live_log_path, "a", encoding="utf-8")
    sys.stdout = _TeeOutput([captured, live_log])

    analysis_started_utc = datetime.datetime.now(datetime.timezone.utc)
    analysis_started_timer = time.perf_counter()
    print(f"[Analysis] start_time={analysis_started_utc.isoformat()} request_id={req_id}")

    final_state = None
    stats_callback = _TrackingStatsHandler(provider)
    try:
        Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
        Path(RESULTS_DIR).mkdir(parents=True, exist_ok=True)
        Path(MEMORY_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        timing_callback = _LLMTimingCallback()
        ta = TradingAgentsGraph(
            debug=API_DEBUG_MODE,
            config=config,
            callbacks=[timing_callback, stats_callback],
        )
        final_state, decision = ta.propagate(ticker, analysis_date)
    finally:
        analysis_ended_utc = datetime.datetime.now(datetime.timezone.utc)
        analysis_duration = time.perf_counter() - analysis_started_timer
        print(
            f"[Analysis] end_time={analysis_ended_utc.isoformat()} "
            f"request_id={req_id} duration_seconds={analysis_duration:.3f}"
        )
        live_log.flush()
        live_log.close()
        sys.stdout = old_stdout
        # Deregister live counter regardless of success or failure
        _live_deregister_calls(provider, stats_callback.get_stats().get("llm_calls", 0))

    full_output = captured.getvalue()
    recommendation = str(decision)
    stats = stats_callback.get_stats()
    stats["total_tokens"] = int(stats.get("tokens_in", 0)) + int(stats.get("tokens_out", 0))
    estimated_cost_usd = _estimate_cost_usd(
        provider,
        deep_model,
        quick_model,
        int(stats.get("tokens_in", 0)),
        int(stats.get("tokens_out", 0)),
    )

    # Extract agent recommendations from final_state.
    agent_recommendations = {}
    if final_state:
        risk_state = final_state.get("risk_debate_state", {}) or {}
        investment_state = final_state.get("investment_debate_state", {}) or {}

        def entry(label: str, weight: int, recommendation) -> dict:
            return {
                "label": label,
                "weight": weight,
                "recommendation": recommendation or "",
            }

        agent_recommendations = {
            "market_analyst": entry("Market Analyst", 15, final_state.get("market_report")),
            "fundamentals_analyst": entry("Fundamentals Analyst", 15, final_state.get("fundamentals_report")),
            "news_analyst": entry("News Analyst", 10, final_state.get("news_report")),
            "social_media_analyst": entry("Social Media Analyst", 10, final_state.get("sentiment_report")),
            "bull_researcher": entry("Bull Researcher", 5, investment_state.get("bull_history")),
            "bear_researcher": entry("Bear Researcher", 5, investment_state.get("bear_history")),
            "investment_judge": entry("Investment Judge", 5, investment_state.get("judge_decision")),
            "trader": entry("Trader", 10, final_state.get("trader_investment_plan")),
            "aggressive_analyst": entry("Aggressive Risk Analyst", 5, risk_state.get("aggressive_history")),
            "neutral_analyst": entry("Neutral Risk Analyst", 5, risk_state.get("neutral_history")),
            "conservative_analyst": entry("Conservative Risk Analyst", 5, risk_state.get("conservative_history")),
            "risk_judge": entry("Risk Judge", 5, risk_state.get("judge_decision")),
            "portfolio_manager": entry("Portfolio Manager", 5, final_state.get("final_trade_decision")),
        }

    # Save detailed analysis to file
    Path(ANALYSIS_DIR).mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{ticker}_{analysis_date}_{ts}.txt"
    filepath = str(Path(ANALYSIS_DIR) / filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"Ticker: {ticker}\nAnalysis Date: {analysis_date}\n\n")
        f.write("=== DETAILED AGENT OUTPUT ===\n\n")
        f.write(full_output)
        f.write("\n\n=== FINAL DECISION ===\n\n")
        f.write(recommendation)
        f.write("\n\n=== USAGE STATS ===\n\n")
        f.write(
            "\n".join(
                [
                    f"llm_calls: {stats.get('llm_calls', 0)}",
                    f"tool_calls: {stats.get('tool_calls', 0)}",
                    f"tokens_in: {stats.get('tokens_in', 0)}",
                    f"tokens_out: {stats.get('tokens_out', 0)}",
                    f"total_tokens: {stats.get('total_tokens', 0)}",
                    f"estimated_cost_usd: {estimated_cost_usd}",
                ]
            )
        )

    return recommendation, filename, stats, provider, deep_model, quick_model, estimated_cost_usd, agent_recommendations


async def worker_loop(db_path: str = DB_PATH) -> None:
    """Drain the task queue forever, running one analysis at a time per executor slot."""
    loop = asyncio.get_running_loop()
    while True:
        req_id, ticker, analysis_date = await task_queue.get()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        due_rows = await list_due_pending_requests(now_iso=now_iso, db_path=db_path)
        if due_rows and int(due_rows[0].get("deferred_for_quota") or 0) == 1 and due_rows[0]["id"] != req_id:
            # Preserve FIFO for normal traffic but let deferred quota work run first.
            await task_queue.put((req_id, ticker, analysis_date))
            task_queue.task_done()
            continue

        row = await get_request(req_id, db_path=db_path)
        if not row or row.get("status") != "pending":
            task_queue.task_done()
            continue

        available_after = row.get("available_after")
        if available_after and available_after > now_iso:
            task_queue.task_done()
            continue

        moved = await update_request_running(req_id, db_path=db_path)
        if not moved:
            task_queue.task_done()
            continue

        request_provider = row.get("llm_provider") if row else None

        if (request_provider or "").strip().lower() == "google":
            if not (os.getenv("GOOGLE_API_KEY") or "").strip():
                retry_at = (
                    datetime.datetime.now(datetime.timezone.utc)
                    + datetime.timedelta(seconds=GOOGLE_MISSING_KEY_RETRY_DELAY_SECONDS)
                ).isoformat()
                await reschedule_running_request(
                    req_id=req_id,
                    available_after=retry_at,
                    reason="GOOGLE_API_KEY is empty; waiting for key update",
                    deferred_for_quota=0,
                    db_path=db_path,
                )
                _append_request_log(req_id, "GOOGLE_API_KEY is empty. Request postponed until key is set.")
                task_queue.task_done()
                continue

            day_start_iso, day_end_iso = _in_one_day_window_iso()
            used_today = await get_google_llm_calls_used_between(
                start_iso=day_start_iso,
                end_iso=day_end_iso,
                db_path=db_path,
            )
            daily_cap = _google_daily_call_limit()
            if used_today >= daily_cap:
                next_day_iso = _next_midnight_utc_iso()
                defer_reason = (
                    f"Google daily call limit reached ({daily_cap}). Deferred to next UTC day."
                )
                await reschedule_running_request(
                    req_id=req_id,
                    available_after=next_day_iso,
                    reason=defer_reason,
                    deferred_for_quota=1,
                    analysis_date=(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)).date().isoformat(),
                    db_path=db_path,
                )
                await defer_due_google_pending_requests(
                    now_iso=now_iso,
                    available_after_iso=next_day_iso,
                    reason=defer_reason,
                    db_path=db_path,
                )
                _append_request_log(req_id, defer_reason)
                task_queue.task_done()
                continue

        attempt = 0
        _provider_lower = (request_provider or "").strip().lower()
        if _provider_lower == "openrouter":
            max_attempts = OPENROUTER_429_MAX_RETRIES + 1
        else:
            max_attempts = GOOGLE_429_MAX_RETRIES + 1
        while attempt < max_attempts:
            try:
                recommendation, filename, stats, provider, deep_model, quick_model, estimated_cost_usd, agent_recommendations = await loop.run_in_executor(
                    _executor, _run_analysis, req_id, ticker, analysis_date, request_provider
                )
                await update_request_completed(
                    req_id,
                    recommendation,
                    filename,
                    llm_provider=provider,
                    deep_model=deep_model,
                    quick_model=quick_model,
                    estimated_cost_usd=estimated_cost_usd,
                    stats=stats,
                    agent_recommendations=agent_recommendations,
                    llm_role_stats=stats.get("role_stats"),
                    db_path=db_path,
                )
                break
            except Exception as exc:
                attempt += 1
                is_google_429 = _is_google_429_error(exc, request_provider)
                is_or_429 = _is_openrouter_429_error(exc, request_provider)
                can_retry = attempt < max_attempts and (is_google_429 or is_or_429)
                if can_retry:
                    if is_or_429:
                        delay = OPENROUTER_429_RETRY_DELAY_SECONDS
                        max_r = OPENROUTER_429_MAX_RETRIES
                        label = "OpenRouter"
                    else:
                        delay = GOOGLE_429_RETRY_DELAY_SECONDS
                        max_r = GOOGLE_429_MAX_RETRIES
                        label = "Google"
                    _append_request_log(
                        req_id,
                        (
                            f"Detected {label} 429 rate-limit error. "
                            f"Waiting {delay}s before retry "
                            f"({attempt}/{max_r})."
                        ),
                    )
                    await asyncio.sleep(delay)
                    row_after_wait = await get_request(req_id, db_path=db_path)
                    if not row_after_wait or row_after_wait.get("status") != "running":
                        break
                    continue

                err = traceback.format_exc()
                await update_request_failed(req_id, err, db_path=db_path)
                break

        task_queue.task_done()
