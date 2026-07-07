"""EvidenceAgent runtime: rendering-bound attribution, abstention, fakes."""

from datetime import datetime, timezone

import pytest

from tests.pro_fakes import make_bars
from tradingagents.contracts import (
    AgentTeam,
    AssetClass,
    Direction,
    IndicatorReading,
    MarketSnapshot,
    MetricReading,
    NewsItem,
    Timeframe,
)
from tradingagents.pro.agents import (
    AgentSpec,
    EvidenceAgent,
    EvidenceDraft,
    build_team,
    render_context,
    run_agents,
)

AS_OF = datetime(2026, 7, 6, 14, 30, tzinfo=timezone.utc)


class FakeStructured:
    def __init__(self, draft):
        self.draft = draft
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.draft, Exception):
            raise self.draft
        return self.draft


class FakeLLM:
    def __init__(self, draft=None):
        self.structured = FakeStructured(
            draft
            if draft is not None
            else EvidenceDraft(
                claim="RSI shows oversold conditions per the shown value.",
                direction="bullish",
                confidence=62,
            )
        )

    def with_structured_output(self, schema):
        assert schema is EvidenceDraft
        return self.structured


def make_snapshot(**overrides) -> MarketSnapshot:
    fields = {
        "symbol": "XAUUSD",
        "asset": AssetClass.GOLD,
        "as_of": AS_OF,
        "bars": make_bars(n=60),
        "indicators": [
            IndicatorReading(
                name="RSI_14", timeframe=Timeframe.D1, value={"value": 27.4},
                params={"period": 14},
            ),
            IndicatorReading(
                name="MACD", timeframe=Timeframe.D1,
                value={"macd": -1.2, "signal": -0.8, "histogram": -0.4},
            ),
        ],
        "macro": [MetricReading(name="DXY", value=104.2, source="gold_cross_asset")],
        "news": [
            NewsItem(headline="Fed holds rates steady", source="reuters",
                     published_at=AS_OF),
        ],
    }
    fields.update(overrides)
    return MarketSnapshot(**fields)


RSI_SPEC = AgentSpec(
    agent_id="rsi", team=AgentTeam.TECHNICAL,
    persona="RSI momentum specialist.", indicators=("RSI_14",),
)


def test_agent_produces_evidence_with_code_attached_attribution():
    llm = FakeLLM()
    agent = EvidenceAgent(RSI_SPEC, llm)
    evidence = agent.analyze(make_snapshot())

    assert evidence is not None
    assert evidence.agent_id == "rsi"
    assert evidence.team is AgentTeam.TECHNICAL
    assert evidence.direction is Direction.BULLISH
    assert evidence.confidence == 62
    # attribution came from the rendered context, not the LLM
    assert [r.name for r in evidence.data_refs] == ["RSI_14"]
    assert evidence.data_refs[0].value == 27.4
    assert evidence.sources[0].id == "indicator_engine"


def test_prompt_contains_only_selected_data():
    llm = FakeLLM()
    agent = EvidenceAgent(RSI_SPEC, llm)
    agent.analyze(make_snapshot())
    prompt = llm.structured.prompts[0]
    assert "RSI_14: value=27.4000" in prompt
    assert "MACD" not in prompt  # not selected by this spec
    assert "DXY" not in prompt
    assert "rsi" in prompt  # agent_id substituted


def test_agent_abstains_when_selected_data_missing():
    spec = AgentSpec(
        agent_id="adx", team=AgentTeam.TECHNICAL,
        persona="ADX specialist.", indicators=("ADX_14",),
    )
    agent = EvidenceAgent(spec, FakeLLM())
    assert agent.analyze(make_snapshot()) is None


def test_agent_abstains_on_structured_failure():
    llm = FakeLLM(draft=RuntimeError("provider exploded"))
    llm.structured.draft = RuntimeError("provider exploded")
    agent = EvidenceAgent(RSI_SPEC, llm)
    assert agent.analyze(make_snapshot()) is None


def test_missing_inputs_are_flagged_in_prompt_not_guessed():
    spec = AgentSpec(
        agent_id="trend", team=AgentTeam.TECHNICAL, persona="Trend.",
        indicators=("SMA_50", "RSI_14"),
    )
    llm = FakeLLM()
    EvidenceAgent(spec, llm).analyze(make_snapshot())
    prompt = llm.structured.prompts[0]
    assert "indicator:SMA_50" in prompt  # flagged as unavailable
    assert "do not guess" in prompt


def test_multi_line_indicator_flattens_to_refs():
    spec = AgentSpec(
        agent_id="macd", team=AgentTeam.TECHNICAL, persona="MACD.",
        indicators=("MACD",),
    )
    evidence = EvidenceAgent(spec, FakeLLM()).analyze(make_snapshot())
    names = {r.name for r in evidence.data_refs}
    assert names == {"MACD.macd", "MACD.signal", "MACD.histogram"}


def test_news_refs_carry_per_item_attribution():
    spec = AgentSpec(
        agent_id="general_news", team=AgentTeam.NEWS_SENTIMENT,
        persona="News.", include_news=5,
    )
    evidence = EvidenceAgent(spec, FakeLLM()).analyze(make_snapshot())
    assert evidence.data_refs[0].name == "NEWS_1"
    assert evidence.sources[0].id == "news:reuters"


def test_extra_metrics_reach_risk_agents():
    spec = AgentSpec(
        agent_id="var", team=AgentTeam.RISK, persona="VaR.",
        metrics=("VAR_95",),
    )
    extra = {"VAR_95": MetricReading(name="VAR_95", value=0.021, source="risk_engine")}
    evidence = EvidenceAgent(spec, FakeLLM()).analyze(make_snapshot(), extra_metrics=extra)
    assert evidence is not None
    assert evidence.data_refs[0].value == pytest.approx(0.021)
    assert evidence.sources[0].id == "risk_engine"


def test_run_agents_drops_abstentions():
    specs = [
        RSI_SPEC,
        AgentSpec(agent_id="adx", team=AgentTeam.TECHNICAL,
                  persona="ADX.", indicators=("ADX_14",)),
    ]
    agents = build_team(specs, FakeLLM())
    evidence = run_agents(agents, make_snapshot())
    assert [e.agent_id for e in evidence] == ["rsi"]


def test_render_context_empty_for_unselectable_spec():
    spec = AgentSpec(agent_id="vwap", team=AgentTeam.TECHNICAL,
                     persona="VWAP.", indicators=("VWAP",))
    ctx = render_context(make_snapshot(), spec)
    assert ctx.empty
    assert ctx.missing == ["indicator:VWAP"]
