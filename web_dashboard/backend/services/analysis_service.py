from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Awaitable, Callable, Optional

from .executor import AnalysisExecutionOutput, AnalysisExecutor, AnalysisExecutorError
from .request_context import RequestContext

BroadcastFn = Callable[[str, dict], Awaitable[None]]
ANALYSIS_STAGE_NAMES = ["analysts", "research", "trading", "risk", "portfolio"]


class AnalysisService:
    """Application service that orchestrates backend analysis jobs without owning strategy logic."""

    def __init__(
        self,
        *,
        executor: AnalysisExecutor,
        result_store,
        job_service,
        retry_count: int = 2,
        retry_base_delay_secs: int = 1,
    ):
        self.executor = executor
        self.result_store = result_store
        self.job_service = job_service
        self.retry_count = retry_count
        self.retry_base_delay_secs = retry_base_delay_secs

    async def start_analysis(
        self,
        *,
        task_id: str,
        ticker: str,
        date: str,
        request_context: RequestContext,
        broadcast_progress: BroadcastFn,
    ) -> dict:
        state = self.job_service.create_analysis_job(
            task_id=task_id,
            ticker=ticker,
            date=date,
            request_id=request_context.request_id,
            executor_type=request_context.executor_type,
            contract_version=request_context.contract_version,
        )
        self.job_service.register_process(task_id, None)
        await broadcast_progress(task_id, state)

        task = asyncio.create_task(
            self._run_analysis(
                task_id=task_id,
                ticker=ticker,
                date=date,
                request_context=request_context,
                broadcast_progress=broadcast_progress,
            )
        )
        self.job_service.register_background_task(task_id, task)
        return {
            "contract_version": "v1alpha1",
            "task_id": task_id,
            "ticker": ticker,
            "date": date,
            "status": "running",
        }

    async def start_portfolio_analysis(
        self,
        *,
        task_id: str,
        date: str,
        request_context: RequestContext,
        broadcast_progress: BroadcastFn,
    ) -> dict:
        watchlist = self.result_store.get_watchlist()
        if not watchlist:
            raise ValueError("自选股为空，请先添加股票")

        state = self.job_service.create_portfolio_job(
            task_id=task_id,
            total=len(watchlist),
            request_id=request_context.request_id,
            executor_type=request_context.executor_type,
            contract_version=request_context.contract_version,
        )
        await broadcast_progress(task_id, state)

        task = asyncio.create_task(
            self._run_portfolio_analysis(
                task_id=task_id,
                date=date,
                watchlist=watchlist,
                request_context=request_context,
                broadcast_progress=broadcast_progress,
            )
        )
        self.job_service.register_background_task(task_id, task)
        return {
            "contract_version": "v1alpha1",
            "task_id": task_id,
            "total": len(watchlist),
            "status": "running",
        }

    async def _run_analysis(
        self,
        *,
        task_id: str,
        ticker: str,
        date: str,
        request_context: RequestContext,
        broadcast_progress: BroadcastFn,
    ) -> None:
        start_time = time.monotonic()
        try:
            output = await self.executor.execute(
                task_id=task_id,
                ticker=ticker,
                date=date,
                request_context=request_context,
                on_stage=lambda stage: self._handle_analysis_stage(
                    task_id=task_id,
                    stage_name=stage,
                    started_at=start_time,
                    broadcast_progress=broadcast_progress,
                ),
            )
            state = self.job_service.task_results[task_id]
            elapsed_seconds = int(time.monotonic() - start_time)
            contract = output.to_result_contract(
                task_id=task_id,
                ticker=ticker,
                date=date,
                created_at=state["created_at"],
                elapsed_seconds=elapsed_seconds,
                current_stage=ANALYSIS_STAGE_NAMES[-1],
            )
            result_ref = self.result_store.save_result_contract(task_id, contract)
            self.job_service.complete_analysis_job(
                task_id,
                contract=contract,
                result_ref=result_ref,
                executor_type=request_context.executor_type,
            )
        except AnalysisExecutorError as exc:
            self._fail_analysis_state(
                task_id=task_id,
                message=str(exc),
                started_at=start_time,
                code=exc.code,
                retryable=exc.retryable,
            )
        except Exception as exc:
            self._fail_analysis_state(
                task_id=task_id,
                message=str(exc),
                started_at=start_time,
                code="analysis_failed",
                retryable=False,
            )

        await broadcast_progress(task_id, self.job_service.task_results[task_id])

    async def _handle_analysis_stage(
        self,
        *,
        task_id: str,
        stage_name: str,
        started_at: float,
        broadcast_progress: BroadcastFn,
    ) -> None:
        state = self.job_service.task_results[task_id]
        try:
            idx = ANALYSIS_STAGE_NAMES.index(stage_name)
        except ValueError:
            return

        for i, entry in enumerate(state["stages"]):
            if i < idx:
                if entry["status"] != "completed":
                    entry["status"] = "completed"
                    entry["completed_at"] = datetime.now().strftime("%H:%M:%S")
            elif i == idx:
                entry["status"] = "completed"
                entry["completed_at"] = entry["completed_at"] or datetime.now().strftime("%H:%M:%S")
            elif i == idx + 1 and entry["status"] == "pending":
                entry["status"] = "running"

        state["progress"] = int((idx + 1) / len(ANALYSIS_STAGE_NAMES) * 100)
        state["current_stage"] = stage_name
        state["elapsed_seconds"] = int(time.monotonic() - started_at)
        state["elapsed"] = state["elapsed_seconds"]
        await broadcast_progress(task_id, state)

    async def _run_portfolio_analysis(
        self,
        *,
        task_id: str,
        date: str,
        watchlist: list[dict],
        request_context: RequestContext,
        broadcast_progress: BroadcastFn,
    ) -> None:
        try:
            for index, stock in enumerate(watchlist):
                stock = {**stock, "_idx": index}
                ticker = stock["ticker"]
                await broadcast_progress(
                    task_id,
                    self.job_service.update_portfolio_progress(task_id, ticker=ticker, completed=index),
                )

                success, rec = await self._run_single_portfolio_analysis(
                    task_id=task_id,
                    ticker=ticker,
                    stock=stock,
                    date=date,
                    request_context=request_context,
                )
                if success and rec is not None:
                    self.job_service.append_portfolio_result(task_id, rec)
                else:
                    self.job_service.mark_portfolio_failure(task_id)

                await broadcast_progress(task_id, self.job_service.task_results[task_id])

            self.job_service.complete_job(task_id)
        except Exception as exc:
            self.job_service.fail_job(task_id, str(exc))

        await broadcast_progress(task_id, self.job_service.task_results[task_id])

    async def _run_single_portfolio_analysis(
        self,
        *,
        task_id: str,
        ticker: str,
        stock: dict,
        date: str,
        request_context: RequestContext,
    ) -> tuple[bool, Optional[dict]]:
        last_error: Optional[str] = None
        for attempt in range(self.retry_count + 1):
            try:
                output = await self.executor.execute(
                    task_id=f"{task_id}_{stock['_idx']}",
                    ticker=ticker,
                    date=date,
                    request_context=request_context,
                )
                rec = self._build_recommendation_record(
                    output=output,
                    ticker=ticker,
                    stock=stock,
                    date=date,
                )
                self.result_store.save_recommendation(date, ticker, rec)
                return True, rec
            except Exception as exc:
                last_error = str(exc)

            if attempt < self.retry_count:
                await asyncio.sleep(self.retry_base_delay_secs ** attempt)

        if last_error:
            self.job_service.task_results[task_id]["last_error"] = last_error
        return False, None

    def _fail_analysis_state(
        self,
        *,
        task_id: str,
        message: str,
        started_at: float,
        code: str,
        retryable: bool,
    ) -> None:
        state = self.job_service.task_results[task_id]
        state["status"] = "failed"
        state["elapsed_seconds"] = int(time.monotonic() - started_at)
        state["elapsed"] = state["elapsed_seconds"]
        state["result"] = None
        state["error"] = {
            "code": code,
            "message": message,
            "retryable": retryable,
        }
        self.result_store.save_task_status(task_id, state)

    @staticmethod
    def _build_recommendation_record(
        *,
        ticker: str,
        stock: dict,
        date: str,
        output: AnalysisExecutionOutput | None = None,
        stdout: str | None = None,
    ) -> dict:
        if output is not None:
            decision = output.decision
            quant_signal = output.quant_signal
            llm_signal = output.llm_signal
            confidence = output.confidence
            data_quality = output.data_quality
            degrade_reason_codes = list(output.degrade_reason_codes)
        else:
            decision = "HOLD"
            quant_signal = None
            llm_signal = None
            confidence = None
            data_quality = None
            degrade_reason_codes = []
            for line in (stdout or "").splitlines():
                if line.startswith("SIGNAL_DETAIL:"):
                    try:
                        detail = json.loads(line.split(":", 1)[1].strip())
                    except Exception:
                        continue
                    quant_signal = detail.get("quant_signal")
                    llm_signal = detail.get("llm_signal")
                    confidence = detail.get("confidence")
                if line.startswith("ANALYSIS_COMPLETE:"):
                    decision = line.split(":", 1)[1].strip()

        return {
            "contract_version": "v1alpha1",
            "ticker": ticker,
            "name": stock.get("name", ticker),
            "date": date,
            "status": "degraded_success" if (degrade_reason_codes or data_quality or quant_signal is None or llm_signal is None) else "completed",
            "created_at": datetime.now().isoformat(),
            "result": {
                "decision": decision,
                "confidence": confidence,
                "signals": {
                    "merged": {
                        "direction": 1 if decision in {"BUY", "OVERWEIGHT"} else -1 if decision in {"SELL", "UNDERWEIGHT"} else 0,
                        "rating": decision,
                    },
                    "quant": {
                        "direction": 1 if quant_signal in {"BUY", "OVERWEIGHT"} else -1 if quant_signal in {"SELL", "UNDERWEIGHT"} else 0,
                        "rating": quant_signal,
                        "available": quant_signal is not None,
                    },
                    "llm": {
                        "direction": 1 if llm_signal in {"BUY", "OVERWEIGHT"} else -1 if llm_signal in {"SELL", "UNDERWEIGHT"} else 0,
                        "rating": llm_signal,
                        "available": llm_signal is not None,
                    },
                },
                "degraded": quant_signal is None or llm_signal is None,
            },
            "degradation": {
                "degraded": bool(degrade_reason_codes) or quant_signal is None or llm_signal is None,
                "reason_codes": degrade_reason_codes,
            },
            "data_quality": data_quality,
            "compat": {
                "analysis_date": date,
                "decision": decision,
                "quant_signal": quant_signal,
                "llm_signal": llm_signal,
                "confidence": confidence,
            },
        }
