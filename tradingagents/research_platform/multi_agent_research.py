"""Provider-neutral, evidence-bounded LLM research orchestration.

This is an additive adapter over normalized research records.  It never emits
trade signals and therefore cannot bypass the deterministic risk layer.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Callable
from queue import Empty, Queue
from statistics import mean, stdev
from threading import Thread
from time import monotonic, perf_counter, sleep
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.factory import create_llm_client

from .agent_contracts import (
    AgentOutputEnvelope,
    AgentOutputSection,
    AgentOutputType,
    AnalystNote,
    ConfidenceLevel,
    EvidenceRef,
    InvestmentThesis,
)
from .narrative_provider import (
    NarrativeProviderError,
    NarrativeProviderUnavailableError,
    ResearchNarrativeContext,
)

PROMPT_VERSION = "multi-agent-research-v6"
TECHNICAL_FEATURE_VERSION = "technical-snapshot-v2-adjusted"
MAX_DETERMINISTIC_REPORT_CHARS = 24_000
ANALYST_ROLES = (
    ("fundamentals", "基本面分析师"),
    ("market", "技术与市场分析师"),
    ("game_news", "新闻、游戏产品与版号分析师"),
    ("valuation", "估值分析师"),
)


class StructuredResearchNote(BaseModel):
    model_config = ConfigDict(frozen=True)
    headline: str = Field(min_length=1, max_length=180)
    summary: str = Field(min_length=1, max_length=3000)
    supporting_points: list[str] = Field(default_factory=list, max_length=8)
    risks: list[str] = Field(default_factory=list, max_length=8)
    evidence_source_ids: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM

    @field_validator("headline", mode="before")
    @classmethod
    def _normalize_headline(cls, value: Any) -> str:
        return _bounded_text(value, 180, "未命名研究结论")

    @field_validator("summary", mode="before")
    @classmethod
    def _normalize_summary(cls, value: Any) -> str:
        return _bounded_text(value, 3_000, "模型未提供研究摘要。")

    @field_validator("supporting_points", "risks", mode="before")
    @classmethod
    def _normalize_bullets(cls, value: Any) -> list[str]:
        return _bounded_list(value, 8)

    @field_validator("evidence_source_ids", mode="before")
    @classmethod
    def _normalize_evidence_ids(cls, value: Any) -> list[str]:
        return _bounded_list(value, 32)

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: Any) -> ConfidenceLevel:
        return _normalize_confidence_level(value)


class StructuredThesis(BaseModel):
    model_config = ConfigDict(frozen=True)
    headline: str = Field(min_length=1, max_length=180)
    base_case: str = Field(min_length=1, max_length=4000)
    bull_case: str = Field(min_length=1, max_length=3000)
    bear_case: str = Field(min_length=1, max_length=3000)
    catalysts: list[str] = Field(default_factory=list, max_length=8)
    disconfirming_evidence: list[str] = Field(default_factory=list, max_length=8)
    evidence_source_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @field_validator("headline", mode="before")
    @classmethod
    def _normalize_headline(cls, value: Any) -> str:
        return _bounded_text(value, 180, "研究经理综合结论")

    @field_validator("base_case", mode="before")
    @classmethod
    def _normalize_base_case(cls, value: Any) -> str:
        return _bounded_text(value, 4_000, "模型未提供基础情景。")

    @field_validator("bull_case", "bear_case", mode="before")
    @classmethod
    def _normalize_scenarios(cls, value: Any) -> str:
        return _bounded_text(value, 3_000, "模型未提供该情景。")

    @field_validator("catalysts", "disconfirming_evidence", mode="before")
    @classmethod
    def _normalize_bullets(cls, value: Any) -> list[str]:
        return _bounded_list(value, 8)

    @field_validator("evidence_source_ids", mode="before")
    @classmethod
    def _normalize_evidence_ids(cls, value: Any) -> list[str]:
        return _bounded_list(value, 32)

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: Any) -> float:
        return _normalize_confidence_score(value)


class LLMResearchConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    base_url: str | None = None
    call_timeout_seconds: float = Field(default=90.0, gt=0, le=600)
    max_retries: int = Field(default=1, ge=0, le=5)
    retry_backoff_seconds: float = Field(default=0.5, ge=0, le=30)
    total_timeout_seconds: float = Field(default=480.0, gt=0, le=3600)

    @classmethod
    def from_environment(cls) -> LLMResearchConfig:
        legacy_deepseek_key = os.getenv("Deepseek Token-TA", "").strip()  # noqa: SIM112
        standard_deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if legacy_deepseek_key and not standard_deepseek_key:
            os.environ["DEEPSEEK_API_KEY"] = legacy_deepseek_key
            standard_deepseek_key = legacy_deepseek_key
        provider = os.getenv("TRADINGAGENTS_RESEARCH_LLM_PROVIDER", "").strip().lower()
        if not provider and standard_deepseek_key:
            provider = "deepseek"
        model = os.getenv("TRADINGAGENTS_RESEARCH_LLM_MODEL", "").strip()
        if not model and provider == "deepseek":
            model = "deepseek-v4-pro"
        base_url = os.getenv("TRADINGAGENTS_RESEARCH_LLM_BASE_URL", "").strip() or None
        if not provider or not model:
            raise NarrativeProviderUnavailableError(
                "Multi-agent research requires TRADINGAGENTS_RESEARCH_LLM_PROVIDER and "
                "TRADINGAGENTS_RESEARCH_LLM_MODEL. For DeepSeek set DEEPSEEK_API_KEY (legacy alias: Deepseek Token-TA)."
            )
        key_env = get_api_key_env(provider)
        if (
            key_env
            and not os.getenv(key_env, "").strip()
            and provider not in {"ollama", "openai_compatible"}
        ):
            raise NarrativeProviderUnavailableError(
                f"Multi-agent research provider '{provider}' requires server-side {key_env}."
            )
        return cls(
            provider=provider,
            model=model,
            base_url=base_url,
            call_timeout_seconds=_env_float("TRADINGAGENTS_RESEARCH_LLM_CALL_TIMEOUT", 90.0),
            max_retries=_env_int("TRADINGAGENTS_RESEARCH_LLM_MAX_RETRIES", 1),
            retry_backoff_seconds=_env_float("TRADINGAGENTS_RESEARCH_LLM_RETRY_BACKOFF", 0.5),
            total_timeout_seconds=_env_float("TRADINGAGENTS_RESEARCH_LLM_TOTAL_TIMEOUT", 480.0),
        )


class LLMInvocationError(NarrativeProviderError):
    """Bounded model-call failure with safe audit metadata."""

    def __init__(self, message: str, audit: dict[str, Any]):
        super().__init__(message)
        self.audit = audit


def multi_agent_configuration_status() -> dict[str, Any]:
    """Return safe readiness metadata; never return credential values."""
    try:
        config = LLMResearchConfig.from_environment()
    except (NarrativeProviderUnavailableError, ValidationError) as error:
        return {"ready": False, "message": str(error), "provider": None, "model": None}
    return {
        "ready": True,
        "message": "服务端多智能体模型配置已就绪",
        "provider": config.provider,
        "model": config.model,
        "call_timeout_seconds": config.call_timeout_seconds,
        "max_retries": config.max_retries,
        "total_timeout_seconds": config.total_timeout_seconds,
    }


class MultiAgentResearchProvider:
    """Run four specialists, a bounded bull/bear debate, and a manager synthesis."""

    def __init__(
        self,
        *,
        config: LLMResearchConfig,
        llm: Any,
        progress_callback: Callable[[str], None] | None = None,
    ):
        self.config = config
        self.llm = llm
        self.progress_callback = progress_callback
        self._context_audit: dict[str, str | int | float | bool | None] = {}
        self._deadline: float | None = None
        self._terminal_error: LLMInvocationError | None = None

    def set_progress_callback(self, callback: Callable[[str], None]) -> None:
        self.progress_callback = callback

    @classmethod
    def from_environment(cls) -> MultiAgentResearchProvider:
        config = LLMResearchConfig.from_environment()
        try:
            llm = create_llm_client(
                config.provider,
                config.model,
                base_url=config.base_url,
                timeout=config.call_timeout_seconds,
                max_retries=0,
            ).get_llm()
        except Exception as error:
            raise NarrativeProviderUnavailableError(
                f"Unable to initialize multi-agent provider: {error}"
            ) from error
        return cls(config=config, llm=llm)

    def generate(self, context: ResearchNarrativeContext) -> list[AgentOutputEnvelope]:
        report_chars = len(context.deterministic_report_markdown or "")
        self._deadline = monotonic() + self.config.total_timeout_seconds
        self._terminal_error = None
        technical_snapshot = _technical_snapshot(context.price_bars)
        self._context_audit = {
            "deterministic_output_count": len(context.deterministic_outputs),
            "deterministic_report_chars": min(report_chars, MAX_DETERMINISTIC_REPORT_CHARS),
            "deterministic_report_truncated": report_chars > MAX_DETERMINISTIC_REPORT_CHARS,
            "technical_bar_count": int(technical_snapshot.get("bar_count") or 0),
            "technical_feature_count": sum(
                value is not None for value in technical_snapshot.values()
            ),
            "technical_feature_version": TECHNICAL_FEATURE_VERSION,
            "technical_price_basis": technical_snapshot.get("price_basis"),
            "technical_adjustment_coverage_pct": technical_snapshot.get("adjustment_coverage_pct"),
            "game_product_count": len(context.game_research.products)
            if context.game_research
            else 0,
            "game_catalyst_count": len(context.game_research.catalysts)
            if context.game_research
            else 0,
            "game_approval_count": context.game_approvals.matched_count
            if context.game_approvals
            else 0,
        }
        outputs: list[AgentOutputEnvelope] = []
        notes: list[AgentOutputEnvelope] = []
        for role_id, role_name in ANALYST_ROLES:
            self._progress(f"multi_agent:{role_id}")
            result = self._note_call(context, role_id, role_name, _context_prompt(context))
            outputs.append(result)
            if result.payload is not None:
                notes.append(result)

        debate_context = _outputs_prompt(notes)
        self._progress("multi_agent:bull")
        bull = self._note_call(context, "bull", "Bull 研究员", debate_context)
        outputs.append(bull)
        self._progress("multi_agent:bear")
        bear = self._note_call(
            context, "bear", "Bear 研究员", debate_context + "\nBull观点:\n" + bull.summary
        )
        outputs.append(bear)

        self._progress("multi_agent:manager")
        manager_prompt = (
            debate_context + "\nBull观点:\n" + bull.summary + "\nBear观点:\n" + bear.summary
        )
        try:
            thesis, audit = self._invoke(
                StructuredThesis, _system("Research Manager", context) + manager_prompt
            )
            evidence = _select_evidence(context.evidence, thesis.evidence_source_ids)
            payload = InvestmentThesis(
                symbol=context.symbol,
                as_of_date=context.as_of_date,
                base_case=thesis.base_case,
                bull_case=thesis.bull_case,
                bear_case=thesis.bear_case,
                catalysts=thesis.catalysts,
                disconfirming_evidence=thesis.disconfirming_evidence,
                evidence=evidence,
                confidence=thesis.confidence,
            )
            outputs.append(
                AgentOutputEnvelope(
                    symbol=context.symbol,
                    as_of_date=context.as_of_date,
                    agent_id="llm-research-manager",
                    agent_role="Research Manager",
                    output_type=AgentOutputType.INVESTMENT_THESIS,
                    headline=thesis.headline,
                    summary=thesis.base_case,
                    evidence=evidence,
                    sections=[
                        AgentOutputSection(
                            title="基础情景", summary=thesis.base_case, evidence=evidence
                        ),
                        AgentOutputSection(title="乐观情景", summary=thesis.bull_case),
                        AgentOutputSection(title="悲观情景", summary=thesis.bear_case),
                        AgentOutputSection(title="潜在催化剂", bullets=thesis.catalysts),
                        AgentOutputSection(
                            title="反证与失效条件", bullets=thesis.disconfirming_evidence
                        ),
                    ],
                    risks=thesis.disconfirming_evidence,
                    payload=payload,
                    confidence=_confidence(thesis.confidence),
                    metadata=self._metadata("manager", audit),
                )
            )
        except Exception as error:
            outputs.append(self._failure(context, "manager", "Research Manager", error))
        self._progress("multi_agent:complete")
        return outputs

    def _progress(self, phase: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(phase)

    def _note_call(
        self, context: ResearchNarrativeContext, role_id: str, role_name: str, material: str
    ) -> AgentOutputEnvelope:
        try:
            note, audit = self._invoke(
                StructuredResearchNote, _system(role_name, context) + material
            )
            evidence = _select_evidence(context.evidence, note.evidence_source_ids)
            payload = AnalystNote(
                symbol=context.symbol,
                analyst_role=role_name,
                as_of_date=context.as_of_date,
                summary=note.summary,
                evidence=evidence,
                risks=note.risks,
                confidence=note.confidence,
            )
            return AgentOutputEnvelope(
                symbol=context.symbol,
                as_of_date=context.as_of_date,
                agent_id=f"llm-{role_id}",
                agent_role=role_name,
                output_type=AgentOutputType.ANALYST_NOTE,
                headline=note.headline,
                summary=note.summary,
                sections=[
                    AgentOutputSection(
                        title="研究要点", bullets=note.supporting_points, evidence=evidence
                    )
                ],
                evidence=evidence,
                risks=note.risks,
                confidence=note.confidence,
                payload=payload,
                metadata=self._metadata(role_id, audit),
            )
        except Exception as error:
            return self._failure(context, role_id, role_name, error)

    def _invoke(self, schema: type[BaseModel], prompt: str) -> tuple[Any, dict[str, Any]]:
        started = perf_counter()
        include_raw = True
        structured_method = "json_mode" if self.config.provider == "deepseek" else None
        if structured_method == "json_mode":
            schema_json = json.dumps(
                schema.model_json_schema(), ensure_ascii=False, separators=(",", ":")
            )
            prompt = (
                prompt
                + "\n只返回一个JSON对象，不要Markdown代码块或额外说明。JSON必须匹配此schema："
                + schema_json
            )
        try:
            if structured_method is not None:
                structured_llm = self.llm.with_structured_output(
                    schema, method=structured_method, include_raw=True
                )
            else:
                structured_llm = self.llm.with_structured_output(schema, include_raw=True)
        except TypeError:
            include_raw = False
            structured_llm = self.llm.with_structured_output(schema)
        response, attempt_count = self._invoke_with_retry(structured_llm, prompt)
        elapsed = round((perf_counter() - started) * 1000)
        raw = response.get("raw") if include_raw and isinstance(response, dict) else response
        parsed = response.get("parsed") if include_raw and isinstance(response, dict) else response
        recovered = False
        if parsed is None and raw is not None:
            parsed = _recover_structured_payload(raw)
            recovered = True
        value = parsed if isinstance(parsed, schema) else schema.model_validate(parsed)
        usage = (
            getattr(raw, "usage_metadata", None) or getattr(response, "usage_metadata", None) or {}
        )
        audit = {
            "latency_ms": elapsed,
            "attempt_count": attempt_count,
            "retry_count": attempt_count - 1,
            "call_timeout_seconds": self.config.call_timeout_seconds,
            "call_executed": True,
            "structured_output_recovered": recovered,
            "structured_method": structured_method or "provider_default",
            **{
                f"usage_{key}": item
                for key, item in usage.items()
                if isinstance(item, (str, int, float, bool))
            },
        }
        return value, audit

    def _invoke_with_retry(self, structured_llm: Any, prompt: str) -> tuple[Any, int]:
        started = perf_counter()
        if self._terminal_error is not None:
            raise LLMInvocationError(
                str(self._terminal_error),
                {
                    **self._terminal_error.audit,
                    "call_executed": False,
                    "latency_ms": 0,
                },
            )

        max_attempts = self.config.max_retries + 1
        for attempt in range(1, max_attempts + 1):
            remaining = (
                self._deadline - monotonic()
                if self._deadline is not None
                else self.config.total_timeout_seconds
            )
            if remaining <= 0:
                error = LLMInvocationError(
                    "The multi-agent research deadline was exceeded.",
                    {
                        "failed": True,
                        "failure_reason": "total_timeout",
                        "attempt_count": attempt - 1,
                        "retry_count": max(0, attempt - 2),
                        "call_executed": False,
                        "latency_ms": 0,
                    },
                )
                self._terminal_error = error
                raise error
            call_timeout = min(self.config.call_timeout_seconds, remaining)
            try:
                return _bounded_invoke(
                    lambda: structured_llm.invoke(prompt),
                    timeout_seconds=call_timeout,
                    attempt_count=attempt,
                ), attempt
            except LLMInvocationError as error:
                self._terminal_error = error
                raise
            except Exception as error:
                if not _is_retryable_error(error) or attempt >= max_attempts:
                    raise LLMInvocationError(
                        "The model call failed after bounded retries.",
                        {
                            "failed": True,
                            "failure_reason": (
                                "transient_retries_exhausted"
                                if _is_retryable_error(error)
                                else "non_retryable_provider_error"
                            ),
                            "attempt_count": attempt,
                            "retry_count": attempt - 1,
                            "provider_error_type": error.__class__.__name__,
                            "call_executed": True,
                            "latency_ms": round((perf_counter() - started) * 1000),
                        },
                    ) from error
                delay = self.config.retry_backoff_seconds * (2 ** (attempt - 1))
                if delay:
                    sleep(min(delay, max(0.0, remaining)))

        raise AssertionError("unreachable")

    def _metadata(self, stage: str, audit: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "prompt_version": PROMPT_VERSION,
            "stage": stage,
            "research_only": True,
            **self._context_audit,
            **audit,
        }

    def _failure(
        self, context: ResearchNarrativeContext, role_id: str, role_name: str, error: Exception
    ) -> AgentOutputEnvelope:
        return AgentOutputEnvelope(
            symbol=context.symbol,
            as_of_date=context.as_of_date,
            agent_id=f"llm-{role_id}",
            agent_role=role_name,
            output_type=AgentOutputType.COCKPIT_PANEL,
            headline=f"{role_name}已降级",
            summary=f"该阶段未生成模型结论；其余研究阶段继续。原因：{error.__class__.__name__}",
            risks=["模型阶段失败，不能将此输出视为完整研究结论。"],
            confidence=ConfidenceLevel.LOW,
            metadata=self._metadata(role_id, _validation_audit(error)),
        )


def _system(role: str, context: ResearchNarrativeContext) -> str:
    ids = ", ".join(item.source_id for item in context.evidence) or "none"
    focus = ""
    if role == "新闻、游戏产品与版号分析师":
        focus = (
            "优先分析已提供的游戏产品状态、产品催化剂和精确法人匹配版号；"
            "明确区分已上线、储备、持续运营和无日期事项，不得把机会雷达分数当成投资结论。"
        )
    if role == "技术与市场分析师":
        focus = (
            "优先解释确定性技术特征中的趋势、均线位置、动量、波动、回撤和量价关系；"
            "不得自行重算或编造指标。"
        )
    return (
        f"你是{role}。所有面向用户的文本必须使用简体中文。"
        "只可使用所给 normalized records 和由它们生成的确定性研究底稿，"
        "禁止引入外部事实或虚构引用。"
        f"{focus}只能引用这些 evidence_source_ids: {ids}。"
        "不得给出交易方向、仓位或绕过风控。\n"
    )


def _context_prompt(context: ResearchNarrativeContext) -> str:
    prices = [
        f"{x.date}:{x.close}/{x.volume}"
        for x in sorted(context.price_bars, key=lambda x: x.date)[-20:]
    ]
    fundamentals = [
        f"{k}={v}" for row in context.fundamentals[-2:] for k, v in sorted(row.metrics.items())
    ]
    news = [f"{x.published_at.date()}|{x.provider}|{x.title}" for x in context.news[:12]]
    refs = [f"{x.source_id}|{x.description}" for x in context.evidence]
    technical = _technical_snapshot(context.price_bars)
    deterministic_outputs = [
        f"{x.agent_role}|{x.output_type.value}|{x.headline}|{x.summary}"
        for x in context.deterministic_outputs
    ]
    game_context = _game_context_prompt(context)
    report = context.deterministic_report_markdown or "None available"
    report_truncated = len(report) > MAX_DETERMINISTIC_REPORT_CHARS
    report = report[:MAX_DETERMINISTIC_REPORT_CHARS]
    return (
        f"Symbol={context.symbol}; as_of={context.as_of_date}\n"
        f"Prices={prices}\nDeterministic technical features={technical}\n"
        f"Fundamentals={fundamentals}\nNews={news}\n{game_context}\nEvidence={refs}\n"
        f"Deterministic outputs={deterministic_outputs}\n"
        f"Deterministic report (truncated={report_truncated}):\n{report}\n"
    )


def _game_context_prompt(context: ResearchNarrativeContext) -> str:
    research = context.game_research
    approvals = context.game_approvals
    opportunity = context.game_opportunity
    if research is None or not research.available:
        return "Game research=None available"
    products = [
        {
            "name": item.name,
            "status": item.status.value,
            "genres": item.genres,
            "platforms": item.platforms,
            "markets": item.markets,
            "evidence_source_ids": [f"game:{source_id}" for source_id in item.evidence_ids],
        }
        for item in research.products
    ]
    catalysts = [
        {
            "title": item.catalyst.title,
            "category": item.catalyst.category.value,
            "status": item.status.value,
            "event_date": item.catalyst.event_date.isoformat()
            if item.catalyst.event_date
            else None,
            "evidence_source_ids": [
                f"game:{source_id}" for source_id in item.catalyst.evidence_ids
            ],
        }
        for item in research.catalysts
    ]
    approval_items = [
        {
            "game_name": item.approval.game_name,
            "approval_date": item.approval.approval_date.isoformat(),
            "kind": item.approval.kind.value,
            "operator": item.approval.operating_entity,
            "evidence_source_id": f"approval:{item.approval.approval_id}",
        }
        for item in (approvals.approvals[:12] if approvals else [])
    ]
    opportunity_view = None
    if opportunity is not None and opportunity.available:
        opportunity_view = {
            "level": opportunity.level.value,
            "score": opportunity.score,
            "max_score": opportunity.max_score,
            "factors": [
                {
                    "factor": item.factor_id,
                    "status": item.status.value,
                    "detail": item.detail,
                }
                for item in opportunity.factors
            ],
            "warning": "Screening context only; not an investment recommendation.",
        }
    return "Game research=" + json.dumps(
        {
            "company_name": research.company_name,
            "research_focus": research.research_focus,
            "products": products,
            "catalysts": catalysts,
            "approvals": approval_items,
            "opportunity_radar": opportunity_view,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _outputs_prompt(outputs: list[AgentOutputEnvelope]) -> str:
    return "\n".join(
        f"{x.agent_role}: {x.summary}; refs={[e.source_id for e in x.evidence]}" for x in outputs
    )


def _select_evidence(allowed: list[EvidenceRef], requested: list[str]) -> list[EvidenceRef]:
    by_id = {item.source_id: item for item in allowed}
    prefix_aliases = {
        "technical": "price",
        "technical_features": "price",
        "market": "price",
        "ohlcv": "price",
        "price": "price",
        "fundamental": "fundamentals",
        "fundamentals": "fundamentals",
        "news": "news",
    }
    selected: list[EvidenceRef] = []
    unknown: list[str] = []
    for source_id in dict.fromkeys(requested):
        if source_id in by_id:
            selected.append(by_id[source_id])
            continue
        prefix = prefix_aliases.get(source_id.split(":", 1)[0].lower())
        candidates = [
            item for item in allowed if prefix and item.source_id.startswith(prefix + ":")
        ]
        if len(candidates) == 1:
            selected.append(candidates[0])
        else:
            unknown.append(source_id)
    if unknown:
        raise NarrativeProviderError(
            f"Model cited evidence outside the normalized context: {sorted(unknown)}"
        )
    return list({item.source_id: item for item in selected}.values())


def _recover_structured_payload(raw: Any) -> dict[str, Any]:
    content = getattr(raw, "content", raw)
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        content = "\n".join(parts)
    if isinstance(content, dict):
        return content
    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0].strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise NarrativeProviderError("Structured response did not contain a JSON object.")
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        raise NarrativeProviderError(
            f"Structured response JSON could not be decoded at position {error.pos}."
        ) from error
    if not isinstance(value, dict):
        raise NarrativeProviderError("Structured response JSON must be an object.")
    return value


def _bounded_text(value: Any, limit: int, fallback: str) -> str:
    text = str(value or "").strip()
    return (text or fallback)[:limit]


def _bounded_list(value: Any, limit: int) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return [str(item).strip() for item in values if str(item).strip()][:limit]


def _normalize_confidence_score(value: Any) -> float:
    if isinstance(value, ConfidenceLevel):
        return {ConfidenceLevel.LOW: 0.3, ConfidenceLevel.MEDIUM: 0.6, ConfidenceLevel.HIGH: 0.85}[
            value
        ]
    if isinstance(value, str):
        normalized = value.strip().lower().rstrip("%")
        labels = {"low": 0.3, "medium": 0.6, "high": 0.85, "低": 0.3, "中": 0.6, "高": 0.85}
        if normalized in labels:
            return labels[normalized]
        try:
            value = float(normalized)
        except ValueError:
            return 0.6
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.6
    if score > 1:
        score /= 100
    return min(1.0, max(0.0, score))


def _normalize_confidence_level(value: Any) -> ConfidenceLevel:
    score = _normalize_confidence_score(value)
    return _confidence(score)


def _technical_snapshot(price_bars: list[Any]) -> dict[str, float | int | str | None]:
    by_date: dict[Any, Any] = {}
    for bar in price_bars:
        current = by_date.get(bar.date)
        provenance = getattr(bar, "provenance", None)
        current_provenance = getattr(current, "provenance", None)
        candidate_rank = (
            bar.adjusted_close is not None,
            str(getattr(provenance, "as_of_date", "")),
            str(getattr(provenance, "retrieved_at", "")),
        )
        current_rank = (
            (
                current.adjusted_close is not None,
                str(getattr(current_provenance, "as_of_date", "")),
                str(getattr(current_provenance, "retrieved_at", "")),
            )
            if current is not None
            else None
        )
        if current_rank is None or candidate_rank > current_rank:
            by_date[bar.date] = bar
    ordered = [by_date[day] for day in sorted(by_date)]
    if not ordered:
        return {"bar_count": 0, "status": "unavailable"}
    adjusted_count = sum(bar.adjusted_close is not None for bar in ordered)
    closes = [
        float(bar.adjusted_close if bar.adjusted_close is not None else bar.close)
        for bar in ordered
    ]
    volumes = [float(bar.volume) for bar in ordered if bar.volume is not None]

    def period_return(days: int) -> float | None:
        return (
            closes[-1] / closes[-days - 1] - 1 if len(closes) > days and closes[-days - 1] else None
        )

    def moving_average(days: int) -> float | None:
        return mean(closes[-days:]) if len(closes) >= days else None

    returns = [
        closes[index] / closes[index - 1] - 1
        for index in range(1, len(closes))
        if closes[index - 1]
    ]
    recent_returns = returns[-20:]
    volatility = stdev(recent_returns) * math.sqrt(252) if len(recent_returns) >= 2 else None
    window = closes[-60:]
    peak = window[0]
    max_drawdown = 0.0
    for close in window:
        peak = max(peak, close)
        if peak:
            max_drawdown = min(max_drawdown, close / peak - 1)
    changes = [
        closes[index] - closes[index - 1] for index in range(max(1, len(closes) - 14), len(closes))
    ]
    gains = sum(max(change, 0) for change in changes)
    losses = sum(max(-change, 0) for change in changes)
    rsi14 = (
        100.0 if changes and losses == 0 else (100 - 100 / (1 + gains / losses) if losses else None)
    )
    sma5, sma20, sma60 = moving_average(5), moving_average(20), moving_average(60)
    volume_ratio = None
    if len(volumes) >= 20 and mean(volumes[-20:]):
        volume_ratio = mean(volumes[-5:]) / mean(volumes[-20:])
    trend = "insufficient"
    if sma5 is not None and sma20 is not None:
        trend = (
            "up" if closes[-1] > sma5 > sma20 else "down" if closes[-1] < sma5 < sma20 else "mixed"
        )
    values: dict[str, float | int | str | None] = {
        "bar_count": len(ordered),
        "adjusted_bar_count": adjusted_count,
        "adjustment_coverage_pct": adjusted_count / len(ordered),
        "price_basis": (
            "forward_adjusted"
            if adjusted_count == len(ordered)
            else "mixed"
            if adjusted_count
            else "raw_unadjusted"
        ),
        "technical_feature_version": TECHNICAL_FEATURE_VERSION,
        "last_close": closes[-1],
        "return_5d": period_return(5),
        "return_20d": period_return(20),
        "return_60d": period_return(60),
        "sma_5": sma5,
        "sma_20": sma20,
        "sma_60": sma60,
        "close_vs_sma20": closes[-1] / sma20 - 1 if sma20 else None,
        "annualized_volatility_20d": volatility,
        "max_drawdown_60d": max_drawdown,
        "rsi_14": rsi14,
        "volume_ratio_5d_vs_20d": volume_ratio,
        "trend_state": trend,
    }
    return {
        key: round(value, 6) if isinstance(value, float) else value for key, value in values.items()
    }


def _bounded_invoke(
    call: Callable[[], Any],
    *,
    timeout_seconds: float,
    attempt_count: int,
) -> Any:
    result: Queue[tuple[bool, Any]] = Queue(maxsize=1)

    def run() -> None:
        try:
            result.put((True, call()))
        except Exception as error:
            result.put((False, error))

    Thread(target=run, name="research-llm-call", daemon=True).start()
    try:
        succeeded, value = result.get(timeout=timeout_seconds)
    except Empty as error:
        raise LLMInvocationError(
            f"The model call exceeded {timeout_seconds:.1f} seconds.",
            {
                "failed": True,
                "failure_reason": "call_timeout",
                "attempt_count": attempt_count,
                "retry_count": attempt_count - 1,
                "call_timeout_seconds": round(timeout_seconds, 3),
                "call_executed": True,
                "latency_ms": round(timeout_seconds * 1000),
            },
        ) from error
    if succeeded:
        return value
    raise value


def _is_retryable_error(error: Exception) -> bool:
    current: BaseException | None = error
    for _ in range(4):
        if current is None:
            break
        status_code = getattr(current, "status_code", None)
        response = getattr(current, "response", None)
        status_code = status_code or getattr(response, "status_code", None)
        if status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True
        name = current.__class__.__name__.lower()
        if any(token in name for token in ("timeout", "connection", "ratelimit")):
            return True
        current = current.__cause__ or current.__context__
    return False


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError as error:
        raise NarrativeProviderUnavailableError(f"{name} must be numeric.") from error


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise NarrativeProviderUnavailableError(f"{name} must be an integer.") from error


def _validation_audit(error: Exception) -> dict[str, Any]:
    current: BaseException | None = error
    if isinstance(error, LLMInvocationError):
        return {
            "error_type": error.__class__.__name__,
            **error.audit,
        }
    if isinstance(error, NarrativeProviderError):
        message = str(error)
        reason = (
            "evidence_boundary"
            if "outside the normalized context" in message
            else "invalid_json"
            if "could not be decoded" in message
            else "missing_json"
            if "did not contain a JSON object" in message
            else "structured_response"
        )
        return {"failed": True, "error_type": "NarrativeProviderError", "failure_reason": reason}
    for _ in range(3):
        if isinstance(current, ValidationError):
            fields = sorted(
                {".".join(str(part) for part in item["loc"]) for item in current.errors()}
            )
            return {
                "failed": True,
                "error_type": "ValidationError",
                "validation_fields": ",".join(fields)[:500],
            }
        current = current.__cause__ or current.__context__ if current is not None else None
    return {"failed": True, "error_type": error.__class__.__name__}


def _confidence(value: float) -> ConfidenceLevel:
    return (
        ConfidenceLevel.HIGH
        if value >= 0.75
        else ConfidenceLevel.LOW
        if value < 0.4
        else ConfidenceLevel.MEDIUM
    )
