import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from agent_os.backend.dependencies import get_current_user
from agent_os.backend.run_metadata import normalize_run_params
from agent_os.backend.services.langgraph_engine import (
    NODE_TO_PHASE,
    SCAN_NODE_TO_REPORT_FIELD,
    AwaitPhase3Decision,
    LangGraphEngine,
    infer_pipeline_resume_phase,
)
from agent_os.backend.services.mock_engine import MockEngine
from agent_os.backend.store import runs
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.scanner_setup import (
    SCANNER_START_NODES,
    get_scanner_descendants,
)
from tradingagents.portfolio.exceptions import ReportStoreError
from tradingagents.portfolio.store_factory import create_report_store
from tradingagents.report_paths import generate_run_id

logger = logging.getLogger("agent_os.runs")

# Module-level MongoDB client singleton (lazy-initialized by _get_mongo_col)
_mongo_client: Any | None = None

router = APIRouter(prefix="/api/run", tags=["runs"])

engine = LangGraphEngine()
mock_engine = MockEngine()
run_tasks: dict[str, asyncio.Task] = {}


def _set_run_task(run_id: str, coro: AsyncGenerator[Any, None] | asyncio.Future[Any] | Any) -> None:
    existing = run_tasks.get(run_id)
    if existing and not existing.done():
        existing.cancel()
    run_tasks[run_id] = asyncio.create_task(coro)


def _clear_run_task(run_id: str) -> None:
    run_tasks.pop(run_id, None)


def _append_system_event(run_id: str, message: str) -> None:
    run = runs.get(run_id)
    if not run:
        return
    run.setdefault("events", []).append(
        {
            "id": f"log_{time.time_ns()}",
            "node_id": "__system__",
            "type": "log",
            "agent": "SYSTEM",
            "tier": "mid",
            "message": message,
            "metrics": {},
            "timestamp": time.strftime("%H:%M:%S"),
        }
    )
    _checkpoint_run_events(run_id)


def _set_failed_with_event(
    run_id: str, reason: str, *, log_exception: Exception | None = None
) -> None:
    """Mark run failed and append a visible system event with the failure reason."""
    run = runs.get(run_id)
    if not run:
        return
    operation = str(run.get("active_operation") or "").strip().lower()
    if operation == "phase3-decision":
        failure_label = "Phase 3 decision failed"
    elif operation:
        failure_label = f"{operation} failed"
    else:
        failure_label = "Run failed"
    run["status"] = "failed"
    run["error"] = reason
    run["error_stage"] = operation or None
    _append_system_event(run_id, f"{failure_label}: {reason}")
    if log_exception is not None:
        logger.exception("Run failed run=%s", run_id)


def _ensure_run_events_loaded_sync(run_id: str) -> None:
    """Synchronous implementation of run event loading (for use in threads)."""
    run = runs.get(run_id)
    if not run:
        return
    # If hydrated_from_disk is True, we may need to load even if 'events' is present
    # (to merge historical data with new resume-request logs).
    if not run.get("events") or run.get("hydrated_from_disk"):
        try:
            from tradingagents.portfolio.store_factory import create_report_store

            date = (run.get("params") or {}).get("date", "")
            if not date:
                return
            store = create_report_store(run_id=run_id)
            disk_events = store.load_run_events(date)
            if disk_events:
                # Deduplicate by 'id' to avoid doubling up on refresh/resume
                current_events = run.get("events") or []
                seen_ids = {e.get("id") for e in current_events if e.get("id")}

                merged = list(current_events)
                for de in disk_events:
                    if de.get("id") not in seen_ids:
                        merged.append(de)

                # Sort by timestamp if available
                # (events are usually appended, but sort is safer)
                # merged.sort(key=lambda x: x.get("ts", 0))

                run["events"] = merged

            # Clear the flag so we don't keep doing expensive disk reads
            run.pop("hydrated_from_disk", None)
        except Exception:
            logger.warning("Failed to lazy-load events for run=%s", run_id)


async def _ensure_run_events_loaded(run_id: str) -> None:
    """Load run events from disk in a background thread to avoid blocking the event loop."""
    run = runs.get(run_id)
    if not run:
        return
    if not run.get("events") or run.get("hydrated_from_disk"):
        await asyncio.to_thread(_ensure_run_events_loaded_sync, run_id)


def _final_scan_results(events: list[dict[str, Any]]) -> dict[str, str]:
    """Return the latest completed report per scan node.

    Scanner nodes can emit an early placeholder ``result`` before they finish
    their tool loop. We only treat a result as final when it appears after the
    node's last child tool/tool_result event.
    """
    last_child_idx: dict[str, int] = {}
    for idx, event in enumerate(events or []):
        parent = event.get("parent_node_id", "")
        if parent in SCAN_NODE_TO_REPORT_FIELD and event.get("type") in {"tool", "tool_result"}:
            last_child_idx[parent] = idx

    final_results: dict[str, str] = {}
    for idx, event in enumerate(events or []):
        node_id = event.get("node_id", "")
        if event.get("identifier") != "MARKET" or event.get("type") != "result":
            continue
        if node_id not in SCAN_NODE_TO_REPORT_FIELD:
            continue
        if idx <= last_child_idx.get(node_id, -1):
            continue
        content = str(event.get("response") or event.get("message") or "").strip()
        if content:
            final_results[node_id] = content
    return final_results


def _infer_scan_resume_node(events: list[dict[str, Any]]) -> str | None:
    """Pick the safest single-node resume point for an interrupted scan."""
    completed = set(_final_scan_results(events))
    if "macro_synthesis" in completed:
        return None

    missing_start_nodes = [node for node in SCANNER_START_NODES if node not in completed]
    if len(missing_start_nodes) > 1:
        return None
    if len(missing_start_nodes) == 1:
        return missing_start_nodes[0]

    if any(
        node not in completed
        for node in (
            "sector_scanner",
            "factor_alignment_scanner",
            "smart_money_scanner",
            "drift_scanner",
        )
    ):
        return "sector_scanner"
    if "industry_deep_dive" not in completed:
        return "industry_deep_dive"
    if "macro_synthesis" not in completed:
        return "macro_synthesis"
    return None


def _infer_pipeline_resume_phase(
    run_id: str, params: dict[str, Any]
) -> tuple[str | None, str | None]:
    ticker = str(params.get("ticker") or params.get("identifier") or "").strip()
    date = str(params.get("date") or "").strip()
    if not ticker or not date:
        return None, None
    try:
        store = create_report_store(run_id=run_id)
        snapshot = store.load_latest_pipeline_node_snapshot(date, ticker)
        if not snapshot:
            return None, None
        return infer_pipeline_resume_phase(snapshot), str(snapshot.get("node_name") or "")
    except ReportStoreError:
        logger.exception(
            "Failed to infer pipeline resume phase run=%s ticker=%s",
            run_id,
            ticker,
        )
        return None, None
    except Exception:
        # Resume inference is best-effort; unexpected errors should not block resuming.
        logger.exception(
            "Unexpected error inferring pipeline resume phase run=%s ticker=%s",
            run_id,
            ticker,
        )
        return None, None


def _persist_run_to_disk(run_id: str, *, include_meta: bool = True) -> None:
    """Persist run metadata and events to the report store."""
    run = runs.get(run_id)
    if not run:
        return
    try:
        from tradingagents.portfolio.store_factory import create_report_store

        store = create_report_store(run_id=run_id)
        date = (run.get("params") or {}).get("date", "")
        if not date:
            return
        meta = {
            "id": run_id,
            "type": run.get("type", ""),
            "status": run.get("status", ""),
            "created_at": run.get("created_at", 0),
            "completed_at": time.time(),
            "user_id": run.get("user_id", "anonymous"),
            "date": date,
            "params": run.get("params", {}),
            "rerun_seq": run.get("rerun_seq", 0),
        }
        if run.get("pending_phase3_decision"):
            meta["pending_phase3_decision"] = run["pending_phase3_decision"]
        store.save_run_events(date, run.get("events", []))
        if include_meta:
            store.save_run_meta(date, meta)
            logger.info("Persisted run to disk run=%s", run_id)
        else:
            logger.debug("Checkpointed run events to disk run=%s", run_id)
    except Exception:
        logger.exception("Failed to persist run to disk run=%s", run_id)


def _checkpoint_run_events(run_id: str) -> None:
    run = runs.get(run_id)
    if not run:
        return
    if run.get("events"):
        _persist_run_to_disk(run_id, include_meta=False)


async def _run_and_store(run_id: str, gen: AsyncGenerator[dict[str, Any], None]) -> None:
    """Drive an engine generator, updating run status and caching events."""
    runs[run_id]["status"] = "running"
    runs[run_id]["events"] = []
    runs[run_id].pop("error", None)
    runs[run_id].pop("error_stage", None)
    runs[run_id].pop("active_operation", None)
    runs[run_id].pop("pending_phase3_decision", None)
    try:
        async for event in gen:
            runs[run_id]["events"].append(event)
            await asyncio.to_thread(_checkpoint_run_events, run_id)
        runs[run_id]["status"] = "completed"
        runs[run_id].pop("active_operation", None)
    except AwaitPhase3Decision as exc:
        runs[run_id]["status"] = "awaiting_decision"
        runs[run_id]["pending_phase3_decision"] = exc.payload
        runs[run_id].pop("active_operation", None)
    except asyncio.CancelledError:
        _set_failed_with_event(
            run_id,
            "Run stopped by user" if runs[run_id].get("stop_requested") else "Run cancelled",
        )
        logger.warning("Run cancelled run=%s", run_id)
    except Exception as exc:
        _set_failed_with_event(run_id, str(exc), log_exception=exc)
    finally:
        runs[run_id].pop("stop_requested", None)
        await asyncio.to_thread(_persist_run_to_disk, run_id)
        _clear_run_task(run_id)


async def _resume_and_store(run_id: str, gen: AsyncGenerator[dict[str, Any], None]) -> None:
    """Drive a whole-run resume while preserving already-streamed events."""
    run = runs.get(run_id)
    if not run:
        return
    run["rerun_seq"] = run.get("rerun_seq", 0) + 1
    run["status"] = "running"
    run.pop("error", None)
    run.pop("error_stage", None)
    run.pop("pending_phase3_decision", None)
    try:
        async for event in gen:
            event["rerun_seq"] = run["rerun_seq"]
            run.setdefault("events", []).append(event)
            await asyncio.to_thread(_checkpoint_run_events, run_id)
        run["status"] = "completed"
        run.pop("active_operation", None)
    except AwaitPhase3Decision as exc:
        run["status"] = "awaiting_decision"
        run["pending_phase3_decision"] = exc.payload
        run.pop("active_operation", None)
    except asyncio.CancelledError:
        _set_failed_with_event(
            run_id,
            "Run stopped by user" if run.get("stop_requested") else "Run cancelled",
        )
        logger.warning("Run resume cancelled run=%s", run_id)
    except Exception as exc:
        _set_failed_with_event(run_id, str(exc), log_exception=exc)
    finally:
        run.pop("stop_requested", None)
        await asyncio.to_thread(_persist_run_to_disk, run_id)
        _clear_run_task(run_id)


@router.post("/scan")
async def trigger_scan(
    background_tasks: BackgroundTasks,
    params: dict[str, Any] | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    p = normalize_run_params("scan", params or {})
    run_id = generate_run_id()
    runs[run_id] = {
        "id": run_id,
        "type": "scan",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": p,
        "rerun_seq": 0,
    }
    background_tasks.add_task(_persist_run_to_disk, run_id)
    logger.info("Queued SCAN run=%s user=%s", run_id, user["user_id"])
    _set_run_task(run_id, _run_and_store(run_id, engine.run_scan(run_id, runs[run_id]["params"])))
    return {"run_id": run_id, "status": "queued"}


@router.post("/pipeline")
async def trigger_pipeline(
    background_tasks: BackgroundTasks,
    params: dict[str, Any] | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    p = normalize_run_params("pipeline", params or {})
    run_id = generate_run_id()
    runs[run_id] = {
        "id": run_id,
        "type": "pipeline",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": p,
        "rerun_seq": 0,
    }
    background_tasks.add_task(_persist_run_to_disk, run_id)
    logger.info("Queued PIPELINE run=%s user=%s", run_id, user["user_id"])
    _set_run_task(
        run_id, _run_and_store(run_id, engine.run_pipeline(run_id, runs[run_id]["params"]))
    )
    return {"run_id": run_id, "status": "queued"}


@router.post("/portfolio")
async def trigger_portfolio(
    background_tasks: BackgroundTasks,
    params: dict[str, Any] | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    p = normalize_run_params("portfolio", params or {})
    run_id = generate_run_id()
    runs[run_id] = {
        "id": run_id,
        "type": "portfolio",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": p,
        "rerun_seq": 0,
    }
    background_tasks.add_task(_persist_run_to_disk, run_id)
    logger.info("Queued PORTFOLIO run=%s user=%s", run_id, user["user_id"])
    _set_run_task(
        run_id, _run_and_store(run_id, engine.run_portfolio(run_id, runs[run_id]["params"]))
    )
    return {"run_id": run_id, "status": "queued"}


@router.post("/auto")
async def trigger_auto(
    background_tasks: BackgroundTasks,
    params: dict[str, Any] | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    p = normalize_run_params("auto", params or {})
    run_id = generate_run_id()
    runs[run_id] = {
        "id": run_id,
        "type": "auto",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": p,
        "rerun_seq": 0,
    }
    background_tasks.add_task(_persist_run_to_disk, run_id)
    logger.info("Queued AUTO run=%s user=%s", run_id, user["user_id"])
    _set_run_task(run_id, _run_and_store(run_id, engine.run_auto(run_id, runs[run_id]["params"])))
    return {"run_id": run_id, "status": "queued"}


@router.post("/mock")
async def trigger_mock(
    background_tasks: BackgroundTasks,
    params: dict[str, Any] | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Start a mock run that streams scripted events — no real LLM calls.

    Accepted params:
      mock_type : "pipeline" | "scan" | "auto"  (default: "pipeline")
      ticker    : ticker symbol for pipeline / auto  (default: "AAPL")
      tickers   : list of tickers for auto mock
      date      : analysis date  (default: today)
      speed     : delay divisor — 1.0 = realistic, 5.0 = fast  (default: 1.0)
    """
    p = normalize_run_params("mock", params or {})
    run_id = generate_run_id()
    runs[run_id] = {
        "id": run_id,
        "type": "mock",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": p,
        "rerun_seq": 0,
    }
    background_tasks.add_task(_persist_run_to_disk, run_id)
    logger.info(
        "Queued MOCK run=%s mock_type=%s user=%s",
        run_id,
        p.get("mock_type", "pipeline"),
        user["user_id"],
    )
    _set_run_task(run_id, _run_and_store(run_id, mock_engine.run_mock(run_id, p)))
    return {"run_id": run_id, "status": "queued"}


# Nodes produced by each phase (used to selectively remove stale events on re-run)
_DEBATE_TRADER_NODES = frozenset(
    {
        "Bull Researcher",
        "Bear Researcher",
        "Research Manager",
        "Trader",
        "Aggressive Analyst",
        "Conservative Analyst",
        "Neutral Analyst",
        "Portfolio Manager",
    }
)
_RISK_NODES = frozenset(
    {
        "Aggressive Analyst",
        "Conservative Analyst",
        "Neutral Analyst",
        "Portfolio Manager",
    }
)
# Portfolio-level cascade nodes always re-run after any phase re-run
_PORTFOLIO_NODES = frozenset({"review_holdings", "make_pm_decision"})


def _filter_rerun_events(events: list, ticker: str, phase: str) -> list:
    """Remove stale events for ticker+phase so fresh re-run events can replace them.

    Events for other tickers and phases earlier than the requested phase are kept,
    preserving the full auto-flow graph context in the UI.
    """
    if phase == "analysts":
        ticker_nodes_to_clear = None  # clear all nodes for this ticker
    elif phase == "debate_and_trader":
        ticker_nodes_to_clear = _DEBATE_TRADER_NODES
    elif phase == "risk":
        ticker_nodes_to_clear = _RISK_NODES
    else:
        return events  # unknown phase — keep everything

    kept = []
    for e in events:
        ident = e.get("identifier", "")
        node_id = e.get("node_id", "")
        parent = e.get("parent_node_id", "")
        # Always remove portfolio-level cascade events (they will be re-emitted)
        if node_id in _PORTFOLIO_NODES:
            continue
        # Remove stale ticker events for the phase being re-run
        if ident == ticker:
            if ticker_nodes_to_clear is None:
                continue
            if node_id in ticker_nodes_to_clear or parent in ticker_nodes_to_clear:
                continue
        kept.append(e)
    return kept


def _filter_scan_rerun_events(events: list, start_node: str) -> list:
    """Remove stale market-scan events for *start_node* and its downstream nodes."""
    nodes_to_clear = get_scanner_descendants(start_node)
    if not nodes_to_clear:
        return events

    kept = []
    for e in events:
        ident = e.get("identifier", "")
        node_id = e.get("node_id", "")
        parent = e.get("parent_node_id", "")
        if ident != "MARKET":
            kept.append(e)
            continue
        if node_id in nodes_to_clear or parent in nodes_to_clear:
            continue
        kept.append(e)
    return kept


def _build_scan_rerun_state(events: list) -> dict[str, Any]:
    """Reconstruct the latest market-scan state from cached run events."""
    state = {
        "messages": [],
        "gatekeeper_universe_report": "",
        "geopolitical_report": "",
        "market_movers_report": "",
        "sector_performance_report": "",
        "factor_alignment_report": "",
        "drift_opportunities_report": "",
        "smart_money_report": "",
        "industry_deep_dive_report": "",
        "macro_scan_summary": "",
        "sender": "",
    }
    for node_id, content in _final_scan_results(events).items():
        field = SCAN_NODE_TO_REPORT_FIELD.get(node_id, "")
        if content:
            state[field] = content
            state["sender"] = node_id
    return state


async def _append_and_store(
    run_id: str,
    gen: AsyncGenerator[dict[str, Any], None],
    ticker: str | None = None,
    phase: str | None = None,
) -> None:
    """Drive a re-run generator, preserving events from other tickers/phases."""
    run = runs.get(run_id)
    if not run:
        return
    run["rerun_seq"] = run.get("rerun_seq", 0) + 1
    run["status"] = "running"
    run.pop("error", None)
    run.pop("error_stage", None)
    # Preserve events for other tickers and earlier phases; remove only the stale
    # nodes that the re-run will replace.
    if ticker and phase:
        run["events"] = _filter_rerun_events(run.get("events") or [], ticker, phase)
    else:
        run["events"] = []
    try:
        async for event in gen:
            event["rerun_seq"] = run["rerun_seq"]
            run["events"].append(event)
            await asyncio.to_thread(_checkpoint_run_events, run_id)
        run["status"] = "completed"
        run.pop("active_operation", None)
    except asyncio.CancelledError:
        _set_failed_with_event(
            run_id,
            "Run stopped by user" if run.get("stop_requested") else "Run cancelled",
        )
        logger.warning("Rerun cancelled run=%s", run_id)
    except Exception as exc:
        _set_failed_with_event(run_id, str(exc), log_exception=exc)
    finally:
        run.pop("stop_requested", None)
        await asyncio.to_thread(_persist_run_to_disk, run_id)
        _clear_run_task(run_id)


async def _append_scan_rerun_and_store(
    run_id: str, gen: AsyncGenerator[dict[str, Any], None], start_node: str
) -> None:
    """Drive a market-scan rerun while preserving unaffected node events."""
    run = runs.get(run_id)
    if not run:
        return
    run["rerun_seq"] = run.get("rerun_seq", 0) + 1
    run["status"] = "running"
    run.pop("error", None)
    run.pop("error_stage", None)
    run["events"] = _filter_scan_rerun_events(run.get("events") or [], start_node)
    try:
        async for event in gen:
            event["rerun_seq"] = run["rerun_seq"]
            run["events"].append(event)
            await asyncio.to_thread(_checkpoint_run_events, run_id)
        run["status"] = "completed"
        run.pop("active_operation", None)
    except asyncio.CancelledError:
        _set_failed_with_event(
            run_id,
            "Run stopped by user" if run.get("stop_requested") else "Run cancelled",
        )
        logger.warning("Scan rerun cancelled run=%s", run_id)
    except Exception as exc:
        _set_failed_with_event(run_id, str(exc), log_exception=exc)
    finally:
        run.pop("stop_requested", None)
        await asyncio.to_thread(_persist_run_to_disk, run_id)
        _clear_run_task(run_id)


@router.post("/rerun-node")
async def trigger_rerun_node(
    background_tasks: BackgroundTasks,
    params: dict[str, Any],
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Re-run a phase of the trading pipeline for a specific ticker.

    Body: { run_id, node_id, identifier, date, portfolio_id }
    """
    run_id = params.get("run_id", "")
    node_id = params.get("node_id", "")
    identifier = params.get("identifier", "")
    date = params.get("date", "")
    portfolio_id = params.get("portfolio_id", "main_portfolio")

    if run_id not in runs:
        raise HTTPException(status_code=404, detail="Run not found")
    _run = runs[run_id]
    rerun_date = date or (_run.get("params") or {}).get("date", "")

    if identifier == "MARKET":
        if node_id not in SCAN_NODE_TO_REPORT_FIELD:
            raise HTTPException(status_code=422, detail=f"Unknown scan node_id: {node_id}")
        rerun_state = _build_scan_rerun_state(_run.get("events") or [])
        rerun_params = {
            "date": rerun_date,
            "portfolio_id": portfolio_id,
            "run_id": run_id,
            "max_tickers": (_run.get("params") or {}).get("max_tickers"),
        }
        logger.info(
            "Queued SCAN RERUN run=%s node=%s user=%s",
            run_id,
            node_id,
            user["user_id"],
        )
        runs[run_id]["status"] = "running"
        _set_run_task(
            run_id,
            _append_scan_rerun_and_store(
                run_id,
                engine.run_scan_from_node(
                    f"{run_id}_rerun_{node_id}", rerun_params, node_id, rerun_state
                ),
                start_node=node_id,
            ),
        )
        return {"run_id": run_id, "phase": node_id, "status": "queued"}

    if node_id not in NODE_TO_PHASE:
        raise HTTPException(status_code=422, detail=f"Unknown node_id: {node_id}")
    if not identifier:
        raise HTTPException(status_code=422, detail="identifier (ticker) is required")

    phase = NODE_TO_PHASE[node_id]
    rerun_params = {
        "ticker": identifier,
        "date": rerun_date,
        "portfolio_id": portfolio_id,
        "run_id": run_id,
    }

    logger.info(
        "Queued RERUN run=%s node=%s phase=%s ticker=%s user=%s",
        run_id,
        node_id,
        phase,
        identifier,
        user["user_id"],
    )
    # Set status synchronously so the WebSocket that reconnects immediately after
    # this response sees "running" and enters the polling loop instead of closing.
    runs[run_id]["status"] = "running"
    _set_run_task(
        run_id,
        _append_and_store(
            run_id,
            engine.run_pipeline_from_phase(f"{run_id}_rerun_{phase}", rerun_params, phase),
            ticker=identifier,
            phase=phase,
        ),
    )
    return {"run_id": run_id, "phase": phase, "status": "queued"}


@router.post("/{run_id}/resume")
async def resume_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if run_id not in runs:
        raise HTTPException(status_code=404, detail="Run not found")

    await _ensure_run_events_loaded(run_id)
    run = runs[run_id]
    status = run.get("status")
    if status == "completed":
        raise HTTPException(status_code=409, detail="Run already completed")
    if status == "running":
        return {"run_id": run_id, "status": "running"}

    params = dict(run.get("params") or {})
    date = params.get("date", "")
    run_type = run.get("type", "")
    portfolio_id = params.get("portfolio_id", "main_portfolio")

    logger.info("Queued RESUME run=%s type=%s user=%s", run_id, run_type, user["user_id"])

    if run_type == "scan":
        resume_node = _infer_scan_resume_node(run.get("events") or [])
        if resume_node:
            rerun_params = {
                "date": date,
                "portfolio_id": portfolio_id,
                "run_id": run_id,
                "max_tickers": params.get("max_tickers"),
            }
            rerun_state = _build_scan_rerun_state(run.get("events") or [])
            run["status"] = "running"
            run.pop("error", None)
            _append_system_event(run_id, f"Resume requested — continuing scan from {resume_node}.")
            _set_run_task(
                run_id,
                _append_scan_rerun_and_store(
                    run_id,
                    engine.run_scan_from_node(
                        f"{run_id}_resume_{resume_node}", rerun_params, resume_node, rerun_state
                    ),
                    start_node=resume_node,
                ),
            )
            return {
                "run_id": run_id,
                "status": "queued",
                "mode": "partial_scan",
                "phase": resume_node,
            }

        resume_params = {"date": date, "run_id": run_id, "_execution_key": f"{run_id}:resume:scan"}
        if params.get("max_tickers"):
            resume_params["max_tickers"] = params["max_tickers"]
        run["status"] = "running"
        run.pop("error", None)
        _append_system_event(run_id, "Resume requested — restarting scan on the same run.")
        _set_run_task(
            run_id,
            _resume_and_store(run_id, engine.run_scan(f"{run_id}:resume:scan", resume_params)),
        )
        return {"run_id": run_id, "status": "queued", "mode": "full_scan"}

    run["status"] = "running"
    run.pop("error", None)
    _append_system_event(
        run_id, f"Resume requested — continuing {run_type} run on the same run id."
    )
    resume_params = {**params, "run_id": run_id, "_execution_key": f"{run_id}:resume:{run_type}"}

    if run_type == "pipeline":
        phase, node_name = _infer_pipeline_resume_phase(run_id, params)
        if phase:
            _append_system_event(
                run_id,
                f"Resume requested — continuing pipeline from {node_name or phase} via {phase} checkpoint.",
            )
            modified_resume_params = {
                **params,
                "run_id": run_id,
                "_execution_key": f"{run_id}:resume:{run_type}",
            }
            if phase == "analysts":
                modified_resume_params["resume_from_latest_snapshot"] = True
                gen = engine.run_pipeline(
                    f"{run_id}:resume:pipeline",
                    modified_resume_params,
                )
            else:
                gen = engine.run_pipeline_from_phase(
                    f"{run_id}:resume:{phase}",
                    modified_resume_params,
                    phase,
                )
            _set_run_task(run_id, _resume_and_store(run_id, gen))
            return {
                "run_id": run_id,
                "status": "queued",
                "mode": "pipeline_checkpoint",
                "phase": phase,
            }

    if run_type == "auto":
        gen = engine.run_auto(f"{run_id}:resume:auto", resume_params)
    elif run_type == "pipeline":
        gen = engine.run_pipeline(f"{run_id}:resume:pipeline", resume_params)
    elif run_type == "portfolio":
        gen = engine.run_portfolio(f"{run_id}:resume:portfolio", resume_params)
    elif run_type == "mock":
        gen = mock_engine.run_mock(f"{run_id}:resume:mock", resume_params)
    else:
        raise HTTPException(status_code=422, detail=f"Unsupported run type: {run_type}")

    _set_run_task(run_id, _resume_and_store(run_id, gen))
    return {"run_id": run_id, "status": "queued", "mode": "same_run"}


@router.post("/{run_id}/phase3-decision")
async def submit_phase3_decision(
    run_id: str,
    params: dict[str, Any] | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.get("type") != "auto":
        raise HTTPException(
            status_code=422, detail="Phase 3 decisions are only supported for auto runs"
        )
    if run.get("status") != "awaiting_decision":
        raise HTTPException(status_code=409, detail="Run is not waiting for a Phase 3 decision")
    pending = run.get("pending_phase3_decision")
    if not pending:
        raise HTTPException(
            status_code=409, detail="No pending Phase 3 decision found for this run"
        )

    raw_retry = (params or {}).get("retry_tickers") or []
    if isinstance(raw_retry, str):
        raw_retry = raw_retry.split(",")
    retry_tickers: list[str] = []
    seen: set[str] = set()
    for item in raw_retry:
        ticker = str(item).strip().upper()
        if ticker and ticker not in seen:
            retry_tickers.append(ticker)
            seen.add(ticker)

    logger.info(
        "Queued PHASE3_DECISION run=%s retry_tickers=%s user=%s",
        run_id,
        retry_tickers,
        user["user_id"],
    )
    run["status"] = "running"
    run.pop("error", None)
    run.pop("error_stage", None)
    run["active_operation"] = "phase3-decision"
    decision_message = (
        "Phase 2 decision received — retrying selected ticker(s): " + ", ".join(retry_tickers)
        if retry_tickers
        else "Phase 2 decision received — continuing to Phase 3 without retrying incomplete tickers."
    )
    _append_system_event(run_id, decision_message)
    decision_params = {**(run.get("params") or {}), "run_id": run_id}
    _set_run_task(
        run_id,
        _resume_and_store(
            run_id,
            engine.run_auto_phase3_decision(
                f"{run_id}:phase3-decision", decision_params, retry_tickers, pending
            ),
        ),
    )
    return {
        "run_id": run_id,
        "status": "queued",
        "retry_tickers": retry_tickers,
    }


@router.post("/{run_id}/stop")
async def stop_run(
    run_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if run_id not in runs:
        raise HTTPException(status_code=404, detail="Run not found")

    run = runs[run_id]
    if run.get("status") in {"completed", "failed"}:
        return {"run_id": run_id, "status": run.get("status"), "stopped": False}
    if run.get("stop_requested"):
        return {"run_id": run_id, "status": "stopping", "stopped": True}

    task = run_tasks.get(run_id)
    if task and not task.done():
        run["stop_requested"] = True
        _append_system_event(run_id, "Immediate stop requested — terminating active tasks.")
        task.cancel()
        logger.info("Stop requested run=%s user=%s (task cancelled)", run_id, user["user_id"])
        return {"run_id": run_id, "status": "stopping", "stopped": True}

    current_status = run.get("status")
    if current_status in {"completed", "failed"}:
        return {"run_id": run_id, "status": current_status, "stopped": False}

    logger.info(
        "Stop requested but no active task was found run=%s user=%s", run_id, user["user_id"]
    )
    return {"run_id": run_id, "status": current_status or "running", "stopped": False}


class ResetPortfolioStageRequest(BaseModel):
    date: str
    portfolio_id: str


@router.delete("/portfolio-stage")
async def reset_portfolio_stage(
    params: ResetPortfolioStageRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete PM decision and execution result for a given date/portfolio_id.

    After calling this, an auto run will re-run Phase 3 from scratch
    (Phases 1 & 2 are skipped if their cached results still exist).
    """
    from tradingagents.portfolio.store_factory import create_report_store

    store = create_report_store()
    deleted = store.clear_portfolio_stage(params.date, params.portfolio_id)
    logger.info(
        "reset_portfolio_stage date=%s portfolio=%s deleted=%s user=%s",
        params.date,
        params.portfolio_id,
        deleted,
        user["user_id"],
    )
    return {"deleted": deleted, "date": params.date, "portfolio_id": params.portfolio_id}


def _get_mongo_col() -> Any | None:
    """Return the run_events collection if MongoDB is configured."""
    global _mongo_client
    uri = DEFAULT_CONFIG.get("mongo_uri")
    db_name = DEFAULT_CONFIG.get("mongo_db", "tradingagents")
    if uri:
        if _mongo_client is None:
            try:
                from pymongo import MongoClient

                _mongo_client = MongoClient(uri)
            except Exception:
                logger.warning("Failed to connect to MongoDB for historical events")
                return None
        return _mongo_client[db_name]["run_events"]
    return None


@router.get("/")
async def list_runs(user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    # Filter by user in production
    all_runs = dict(runs)

    # Supplement with historical metadata from MongoDB if available
    col = _get_mongo_col()
    if col is not None:
        try:
            # Fetch unique run_ids from the last 7 days (simplified)
            # In a real app, we'd have a separate 'runs' collection for metadata.
            # Here we use the events collection and group by run_id.
            pipeline = [
                {"$match": {"type": "log", "agent": "SYSTEM"}},  # Filter for start logs
                {"$sort": {"ts": -1}},
                {
                    "$group": {
                        "_id": "$run_id",
                        "id": {"$first": "$run_id"},
                        "type": {"$first": "$type"},
                        "created_at": {"$first": "$ts"},
                        # Status is harder to get from events without a dedicated meta doc
                    }
                },
                {"$limit": 50},
            ]
            for doc in col.aggregate(pipeline):
                rid = doc["id"]
                if rid not in all_runs:
                    all_runs[rid] = {
                        "id": rid,
                        "type": doc.get("type", "unknown"),
                        "status": "historical",
                        "created_at": doc.get("created_at", 0),
                        "user_id": "anonymous",
                    }
        except Exception:
            logger.warning("Failed to fetch historical runs from MongoDB")

    return list(all_runs.values())


@router.get("/{run_id}")
async def get_run_status(
    run_id: str, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    if run_id in runs:
        run = runs[run_id]
        await _ensure_run_events_loaded(run_id)
        if run.get("hydrated_from_disk") and run.get("status") == "running":
            _set_failed_with_event(run_id, "Run did not complete (server restarted)")
        # Derive nodes_fired from events for client compatibility
        events = run.get("events") or []
        run["nodes_fired"] = sorted(
            {
                e["node_id"]
                for e in events
                if isinstance(e, dict) and e.get("node_id") and e.get("node_id") != "__system__"
            }
        )
        return run

    # Not in memory — try MongoDB
    col = _get_mongo_col()
    if col is not None:
        try:
            cursor = col.find({"run_id": run_id}).sort("ts", 1)
            events = list(cursor)
            if events:
                # Remove MongoDB _id for JSON serialization
                for e in events:
                    e.pop("_id", None)
                return {
                    "id": run_id,
                    "status": "historical",
                    "events": events,
                    "type": events[0].get("type", "unknown") if events else "unknown",
                    "created_at": events[0].get("ts", 0) if events else 0,
                }
        except Exception:
            logger.warning("Failed to fetch historical run %s from MongoDB", run_id)

    raise HTTPException(status_code=404, detail="Run not found")
