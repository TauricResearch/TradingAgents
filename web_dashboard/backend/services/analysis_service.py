from __future__ import annotations

import asyncio
import json
import time
from dataclasses import replace
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

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
        self.local_recovery_limit = 1
        self.provider_probe_limit = 1

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
                request_context=await self._enrich_request_context(
                    request_context,
                    ticker=ticker,
                    date=date,
                ),
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
                request_context=self._freeze_batch_peer_snapshot(
                    request_context,
                    date=date,
                    watchlist=watchlist,
                ),
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
        state = self.job_service.task_results[task_id]
        evidence_attempts: list[dict[str, Any]] = []
        budget_state = self._initial_budget_state(request_context)
        try:
            await self._set_analysis_runtime_state(
                task_id=task_id,
                status="collecting_evidence",
                current_stage="analysts",
                started_at=start_time,
                broadcast_progress=broadcast_progress,
                budget_state=budget_state,
            )
            baseline_context = self._with_attempt_metadata(
                request_context,
                attempt_index=0,
                attempt_mode="baseline",
                probe_mode="none",
                stdout_timeout_secs=budget_state["baseline_timeout_secs"],
                cost_cap=None,
            )
            output, evidence_attempts, tentative_classification = await self._execute_with_runtime_policy(
                task_id=task_id,
                ticker=ticker,
                date=date,
                request_context=baseline_context,
                broadcast_progress=broadcast_progress,
                started_at=start_time,
                evidence_attempts=evidence_attempts,
                budget_state=budget_state,
            )
            elapsed_seconds = int(time.monotonic() - start_time)
            contract = output.to_result_contract(
                task_id=task_id,
                ticker=ticker,
                date=date,
                created_at=state["created_at"],
                elapsed_seconds=elapsed_seconds,
                current_stage=ANALYSIS_STAGE_NAMES[-1],
            )
            contract["evidence"] = self._build_evidence_summary(evidence_attempts, fallback=output.observation)
            contract["tentative_classification"] = tentative_classification
            contract["budget_state"] = budget_state
            result_ref = self.result_store.save_result_contract(task_id, contract)
            self.job_service.complete_analysis_job(
                task_id,
                contract=contract,
                result_ref=result_ref,
                executor_type=request_context.executor_type,
            )
        except AnalysisExecutorError as exc:
            observation = exc.observation or {}
            if observation and self._should_append_observation(evidence_attempts, observation):
                evidence_attempts.append(observation)
            tentative_classification = self._classify_attempts(evidence_attempts) if evidence_attempts else None
            self._fail_analysis_state(
                task_id=task_id,
                message=str(exc),
                started_at=start_time,
                code=exc.code,
                retryable=exc.retryable,
                degradation={
                    "degraded": bool(exc.degrade_reason_codes) or bool(exc.data_quality),
                    "reason_codes": list(exc.degrade_reason_codes),
                    "source_diagnostics": exc.source_diagnostics or {},
                }
                if (exc.degrade_reason_codes or exc.data_quality or exc.source_diagnostics)
                else None,
                data_quality=exc.data_quality,
                evidence_summary=self._build_evidence_summary(evidence_attempts, fallback=observation or None),
                tentative_classification=tentative_classification,
                budget_state=budget_state,
            )
        except Exception as exc:
            self._fail_analysis_state(
                task_id=task_id,
                message=str(exc),
                started_at=start_time,
                code="analysis_failed",
                retryable=False,
                degradation=None,
                data_quality=None,
                evidence_summary=self._build_evidence_summary(evidence_attempts),
                tentative_classification=self._classify_attempts(evidence_attempts) if evidence_attempts else None,
                budget_state=budget_state,
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
                    request_context=await self._enrich_request_context(
                        request_context,
                        ticker=ticker,
                        date=date,
                        stock=stock,
                    ),
                )
                if rec is not None:
                    self.job_service.append_portfolio_result(task_id, rec)
                if not success:
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
        child_task_id = f"{task_id}_{stock['_idx']}"
        evidence_attempts: list[dict[str, Any]] = []
        budget_state = self._initial_budget_state(request_context)
        baseline_context = self._with_attempt_metadata(
            request_context,
            attempt_index=0,
            attempt_mode="baseline",
            probe_mode="none",
            stdout_timeout_secs=budget_state["baseline_timeout_secs"],
            cost_cap=None,
        )

        try:
            output = await self._execute_portfolio_with_runtime_policy(
                task_id=child_task_id,
                ticker=ticker,
                date=date,
                request_context=baseline_context,
                evidence_attempts=evidence_attempts,
                budget_state=budget_state,
            )
            tentative_classification = self._classify_attempts(evidence_attempts)
            rec = self._build_recommendation_record(
                output=output,
                ticker=ticker,
                stock=stock,
                date=date,
                evidence_summary=self._build_evidence_summary(evidence_attempts, fallback=output.observation),
                tentative_classification=tentative_classification,
                budget_state=budget_state,
            )
            self.result_store.save_recommendation(date, ticker, rec)
            return True, rec
        except AnalysisExecutorError as exc:
            if exc.observation and self._should_append_observation(evidence_attempts, exc.observation):
                evidence_attempts.append(exc.observation)
            if exc.observation:
                self.job_service.task_results[task_id]["last_error"] = exc.observation.get("message") or str(exc)
            else:
                self.job_service.task_results[task_id]["last_error"] = str(exc)
            rec = self._build_failed_recommendation_record(
                ticker=ticker,
                stock=stock,
                date=date,
                evidence_summary=self._build_evidence_summary(evidence_attempts),
                tentative_classification=self._classify_attempts(evidence_attempts) if evidence_attempts else None,
                budget_state=budget_state,
                exc=exc,
            )
            self.result_store.save_recommendation(date, ticker, rec)
            return False, rec
        except Exception as exc:
            self.job_service.task_results[task_id]["last_error"] = str(exc)
            return False, None

    async def _execute_portfolio_with_runtime_policy(
        self,
        *,
        task_id: str,
        ticker: str,
        date: str,
        request_context: RequestContext,
        evidence_attempts: list[dict[str, Any]],
        budget_state: dict[str, Any],
    ) -> AnalysisExecutionOutput:
        try:
            output = await self.executor.execute(
                task_id=task_id,
                ticker=ticker,
                date=date,
                request_context=request_context,
            )
            if output.observation:
                evidence_attempts.append(output.observation)
            return output
        except AnalysisExecutorError as baseline_exc:
            if baseline_exc.observation:
                evidence_attempts.append(baseline_exc.observation)
            tentative_classification = self._classify_attempts(evidence_attempts)

            if self._can_use_local_recovery(budget_state):
                budget_state["local_recovery_used"] = True
                budget_state["local_recovery_cost_used"] += 1.0
                recovery_context = self._with_attempt_metadata(
                    request_context,
                    attempt_index=1,
                    attempt_mode="local_recovery",
                    probe_mode="none",
                    stdout_timeout_secs=budget_state["local_recovery_timeout_secs"],
                    cost_cap=budget_state["local_recovery_cost_cap"],
                )
                try:
                    output = await self.executor.execute(
                        task_id=task_id,
                        ticker=ticker,
                        date=date,
                        request_context=recovery_context,
                    )
                    if output.observation:
                        evidence_attempts.append(output.observation)
                    return output
                except AnalysisExecutorError as recovery_exc:
                    if recovery_exc.observation:
                        evidence_attempts.append(recovery_exc.observation)
                    tentative_classification = self._classify_attempts(evidence_attempts)
                    if self._can_use_provider_probe(budget_state, tentative_classification):
                        budget_state["provider_probe_used"] = True
                        budget_state["provider_probe_cost_used"] += 1.0
                        probe_context = self._build_probe_context(request_context, budget_state)
                        try:
                            output = await self.executor.execute(
                                task_id=task_id,
                                ticker=ticker,
                                date=date,
                                request_context=probe_context,
                            )
                            if output.observation:
                                evidence_attempts.append(output.observation)
                            return output
                        except AnalysisExecutorError as probe_exc:
                            if probe_exc.observation:
                                evidence_attempts.append(probe_exc.observation)
                            raise probe_exc
                    raise recovery_exc
            raise baseline_exc

    async def _enrich_request_context(
        self,
        request_context: RequestContext,
        *,
        ticker: str,
        date: str,
        stock: Optional[dict[str, Any]] = None,
    ) -> RequestContext:
        metadata = dict(request_context.metadata or {})
        if not str(metadata.get("portfolio_context") or "").strip():
            metadata["portfolio_context"] = await self._build_portfolio_context(
                ticker=ticker,
                stock=stock,
            )
        if not str(metadata.get("peer_context") or "").strip():
            metadata["peer_context"] = self._build_peer_context(
                ticker=ticker,
                date=date,
                peer_snapshot=metadata.get("peer_recommendation_snapshot"),
                watchlist_snapshot=metadata.get("peer_context_batch_watchlist"),
            )
            metadata.setdefault("peer_context_mode", "PORTFOLIO_SNAPSHOT")
        elif not str(metadata.get("peer_context_mode") or "").strip():
            metadata["peer_context_mode"] = "CALLER_PROVIDED"
        return replace(request_context, metadata=metadata)

    def _freeze_batch_peer_snapshot(
        self,
        request_context: RequestContext,
        *,
        date: str,
        watchlist: list[dict[str, Any]],
    ) -> RequestContext:
        metadata = dict(request_context.metadata or {})
        if metadata.get("peer_recommendation_snapshot") is not None:
            return request_context
        snapshot = (
            self.result_store.get_recommendations(date=date, limit=200, offset=0).get("recommendations", [])
        )
        metadata["peer_recommendation_snapshot"] = snapshot
        metadata.setdefault("peer_context_mode", "PORTFOLIO_SNAPSHOT")
        metadata["peer_context_batch_watchlist"] = [
            {"ticker": item.get("ticker"), "name": item.get("name")}
            for item in watchlist
        ]
        return replace(request_context, metadata=metadata)

    async def _build_portfolio_context(
        self,
        *,
        ticker: str,
        stock: Optional[dict[str, Any]] = None,
    ) -> str:
        try:
            positions = await self.result_store.get_positions(None)
        except Exception:
            positions = []

        if not positions:
            watchlist = self.result_store.get_watchlist() or []
            if watchlist:
                return (
                    f"No recorded open positions. Watchlist size={len(watchlist)}. "
                    f"Current analysis target={ticker} ({(stock or {}).get('name', ticker)})."
                )
            return f"No recorded open positions for the current book. Current analysis target={ticker}."

        def _position_value(pos: dict[str, Any]) -> float:
            price = pos.get("current_price")
            if price is None:
                price = pos.get("cost_price") or 0.0
            return float(price or 0.0) * float(pos.get("shares") or 0.0)

        sorted_positions = sorted(positions, key=_position_value, reverse=True)
        current_positions = [pos for pos in positions if pos.get("ticker") == ticker]
        top_positions = sorted_positions[:4]
        losing_positions = sorted(
            [pos for pos in positions if pos.get("unrealized_pnl_pct") is not None],
            key=lambda pos: float(pos.get("unrealized_pnl_pct") or 0.0),
        )[:3]

        lines = [f"Current portfolio has {len(positions)} open position(s)."]
        if current_positions:
            current = current_positions[0]
            pnl_pct = current.get("unrealized_pnl_pct")
            pnl_text = (
                f", unrealized_pnl_pct={float(pnl_pct):.2f}%"
                if pnl_pct is not None
                else ""
            )
            lines.append(
                "Existing position in target: "
                f"{ticker}, shares={current.get('shares')}, cost={current.get('cost_price')}{pnl_text}."
            )
        else:
            lines.append(f"No existing position in target ticker {ticker}.")

        if top_positions:
            top_text = ", ".join(
                f"{pos.get('ticker')} value~{_position_value(pos):.0f}"
                for pos in top_positions
            )
            lines.append(f"Largest current positions: {top_text}.")

        if losing_positions:
            losing_text = ", ".join(
                f"{pos.get('ticker')} pnl={float(pos.get('unrealized_pnl_pct') or 0.0):.2f}%"
                for pos in losing_positions
            )
            lines.append(f"Weakest current positions by unrealized P&L: {losing_text}.")

        return " ".join(lines)

    def _build_peer_context(
        self,
        *,
        ticker: str,
        date: str,
        peer_snapshot: Optional[list[dict[str, Any]]] = None,
        watchlist_snapshot: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        recommendations = peer_snapshot
        if recommendations is None:
            recommendations = (
                self.result_store.get_recommendations(date=date, limit=20, offset=0).get("recommendations", [])
            )
        peers = [rec for rec in recommendations if rec.get("ticker") != ticker]
        if not peers:
            watchlist = watchlist_snapshot or self.result_store.get_watchlist() or []
            if watchlist:
                sample = ", ".join(item.get("ticker", "") for item in watchlist[:5] if item.get("ticker"))
                return (
                    "No prior recommendation peers are available for this date yet. "
                    f"Current watchlist sample: {sample}."
                )
            return "No prior recommendation peers are available for this date yet."

        def _decision_rank(rec: dict[str, Any]) -> tuple[int, float]:
            rating = (((rec.get("result") or {}).get("decision")) or "").upper()
            confidence = float(((rec.get("result") or {}).get("confidence")) or 0.0)
            direction = 1 if rating in {"BUY", "OVERWEIGHT"} else -1 if rating in {"SELL", "UNDERWEIGHT"} else 0
            return direction, confidence

        bullish = sorted(
            [rec for rec in peers if _decision_rank(rec)[0] > 0],
            key=lambda rec: _decision_rank(rec)[1],
            reverse=True,
        )[:3]
        bearish = sorted(
            [rec for rec in peers if _decision_rank(rec)[0] < 0],
            key=lambda rec: _decision_rank(rec)[1],
            reverse=True,
        )[:3]
        neutral = sorted(
            [rec for rec in peers if _decision_rank(rec)[0] == 0],
            key=lambda rec: _decision_rank(rec)[1],
            reverse=True,
        )[:2]

        lines = [
            "Peer context is auto-derived from a portfolio/book snapshot and is not industry-normalized. "
            "It should be used for broad book-relative comparison, not as evidence for SAME_THEME_RANK."
        ]
        if bullish:
            lines.append(
                "Current strongest bullish peers: "
                + ", ".join(
                    f"{rec.get('ticker')}:{((rec.get('result') or {}).get('decision'))}"
                    for rec in bullish
                )
                + "."
            )
        if bearish:
            lines.append(
                "Current strongest bearish peers: "
                + ", ".join(
                    f"{rec.get('ticker')}:{((rec.get('result') or {}).get('decision'))}"
                    for rec in bearish
                )
                + "."
            )
        if neutral and not bullish and not bearish:
            lines.append(
                "Current neutral peers: "
                + ", ".join(
                    f"{rec.get('ticker')}:{((rec.get('result') or {}).get('decision'))}"
                    for rec in neutral
                )
                + "."
            )
        return " ".join(lines)

    async def _execute_with_runtime_policy(
        self,
        *,
        task_id: str,
        ticker: str,
        date: str,
        request_context: RequestContext,
        broadcast_progress: BroadcastFn,
        started_at: float,
        evidence_attempts: list[dict[str, Any]],
        budget_state: dict[str, Any],
        ) -> tuple[AnalysisExecutionOutput, list[dict[str, Any]], dict[str, Any]]:
        try:
            output = await self._execute_once(
                task_id=task_id,
                ticker=ticker,
                date=date,
                request_context=request_context,
                started_at=started_at,
                broadcast_progress=broadcast_progress,
            )
            self._record_observation(evidence_attempts, output.observation)
            return output, evidence_attempts, self._classify_attempts(evidence_attempts)
        except AnalysisExecutorError as baseline_exc:
            self._record_observation(evidence_attempts, baseline_exc.observation)
            tentative_classification = self._classify_attempts(evidence_attempts)

            if self._can_use_local_recovery(budget_state):
                budget_state["local_recovery_used"] = True
                budget_state["local_recovery_cost_used"] += 1.0
                await self._set_analysis_runtime_state(
                    task_id=task_id,
                    status="auto_recovering",
                    current_stage=self.job_service.task_results[task_id].get("current_stage"),
                    started_at=started_at,
                    broadcast_progress=broadcast_progress,
                    evidence_summary=self._build_evidence_summary(evidence_attempts),
                    tentative_classification=tentative_classification,
                    budget_state=budget_state,
                )
                recovery_context = self._with_attempt_metadata(
                    request_context,
                    attempt_index=1,
                    attempt_mode="local_recovery",
                    probe_mode="none",
                    stdout_timeout_secs=budget_state["local_recovery_timeout_secs"],
                    cost_cap=budget_state["local_recovery_cost_cap"],
                )
                try:
                    output = await self._execute_once(
                        task_id=task_id,
                        ticker=ticker,
                        date=date,
                        request_context=recovery_context,
                        started_at=started_at,
                        broadcast_progress=broadcast_progress,
                    )
                    self._record_observation(evidence_attempts, output.observation)
                    return output, evidence_attempts, self._classify_attempts(evidence_attempts)
                except AnalysisExecutorError as recovery_exc:
                    self._record_observation(evidence_attempts, recovery_exc.observation)
                    tentative_classification = self._classify_attempts(evidence_attempts)
                    if self._can_use_provider_probe(budget_state, tentative_classification):
                        budget_state["provider_probe_used"] = True
                        budget_state["provider_probe_cost_used"] += 1.0
                        await self._set_analysis_runtime_state(
                            task_id=task_id,
                            status="classification_pending",
                            current_stage=self.job_service.task_results[task_id].get("current_stage"),
                            started_at=started_at,
                            broadcast_progress=broadcast_progress,
                            evidence_summary=self._build_evidence_summary(evidence_attempts),
                            tentative_classification=tentative_classification,
                            budget_state=budget_state,
                        )
                        await self._set_analysis_runtime_state(
                            task_id=task_id,
                            status="probing_provider",
                            current_stage=self.job_service.task_results[task_id].get("current_stage"),
                            started_at=started_at,
                            broadcast_progress=broadcast_progress,
                            evidence_summary=self._build_evidence_summary(evidence_attempts),
                            tentative_classification=tentative_classification,
                            budget_state=budget_state,
                        )
                        probe_context = self._build_probe_context(request_context, budget_state)
                        try:
                            output = await self._execute_once(
                                task_id=task_id,
                                ticker=ticker,
                                date=date,
                                request_context=probe_context,
                                started_at=started_at,
                                broadcast_progress=broadcast_progress,
                            )
                            self._record_observation(evidence_attempts, output.observation)
                            return output, evidence_attempts, self._classify_attempts(evidence_attempts)
                        except AnalysisExecutorError as probe_exc:
                            self._record_observation(evidence_attempts, probe_exc.observation)
                            raise probe_exc
                    raise recovery_exc
            raise baseline_exc

    async def _execute_once(
        self,
        *,
        task_id: str,
        ticker: str,
        date: str,
        request_context: RequestContext,
        started_at: float,
        broadcast_progress: BroadcastFn,
    ) -> AnalysisExecutionOutput:
        return await self.executor.execute(
            task_id=task_id,
            ticker=ticker,
            date=date,
            request_context=request_context,
            on_stage=lambda stage: self._handle_analysis_stage(
                task_id=task_id,
                stage_name=stage,
                started_at=started_at,
                broadcast_progress=broadcast_progress,
            ),
        )

    async def _set_analysis_runtime_state(
        self,
        *,
        task_id: str,
        status: str,
        current_stage: Optional[str],
        started_at: float,
        broadcast_progress: BroadcastFn,
        evidence_summary: Optional[dict] = None,
        tentative_classification: Optional[dict] = None,
        budget_state: Optional[dict] = None,
    ) -> None:
        state = self.job_service.task_results[task_id]
        state["status"] = status
        if current_stage is not None:
            state["current_stage"] = current_stage
        state["elapsed_seconds"] = int(time.monotonic() - started_at)
        state["elapsed"] = state["elapsed_seconds"]
        if evidence_summary is not None:
            state["evidence_summary"] = evidence_summary
        if tentative_classification is not None:
            state["tentative_classification"] = tentative_classification
        if budget_state is not None:
            state["budget_state"] = dict(budget_state)
        self.result_store.save_task_status(task_id, state)
        await broadcast_progress(task_id, state)

    def _initial_budget_state(self, request_context: RequestContext) -> dict[str, Any]:
        metadata = dict(request_context.metadata or {})
        baseline_timeout = float(metadata.get("stdout_timeout_secs", 300.0))
        local_recovery_timeout = float(metadata.get("local_recovery_timeout_secs", min(baseline_timeout, 180.0)))
        provider_probe_timeout = float(metadata.get("provider_probe_timeout_secs", min(baseline_timeout, 90.0)))
        return {
            "local_recovery_used": False,
            "provider_probe_used": False,
            "local_recovery_limit": self.local_recovery_limit,
            "provider_probe_limit": self.provider_probe_limit,
            "local_recovery_cost_cap": float(metadata.get("local_recovery_cost_cap", 1.0)),
            "provider_probe_cost_cap": float(metadata.get("provider_probe_cost_cap", 1.0)),
            "local_recovery_cost_used": 0.0,
            "provider_probe_cost_used": 0.0,
            "baseline_timeout_secs": baseline_timeout,
            "local_recovery_timeout_secs": local_recovery_timeout,
            "provider_probe_timeout_secs": provider_probe_timeout,
        }

    def _with_attempt_metadata(
        self,
        request_context: RequestContext,
        *,
        attempt_index: int,
        attempt_mode: str,
        probe_mode: str,
        stdout_timeout_secs: float,
        cost_cap: Optional[float],
    ) -> RequestContext:
        metadata = dict(request_context.metadata or {})
        metadata.update({
            "attempt_index": attempt_index,
            "attempt_mode": attempt_mode,
            "probe_mode": probe_mode,
            "stdout_timeout_secs": stdout_timeout_secs,
            "cost_cap": cost_cap,
            "evidence_id": f"{request_context.request_id}:{attempt_mode}:{attempt_index}",
        })
        return replace(request_context, metadata=metadata)

    def _build_probe_context(self, request_context: RequestContext, budget_state: dict[str, Any]) -> RequestContext:
        selected = tuple(request_context.selected_analysts or ("market",))
        probe_selected = ("market",) if "market" in selected else (selected[0],)
        return self._with_attempt_metadata(
            replace(
                request_context,
                selected_analysts=probe_selected,
                analysis_prompt_style=request_context.analysis_prompt_style or "compact",
            ),
            attempt_index=2,
            attempt_mode="provider_probe",
            probe_mode="provider_boundary",
            stdout_timeout_secs=budget_state["provider_probe_timeout_secs"],
            cost_cap=budget_state["provider_probe_cost_cap"],
        )

    def _build_evidence_summary(
        self,
        observations: list[dict[str, Any]],
        *,
        fallback: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        last_observation = observations[-1] if observations else fallback
        return {
            "attempts": observations,
            "last_observation": last_observation,
        }

    def _record_observation(
        self,
        observations: list[dict[str, Any]],
        observation: Optional[dict[str, Any]],
    ) -> None:
        if observation and self._should_append_observation(observations, observation):
            observations.append(observation)

    def _can_use_local_recovery(self, budget_state: dict[str, Any]) -> bool:
        return (
            not budget_state["local_recovery_used"]
            and budget_state["local_recovery_cost_used"] < budget_state["local_recovery_cost_cap"]
        )

    def _can_use_provider_probe(
        self,
        budget_state: dict[str, Any],
        tentative_classification: dict[str, Any],
    ) -> bool:
        return (
            not budget_state["provider_probe_used"]
            and budget_state["provider_probe_cost_used"] < budget_state["provider_probe_cost_cap"]
            and tentative_classification.get("kind") in {"interaction_effect", "provider_boundary"}
        )

    def _classify_attempts(self, observations: list[dict[str, Any]]) -> dict[str, Any]:
        if not observations:
            return {
                "kind": "interaction_effect",
                "tentative": True,
                "basis": ["no_observation"],
            }

        if any(
            observation.get("attempt_mode") == "local_recovery" and observation.get("status") == "completed"
            for observation in observations
        ):
            return {
                "kind": "local_runtime",
                "tentative": True,
                "basis": ["local_recovery_succeeded"],
                "last_observation_code": observations[-1].get("observation_code"),
            }

        if any(
            observation.get("attempt_mode") == "provider_probe" and observation.get("status") == "completed"
            for observation in observations
        ):
            return {
                "kind": "interaction_effect",
                "tentative": True,
                "basis": ["provider_probe_succeeded_after_runtime_failures"],
                "last_observation_code": observations[-1].get("observation_code"),
            }

        latest_kind = self._classify_observation(observations[-1])
        return {
            "kind": latest_kind,
            "tentative": True,
            "basis": [obs.get("observation_code") for obs in observations if obs.get("observation_code")],
            "last_observation_code": observations[-1].get("observation_code"),
        }

    @staticmethod
    def _should_append_observation(observations: list[dict[str, Any]], observation: dict[str, Any]) -> bool:
        if not observations:
            return True
        last = observations[-1]
        if last.get("evidence_id") and observation.get("evidence_id"):
            return last.get("evidence_id") != observation.get("evidence_id")
        return last != observation

    def _classify_observation(self, observation: dict[str, Any]) -> str:
        data_quality = observation.get("data_quality") or {}
        status = str(observation.get("status") or "").lower()
        state = str(data_quality.get("state") or "").lower()
        message = str(observation.get("message") or "").lower()
        code = str(observation.get("observation_code") or "").lower()
        if status == "completed":
            return "no_issue"
        if state == "provider_mismatch" or "api key not configured" in message:
            return "local_runtime"
        if code == "analysis_protocol_failed" or "required markers" in message or "parse result_meta" in message:
            return "local_runtime"

        provider_markers = (
            "429",
            "529",
            "overloaded",
            "temporarily unavailable",
            "connection reset",
            "rate limit",
        )
        if any(marker in message for marker in provider_markers):
            return "provider_boundary"
        if "timed out" in message or code == "subprocess_stdout_timeout":
            return "interaction_effect"
        return "interaction_effect"

    def _fail_analysis_state(
        self,
        *,
        task_id: str,
        message: str,
        started_at: float,
        code: str,
        retryable: bool,
        degradation: Optional[dict],
        data_quality: Optional[dict],
        evidence_summary: Optional[dict],
        tentative_classification: Optional[dict],
        budget_state: Optional[dict],
    ) -> None:
        state = self.job_service.task_results[task_id]
        state["status"] = "failed"
        state["elapsed_seconds"] = int(time.monotonic() - started_at)
        state["elapsed"] = state["elapsed_seconds"]
        state["result"] = None
        state["degradation_summary"] = degradation
        state["data_quality_summary"] = data_quality
        state["evidence_summary"] = evidence_summary
        state["tentative_classification"] = tentative_classification
        state["budget_state"] = budget_state or {}
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
        evidence_summary: Optional[dict] = None,
        tentative_classification: Optional[dict] = None,
        budget_state: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> dict:
        if output is not None:
            decision = output.decision
            quant_signal = output.quant_signal
            llm_signal = output.llm_signal
            confidence = output.confidence
            llm_decision_structured = output.llm_decision_structured
            data_quality = output.data_quality
            degrade_reason_codes = list(output.degrade_reason_codes)
        else:
            decision = "HOLD"
            quant_signal = None
            llm_signal = None
            confidence = None
            llm_decision_structured = None
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
                    llm_decision_structured = detail.get("llm_decision_structured")
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
                        "structured": llm_decision_structured,
                    },
                },
                "degraded": quant_signal is None or llm_signal is None,
            },
            "degradation": {
                "degraded": bool(degrade_reason_codes) or quant_signal is None or llm_signal is None,
                "reason_codes": degrade_reason_codes,
            },
            "data_quality": data_quality,
            "evidence": evidence_summary,
            "tentative_classification": tentative_classification,
            "budget_state": budget_state or {},
            "error": error_message,
            "compat": {
                "analysis_date": date,
                "decision": decision,
                "quant_signal": quant_signal,
                "llm_signal": llm_signal,
                "confidence": confidence,
                "llm_decision_structured": llm_decision_structured,
            },
        }

    @staticmethod
    def _build_failed_recommendation_record(
        *,
        ticker: str,
        stock: dict,
        date: str,
        evidence_summary: Optional[dict],
        tentative_classification: Optional[dict],
        budget_state: Optional[dict],
        exc: AnalysisExecutorError,
    ) -> dict:
        return {
            "contract_version": "v1alpha1",
            "ticker": ticker,
            "name": stock.get("name", ticker),
            "date": date,
            "status": "failed",
            "created_at": datetime.now().isoformat(),
            "result": {
                "decision": None,
                "confidence": None,
                "signals": {
                    "merged": {
                        "direction": 0,
                        "rating": None,
                    },
                    "quant": {
                        "direction": 0,
                        "rating": None,
                        "available": False,
                    },
                    "llm": {
                        "direction": 0,
                        "rating": None,
                        "available": False,
                    },
                },
                "degraded": False,
            },
            "degradation": {
                "degraded": bool(exc.degrade_reason_codes) or bool(exc.data_quality),
                "reason_codes": list(exc.degrade_reason_codes),
                "source_diagnostics": exc.source_diagnostics or {},
            },
            "data_quality": exc.data_quality,
            "evidence": evidence_summary,
            "tentative_classification": tentative_classification,
            "budget_state": budget_state or {},
            "error": {
                "code": exc.code,
                "message": str(exc),
                "retryable": exc.retryable,
            },
            "compat": {
                "analysis_date": date,
                "decision": None,
                "quant_signal": None,
                "llm_signal": None,
                "confidence": None,
            },
        }
