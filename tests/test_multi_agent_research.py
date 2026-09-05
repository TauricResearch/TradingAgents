import json
from datetime import date, timedelta
from time import monotonic, sleep
from types import SimpleNamespace

from tradingagents.research_platform.agent_contracts import AgentOutputType, EvidenceRef
from tradingagents.research_platform.game_universe import build_game_research_snapshot
from tradingagents.research_platform.multi_agent_research import (
    LLMResearchConfig,
    MultiAgentResearchProvider,
    StructuredResearchNote,
    StructuredThesis,
    _select_evidence,
    _technical_snapshot,
    multi_agent_configuration_status,
)
from tradingagents.research_platform.narrative_provider import ResearchNarrativeContext


class FakeStructured:
    def __init__(self, owner, schema):
        self.owner, self.schema = owner, schema

    def invoke(self, prompt):
        self.owner.prompts.append(prompt)
        call = len(self.owner.prompts)
        if self.owner.fail_call == call:
            raise RuntimeError("fixture failure")
        if self.schema is StructuredThesis:
            return StructuredThesis(
                headline="综合研究命题",
                base_case="基本情景",
                bull_case="乐观情景",
                bear_case="悲观情景",
                catalysts=["催化剂"],
                disconfirming_evidence=["反证"],
                evidence_source_ids=["price:fixture"],
                confidence=0.65,
            )
        return StructuredResearchNote(
            headline="角色结论",
            summary="仅依据归一化证据的结论。",
            supporting_points=["研究要点"],
            risks=["不确定性"],
            evidence_source_ids=["price:fixture"],
            confidence="medium",
        )


class FakeLLM:
    def __init__(self, fail_call=None):
        self.fail_call = fail_call
        self.prompts = []

    def with_structured_output(self, schema):
        return FakeStructured(self, schema)


def context():
    return ResearchNarrativeContext(
        symbol="002624",
        as_of_date=date(2026, 7, 12),
        evidence=[
            EvidenceRef(
                source_id="price:fixture",
                description="normalized bars",
                as_of_date=date(2026, 7, 12),
                confidence=0.9,
            )
        ],
        deterministic_report_markdown="# Deterministic report\nVerified deterministic thesis.",
    )


def test_orchestration_runs_specialists_debate_and_manager():
    llm = FakeLLM()
    outputs = MultiAgentResearchProvider(
        config=LLMResearchConfig(provider="deepseek", model="configured-model"), llm=llm
    ).generate(context())

    assert len(outputs) == 7
    assert len(llm.prompts) == 7
    assert "Deterministic report" in llm.prompts[0]
    assert "Verified deterministic thesis" in llm.prompts[0]
    assert outputs[-1].output_type == AgentOutputType.INVESTMENT_THESIS
    assert outputs[-1].payload.bull_case == "乐观情景"
    assert [section.title for section in outputs[-1].sections] == [
        "基础情景",
        "乐观情景",
        "悲观情景",
        "潜在催化剂",
        "反证与失效条件",
    ]
    assert outputs[-1].metadata["provider"] == "deepseek"
    assert outputs[-1].metadata["research_only"] is True
    assert outputs[-1].metadata["deterministic_report_chars"] > 0
    assert outputs[-1].metadata["deterministic_report_truncated"] is False
    assert all(output.output_type != AgentOutputType.TRADE_SIGNAL for output in outputs)


def test_one_agent_failure_degrades_and_later_stages_continue():
    outputs = MultiAgentResearchProvider(
        config=LLMResearchConfig(provider="deepseek", model="configured-model"),
        llm=FakeLLM(fail_call=2),
    ).generate(context())
    assert outputs[1].output_type == AgentOutputType.COCKPIT_PANEL
    assert outputs[1].metadata["failed"] is True
    assert outputs[-1].output_type == AgentOutputType.INVESTMENT_THESIS


class TransientProviderError(RuntimeError):
    status_code = 503


class RetryLLM:
    def __init__(self):
        self.calls = 0

    def with_structured_output(self, schema, **kwargs):
        owner = self

        class Runner:
            def invoke(self, prompt):
                owner.calls += 1
                if owner.calls == 1:
                    raise TransientProviderError("temporary gateway failure")
                if schema is StructuredThesis:
                    return StructuredThesis(
                        headline="manager",
                        base_case="base",
                        bull_case="bull",
                        bear_case="bear",
                        evidence_source_ids=["price:fixture"],
                        confidence=0.6,
                    )
                return StructuredResearchNote(
                    headline="note",
                    summary="summary",
                    evidence_source_ids=["price:fixture"],
                )

        return Runner()


def test_transient_model_error_is_retried_with_a_bounded_budget():
    llm = RetryLLM()
    outputs = MultiAgentResearchProvider(
        config=LLMResearchConfig(
            provider="deepseek",
            model="configured-model",
            max_retries=1,
            retry_backoff_seconds=0,
        ),
        llm=llm,
    ).generate(context())

    assert outputs[0].metadata["attempt_count"] == 2
    assert outputs[0].metadata["retry_count"] == 1
    assert outputs[-1].output_type == AgentOutputType.INVESTMENT_THESIS
    assert llm.calls == 8


class HangingLLM:
    def __init__(self):
        self.calls = 0

    def with_structured_output(self, schema, **kwargs):
        owner = self

        class Runner:
            def invoke(self, prompt):
                owner.calls += 1
                sleep(0.25)
                raise AssertionError("late result must be ignored")

        return Runner()


def test_call_timeout_releases_orchestration_and_short_circuits_remaining_stages():
    llm = HangingLLM()
    provider = MultiAgentResearchProvider(
        config=LLMResearchConfig(
            provider="deepseek",
            model="configured-model",
            call_timeout_seconds=0.02,
            max_retries=2,
            total_timeout_seconds=1,
        ),
        llm=llm,
    )
    started = monotonic()
    outputs = provider.generate(context())
    elapsed = monotonic() - started

    assert elapsed < 0.20
    assert llm.calls == 1
    assert all(output.output_type == AgentOutputType.COCKPIT_PANEL for output in outputs)
    assert all(output.metadata["failure_reason"] == "call_timeout" for output in outputs)
    assert outputs[0].metadata["attempt_count"] == 1
    assert outputs[0].metadata["retry_count"] == 0


def test_unknown_evidence_is_rejected_and_degraded():
    class EscapingLLM(FakeLLM):
        def with_structured_output(self, schema):
            structured = super().with_structured_output(schema)
            original = structured.invoke

            def invoke(prompt):
                value = original(prompt)
                return value.model_copy(update={"evidence_source_ids": ["outside"]})

            structured.invoke = invoke
            return structured

    outputs = MultiAgentResearchProvider(
        config=LLMResearchConfig(provider="deepseek", model="configured-model"), llm=EscapingLLM()
    ).generate(context())
    assert all(output.output_type == AgentOutputType.COCKPIT_PANEL for output in outputs)


def test_configuration_status_never_exposes_key(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_RESEARCH_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("TRADINGAGENTS_RESEARCH_LLM_MODEL", "user-supplied-v4-pro-id")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "super-secret")
    status = multi_agent_configuration_status()
    assert status == {
        "ready": True,
        "message": "服务端多智能体模型配置已就绪",
        "provider": "deepseek",
        "model": "user-supplied-v4-pro-id",
        "call_timeout_seconds": 90.0,
        "max_retries": 1,
        "total_timeout_seconds": 480.0,
    }
    assert "secret" not in repr(status)


def test_configuration_requires_explicit_model(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("Deepseek Token-TA", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_RESEARCH_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_RESEARCH_LLM_MODEL", raising=False)
    assert multi_agent_configuration_status()["ready"] is False


def test_progress_callback_reports_each_bounded_stage():
    phases = []
    provider = MultiAgentResearchProvider(
        config=LLMResearchConfig(provider="deepseek", model="configured-model"),
        llm=FakeLLM(),
    )
    provider.set_progress_callback(phases.append)
    provider.generate(context())
    assert phases == [
        "multi_agent:fundamentals",
        "multi_agent:market",
        "multi_agent:game_news",
        "multi_agent:valuation",
        "multi_agent:bull",
        "multi_agent:bear",
        "multi_agent:manager",
        "multi_agent:complete",
    ]


def test_legacy_deepseek_token_name_selects_v4_pro_without_exposing_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_RESEARCH_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_RESEARCH_LLM_MODEL", raising=False)
    monkeypatch.setenv("Deepseek Token-TA", "legacy-secret")
    status = multi_agent_configuration_status()
    assert status["ready"] is True
    assert status["provider"] == "deepseek"
    assert status["model"] == "deepseek-v4-pro"
    assert "legacy-secret" not in repr(status)


def test_deepseek_note_shape_is_normalized_before_constraints():
    note = StructuredResearchNote(
        headline="H" * 240,
        summary="S" * 3_500,
        supporting_points="single point",
        risks=[f"risk-{index}" for index in range(12)],
        evidence_source_ids="price:fixture",
        confidence=82,
    )
    assert len(note.headline) == 180
    assert len(note.summary) == 3_000
    assert note.supporting_points == ["single point"]
    assert len(note.risks) == 8
    assert note.evidence_source_ids == ["price:fixture"]
    assert note.confidence.value == "high"


def test_deterministic_technical_snapshot_computes_market_features():
    bars = [
        SimpleNamespace(
            date=date(2026, 1, 1) + timedelta(days=index),
            adjusted_close=None,
            close=100 + index,
            volume=1_000 + index * 10,
        )
        for index in range(61)
    ]
    snapshot = _technical_snapshot([*bars, *bars])
    assert snapshot["bar_count"] == 61
    assert snapshot["return_20d"] > 0
    assert snapshot["sma_5"] > snapshot["sma_20"] > snapshot["sma_60"]
    assert snapshot["trend_state"] == "up"
    assert snapshot["rsi_14"] == 100.0
    assert snapshot["annualized_volatility_20d"] is not None


class RawFallbackLLM:
    def __init__(self):
        self.methods = []

    def with_structured_output(self, schema, method=None, include_raw=False):
        self.methods.append(method)

        class Runner:
            def invoke(self, prompt):
                if schema is StructuredThesis:
                    payload = {
                        "headline": "manager",
                        "base_case": "base",
                        "bull_case": "bull",
                        "bear_case": "bear",
                        "catalysts": [],
                        "disconfirming_evidence": [],
                        "evidence_source_ids": ["price:fixture"],
                        "confidence": "65%",
                    }
                else:
                    payload = {
                        "headline": "note",
                        "summary": "summary",
                        "supporting_points": "point",
                        "risks": [],
                        "evidence_source_ids": ["price:fixture"],
                        "confidence": 78,
                    }
                raw = SimpleNamespace(
                    content="```json\n" + json.dumps(payload) + "\n```",
                    usage_metadata={"input_tokens": 10, "output_tokens": 5},
                )
                return (
                    {"raw": raw, "parsed": None, "parsing_error": ValueError("fixture")}
                    if include_raw
                    else payload
                )

        return Runner()


def test_raw_json_is_recovered_when_provider_parser_returns_none():
    llm = RawFallbackLLM()
    outputs = MultiAgentResearchProvider(
        config=LLMResearchConfig(provider="deepseek", model="configured-model"),
        llm=llm,
    ).generate(context())
    assert all(not output.metadata.get("failed") for output in outputs)
    assert all(output.metadata["structured_output_recovered"] is True for output in outputs)
    assert set(llm.methods) == {"json_mode"}
    assert all(output.metadata["structured_method"] == "json_mode" for output in outputs)
    assert outputs[0].confidence.value == "high"
    assert outputs[-1].payload.confidence == 0.65
    assert outputs[-1].metadata["usage_input_tokens"] == 10


def test_technical_evidence_alias_maps_only_to_canonical_price_evidence():
    allowed = context().evidence
    selected = _select_evidence(allowed, ["technical_features:002624:2026-07-12"])
    assert selected == allowed


def test_game_products_and_catalysts_are_included_in_agent_context():
    game_context = context().model_copy(
        update={
            "game_research": build_game_research_snapshot("002602", as_of_date=date(2026, 7, 12))
        }
    )
    llm = FakeLLM()
    outputs = MultiAgentResearchProvider(
        config=LLMResearchConfig(provider="deepseek", model="configured-model"), llm=llm
    ).generate(game_context)

    assert "Whiteout Survival" in llm.prompts[0]
    assert "Kingshot" in llm.prompts[0]
    assert "新SLG与休闲产品的测试和商业化验证" in llm.prompts[0]
    assert outputs[-1].metadata["game_product_count"] == 5
    assert outputs[-1].metadata["game_catalyst_count"] == 2
