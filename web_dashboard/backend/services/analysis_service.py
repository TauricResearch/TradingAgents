from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional

from .request_context import RequestContext

BroadcastFn = Callable[[str, dict], Awaitable[None]]


class AnalysisService:
    """Application service that orchestrates backend analysis jobs without owning strategy logic."""

    def __init__(
        self,
        *,
        analysis_python: Path,
        repo_root: Path,
        analysis_script_template: str,
        api_key_resolver: Callable[[], Optional[str]],
        result_store,
        job_service,
        retry_count: int = 2,
        retry_base_delay_secs: int = 1,
    ):
        self.analysis_python = analysis_python
        self.repo_root = repo_root
        self.analysis_script_template = analysis_script_template
        self.api_key_resolver = api_key_resolver
        self.result_store = result_store
        self.job_service = job_service
        self.retry_count = retry_count
        self.retry_base_delay_secs = retry_base_delay_secs

    async def start_portfolio_analysis(
        self,
        *,
        task_id: str,
        date: str,
        request_context: RequestContext,
        broadcast_progress: BroadcastFn,
    ) -> dict:
        del request_context  # Reserved for future auditing/auth propagation.
        watchlist = self.result_store.get_watchlist()
        if not watchlist:
            raise ValueError("自选股为空，请先添加股票")

        analysis_api_key = self.api_key_resolver()
        if not analysis_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")

        state = self.job_service.create_portfolio_job(task_id=task_id, total=len(watchlist))
        await broadcast_progress(task_id, state)

        task = asyncio.create_task(
            self._run_portfolio_analysis(
                task_id=task_id,
                date=date,
                watchlist=watchlist,
                analysis_api_key=analysis_api_key,
                broadcast_progress=broadcast_progress,
            )
        )
        self.job_service.register_background_task(task_id, task)
        return {
            "task_id": task_id,
            "total": len(watchlist),
            "status": "running",
        }

    async def _run_portfolio_analysis(
        self,
        *,
        task_id: str,
        date: str,
        watchlist: list[dict],
        analysis_api_key: str,
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
                    analysis_api_key=analysis_api_key,
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
        analysis_api_key: str,
    ) -> tuple[bool, Optional[dict]]:
        last_error: Optional[str] = None
        for attempt in range(self.retry_count + 1):
            script_path: Optional[Path] = None
            try:
                fd, script_path_str = tempfile.mkstemp(
                    suffix=".py",
                    prefix=f"analysis_{task_id}_{stock['_idx']}_",
                )
                script_path = Path(script_path_str)
                os.chmod(script_path, 0o600)
                with os.fdopen(fd, "w") as handle:
                    handle.write(self.analysis_script_template)

                clean_env = {
                    key: value
                    for key, value in os.environ.items()
                    if not key.startswith(("PYTHON", "CONDA", "VIRTUAL"))
                }
                clean_env["ANTHROPIC_API_KEY"] = analysis_api_key
                clean_env["ANTHROPIC_BASE_URL"] = "https://api.minimaxi.com/anthropic"

                proc = await asyncio.create_subprocess_exec(
                    str(self.analysis_python),
                    str(script_path),
                    ticker,
                    date,
                    str(self.repo_root),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=clean_env,
                )
                self.job_service.register_process(task_id, proc)
                stdout, stderr = await proc.communicate()

                if proc.returncode == 0:
                    rec = self._build_recommendation_record(
                        stdout=stdout.decode(),
                        ticker=ticker,
                        stock=stock,
                        date=date,
                    )
                    self.result_store.save_recommendation(date, ticker, rec)
                    return True, rec

                last_error = stderr.decode()[-500:] if stderr else f"exit {proc.returncode}"
            except Exception as exc:
                last_error = str(exc)
            finally:
                if script_path is not None:
                    try:
                        script_path.unlink()
                    except Exception:
                        pass

            if attempt < self.retry_count:
                await asyncio.sleep(self.retry_base_delay_secs ** attempt)

        if last_error:
            self.job_service.task_results[task_id]["last_error"] = last_error
        return False, None

    @staticmethod
    def _build_recommendation_record(*, stdout: str, ticker: str, stock: dict, date: str) -> dict:
        decision = "HOLD"
        quant_signal = None
        llm_signal = None
        confidence = None
        for line in stdout.splitlines():
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
            "ticker": ticker,
            "name": stock.get("name", ticker),
            "analysis_date": date,
            "decision": decision,
            "quant_signal": quant_signal,
            "llm_signal": llm_signal,
            "confidence": confidence,
            "created_at": datetime.now().isoformat(),
        }
