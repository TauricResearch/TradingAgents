from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable


class JobService:
    """Application-layer job state orchestrator with legacy-compatible payloads."""

    def __init__(
        self,
        *,
        task_results: dict[str, dict],
        analysis_tasks: dict[str, asyncio.Task],
        processes: dict[str, Any],
        persist_task: Callable[[str, dict], None],
        delete_task: Callable[[str], None],
    ):
        self.task_results = task_results
        self.analysis_tasks = analysis_tasks
        self.processes = processes
        self.persist_task = persist_task
        self.delete_task = delete_task

    def restore_task_results(self, restored: dict[str, dict]) -> None:
        self.task_results.update(restored)

    def create_portfolio_job(self, *, task_id: str, total: int) -> dict:
        state = {
            "task_id": task_id,
            "type": "portfolio",
            "status": "running",
            "total": total,
            "completed": 0,
            "failed": 0,
            "current_ticker": None,
            "results": [],
            "error": None,
            "created_at": datetime.now().isoformat(),
        }
        self.task_results[task_id] = state
        self.processes.setdefault(task_id, None)
        return state

    def update_portfolio_progress(self, task_id: str, *, ticker: str, completed: int) -> dict:
        state = self.task_results[task_id]
        state["current_ticker"] = ticker
        state["status"] = "running"
        state["completed"] = completed
        return state

    def append_portfolio_result(self, task_id: str, rec: dict) -> dict:
        state = self.task_results[task_id]
        state["completed"] += 1
        state["results"].append(rec)
        return state

    def mark_portfolio_failure(self, task_id: str) -> dict:
        state = self.task_results[task_id]
        state["failed"] += 1
        return state

    def complete_job(self, task_id: str) -> dict:
        state = self.task_results[task_id]
        state["status"] = "completed"
        state["current_ticker"] = None
        self.persist_task(task_id, state)
        return state

    def fail_job(self, task_id: str, error: str) -> dict:
        state = self.task_results[task_id]
        state["status"] = "failed"
        state["error"] = error
        self.persist_task(task_id, state)
        return state

    def register_background_task(self, task_id: str, task: asyncio.Task) -> None:
        self.analysis_tasks[task_id] = task

    def register_process(self, task_id: str, process: Any) -> None:
        self.processes[task_id] = process

    def cancel_job(self, task_id: str, error: str = "用户取消") -> dict | None:
        task = self.analysis_tasks.get(task_id)
        if task:
            task.cancel()
        state = self.task_results.get(task_id)
        if not state:
            return None
        state["status"] = "failed"
        state["error"] = error
        self.persist_task(task_id, state)
        return state
