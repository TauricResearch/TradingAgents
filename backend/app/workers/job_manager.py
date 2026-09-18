import asyncio
import contextlib
import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from ..core.config import settings
from ..core.database import db
from .runner import run_analysis_task

logger = logging.getLogger(__name__)

def _safe_json_dumps(obj: Any) -> str:
    def _default(o):
        if hasattr(o, "content"):
            return getattr(o, "content", str(o))
        if hasattr(o, "__dict__"):
            return {k: v for k, v in o.__dict__.items() if not k.startswith("_")}
        return str(o)
    try:
        return json.dumps(obj, default=_default, ensure_ascii=False)
    except Exception:
        return json.dumps(str(obj), ensure_ascii=False)

class JobManager:
    """Manages multi-job concurrency, worker thread pool, and real-time SSE event dispatching."""

    def __init__(self, max_workers: int = settings.MAX_CONCURRENT_JOBS):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ta_worker")
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        # job_id -> set of asyncio.Queue for live SSE streaming clients
        self._event_subscribers: dict[str, set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    def subscribe(self, job_id: str) -> asyncio.Queue:
        """Subscribe to real-time events for a specific job (used by SSE endpoint)."""
        queue: asyncio.Queue = asyncio.Queue()
        if job_id not in self._event_subscribers:
            self._event_subscribers[job_id] = set()
        self._event_subscribers[job_id].add(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue):
        """Unsubscribe when client disconnects."""
        if job_id in self._event_subscribers:
            self._event_subscribers[job_id].discard(queue)
            if not self._event_subscribers[job_id]:
                del self._event_subscribers[job_id]

    def _broadcast_event(self, job_id: str, event_type: str, data: dict[str, Any]):
        """Persist event to DB and broadcast to all active SSE subscribers."""
        # 1. Persist in database
        try:
            db.add_event(job_id, event_type, data)
        except Exception as e:
            logger.warning(f"Failed to persist event for job {job_id}: {e}")

        # 2. Update job status / progress on key events
        if event_type == "stage_change":
            stage = data.get("stage", "Running")
            progress = data.get("progress")
            db.update_job_status(job_id, status="running", progress=progress, current_stage=stage)
        elif event_type == "agent_completed":
            progress = data.get("progress")
            db.update_job_status(job_id, status="running", progress=progress, current_stage=f"Completed {data.get('agent')}")
        elif event_type == "debate_speech":
            progress = data.get("progress")
            db.update_job_status(job_id, status="running", progress=progress, current_stage="Bull vs Bear Debate")
        elif event_type == "trader_proposal":
            progress = data.get("progress")
            db.update_job_status(job_id, status="running", progress=progress, current_stage="Formulating Trade Proposal")
        elif event_type == "risk_speech":
            progress = data.get("progress")
            db.update_job_status(job_id, status="running", progress=progress, current_stage="Risk Management Debate")
        elif event_type == "final_decision":
            progress = data.get("progress")
            signal = data.get("rating")
            db.update_job_status(job_id, status="running", progress=progress, current_stage="Final Portfolio Decision", decision_signal=signal)

        # 3. Notify connected SSE clients
        if job_id in self._event_subscribers:
            event_payload = {
                "job_id": job_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "event_type": event_type,
                "data": data
            }
            for q in list(self._event_subscribers[job_id]):
                with contextlib.suppress(asyncio.QueueFull):
                    q.put_nowait(event_payload)

    async def create_and_start_job(self, req_dict: dict[str, Any]) -> dict[str, Any]:
        """Create a job entry and launch it asynchronously in the worker pool."""
        job_id = str(uuid.uuid4())
        trade_date = req_dict.get("trade_date") or datetime.now().strftime("%Y-%m-%d")

        job_record = {
            "id": job_id,
            "ticker": req_dict["ticker"].strip().upper(),
            "trade_date": trade_date,
            "asset_type": req_dict.get("asset_type", "stock"),
            "analysts": json.dumps(req_dict.get("analysts", ["market", "social", "news", "fundamentals"])),
            "llm_provider": req_dict.get("llm_provider", "openai"),
            "deep_think_llm": req_dict.get("deep_think_llm", "gpt-5.6"),
            "quick_think_llm": req_dict.get("quick_think_llm", "gpt-5.6-luna"),
            "max_debate_rounds": req_dict.get("max_debate_rounds", 1),
            "max_risk_discuss_rounds": req_dict.get("max_risk_discuss_rounds", 1),
            "output_language": req_dict.get("output_language", "English"),
            "status": "queued",
            "progress": 0,
            "current_stage": "Queued in worker pool",
            "created_at": datetime.utcnow().isoformat() + "Z"
        }

        # Save to DB
        created_job = db.create_job(job_record)

        # Launch worker task in background
        task = asyncio.create_task(self._execute_job(created_job))
        async with self._lock:
            self._running_tasks[job_id] = task

        return db.get_job(job_id)

    async def _execute_job(self, job_dict: dict[str, Any]):
        job_id = job_dict["id"]
        started_at = datetime.utcnow().isoformat() + "Z"

        db.update_job_status(job_id, status="running", progress=5, current_stage="Starting execution", started_at=started_at)
        self._broadcast_event(job_id, "job_started", {"job_id": job_id, "started_at": started_at})

        loop = asyncio.get_running_loop()
        cancel_event = threading.Event()
        self._cancel_events[job_id] = cancel_event

        # Bridge callback from worker thread to async event loop
        def thread_event_callback(event_type: str, data: dict[str, Any]):
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._broadcast_event, job_id, event_type, data)

        try:
            # Run the heavy agent graph in the worker thread pool with cancel_event
            result = await loop.run_in_executor(
                self.executor,
                run_analysis_task,
                job_dict,
                thread_event_callback,
                cancel_event
            )

            completed_at = datetime.utcnow().isoformat() + "Z"

            if result.get("status") == "completed":
                db.update_job_status(
                    job_id,
                    status="completed",
                    progress=100,
                    current_stage="Completed",
                    decision_signal=result.get("decision_signal"),
                    completed_at=completed_at,
                    duration_seconds=result.get("duration_seconds")
                )

                # Save report
                db.save_report({
                    "job_id": job_id,
                    "final_state": _safe_json_dumps(result.get("final_state", {})),
                    "complete_report_md": result.get("complete_report_md", ""),
                    "executive_summary": result.get("executive_summary", ""),
                    "recommendation": result.get("recommendation", ""),
                    "entry_price": result.get("entry_price"),
                    "stop_loss": result.get("stop_loss"),
                    "target_price": result.get("target_price"),
                    "market_report_md": result.get("market_report_md", ""),
                    "sentiment_report_md": result.get("sentiment_report_md", ""),
                    "news_report_md": result.get("news_report_md", ""),
                    "fundamentals_report_md": result.get("fundamentals_report_md", "")
                })
            elif result.get("status") == "cancelled":
                db.update_job_status(
                    job_id,
                    status="cancelled",
                    current_stage="Cancelled by user",
                    completed_at=completed_at,
                    duration_seconds=result.get("duration_seconds")
                )
                self._broadcast_event(job_id, "job_cancelled", {"job_id": job_id})
            else:
                db.update_job_status(
                    job_id,
                    status="failed",
                    current_stage="Failed",
                    error_message=result.get("error_message"),
                    completed_at=completed_at,
                    duration_seconds=result.get("duration_seconds")
                )

        except asyncio.CancelledError:
            completed_at = datetime.utcnow().isoformat() + "Z"
            db.update_job_status(job_id, status="cancelled", current_stage="Cancelled by user", completed_at=completed_at)
            self._broadcast_event(job_id, "job_cancelled", {"job_id": job_id})
        except Exception as e:
            completed_at = datetime.utcnow().isoformat() + "Z"
            logger.error(f"Unhandled error in _execute_job {job_id}: {e}")
            db.update_job_status(job_id, status="failed", current_stage="Failed with error", error_message=str(e), completed_at=completed_at)
            self._broadcast_event(job_id, "job_failed", {"job_id": job_id, "error": str(e)})
        finally:
            self._cancel_events.pop(job_id, None)
            async with self._lock:
                if job_id in self._running_tasks:
                    del self._running_tasks[job_id]

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running or queued job."""
        # 1. Trigger thread-level cancel flag
        if job_id in self._cancel_events:
            self._cancel_events[job_id].set()

        # 2. Cancel async task wrapper
        async with self._lock:
            task = self._running_tasks.get(job_id)
            if task and not task.done():
                task.cancel()
                return True
        # If it's in queued status in DB, mark cancelled
        job = db.get_job(job_id)
        if job and job["status"] in ("queued", "running"):
            db.update_job_status(job_id, status="cancelled", current_stage="Cancelled by user")
            self._broadcast_event(job_id, "job_cancelled", {"job_id": job_id})
            return True
        return False


job_manager = JobManager()
