from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional, Protocol

from .request_context import (
    CONTRACT_VERSION,
    DEFAULT_EXECUTOR_TYPE,
    RequestContext,
)

StageCallback = Callable[[str], Awaitable[None]]
ProcessRegistry = Callable[[str, asyncio.subprocess.Process | None], None]

LEGACY_ANALYSIS_SCRIPT_TEMPLATE = """
import json
import os
import sys
from pathlib import Path

ticker = sys.argv[1]
date = sys.argv[2]
repo_root = sys.argv[3]

sys.path.insert(0, repo_root)

import py_mini_racer
sys.modules["mini_racer"] = py_mini_racer

from orchestrator.config import OrchestratorConfig
from orchestrator.orchestrator import TradingOrchestrator
from tradingagents.default_config import get_default_config

trading_config = get_default_config()
trading_config["project_dir"] = os.path.join(repo_root, "tradingagents")
trading_config["results_dir"] = os.path.join(repo_root, "results")
trading_config["max_debate_rounds"] = 1
trading_config["max_risk_discuss_rounds"] = 1
if os.environ.get("TRADINGAGENTS_LLM_PROVIDER"):
    trading_config["llm_provider"] = os.environ["TRADINGAGENTS_LLM_PROVIDER"]
elif os.environ.get("ANTHROPIC_BASE_URL"):
    trading_config["llm_provider"] = "anthropic"
elif os.environ.get("OPENAI_BASE_URL"):
    trading_config["llm_provider"] = "openai"
if os.environ.get("TRADINGAGENTS_BACKEND_URL"):
    trading_config["backend_url"] = os.environ["TRADINGAGENTS_BACKEND_URL"]
elif os.environ.get("ANTHROPIC_BASE_URL"):
    trading_config["backend_url"] = os.environ["ANTHROPIC_BASE_URL"]
elif os.environ.get("OPENAI_BASE_URL"):
    trading_config["backend_url"] = os.environ["OPENAI_BASE_URL"]
if os.environ.get("TRADINGAGENTS_MODEL"):
    trading_config["deep_think_llm"] = os.environ["TRADINGAGENTS_MODEL"]
    trading_config["quick_think_llm"] = os.environ["TRADINGAGENTS_MODEL"]
if os.environ.get("TRADINGAGENTS_DEEP_MODEL"):
    trading_config["deep_think_llm"] = os.environ["TRADINGAGENTS_DEEP_MODEL"]
if os.environ.get("TRADINGAGENTS_QUICK_MODEL"):
    trading_config["quick_think_llm"] = os.environ["TRADINGAGENTS_QUICK_MODEL"]
if os.environ.get("TRADINGAGENTS_SELECTED_ANALYSTS"):
    trading_config["selected_analysts"] = [
        item.strip() for item in os.environ["TRADINGAGENTS_SELECTED_ANALYSTS"].split(",") if item.strip()
    ]
if os.environ.get("TRADINGAGENTS_ANALYSIS_PROMPT_STYLE"):
    trading_config["analysis_prompt_style"] = os.environ["TRADINGAGENTS_ANALYSIS_PROMPT_STYLE"]
if os.environ.get("TRADINGAGENTS_LLM_TIMEOUT"):
    trading_config["llm_timeout"] = float(os.environ["TRADINGAGENTS_LLM_TIMEOUT"])
if os.environ.get("TRADINGAGENTS_LLM_MAX_RETRIES"):
    trading_config["llm_max_retries"] = int(os.environ["TRADINGAGENTS_LLM_MAX_RETRIES"])
print("STAGE:analysts", flush=True)
print("STAGE:research", flush=True)

config = OrchestratorConfig(
    quant_backtest_path=os.environ.get("QUANT_BACKTEST_PATH", ""),
    trading_agents_config=trading_config,
)

orchestrator = TradingOrchestrator(config)

print("STAGE:trading", flush=True)

try:
    result = orchestrator.get_combined_signal(ticker, date)
except Exception as exc:
    result_meta = {
        "degrade_reason_codes": list(getattr(exc, "reason_codes", ()) or ()),
        "data_quality": getattr(exc, "data_quality", None),
        "source_diagnostics": getattr(exc, "source_diagnostics", None),
    }
    print("RESULT_META:" + json.dumps(result_meta), file=sys.stderr, flush=True)
    print("ANALYSIS_ERROR:" + str(exc), file=sys.stderr, flush=True)
    sys.exit(1)

print("STAGE:risk", flush=True)

direction = result.direction
confidence = result.confidence
llm_sig_obj = result.llm_signal
quant_sig_obj = result.quant_signal
llm_signal = llm_sig_obj.metadata.get("rating", "HOLD") if llm_sig_obj else "HOLD"
if quant_sig_obj is None:
    quant_signal = "HOLD"
elif quant_sig_obj.direction == 1:
    quant_signal = "BUY" if quant_sig_obj.confidence >= 0.7 else "OVERWEIGHT"
elif quant_sig_obj.direction == -1:
    quant_signal = "SELL" if quant_sig_obj.confidence >= 0.7 else "UNDERWEIGHT"
else:
    quant_signal = "HOLD"

if direction == 1:
    signal = "BUY" if confidence >= 0.7 else "OVERWEIGHT"
elif direction == -1:
    signal = "SELL" if confidence >= 0.7 else "UNDERWEIGHT"
else:
    signal = "HOLD"

results_dir = Path(repo_root) / "results" / ticker / date
results_dir.mkdir(parents=True, exist_ok=True)

report_content = (
    "# TradingAgents 分析报告\\n\\n"
    "**股票**: " + ticker + "\\n"
    "**日期**: " + date + "\\n\\n"
    "## 最终决策\\n\\n"
    "**" + signal + "**\\n\\n"
    "## 信号详情\\n\\n"
    "- LLM 信号: " + llm_signal + "\\n"
    "- Quant 信号: " + quant_signal + "\\n"
    "- 置信度: " + f"{confidence:.1%}" + "\\n\\n"
    "## 分析摘要\\n\\n"
    "N/A\\n"
)

report_path = results_dir / "complete_report.md"
report_path.write_text(report_content)

print("STAGE:portfolio", flush=True)
signal_detail = json.dumps({"llm_signal": llm_signal, "quant_signal": quant_signal, "confidence": confidence})
result_meta = json.dumps({
    "degrade_reason_codes": list(getattr(result, "degrade_reason_codes", ())),
    "data_quality": (result.metadata or {}).get("data_quality"),
    "source_diagnostics": (result.metadata or {}).get("source_diagnostics"),
})
print("SIGNAL_DETAIL:" + signal_detail, flush=True)
print("RESULT_META:" + result_meta, flush=True)
print("ANALYSIS_COMPLETE:" + signal, flush=True)
"""


def _rating_to_direction(rating: Optional[str]) -> int:
    if rating in {"BUY", "OVERWEIGHT"}:
        return 1
    if rating in {"SELL", "UNDERWEIGHT"}:
        return -1
    return 0


@dataclass(frozen=True)
class AnalysisExecutionOutput:
    decision: str
    quant_signal: Optional[str]
    llm_signal: Optional[str]
    confidence: Optional[float]
    report_path: Optional[str] = None
    degrade_reason_codes: tuple[str, ...] = ()
    data_quality: Optional[dict] = None
    source_diagnostics: Optional[dict] = None
    contract_version: str = CONTRACT_VERSION
    executor_type: str = DEFAULT_EXECUTOR_TYPE

    def to_result_contract(
        self,
        *,
        task_id: str,
        ticker: str,
        date: str,
        created_at: str,
        elapsed_seconds: int,
        current_stage: str = "portfolio",
    ) -> dict:
        degraded = bool(self.degrade_reason_codes) or bool(self.data_quality) or self.quant_signal is None or self.llm_signal is None
        return {
            "contract_version": self.contract_version,
            "task_id": task_id,
            "ticker": ticker,
            "date": date,
            "status": "degraded_success" if degraded else "completed",
            "progress": 100,
            "current_stage": current_stage,
            "created_at": created_at,
            "elapsed_seconds": elapsed_seconds,
            "elapsed": elapsed_seconds,
            "degradation": {
                "degraded": degraded,
                "reason_codes": list(self.degrade_reason_codes),
                "source_diagnostics": self.source_diagnostics or {},
            },
            "data_quality": self.data_quality,
            "result": {
                "decision": self.decision,
                "confidence": self.confidence,
                "signals": {
                    "merged": {
                        "direction": _rating_to_direction(self.decision),
                        "rating": self.decision,
                    },
                    "quant": {
                        "direction": _rating_to_direction(self.quant_signal),
                        "rating": self.quant_signal,
                        "available": self.quant_signal is not None,
                    },
                    "llm": {
                        "direction": _rating_to_direction(self.llm_signal),
                        "rating": self.llm_signal,
                        "available": self.llm_signal is not None,
                    },
                },
                "degraded": degraded,
                "report": {
                    "path": self.report_path,
                    "available": bool(self.report_path),
                },
            },
            "error": None,
        }


class AnalysisExecutorError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "analysis_failed",
        retryable: bool = False,
        degrade_reason_codes: tuple[str, ...] = (),
        data_quality: Optional[dict] = None,
        source_diagnostics: Optional[dict] = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.degrade_reason_codes = degrade_reason_codes
        self.data_quality = data_quality
        self.source_diagnostics = source_diagnostics


class AnalysisExecutor(Protocol):
    async def execute(
        self,
        *,
        task_id: str,
        ticker: str,
        date: str,
        request_context: RequestContext,
        on_stage: Optional[StageCallback] = None,
    ) -> AnalysisExecutionOutput: ...


class LegacySubprocessAnalysisExecutor:
    """Run the legacy dashboard analysis script behind a stable executor contract."""

    def __init__(
        self,
        *,
        analysis_python: Path,
        repo_root: Path,
        api_key_resolver: Callable[..., Optional[str]],
        process_registry: Optional[ProcessRegistry] = None,
        script_template: str = LEGACY_ANALYSIS_SCRIPT_TEMPLATE,
        stdout_timeout_secs: float = 300.0,
    ):
        self.analysis_python = analysis_python
        self.repo_root = repo_root
        self.api_key_resolver = api_key_resolver
        self.process_registry = process_registry
        self.script_template = script_template
        self.stdout_timeout_secs = stdout_timeout_secs

    async def execute(
        self,
        *,
        task_id: str,
        ticker: str,
        date: str,
        request_context: RequestContext,
        on_stage: Optional[StageCallback] = None,
    ) -> AnalysisExecutionOutput:
        llm_provider = (request_context.llm_provider or "anthropic").lower()
        analysis_api_key = request_context.provider_api_key or self._resolve_provider_api_key(llm_provider)
        if llm_provider != "ollama" and not analysis_api_key:
            raise RuntimeError(f"{llm_provider} provider API key not configured")

        script_path: Optional[Path] = None
        proc: asyncio.subprocess.Process | None = None
        try:
            fd, script_path_str = tempfile.mkstemp(suffix=".py", prefix=f"analysis_{task_id}_")
            script_path = Path(script_path_str)
            os.chmod(script_path, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(self.script_template)

            clean_env = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith(("PYTHON", "CONDA", "VIRTUAL"))
            }
            clean_env["TRADINGAGENTS_LLM_PROVIDER"] = llm_provider
            if request_context.backend_url:
                clean_env["TRADINGAGENTS_BACKEND_URL"] = request_context.backend_url
            if request_context.deep_think_llm:
                clean_env["TRADINGAGENTS_DEEP_MODEL"] = request_context.deep_think_llm
            if request_context.quick_think_llm:
                clean_env["TRADINGAGENTS_QUICK_MODEL"] = request_context.quick_think_llm
            if request_context.selected_analysts:
                clean_env["TRADINGAGENTS_SELECTED_ANALYSTS"] = ",".join(request_context.selected_analysts)
            if request_context.analysis_prompt_style:
                clean_env["TRADINGAGENTS_ANALYSIS_PROMPT_STYLE"] = request_context.analysis_prompt_style
            if request_context.llm_timeout is not None:
                clean_env["TRADINGAGENTS_LLM_TIMEOUT"] = str(request_context.llm_timeout)
            if request_context.llm_max_retries is not None:
                clean_env["TRADINGAGENTS_LLM_MAX_RETRIES"] = str(request_context.llm_max_retries)
            for env_name in self._provider_api_env_names(llm_provider):
                if analysis_api_key:
                    clean_env[env_name] = analysis_api_key

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
            if self.process_registry is not None:
                self.process_registry(task_id, proc)

            stdout_lines: list[str] = []
            assert proc.stdout is not None
            while True:
                try:
                    line_bytes = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=self.stdout_timeout_secs,
                    )
                except asyncio.TimeoutError as exc:
                    await self._terminate_process(proc)
                    raise AnalysisExecutorError(
                        f"analysis subprocess timed out after {self.stdout_timeout_secs:g}s",
                        retryable=True,
                    ) from exc
                if not line_bytes:
                    break
                line = line_bytes.decode(errors="replace").rstrip()
                stdout_lines.append(line)
                if on_stage is not None and line.startswith("STAGE:"):
                    await on_stage(line.split(":", 1)[1].strip())

            await proc.wait()
            stderr_bytes = await proc.stderr.read() if proc.stderr is not None else b""
            stderr_lines = stderr_bytes.decode(errors="replace").splitlines() if stderr_bytes else []
            if proc.returncode != 0:
                failure_meta = self._parse_failure_metadata(stdout_lines, stderr_lines)
                message = self._extract_error_message(stderr_lines) or (stderr_bytes.decode(errors="replace")[-1000:] if stderr_bytes else f"exit {proc.returncode}")
                if failure_meta is None:
                    raise AnalysisExecutorError(
                        "analysis subprocess failed without required markers: RESULT_META",
                        code="analysis_protocol_failed",
                    )
                raise AnalysisExecutorError(
                    message,
                    code="analysis_failed",
                    degrade_reason_codes=failure_meta["degrade_reason_codes"],
                    data_quality=failure_meta["data_quality"],
                    source_diagnostics=failure_meta["source_diagnostics"],
                )

            return self._parse_output(
                stdout_lines=stdout_lines,
                ticker=ticker,
                date=date,
                contract_version=request_context.contract_version,
                executor_type=request_context.executor_type,
            )
        finally:
            if self.process_registry is not None:
                self.process_registry(task_id, None)
            if script_path is not None:
                try:
                    script_path.unlink()
                except Exception:
                    pass

    @staticmethod
    async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        try:
            proc.kill()
        except ProcessLookupError:
            return
        await proc.wait()

    def _resolve_provider_api_key(self, provider: str) -> Optional[str]:
        try:
            return self.api_key_resolver(provider)  # type: ignore[misc]
        except TypeError:
            return self.api_key_resolver()

    @staticmethod
    def _provider_api_env_names(provider: str) -> tuple[str, ...]:
        return {
            "anthropic": ("ANTHROPIC_API_KEY",),
            "openai": ("OPENAI_API_KEY",),
            "openrouter": ("OPENROUTER_API_KEY",),
            "xai": ("XAI_API_KEY",),
            "google": ("GOOGLE_API_KEY",),
            "ollama": tuple(),
        }.get(provider, tuple())

    @staticmethod
    def _parse_failure_metadata(stdout_lines: list[str], stderr_lines: list[str]) -> Optional[dict]:
        for line in [*stdout_lines, *stderr_lines]:
            if line.startswith("RESULT_META:"):
                try:
                    detail = json.loads(line.split(":", 1)[1].strip())
                except Exception as exc:
                    raise AnalysisExecutorError(
                        "failed to parse RESULT_META payload",
                        code="analysis_protocol_failed",
                    ) from exc
                return {
                    "degrade_reason_codes": tuple(detail.get("degrade_reason_codes") or ()),
                    "data_quality": detail.get("data_quality"),
                    "source_diagnostics": detail.get("source_diagnostics"),
                }
        return None

    @staticmethod
    def _extract_error_message(stderr_lines: list[str]) -> Optional[str]:
        for line in stderr_lines:
            if line.startswith("ANALYSIS_ERROR:"):
                return line.split(":", 1)[1].strip()
        return None

    @staticmethod
    def _parse_output(
        *,
        stdout_lines: list[str],
        ticker: str,
        date: str,
        contract_version: str,
        executor_type: str,
    ) -> AnalysisExecutionOutput:
        decision: Optional[str] = None
        quant_signal = None
        llm_signal = None
        confidence = None
        degrade_reason_codes: tuple[str, ...] = ()
        data_quality = None
        source_diagnostics = None
        seen_signal_detail = False
        seen_result_meta = False
        seen_complete = False

        for line in stdout_lines:
            if line.startswith("SIGNAL_DETAIL:"):
                seen_signal_detail = True
                try:
                    detail = json.loads(line.split(":", 1)[1].strip())
                except Exception as exc:
                    raise AnalysisExecutorError("failed to parse SIGNAL_DETAIL payload") from exc
                quant_signal = detail.get("quant_signal")
                llm_signal = detail.get("llm_signal")
                confidence = detail.get("confidence")
            elif line.startswith("RESULT_META:"):
                seen_result_meta = True
                try:
                    detail = json.loads(line.split(":", 1)[1].strip())
                except Exception as exc:
                    raise AnalysisExecutorError("failed to parse RESULT_META payload") from exc
                degrade_reason_codes = tuple(detail.get("degrade_reason_codes") or ())
                data_quality = detail.get("data_quality")
                source_diagnostics = detail.get("source_diagnostics")
            elif line.startswith("ANALYSIS_COMPLETE:"):
                seen_complete = True
                decision = line.split(":", 1)[1].strip()

        missing_markers = []
        if not seen_signal_detail:
            missing_markers.append("SIGNAL_DETAIL")
        if not seen_result_meta:
            missing_markers.append("RESULT_META")
        if not seen_complete:
            missing_markers.append("ANALYSIS_COMPLETE")
        if missing_markers:
            raise AnalysisExecutorError(
                "analysis subprocess completed without required markers: "
                + ", ".join(missing_markers)
            )

        report_path = str(Path("results") / ticker / date / "complete_report.md")
        return AnalysisExecutionOutput(
            decision=decision or "HOLD",
            quant_signal=quant_signal,
            llm_signal=llm_signal,
            confidence=confidence,
            report_path=report_path,
            degrade_reason_codes=degrade_reason_codes,
            data_quality=data_quality,
            source_diagnostics=source_diagnostics,
            contract_version=contract_version,
            executor_type=executor_type,
        )


class DirectAnalysisExecutor:
    """Placeholder for a future in-process executor implementation."""

    async def execute(
        self,
        *,
        task_id: str,
        ticker: str,
        date: str,
        request_context: RequestContext,
        on_stage: Optional[StageCallback] = None,
    ) -> AnalysisExecutionOutput:
        del task_id, ticker, date, request_context, on_stage
        raise NotImplementedError("DirectAnalysisExecutor is not implemented in phase 1")
