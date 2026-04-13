from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable


CONTRACT_VERSION = "v1alpha1"
DEFAULT_EXECUTOR_TYPE = "legacy_subprocess"


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
        self.task_results.update(
            {
                task_id: self._normalize_task_state(task_id, state)
                for task_id, state in restored.items()
            }
        )

    def create_analysis_job(
        self,
        *,
        task_id: str,
        ticker: str,
        date: str,
        request_id: str | None = None,
        executor_type: str = DEFAULT_EXECUTOR_TYPE,
        contract_version: str = CONTRACT_VERSION,
        result_ref: str | None = None,
    ) -> dict:
        state = self._normalize_task_state(task_id, {
            "task_id": task_id,
            "ticker": ticker,
            "date": date,
            "status": "running",
            "progress": 0,
            "current_stage": "analysts",
            "created_at": datetime.now().isoformat(),
            "elapsed_seconds": 0,
            "elapsed": 0,
            "stages": [
                {
                    "name": stage_name,
                    "status": "running" if index == 0 else "pending",
                    "completed_at": None,
                }
                for index, stage_name in enumerate(
                    ["analysts", "research", "trading", "risk", "portfolio"]
                )
            ],
            "logs": [],
            "decision": None,
            "quant_signal": None,
            "llm_signal": None,
            "confidence": None,
            "result": None,
            "error": None,
            "request_id": request_id,
            "executor_type": executor_type,
            "contract_version": contract_version,
            "result_ref": result_ref,
        })
        self.task_results[task_id] = state
        self.processes.setdefault(task_id, None)
        return state

    def create_portfolio_job(
        self,
        *,
        task_id: str,
        total: int,
        request_id: str | None = None,
        executor_type: str = DEFAULT_EXECUTOR_TYPE,
        contract_version: str = CONTRACT_VERSION,
        result_ref: str | None = None,
    ) -> dict:
        state = self._normalize_task_state(task_id, {
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
            "request_id": request_id,
            "executor_type": executor_type,
            "contract_version": contract_version,
            "result_ref": result_ref,
        })
        self.task_results[task_id] = state
        self.processes.setdefault(task_id, None)
        return state

    def attach_result_contract(
        self,
        task_id: str,
        *,
        result_ref: str,
        contract_version: str = CONTRACT_VERSION,
        executor_type: str | None = None,
    ) -> dict:
        state = self.task_results[task_id]
        state["result_ref"] = result_ref
        state["contract_version"] = contract_version or state.get("contract_version") or CONTRACT_VERSION
        if executor_type:
            state["executor_type"] = executor_type
        return state

    def complete_analysis_job(
        self,
        task_id: str,
        *,
        contract: dict,
        result_ref: str,
        executor_type: str | None = None,
    ) -> dict:
        state = self.task_results[task_id]
        result = dict(contract.get("result") or {})
        signals = result.get("signals") or {}
        quant = signals.get("quant") or {}
        llm = signals.get("llm") or {}

        state["status"] = contract.get("status", "completed")
        state["progress"] = contract.get("progress", 100)
        state["current_stage"] = contract.get("current_stage", state.get("current_stage"))
        state["elapsed_seconds"] = contract.get("elapsed_seconds", state.get("elapsed_seconds", 0))
        state["elapsed"] = contract.get("elapsed", state["elapsed_seconds"])
        state["decision"] = result.get("decision")
        state["quant_signal"] = quant.get("rating")
        state["llm_signal"] = llm.get("rating")
        state["confidence"] = result.get("confidence")
        state["result"] = result
        state["error"] = contract.get("error")
        state["contract_version"] = contract.get("contract_version", state.get("contract_version"))
        self.attach_result_contract(
            task_id,
            result_ref=result_ref,
            contract_version=state["contract_version"],
            executor_type=executor_type,
        )
        self.persist_task(task_id, state)
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

    @staticmethod
    def _normalize_task_state(task_id: str, state: dict) -> dict:
        normalized = dict(state)
        normalized.setdefault("request_id", task_id)
        normalized.setdefault("executor_type", DEFAULT_EXECUTOR_TYPE)
        normalized.setdefault("contract_version", CONTRACT_VERSION)
        normalized.setdefault("result_ref", None)
        return normalized
