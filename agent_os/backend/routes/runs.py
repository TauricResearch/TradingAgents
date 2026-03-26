from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from typing import Dict, Any, List, AsyncGenerator
import logging
import uuid
import time
import os
from agent_os.backend.store import runs
from agent_os.backend.dependencies import get_current_user
from agent_os.backend.services.langgraph_engine import LangGraphEngine, NODE_TO_PHASE
from agent_os.backend.services.mock_engine import MockEngine
from tradingagents.report_paths import generate_flow_id, generate_run_id

logger = logging.getLogger("agent_os.runs")

router = APIRouter(prefix="/api/run", tags=["runs"])

engine = LangGraphEngine()
mock_engine = MockEngine()


def _persist_run_to_disk(run_id: str) -> None:
    """Persist run metadata and events to the report store."""
    run = runs.get(run_id)
    if not run:
        return
    try:
        from tradingagents.portfolio.store_factory import create_report_store
        flow_id = run.get("flow_id") or run.get("short_rid") or run_id[:8]
        store = create_report_store(flow_id=flow_id)
        date = (run.get("params") or {}).get("date", "")
        if not date:
            return
        meta = {
            "id": run_id,
            "flow_id": flow_id,
            "short_rid": flow_id,  # backward compat alias
            "type": run.get("type", ""),
            "status": run.get("status", ""),
            "created_at": run.get("created_at", 0),
            "completed_at": time.time(),
            "user_id": run.get("user_id", "anonymous"),
            "date": date,
            "params": run.get("params", {}),
            "rerun_seq": run.get("rerun_seq", 0),
        }
        store.save_run_meta(date, meta)
        store.save_run_events(date, run.get("events", []))
        logger.info("Persisted run to disk run=%s flow_id=%s", run_id, flow_id)
    except Exception:
        logger.exception("Failed to persist run to disk run=%s", run_id)


async def _run_and_store(run_id: str, gen: AsyncGenerator[Dict[str, Any], None]) -> None:
    """Drive an engine generator, updating run status and caching events."""
    runs[run_id]["status"] = "running"
    runs[run_id]["events"] = []
    try:
        async for event in gen:
            runs[run_id]["events"].append(event)
        runs[run_id]["status"] = "completed"
    except Exception as exc:
        runs[run_id]["status"] = "failed"
        runs[run_id]["error"] = str(exc)
        logger.exception("Run failed run=%s", run_id)
    finally:
        _persist_run_to_disk(run_id)


@router.post("/scan")
async def trigger_scan(
    background_tasks: BackgroundTasks,
    params: Dict[str, Any] = None,
    user: dict = Depends(get_current_user)
):
    p = params or {}
    run_id = str(uuid.uuid4())
    flow_id = p.get("flow_id") or generate_flow_id()
    runs[run_id] = {
        "id": run_id,
        "flow_id": flow_id,
        "short_rid": flow_id,  # backward compat alias
        "type": "scan",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": {**p, "flow_id": flow_id},
        "rerun_seq": 0,
    }
    logger.info("Queued SCAN run=%s flow_id=%s user=%s", run_id, flow_id, user["user_id"])
    background_tasks.add_task(_run_and_store, run_id, engine.run_scan(run_id, runs[run_id]["params"]))
    return {"run_id": run_id, "flow_id": flow_id, "status": "queued"}

@router.post("/pipeline")
async def trigger_pipeline(
    background_tasks: BackgroundTasks,
    params: Dict[str, Any] = None,
    user: dict = Depends(get_current_user)
):
    p = params or {}
    run_id = str(uuid.uuid4())
    flow_id = p.get("flow_id") or generate_flow_id()
    runs[run_id] = {
        "id": run_id,
        "flow_id": flow_id,
        "short_rid": flow_id,
        "type": "pipeline",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": {**p, "flow_id": flow_id},
        "rerun_seq": 0,
    }
    logger.info("Queued PIPELINE run=%s flow_id=%s user=%s", run_id, flow_id, user["user_id"])
    background_tasks.add_task(_run_and_store, run_id, engine.run_pipeline(run_id, runs[run_id]["params"]))
    return {"run_id": run_id, "flow_id": flow_id, "status": "queued"}

@router.post("/portfolio")
async def trigger_portfolio(
    background_tasks: BackgroundTasks,
    params: Dict[str, Any] = None,
    user: dict = Depends(get_current_user)
):
    p = params or {}
    run_id = str(uuid.uuid4())
    flow_id = p.get("flow_id") or generate_flow_id()
    runs[run_id] = {
        "id": run_id,
        "flow_id": flow_id,
        "short_rid": flow_id,
        "type": "portfolio",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": {**p, "flow_id": flow_id},
        "rerun_seq": 0,
    }
    logger.info("Queued PORTFOLIO run=%s flow_id=%s user=%s", run_id, flow_id, user["user_id"])
    background_tasks.add_task(_run_and_store, run_id, engine.run_portfolio(run_id, runs[run_id]["params"]))
    return {"run_id": run_id, "flow_id": flow_id, "status": "queued"}

@router.post("/auto")
async def trigger_auto(
    background_tasks: BackgroundTasks,
    params: Dict[str, Any] = None,
    user: dict = Depends(get_current_user)
):
    p = params or {}
    run_id = str(uuid.uuid4())
    flow_id = p.get("flow_id") or generate_flow_id()
    runs[run_id] = {
        "id": run_id,
        "flow_id": flow_id,
        "short_rid": flow_id,
        "type": "auto",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": {**p, "flow_id": flow_id},
        "rerun_seq": 0,
    }
    logger.info("Queued AUTO run=%s flow_id=%s user=%s", run_id, flow_id, user["user_id"])
    background_tasks.add_task(_run_and_store, run_id, engine.run_auto(run_id, runs[run_id]["params"]))
    return {"run_id": run_id, "flow_id": flow_id, "status": "queued"}

@router.post("/mock")
async def trigger_mock(
    background_tasks: BackgroundTasks,
    params: Dict[str, Any] = None,
    user: dict = Depends(get_current_user),
):
    """Start a mock run that streams scripted events — no real LLM calls.

    Accepted params:
      mock_type : "pipeline" | "scan" | "auto"  (default: "pipeline")
      ticker    : ticker symbol for pipeline / auto  (default: "AAPL")
      tickers   : list of tickers for auto mock
      date      : analysis date  (default: today)
      speed     : delay divisor — 1.0 = realistic, 5.0 = fast  (default: 1.0)
    """
    p = params or {}
    run_id = str(uuid.uuid4())
    flow_id = p.get("flow_id") or generate_flow_id()
    p_with_flow = {**p, "flow_id": flow_id}
    runs[run_id] = {
        "id": run_id,
        "flow_id": flow_id,
        "short_rid": flow_id,
        "type": "mock",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": p_with_flow,
        "rerun_seq": 0,
    }
    logger.info(
        "Queued MOCK run=%s mock_type=%s flow_id=%s user=%s",
        run_id, p.get("mock_type", "pipeline"), flow_id, user["user_id"],
    )
    background_tasks.add_task(
        _run_and_store, run_id, mock_engine.run_mock(run_id, p_with_flow)
    )
    return {"run_id": run_id, "flow_id": flow_id, "status": "queued"}

# Nodes produced by each phase (used to selectively remove stale events on re-run)
_DEBATE_TRADER_NODES = frozenset({
    "Bull Researcher", "Bear Researcher", "Research Manager", "Trader",
    "Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager",
})
_RISK_NODES = frozenset({
    "Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager",
})
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


async def _append_and_store(run_id: str, gen, ticker: str = None, phase: str = None) -> None:
    """Drive a re-run generator, preserving events from other tickers/phases."""
    run = runs.get(run_id)
    if not run:
        return
    run["rerun_seq"] = run.get("rerun_seq", 0) + 1
    run["status"] = "running"
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
        run["status"] = "completed"
    except Exception as exc:
        run["status"] = "failed"
        run["error"] = str(exc)
        logger.exception("Rerun failed run=%s", run_id)
    finally:
        _persist_run_to_disk(run_id)


@router.post("/rerun-node")
async def trigger_rerun_node(
    background_tasks: BackgroundTasks,
    params: Dict[str, Any],
    user: dict = Depends(get_current_user),
):
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
    if node_id not in NODE_TO_PHASE:
        raise HTTPException(status_code=422, detail=f"Unknown node_id: {node_id}")
    if not identifier:
        raise HTTPException(status_code=422, detail="identifier (ticker) is required")

    phase = NODE_TO_PHASE[node_id]
    _run = runs[run_id]
    _orig_flow_id = (
        _run.get("flow_id")
        or _run.get("short_rid")
        or (_run.get("params") or {}).get("flow_id")
    )
    rerun_params = {
        "ticker": identifier,
        "date": date or (_run.get("params") or {}).get("date", ""),
        "portfolio_id": portfolio_id,
        "flow_id": _orig_flow_id,  # preserve original flow_id for checkpoint lookup
    }

    logger.info(
        "Queued RERUN run=%s node=%s phase=%s ticker=%s user=%s",
        run_id, node_id, phase, identifier, user["user_id"],
    )
    # Set status synchronously so the WebSocket that reconnects immediately after
    # this response sees "running" and enters the polling loop instead of closing.
    runs[run_id]["status"] = "running"
    background_tasks.add_task(
        _append_and_store,
        run_id,
        engine.run_pipeline_from_phase(f"{run_id}_rerun_{phase}", rerun_params, phase),
        ticker=identifier,
        phase=phase,
    )
    return {"run_id": run_id, "phase": phase, "status": "queued"}


@router.delete("/portfolio-stage")
async def reset_portfolio_stage(
    params: Dict[str, Any],
    user: dict = Depends(get_current_user),
):
    """Delete PM decision and execution result for a given date/portfolio_id.

    After calling this, an auto run will re-run Phase 3 from scratch
    (Phases 1 & 2 are skipped if their cached results still exist).
    """
    from tradingagents.portfolio.store_factory import create_report_store
    date = params.get("date")
    portfolio_id = params.get("portfolio_id")
    if not date or not portfolio_id:
        raise HTTPException(status_code=422, detail="date and portfolio_id are required")
    store = create_report_store()
    deleted = store.clear_portfolio_stage(date, portfolio_id)
    logger.info("reset_portfolio_stage date=%s portfolio=%s deleted=%s user=%s", date, portfolio_id, deleted, user["user_id"])
    return {"deleted": deleted, "date": date, "portfolio_id": portfolio_id}


def _get_mongo_col():
    """Return the run_events collection if MongoDB is configured."""
    uri = os.getenv("TRADINGAGENTS_MONGO_URI")
    db_name = os.getenv("TRADINGAGENTS_MONGO_DB", "tradingagents")
    if uri:
        try:
            from pymongo import MongoClient
            client = MongoClient(uri)
            return client[db_name]["run_events"]
        except Exception:
            logger.warning("Failed to connect to MongoDB for historical events")
    return None


@router.get("/")
async def list_runs(user: dict = Depends(get_current_user)):
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
                {"$match": {"type": "log", "agent": "SYSTEM"}}, # Filter for start logs
                {"$sort": {"ts": -1}},
                {"$group": {
                    "_id": "$run_id",
                    "id": {"$first": "$run_id"},
                    "type": {"$first": "$type"},
                    "created_at": {"$first": "$ts"},
                    # Status is harder to get from events without a dedicated meta doc
                }},
                {"$limit": 50}
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
async def get_run_status(run_id: str, user: dict = Depends(get_current_user)):
    if run_id in runs:
        run = runs[run_id]
        # Lazy-load events from disk if they were not kept in memory
        if (
            not run.get("events")
            and run.get("status") in ("completed", "failed")
        ):
            try:
                from tradingagents.portfolio.store_factory import create_report_store
                flow_id = run.get("flow_id") or run.get("short_rid") or run_id[:8]
                store = create_report_store(flow_id=flow_id)
                date = (run.get("params") or {}).get("date", "")
                if date:
                    events = store.load_run_events(date)
                    if events:
                        run["events"] = events
            except Exception:
                logger.warning("Failed to lazy-load events for run=%s", run_id)
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
