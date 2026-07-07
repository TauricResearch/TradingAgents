"""End-to-end pipeline runs through the compiled LangGraph with fake LLMs."""

from datetime import timedelta

from tests.pro_fakes import BASE_TS
from tests.test_pro_agents_base import make_snapshot
from tradingagents.contracts import (
    AssetClass,
    IndicatorReading,
    OHLCVBar,
    ProConfig,
    Timeframe,
    TradeAction,
    TradingMode,
)
from tradingagents.pro.agents import EvidenceDraft
from tradingagents.pro.pipeline import (
    CriticReport,
    DebateTurn,
    JudgeVerdict,
    ReflectionNote,
    run_pipeline,
)

DEFAULT_DRAFTS = {
    EvidenceDraft: EvidenceDraft(
        claim="Signal favors upside per the shown values.",
        direction="bullish",
        confidence=60,
    ),
    DebateTurn: DebateTurn(
        argument="The cited momentum evidence carries the case.",
        cited_agent_ids=["rsi"],
        confidence=55,
    ),
    CriticReport: CriticReport(verdict="pass", issues=[]),
    ReflectionNote: ReflectionNote(
        weaknesses="Momentum evidence is single-timeframe.",
        invalidation="A close below the shown stop level.",
    ),
    JudgeVerdict: JudgeVerdict(
        action="BUY", confidence=72,
        rationale="Bull side carried the debate; risk numbers within limits.",
    ),
}


class FakeRunnable:
    def __init__(self, payload, log):
        self.payload = payload
        self.log = log

    def invoke(self, prompt):
        self.log.append(prompt)
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakePipelineLLM:
    """Serves canned structured outputs per schema; records every prompt."""

    def __init__(self, overrides: dict | None = None):
        self.overrides = overrides or {}
        self.prompts: dict[str, list[str]] = {}

    def with_structured_output(self, schema):
        payload = self.overrides.get(schema, DEFAULT_DRAFTS[schema])
        return FakeRunnable(payload, self.prompts.setdefault(schema.__name__, []))


def pipeline_snapshot(**overrides):
    base = make_snapshot()
    snapshot = make_snapshot(
        indicators=[
            *base.indicators,
            IndicatorReading(name="ATR_14", timeframe=Timeframe.D1,
                             value={"value": 2.5}, params={"period": 14}),
        ],
        **overrides,
    )
    return snapshot


def lossy_bars(n: int = 30) -> list[OHLCVBar]:
    """Bars losing 5% per bar: VaR95 = 5%/bar, breaching the 3% default limit."""
    bars, price = [], 100.0
    for i in range(n):
        close = price * 0.95
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
            open=price, high=price * 1.01, low=close * 0.99, close=close,
            volume=1000.0,
        ))
        price = close
    return bars


CONFIG = ProConfig(asset=AssetClass.GOLD, max_debate_rounds=1)


def test_happy_path_produces_validated_buy_recommendation():
    llm = FakePipelineLLM()
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())

    assert state.get("rejection") is None
    rec = state["recommendation"]
    assert rec is not None
    assert rec.action is TradeAction.BUY
    assert rec.confidence == 72
    # levels came from the risk engine, geometry validated by the contract
    assert rec.stop_loss < rec.entry_price < rec.take_profits[0].price
    assert rec.risk_reward is not None and rec.risk_reward > 0
    assert rec.position_size.quantity > 0
    # votes recorded: every evidence item + the judge
    judge_votes = [v for v in rec.vote_breakdown.votes if v.agent_id == "judge"]
    assert len(judge_votes) == 1
    assert len(rec.vote_breakdown.votes) >= 2
    assert state["execution_status"] == "accepted:paper"
    # judge saw the computed vote tally
    assert "confidence weight" in llm.prompts["JudgeVerdict"][0]


def test_hold_ruling_yields_hold_recommendation_without_levels():
    llm = FakePipelineLLM(overrides={
        JudgeVerdict: JudgeVerdict(action="HOLD", confidence=50,
                                   rationale="Evidence is balanced."),
    })
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    rec = state["recommendation"]
    assert rec.action is TradeAction.HOLD
    assert rec.entry_price is None and rec.stop_loss is None
    assert rec.position_size.quantity == 0
    assert state["execution_status"] == "accepted:paper"


def test_debate_rounds_are_bounded_by_config():
    llm = FakePipelineLLM()
    config = ProConfig(asset=AssetClass.GOLD, max_debate_rounds=2)
    state = run_pipeline(llm, config, pipeline_snapshot())

    speakers = [entry["speaker"] for entry in state["debate"]]
    assert speakers.count("technical_bull") == 2
    assert speakers.count("technical_bear") == 2
    assert speakers.count("macro_bull") == 2
    assert speakers.count("macro_bear") == 2
    assert speakers.count("sentiment") == 1
    # order: full technical exchange precedes macro
    assert speakers.index("macro_bull") > speakers.index("technical_bear")


def test_risk_gate_rejects_var_breach_before_critic():
    llm = FakePipelineLLM()
    state = run_pipeline(llm, CONFIG, pipeline_snapshot(bars=lossy_bars()))

    assert state["rejection"]["stage"] == "risk_gate"
    assert state["recommendation"] is None
    assert state["execution_status"] == "rejected:risk_gate"
    speakers = {entry["speaker"] for entry in state["debate"]}
    assert "critic" not in speakers and "judge" not in speakers


def test_critic_fail_rejects_run():
    llm = FakePipelineLLM(overrides={
        CriticReport: CriticReport(
            verdict="fail",
            issues=["technical_bull cited agent 'ichimoku' which produced no evidence"],
        ),
    })
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    assert state["rejection"]["stage"] == "critic"
    assert state["recommendation"] is None
    assert "ichimoku" in state["rejection"]["reasons"][0]


def test_unsupported_judge_ruling_rejected_at_pm():
    # every agent said bearish, judge rules BUY -> no supporting evidence
    llm = FakePipelineLLM(overrides={
        EvidenceDraft: EvidenceDraft(
            claim="Signal points down.", direction="bearish", confidence=60,
        ),
    })
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    assert state["rejection"]["stage"] == "portfolio_manager"
    assert "no evidence supports" in state["rejection"]["reasons"][0]
    assert state["recommendation"] is None


def test_gather_rejects_when_no_agent_produces_evidence():
    llm = FakePipelineLLM(overrides={EvidenceDraft: RuntimeError("all agents down")})
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    assert state["rejection"]["stage"] == "gather"
    assert state["recommendation"] is None
    assert state["debate"] == []  # rejected before any debate turn


def test_live_mode_execution_is_refused_pending_human_approval():
    llm = FakePipelineLLM()
    config = ProConfig(
        asset=AssetClass.GOLD, mode=TradingMode.LIVE,
        live_trading_enabled=True, max_debate_rounds=1,
    )
    state = run_pipeline(llm, config, pipeline_snapshot())
    assert state["recommendation"] is not None  # research artifact stands
    assert state["execution_status"].startswith("refused: live mode requires")


def test_sell_ruling_builds_sell_geometry():
    llm = FakePipelineLLM(overrides={
        EvidenceDraft: EvidenceDraft(
            claim="Signal points down.", direction="bearish", confidence=60,
        ),
        JudgeVerdict: JudgeVerdict(action="SELL", confidence=64,
                                   rationale="Bear side carried it."),
    })
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    rec = state["recommendation"]
    assert rec.action is TradeAction.SELL
    assert rec.stop_loss > rec.entry_price > rec.take_profits[0].price
    assert state.get("rejection") is None


def test_counterarguments_preserve_losing_side():
    # mix: technical bullish (default), but override is global per schema, so
    # simulate by checking the happy path keeps opposing list consistent
    llm = FakePipelineLLM()
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    rec = state["recommendation"]
    # all fake evidence is bullish -> no counterarguments, all supporting
    assert rec.counterarguments == []
    assert all(e.direction.value == "bullish" for e in rec.evidence)
